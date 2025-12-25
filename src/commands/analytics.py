"""Analytics and reporting commands for ServerPulse."""

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

import discord
from discord import app_commands
from discord.ext import commands

from src.utils.helpers import (
    get_period_display_name, get_period_hours, format_number, 
    get_emoji_for_rank, format_time_duration, create_progress_bar
)
from src.utils.logger import LoggerMixin


class AnalyticsCommands(commands.Cog, LoggerMixin):
    """Analytics and reporting commands."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db_manager
        self.redis = bot.redis_manager
        self.analytics = bot.analytics_manager
    
    @app_commands.command(name="topmessagers", description="Show most active users in the server")
    @app_commands.describe(
        period="Time period for the leaderboard",
        limit="Number of users to show (max 25)"
    )
    @app_commands.choices(period=[
        app_commands.Choice(name="Last Hour", value="1h"),
        app_commands.Choice(name="Last 6 Hours", value="6h"),
        app_commands.Choice(name="Last 12 Hours", value="12h"),
        app_commands.Choice(name="Last 24 Hours", value="24h"),
        app_commands.Choice(name="Last 7 Days", value="7d"),
        app_commands.Choice(name="Last 30 Days", value="30d"),
        app_commands.Choice(name="All Time", value="all")
    ])
    async def topmessagers(self, interaction: discord.Interaction, 
                          period: str = "24h", limit: int = 10) -> None:
        """Show server leaderboard for most active users."""
        if limit > 25:
            limit = 25
        elif limit < 1:
            limit = 10
        
        await interaction.response.defer()
        
        # Check if server is set up
        guild_settings = await self.db.get_guild_settings(interaction.guild.id)
        if not guild_settings or not guild_settings.get('setup_completed', False):
            embed = discord.Embed(
                title="⚙️ Setup Required",
                description="ServerPulse needs to be configured first. Use `/setup` to get started!",
                color=discord.Color.orange()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # Get leaderboard data
        try:
            leaderboard = await self.analytics.get_leaderboard(
                interaction.guild.id, period, limit=limit
            )
        except Exception as e:
            self.logger.error(f"Error getting leaderboard: {e}")
            await interaction.followup.send(
                "❌ An error occurred while fetching the leaderboard. Please try again.",
                ephemeral=True
            )
            return
        
        if not leaderboard:
            embed = discord.Embed(
                title="📊 No Activity Data",
                description=f"No message activity found for {get_period_display_name(period).lower()}.",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="Possible Reasons:",
                value=(
                    "• No tracked channels have activity\n"
                    "• Time period too short\n"
                    "• Bot recently added to server"
                ),
                inline=False
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Create leaderboard embed
        embed = discord.Embed(
            title=f"🏆 Top Messagers - {get_period_display_name(period)}",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        
        # Build leaderboard text
        leaderboard_text = ""
        total_messages = sum(user['message_count'] for user in leaderboard)
        
        for i, user_data in enumerate(leaderboard, 1):
            user = interaction.guild.get_member(user_data['user_id'])
            user_mention = user.mention if user else f"<@{user_data['user_id']}>"
            
            message_count = user_data['message_count']
            avg_length = user_data.get('avg_length', 0)
            
            # Calculate percentage of total
            percentage = (message_count / total_messages * 100) if total_messages > 0 else 0
            
            rank_emoji = get_emoji_for_rank(i)
            leaderboard_text += (
                f"{rank_emoji} {user_mention}\n"
                f"   💬 {format_number(message_count)} messages ({percentage:.1f}%) "
                f"| 📝 Avg: {avg_length:.0f} chars\n\n"
            )
        
        embed.description = leaderboard_text
        
        # Add summary footer
        embed.add_field(
            name="📊 Summary",
            value=(
                f"💬 **Total Messages:** {format_number(total_messages)}\n"
                f"👥 **Active Users:** {len(leaderboard)}\n"
                f"🕰️ **Period:** {get_period_display_name(period)}"
            ),
            inline=False
        )
        
        embed.set_footer(
            text=f"Requested by {interaction.user.display_name}",
            icon_url=interaction.user.display_avatar.url
        )
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="leaderboard", description="Show leaderboard for a specific channel")
    @app_commands.describe(
        channel="Channel to analyze",
        period="Time period for the analysis",
        limit="Number of users to show (max 25)"
    )
    @app_commands.choices(period=[
        app_commands.Choice(name="Last Hour", value="1h"),
        app_commands.Choice(name="Last 6 Hours", value="6h"),
        app_commands.Choice(name="Last 12 Hours", value="12h"),
        app_commands.Choice(name="Last 24 Hours", value="24h"),
        app_commands.Choice(name="Last 7 Days", value="7d"),
        app_commands.Choice(name="Last 30 Days", value="30d"),
        app_commands.Choice(name="All Time", value="all")
    ])
    async def leaderboard(self, interaction: discord.Interaction,
                         channel: discord.TextChannel, period: str = "24h", 
                         limit: int = 10) -> None:
        """Show leaderboard for specific channel."""
        if limit > 25:
            limit = 25
        elif limit < 1:
            limit = 10
        
        await interaction.response.defer()
        
        # Check if channel is tracked
        guild_settings = await self.db.get_guild_settings(interaction.guild.id)
        if not guild_settings or not guild_settings.get('setup_completed', False):
            embed = discord.Embed(
                title="⚙️ Setup Required",
                description="ServerPulse needs to be configured first. Use `/setup` to get started!",
                color=discord.Color.orange()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        tracked_channels = guild_settings.get('tracked_channels', [])
        if channel.id not in tracked_channels:
            embed = discord.Embed(
                title="🚫 Channel Not Tracked",
                description=f"{channel.mention} is not currently being tracked.",
                color=discord.Color.red()
            )
            embed.add_field(
                name="To track this channel:",
                value=f"Use `/add-collect-channel {channel.mention}` (requires admin permissions)",
                inline=False
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # Get channel-specific leaderboard
        try:
            leaderboard = await self.analytics.get_leaderboard(
                interaction.guild.id, period, channel.id, limit
            )
            stats = await self.analytics.get_server_stats(
                interaction.guild.id, period, channel.id
            )
        except Exception as e:
            self.logger.error(f"Error getting channel leaderboard: {e}")
            await interaction.followup.send(
                "❌ An error occurred while fetching channel analytics. Please try again.",
                ephemeral=True
            )
            return
        
        if not leaderboard:
            embed = discord.Embed(
                title=f"📊 No Activity in {channel.name}",
                description=f"No messages found in {channel.mention} for {get_period_display_name(period).lower()}.",
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Create channel leaderboard embed
        embed = discord.Embed(
            title=f"📊 {channel.name} - {get_period_display_name(period)}",
            color=discord.Color.blurple(),
            timestamp=datetime.utcnow()
        )
        
        # Channel stats summary
        message_stats = stats.get('message_stats', {})
        total_messages = message_stats.get('total_messages', 0)
        unique_users = message_stats.get('unique_users', 0)
        avg_length = message_stats.get('avg_message_length', 0)
        
        embed.add_field(
            name=f"📊 Channel Stats",
            value=(
                f"💬 **Messages:** {format_number(total_messages)}\n"
                f"👥 **Active Users:** {format_number(unique_users)}\n"
                f"📝 **Avg Length:** {avg_length:.0f} characters"
            ),
            inline=True
        )
        
        # Activity score and comparison
        activity_score = stats.get('activity_score', 0)
        anomaly = stats.get('anomaly')
        
        status_text = "🟢 Normal"
        if anomaly:
            if 'spike' in anomaly:
                status_text = f"📈 +{anomaly.split('_')[1]}% vs usual"
            elif 'drop' in anomaly:
                status_text = f"📉 -{anomaly.split('_')[1]}% vs usual"
        
        embed.add_field(
            name="🎯 Activity Status",
            value=(
                f"🏆 **Score:** {activity_score}\n"
                f"🔍 **Status:** {status_text}"
            ),
            inline=True
        )
        
        # Top users in channel
        leaderboard_text = ""
        for i, user_data in enumerate(leaderboard, 1):
            user = interaction.guild.get_member(user_data['user_id'])
            user_mention = user.mention if user else f"<@{user_data['user_id']}>"
            
            message_count = user_data['message_count']
            percentage = (message_count / total_messages * 100) if total_messages > 0 else 0
            
            rank_emoji = get_emoji_for_rank(i)
            leaderboard_text += (
                f"{rank_emoji} {user_mention} - {format_number(message_count)} ({percentage:.1f}%)\n"
            )
        
        embed.add_field(
            name=f"🏆 Top {len(leaderboard)} Users",
            value=leaderboard_text,
            inline=False
        )
        
        embed.set_footer(
            text=f"Requested by {interaction.user.display_name}",
            icon_url=interaction.user.display_avatar.url
        )
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="serverstats", description="Show comprehensive server statistics")
    @app_commands.describe(period="Time period for the statistics")
    @app_commands.choices(period=[
        app_commands.Choice(name="Last Hour", value="1h"),
        app_commands.Choice(name="Last 6 Hours", value="6h"),
        app_commands.Choice(name="Last 12 Hours", value="12h"),
        app_commands.Choice(name="Last 24 Hours", value="24h"),
        app_commands.Choice(name="Last 7 Days", value="7d"),
        app_commands.Choice(name="Last 30 Days", value="30d")
    ])
    async def serverstats(self, interaction: discord.Interaction, period: str = "24h") -> None:
        """Show comprehensive server statistics."""
        await interaction.response.defer()
        
        guild_settings = await self.db.get_guild_settings(interaction.guild.id)
        if not guild_settings or not guild_settings.get('setup_completed', False):
            embed = discord.Embed(
                title="⚙️ Setup Required",
                description="ServerPulse needs to be configured first. Use `/setup` to get started!",
                color=discord.Color.orange()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        try:
            # Get comprehensive stats
            stats = await self.analytics.get_server_stats(interaction.guild.id, period)
            member_activity = await self.db.get_member_activity(
                interaction.guild.id, get_period_hours(period)
            )
            channel_comparison = await self.analytics.get_channel_comparison(
                interaction.guild.id, period
            )
        except Exception as e:
            self.logger.error(f"Error getting server stats: {e}")
            await interaction.followup.send(
                "❌ An error occurred while fetching server statistics. Please try again.",
                ephemeral=True
            )
            return
        
        # Main stats embed
        embed = discord.Embed(
            title=f"📊 Server Statistics - {get_period_display_name(period)}",
            description=f"Comprehensive analytics for **{interaction.guild.name}**",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        # Message statistics
        message_stats = stats.get('message_stats', {})
        total_messages = message_stats.get('total_messages', 0)
        unique_users = message_stats.get('unique_users', 0)
        avg_length = message_stats.get('avg_message_length', 0)
        attachments = message_stats.get('attachments', 0)
        
        embed.add_field(
            name="💬 Message Activity",
            value=(
                f"📝 **Total:** {format_number(total_messages)}\n"
                f"👥 **Active Users:** {format_number(unique_users)}\n"
                f"📎 **Attachments:** {format_number(attachments)}\n"
                f"📏 **Avg Length:** {avg_length:.0f} chars"
            ),
            inline=True
        )
        
        # Visual separator
        embed.add_field(name="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", value="\u200b", inline=False)

        # Member activity
        joins = member_activity.get('joins', 0)
        leaves = member_activity.get('leaves', 0)
        net_growth = joins - leaves
        
        growth_emoji = "📈" if net_growth > 0 else "📉" if net_growth < 0 else "➡️"
        
        embed.add_field(
            name="👥 Member Activity",
            value=(
                f"👋 **Joins:** {format_number(joins)}\n"
                f"🚪 **Leaves:** {format_number(leaves)}\n"
                f"{growth_emoji} **Net:** {net_growth:+d}\n"
                f"📊 **Total Members:** {format_number(interaction.guild.member_count)}"
            ),
            inline=True
        )
        
        # Visual separator
        embed.add_field(name="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", value="\u200b", inline=False)


        # Activity analysis
        activity_score = stats.get('activity_score', 0)
        anomaly = stats.get('anomaly')
        historical_avg = stats.get('historical_avg', 0)
        
        status_text = "🟢 Normal activity"
        if anomaly:
            if 'spike' in anomaly:
                status_text = f"📈 Activity spike (+{anomaly.split('_')[1]}%)"
            elif 'drop' in anomaly:
                status_text = f"📉 Activity drop (-{anomaly.split('_')[1]}%)"
        
        embed.add_field(
            name="🔍 Activity Analysis",
            value=(
                f"🏆 **Activity Score:** {activity_score}\n"
                f"📊 **Historical Avg:** {historical_avg:.1f}/period\n"
                f"🔍 **Status:** {status_text}"
            ),
            inline=False
        )
        
        # Visual separator
        embed.add_field(name="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", value="\u200b", inline=False)


        # Top channels by activity
        if channel_comparison:
            top_channels = channel_comparison[:5]  # Top 5
            channel_text = ""
            
            for i, channel_data in enumerate(top_channels, 1):
                channel = interaction.guild.get_channel(channel_data['channel_id'])
                if channel:
                    channel_stats = channel_data['stats']
                    messages = channel_stats.get('total_messages', 0)
                    users = channel_stats.get('unique_users', 0)
                    
                    channel_text += f"{i}. {channel.mention} - {format_number(messages)} msgs, {users} users\n"
            
            if channel_text:
                embed.add_field(
                    name="📊 Top Active Channels",
                    value=channel_text,
                    inline=False
                )
        
        # Server info footer
        tracked_channels = len(guild_settings.get('tracked_channels', []))
        embed.set_footer(
            text=f"{tracked_channels} tracked channels • Requested by {interaction.user.display_name}",
            icon_url=interaction.user.display_avatar.url
        )
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="user-stats", description="Show detailed statistics for a specific user")
    @app_commands.describe(
        user="User to analyze",
        period="Time period for the analysis"
    )
    @app_commands.choices(period=[
        app_commands.Choice(name="Last 24 Hours", value="24h"),
        app_commands.Choice(name="Last 7 Days", value="7d"),
        app_commands.Choice(name="Last 30 Days", value="30d"),
        app_commands.Choice(name="All Time", value="all")
    ])
    async def user_stats(self, interaction: discord.Interaction, 
                        user: discord.Member, period: str = "7d") -> None:
        """Show detailed user engagement statistics."""
        await interaction.response.defer()
        
        guild_settings = await self.db.get_guild_settings(interaction.guild.id)
        if not guild_settings or not guild_settings.get('setup_completed', False):
            embed = discord.Embed(
                title="⚙️ Setup Required",
                description="ServerPulse needs to be configured first. Use `/setup` to get started!",
                color=discord.Color.orange()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        try:
            user_stats = await self.analytics.get_user_engagement_stats(
                interaction.guild.id, user.id, period
            )
        except Exception as e:
            self.logger.error(f"Error getting user stats: {e}")
            await interaction.followup.send(
                "❌ An error occurred while fetching user statistics. Please try again.",
                ephemeral=True
            )
            return
        
        if user_stats['total_messages'] == 0:
            embed = discord.Embed(
                title="📊 No Activity Found",
                description=f"{user.mention} has no recorded activity for {get_period_display_name(period).lower()}.",
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed)
            return
        
        # User stats embed
        embed = discord.Embed(
            title=f"👤 User Statistics - {user.display_name}",
            description=f"Activity analysis for {get_period_display_name(period).lower()}",
            color=user.color if user.color != discord.Color.default() else discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        
        embed.set_thumbnail(url=user.display_avatar.url)
        
        # Basic stats
        embed.add_field(
            name="💬 Message Activity",
            value=(
                f"📝 **Messages:** {format_number(user_stats['total_messages'])}\n"
                f"📏 **Avg Length:** {user_stats['avg_message_length']:.0f} chars\n"
                f"📊 **Channels Used:** {user_stats['channels_count']}"
            ),
            inline=True
        )
        
        # Calculate user rank in server
        server_leaderboard = await self.analytics.get_leaderboard(
            interaction.guild.id, period, limit=100
        )
        
        user_rank = None
        for i, user_data in enumerate(server_leaderboard, 1):
            if user_data['user_id'] == user.id:
                user_rank = i
                break
        
        embed.add_field(
            name="🏆 Server Ranking",
            value=(
                f"🏅 **Rank:** #{user_rank or 'Not ranked'}\n"
                f"📊 **Out of:** {len(server_leaderboard)} active users"
            ),
            inline=True
        )
        
        # Most active channels
        channels_used = user_stats.get('channels_used', [])
        if channels_used:
            channel_mentions = []
            for channel_id in channels_used[:5]:  # Top 5 channels
                channel = interaction.guild.get_channel(channel_id)
                if channel:
                    channel_mentions.append(channel.mention)
            
            embed.add_field(
                name="📊 Most Active Channels",
                value="\n".join(channel_mentions) if channel_mentions else "None",
                inline=False
            )
        
        embed.set_footer(
            text=f"Requested by {interaction.user.display_name}",
            icon_url=interaction.user.display_avatar.url
        )
        
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AnalyticsCommands(bot))
