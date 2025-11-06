"""Analytics and statistics commands for ServerPulse."""

import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, Literal
from datetime import datetime, timedelta

from src.utils.logger import LoggerMixin
from src.utils.helpers import (
    format_number, get_period_display_name, get_emoji_for_rank,
    get_activity_emoji, create_progress_bar, format_time_duration
)


class AnalyticsCommands(commands.Cog, LoggerMixin):
    """Analytics and statistics commands."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db_manager
        self.redis = bot.redis_manager
        self.analytics = bot.analytics_manager
    
    @app_commands.command(name="topmessagers", description="Show most active users in the server")
    @app_commands.describe(
        period="Time period for statistics",
        channel="Specific channel to analyze (optional)"
    )
    async def top_messagers(self, interaction: discord.Interaction, 
                           period: Literal['1h', '6h', '12h', '24h', '7d', '30d', 'all'] = '24h',
                           channel: Optional[discord.TextChannel] = None):
        """Show server activity leaderboard."""
        await interaction.response.defer()
        
        # Check if server is set up
        guild_settings = await self.db.get_guild_settings(interaction.guild.id)
        if not guild_settings or not guild_settings.get('setup_completed', False):
            await interaction.followup.send(
                "❌ Please run `/setup` first to configure ServerPulse!",
                ephemeral=True
            )
            return
        
        # Get leaderboard data
        leaderboard = await self.analytics.get_leaderboard(
            interaction.guild.id, period, channel.id if channel else None, 15
        )
        
        if not leaderboard:
            await interaction.followup.send(
                f"📊 No activity data found for {get_period_display_name(period).lower()}."
                f"{f' in {channel.mention}' if channel else ''}"
            )
            return
        
        # Create embed
        embed = discord.Embed(
            title=f"🏆 Top Messagers - {get_period_display_name(period)}",
            description=f"Most active users{f' in {channel.mention}' if channel else ''}",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        
        # Add leaderboard entries
        leaderboard_text = ""
        for i, user_data in enumerate(leaderboard[:10], 1):
            user_id = user_data['user_id']
            message_count = user_data['message_count']
            avg_length = user_data.get('avg_length', 0)
            
            # Try to get member object
            member = interaction.guild.get_member(user_id)
            display_name = member.display_name if member else f"Unknown User"
            
            # Format entry
            rank_emoji = get_emoji_for_rank(i)
            leaderboard_text += f"{rank_emoji} **{display_name}** - {format_number(message_count)} messages"
            
            if avg_length > 0:
                leaderboard_text += f" (avg: {avg_length:.0f} chars)"
            
            leaderboard_text += "\n"
        
        embed.add_field(
            name="📈 Leaderboard",
            value=leaderboard_text,
            inline=False
        )
        
        # Add summary stats
        total_messages = sum(user['message_count'] for user in leaderboard)
        unique_users = len(leaderboard)
        
        embed.add_field(
            name="📊 Summary",
            value=f"**Total Messages:** {format_number(total_messages)}\n"
                  f"**Active Users:** {format_number(unique_users)}\n"
                  f"**Average per User:** {format_number(total_messages // max(unique_users, 1))}",
            inline=True
        )
        
        # Add period info
        embed.set_footer(
            text=f"Period: {get_period_display_name(period)} | Data updates in real-time"
        )
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="leaderboard", description="Detailed leaderboard for a specific channel")
    @app_commands.describe(
        channel="Channel to analyze",
        period="Time period for statistics"
    )
    async def channel_leaderboard(self, interaction: discord.Interaction,
                                 channel: discord.TextChannel,
                                 period: Literal['1h', '6h', '12h', '24h', '7d', '30d', 'all'] = '24h'):
        """Show detailed leaderboard for specific channel."""
        await interaction.response.defer()
        
        # Check if server is set up
        guild_settings = await self.db.get_guild_settings(interaction.guild.id)
        if not guild_settings or not guild_settings.get('setup_completed', False):
            await interaction.followup.send(
                "❌ Please run `/setup` first to configure ServerPulse!",
                ephemeral=True
            )
            return
        
        # Check if channel is tracked
        tracked_channels = guild_settings.get('tracked_channels', [])
        if channel.id not in tracked_channels:
            await interaction.followup.send(
                f"❌ {channel.mention} is not being tracked! Use `/add-collect-channel` to start tracking.",
                ephemeral=True
            )
            return
        
        # Get stats and leaderboard
        stats = await self.analytics.get_server_stats(
            interaction.guild.id, period, channel.id
        )
        
        leaderboard = await self.analytics.get_leaderboard(
            interaction.guild.id, period, channel.id, 10
        )
        
        if not stats['message_stats']['total_messages']:
            await interaction.followup.send(
                f"📊 No activity data found for {channel.mention} in the {get_period_display_name(period).lower()}."
            )
            return
        
        # Create embed
        embed = discord.Embed(
            title=f"📊 {channel.name} Analytics",
            description=f"Detailed statistics for {get_period_display_name(period).lower()}",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        # Channel stats
        msg_stats = stats['message_stats']
        embed.add_field(
            name="📈 Channel Activity",
            value=f"**Messages:** {format_number(msg_stats['total_messages'])}\n"
                  f"**Unique Users:** {format_number(msg_stats['unique_users'])}\n"
                  f"**Avg Message Length:** {msg_stats.get('avg_message_length', 0):.1f} chars\n"
                  f"**Activity Score:** {stats['activity_score']}",
            inline=True
        )
        
        # Anomaly detection
        if stats['anomaly']:
            anomaly_type, percentage = stats['anomaly'].split('_')
            anomaly_emoji = "📈" if anomaly_type == "spike" else "📉"
            embed.add_field(
                name=f"{anomaly_emoji} Activity {anomaly_type.title()}",
                value=f"{percentage}% {'increase' if anomaly_type == 'spike' else 'decrease'} vs normal",
                inline=True
            )
        
        # Top users in channel
        if leaderboard:
            top_users_text = ""
            for i, user_data in enumerate(leaderboard[:5], 1):
                member = interaction.guild.get_member(user_data['user_id'])
                display_name = member.display_name if member else "Unknown User"
                
                top_users_text += f"{get_emoji_for_rank(i)} {display_name} - {format_number(user_data['message_count'])}\n"
            
            embed.add_field(
                name="🏆 Top Contributors",
                value=top_users_text,
                inline=False
            )
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="serverstats", description="Complete server analytics overview")
    @app_commands.describe(period="Time period for statistics")
    async def server_stats(self, interaction: discord.Interaction,
                          period: Literal['1h', '6h', '12h', '24h', '7d', '30d', 'all'] = '24h'):
        """Show comprehensive server statistics."""
        await interaction.response.defer()
        
        # Check if server is set up
        guild_settings = await self.db.get_guild_settings(interaction.guild.id)
        if not guild_settings or not guild_settings.get('setup_completed', False):
            await interaction.followup.send(
                "❌ Please run `/setup` first to configure ServerPulse!",
                ephemeral=True
            )
            return
        
        # Get overall server stats
        stats = await self.analytics.get_server_stats(interaction.guild.id, period)
        
        # Get member activity
        member_activity = await self.db.get_member_activity(
            interaction.guild.id, 
            __import__('src.utils.helpers', fromlist=['get_period_hours']).get_period_hours(period)
        )
        
        # Get channel comparison
        channel_comparison = await self.analytics.get_channel_comparison(interaction.guild.id, period)
        
        # Create main embed
        embed = discord.Embed(
            title=f"📊 Server Analytics - {interaction.guild.name}",
            description=f"Complete overview for {get_period_display_name(period).lower()}",
            color=discord.Color.purple(),
            timestamp=datetime.utcnow()
        )
        
        # Message statistics
        msg_stats = stats['message_stats']
        embed.add_field(
            name="💬 Message Activity",
            value=f"**Total:** {format_number(msg_stats['total_messages'])}\n"
                  f"**Active Users:** {format_number(msg_stats['unique_users'])}\n"
                  f"**Avg Length:** {msg_stats.get('avg_message_length', 0):.1f} chars\n"
                  f"**Attachments:** {format_number(msg_stats.get('attachments', 0))}",
            inline=True
        )
        
        # Member activity
        embed.add_field(
            name="👥 Member Activity",
            value=f"**Joins:** {get_activity_emoji('join')} {format_number(member_activity['joins'])}\n"
                  f"**Leaves:** {get_activity_emoji('leave')} {format_number(member_activity['leaves'])}\n"
                  f"**Net Growth:** {format_number(member_activity['joins'] - member_activity['leaves'])}\n"
                  f"**Current Members:** {format_number(interaction.guild.member_count)}",
            inline=True
        )
        
        # Activity score and trends
        embed.add_field(
            name="📈 Activity Analysis",
            value=f"**Activity Score:** {stats['activity_score']}\n"
                  f"**Engagement:** {self._get_engagement_level(stats['activity_score'])}\n"
                  f"**Historical Avg:** {stats['historical_avg']:.1f} msg/period\n"
                  f"**Trend:** {self._get_trend_indicator(stats.get('anomaly'))}",
            inline=True
        )
        
        # Channel breakdown (top 5)
        if channel_comparison:
            channel_text = ""
            for i, channel_data in enumerate(channel_comparison[:5], 1):
                channel_id = channel_data['channel_id']
                channel = interaction.guild.get_channel(channel_id)
                channel_name = channel.name if channel else "Unknown"
                
                messages = channel_data['stats']['total_messages']
                score = channel_data['activity_score']
                
                channel_text += f"{i}. **#{channel_name}** - {format_number(messages)} msg (score: {score})\n"
            
            embed.add_field(
                name="🏆 Most Active Channels",
                value=channel_text,
                inline=False
            )
        
        # Footer with tracking info
        tracked_channels = len(guild_settings.get('tracked_channels', []))
        embed.set_footer(
            text=f"Tracking {tracked_channels} channels | Data updates in real-time"
        )
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="userstats", description="Get detailed statistics for a specific user")
    @app_commands.describe(
        user="User to analyze",
        period="Time period for statistics"
    )
    async def user_stats(self, interaction: discord.Interaction,
                        user: discord.Member,
                        period: Literal['24h', '7d', '30d', 'all'] = '24h'):
        """Show detailed user engagement statistics."""
        await interaction.response.defer()
        
        # Check if server is set up
        guild_settings = await self.db.get_guild_settings(interaction.guild.id)
        if not guild_settings or not guild_settings.get('setup_completed', False):
            await interaction.followup.send(
                "❌ Please run `/setup` first to configure ServerPulse!",
                ephemeral=True
            )
            return
        
        # Get user stats
        user_stats = await self.analytics.get_user_engagement_stats(
            interaction.guild.id, user.id, period
        )
        
        if not user_stats['total_messages']:
            await interaction.followup.send(
                f"📊 No activity data found for {user.display_name} in the {get_period_display_name(period).lower()}."
            )
            return
        
        # Create embed
        embed = discord.Embed(
            title=f"👤 User Analytics - {user.display_name}",
            description=f"Activity summary for {get_period_display_name(period).lower()}",
            color=user.color if user.color != discord.Color.default() else discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        
        embed.set_thumbnail(url=user.display_avatar.url)
        
        # Basic stats
        embed.add_field(
            name="💬 Message Activity",
            value=f"**Total Messages:** {format_number(user_stats['total_messages'])}\n"
                  f"**Avg Length:** {user_stats['avg_message_length']:.1f} chars\n"
                  f"**Channels Used:** {user_stats['channels_count']}\n"
                  f"**Rank:** {await self._get_user_rank(interaction.guild.id, user.id, period)}",
            inline=True
        )
        
        # Member info
        joined_days = (datetime.utcnow() - user.joined_at).days if user.joined_at else 0
        embed.add_field(
            name="👥 Member Info",
            value=f"**Joined:** {format_time_duration(joined_days * 24 * 3600)} ago\n"
                  f"**Roles:** {len(user.roles) - 1}\n"
                  f"**Top Role:** {user.top_role.mention}\n"
                  f"**Status:** {str(user.status).title()}",
            inline=True
        )
        
        # Activity distribution (if available)
        if 'hourly_distribution' in user_stats and user_stats['hourly_distribution']:
            # Calculate most active hours
            hour_counts = {}
            for entry in user_stats['hourly_distribution']:
                hour = entry['hour']
                hour_counts[hour] = hour_counts.get(hour, 0) + 1
            
            if hour_counts:
                most_active_hour = max(hour_counts.keys(), key=lambda h: hour_counts[h])
                embed.add_field(
                    name="⏰ Activity Pattern",
                    value=f"**Most Active Hour:** {most_active_hour:02d}:00\n"
                          f"**Messages at Peak:** {hour_counts[most_active_hour]}\n"
                          f"**Activity Spread:** {len(hour_counts)}/24 hours",
                    inline=True
                )
        
        await interaction.followup.send(embed=embed)
    
    def _get_engagement_level(self, activity_score: int) -> str:
        """Convert activity score to engagement level."""
        if activity_score >= 1000:
            return "🔥 Very High"
        elif activity_score >= 500:
            return "📈 High"
        elif activity_score >= 200:
            return "📊 Medium"
        elif activity_score >= 50:
            return "📉 Low"
        else:
            return "💤 Very Low"
    
    def _get_trend_indicator(self, anomaly: Optional[str]) -> str:
        """Get trend indicator from anomaly data."""
        if not anomaly:
            return "➡️ Stable"
        
        if anomaly.startswith("spike"):
            return "📈 Increasing"
        elif anomaly.startswith("drop"):
            return "📉 Decreasing"
        else:
            return "➡️ Stable"
    
    async def _get_user_rank(self, guild_id: int, user_id: int, period: str) -> str:
        """Get user's rank in server leaderboard."""
        leaderboard = await self.analytics.get_leaderboard(guild_id, period, limit=100)
        
        for i, user_data in enumerate(leaderboard, 1):
            if user_data['user_id'] == user_id:
                total_users = len(leaderboard)
                percentile = ((total_users - i) / total_users) * 100
                return f"#{i} (top {percentile:.0f}%)"
        
        return "Not ranked"


async def setup(bot):
    await bot.add_cog(AnalyticsCommands(bot))
