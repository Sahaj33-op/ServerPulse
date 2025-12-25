"""Voice analytics commands for ServerPulse."""

from datetime import datetime, timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.utils.helpers import format_time_duration, format_number, get_period_hours
from src.utils.logger import LoggerMixin


class VoiceAnalyticsCommands(commands.Cog, LoggerMixin):
    """Voice-specific analytics commands."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db_manager
        self.redis = bot.redis_manager
    
    @app_commands.command(name="voice-stats", description="View voice channel statistics")
    @app_commands.describe(
        period="Time period to analyze",
        channel="Specific voice channel (optional)"
    )
    @app_commands.choices(period=[
        app_commands.Choice(name="Last Hour", value="1h"),
        app_commands.Choice(name="Last 6 Hours", value="6h"),
        app_commands.Choice(name="Last 24 Hours", value="24h"),
        app_commands.Choice(name="Last 7 Days", value="7d"),
        app_commands.Choice(name="Last 30 Days", value="30d")
    ])
    async def voice_stats(self, interaction: discord.Interaction, 
                         period: str = "24h",
                         channel: Optional[discord.VoiceChannel] = None) -> None:
        """Show voice channel statistics."""
        await interaction.response.defer()
        
        period_hours = get_period_hours(period)
        channel_id = channel.id if channel else None
        
        # Get voice session stats
        stats = await self.db.get_voice_session_stats(
            interaction.guild.id,
            period_hours,
            channel_id
        )
        
        # Get channel popularity if not filtering by specific channel
        popular_channels = []
        if not channel_id:
            popular_channels = await self.db.get_voice_channel_popularity(
                interaction.guild.id,
                period_hours
            )
        
        # Create embed
        period_display = {
            "1h": "Last Hour",
            "6h": "Last 6 Hours",
            "24h": "Last 24 Hours",
            "7d": "Last 7 Days",
            "30d": "Last 30 Days"
        }.get(period, "Recent Period")
        
        if channel:
            title = f"🎙️ Voice Stats: {channel.name}"
        else:
            title = f"🎙️ Voice Statistics - {interaction.guild.name}"
        
        embed = discord.Embed(
            title=title,
            description=f"**Period:** {period_display}",
            color=discord.Color.purple(),
            timestamp=discord.utils.utcnow()
        )
        
        # Overview stats
        total_sessions = stats.get('total_sessions', 0)
        unique_users = stats.get('unique_users', 0)
        total_duration = stats.get('total_duration', 0)
        avg_duration = stats.get('avg_duration', 0)
        
        if total_sessions > 0:
            overview = (
                f"📊 **Sessions:** {format_number(total_sessions)}\n"
                f"👥 **Unique Users:** {format_number(unique_users)}\n"
                f"⏱️ **Total Time:** {format_time_duration(total_duration)}\n"
                f"⌛ **Avg Session:** {format_time_duration(avg_duration)}"
            )
            
            embed.add_field(
                name="📈 Overview",
                value=overview,
                inline=False
            )
            
            # Separator
            embed.add_field(name="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", value="\u200b", inline=False)
            
            # Additional metrics
            max_duration = stats.get('max_duration', 0)
            min_duration = stats.get('min_duration', 0)
            
            if max_duration > 0:
                metrics = (
                    f"🔝 **Longest Session:** {format_time_duration(max_duration)}\n"
                    f"🔻 **Shortest Session:** {format_time_duration(min_duration)}"
                )
                embed.add_field(
                    name="📊 Session Metrics",
                    value=metrics,
                    inline=False
                )
                
                # Separator
                embed.add_field(name="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", value="\u200b", inline=False)
            
            # Popular channels (if showing server-wide stats)
            if popular_channels:
                channel_lines = []
                for i, ch_data in enumerate(popular_channels[:5], 1):
                    ch = interaction.guild.get_channel(ch_data['channel_id'])
                    if ch:
                        emoji = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i-1]
                        channel_lines.append(
                            f"{emoji} **{ch.name}**\n"
                            f"   ⏱️ {format_time_duration(ch_data['total_time'])} • "
                            f"👥 {ch_data['unique_users']} users • "
                            f"📊 {ch_data['session_count']} sessions"
                        )
                
                if channel_lines:
                    embed.add_field(
                        name="🏆 Most Popular Channels",
                        value="\n\n".join(channel_lines),
                        inline=False
                    )
        else:
            embed.add_field(
                name="📊 No Activity",
                value=f"No voice activity detected during {period_display.lower()}.",
                inline=False
            )
            
            embed.add_field(
                name="💡 Tip",
                value="Voice stats are tracked when members join and leave voice channels.",
                inline=False
            )
        
        embed.set_footer(text=f"Requested by {interaction.user.display_name}")
        
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="voice-leaderboard", description="Show most active voice users")
    @app_commands.describe(
        period="Time period to analyze",
        channel="Specific voice channel (optional)",
        limit="Number of users to show (1-25)"
    )
    @app_commands.choices(period=[
        app_commands.Choice(name="Last Hour", value="1h"),
        app_commands.Choice(name="Last 6 Hours", value="6h"),
        app_commands.Choice(name="Last 24 Hours", value="24h"),
        app_commands.Choice(name="Last 7 Days", value="7d"),
        app_commands.Choice(name="Last 30 Days", value="30d")
    ])
    async def voice_leaderboard(self, interaction: discord.Interaction,
                               period: str = "24h",
                               channel: Optional[discord.VoiceChannel] = None,
                               limit: int = 10) -> None:
        """Show voice activity leaderboard."""
        await interaction.response.defer()
        
        # Validate limit
        limit = max(1, min(limit, 25))
        
        period_hours = get_period_hours(period)
        channel_id = channel.id if channel else None
        
        # Get top voice users
        top_users = await self.db.get_top_voice_users(
            interaction.guild.id,
            period_hours,
            limit,
            channel_id
        )
        
        # Create embed
        period_display = {
            "1h": "Last Hour",
            "6h": "Last 6 Hours",
            "24h": "Last 24 Hours",
            "7d": "Last 7 Days",
            "30d": "Last 30 Days"
        }.get(period, "Recent Period")
        
        if channel:
            title = f"🎙️ Voice Leaderboard: {channel.name}"
        else:
            title = f"🎙️ Voice Leaderboard - {interaction.guild.name}"
        
        embed = discord.Embed(
            title=title,
            description=f"**Period:** {period_display}",
            color=discord.Color.gold(),
            timestamp=discord.utils.utcnow()
        )
        
        if top_users:
            leaderboard_lines = []
            
            for i, user_data in enumerate(top_users, 1):
                user = interaction.guild.get_member(user_data['user_id'])
                if user:
                    # Medal emojis for top 3
                    if i == 1:
                        rank_emoji = "🥇"
                    elif i == 2:
                        rank_emoji = "🥈"
                    elif i == 3:
                        rank_emoji = "🥉"
                    else:
                        rank_emoji = f"**{i}.**"
                    
                    total_time = user_data['total_time']
                    session_count = user_data['session_count']
                    avg_session = user_data['avg_session_time']
                    
                    leaderboard_lines.append(
                        f"{rank_emoji} **{user.display_name}**\n"
                        f"   ⏱️ {format_time_duration(total_time)} total • "
                        f"📊 {session_count} sessions • "
                        f"⌛ {format_time_duration(avg_session)} avg"
                    )
            
            embed.add_field(
                name="🏆 Top Voice Users",
                value="\n\n".join(leaderboard_lines),
                inline=False
            )
            
            # Separator
            embed.add_field(name="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", value="\u200b", inline=False)
            
            # Summary stats
            total_time = sum(u['total_time'] for u in top_users)
            total_sessions = sum(u['session_count'] for u in top_users)
            
            embed.add_field(
                name="📊 Summary",
                value=(
                    f"⏱️ **Combined Time:** {format_time_duration(total_time)}\n"
                    f"📊 **Total Sessions:** {format_number(total_sessions)}\n"
                    f"👥 **Active Users:** {len(top_users)}"
                ),
                inline=False
            )
        else:
            embed.add_field(
                name="📊 No Activity",
                value=f"No voice activity detected during {period_display.lower()}.",
                inline=False
            )
        
        embed.set_footer(text=f"Requested by {interaction.user.display_name}")
        
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VoiceAnalyticsCommands(bot))
