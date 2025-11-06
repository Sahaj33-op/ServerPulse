"""Administrative commands for ServerPulse."""

import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, Literal, List
from datetime import datetime
import json
import csv
import io

from src.config import settings, AIProvider
from src.utils.logger import LoggerMixin
from src.utils.helpers import format_number, get_alert_emoji


class AdminCommands(commands.Cog, LoggerMixin):
    """Administrative and configuration commands."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db_manager
        self.redis = bot.redis_manager
        self.ai_manager = bot.ai_manager
    
    @app_commands.command(name="toggle-alert", description="Enable or disable specific alert types")
    @app_commands.describe(
        alert_type="Type of alert to toggle",
        enabled="Whether to enable or disable the alert"
    )
    @app_commands.default_permissions(administrator=True)
    async def toggle_alert(self, interaction: discord.Interaction,
                          alert_type: Literal['join_raid', 'activity_drop', 'mass_delete', 'voice_surge'],
                          enabled: bool):
        """Toggle alert types on/off."""
        await interaction.response.defer(ephemeral=True)
        
        guild_settings = await self.db.get_guild_settings(interaction.guild.id)
        if not guild_settings:
            await interaction.followup.send(
                "❌ Please run `/setup` first!",
                ephemeral=True
            )
            return
        
        # Update alert settings
        alerts_enabled = guild_settings.get('alerts_enabled', {})
        alerts_enabled[alert_type] = enabled
        
        await self.db.upsert_guild_settings(interaction.guild.id, {
            'alerts_enabled': alerts_enabled
        })
        
        # Format alert type for display
        alert_names = {
            'join_raid': 'Join Raid',
            'activity_drop': 'Activity Drop',
            'mass_delete': 'Mass Deletion',
            'voice_surge': 'Voice Surge'
        }
        
        status = "enabled" if enabled else "disabled"
        emoji = get_alert_emoji(alert_type)
        
        await interaction.followup.send(
            f"✅ {emoji} **{alert_names[alert_type]}** alerts {status}!",
            ephemeral=True
        )
    
    @app_commands.command(name="set-threshold", description="Set custom alert thresholds")
    @app_commands.describe(
        alert_type="Type of alert to configure",
        threshold="New threshold value"
    )
    @app_commands.default_permissions(administrator=True)
    async def set_threshold(self, interaction: discord.Interaction,
                           alert_type: Literal['join_raid', 'activity_drop', 'mass_delete', 'voice_surge'],
                           threshold: int):
        """Set custom alert thresholds."""
        await interaction.response.defer(ephemeral=True)
        
        # Validate threshold values
        if threshold < 1:
            await interaction.followup.send(
                "❌ Threshold must be at least 1!",
                ephemeral=True
            )
            return
        
        # Type-specific validation
        if alert_type == 'join_raid' and threshold > 100:
            await interaction.followup.send(
                "⚠️ Join raid threshold over 100 might be too high for most servers.",
                ephemeral=True
            )
        elif alert_type == 'activity_drop' and (threshold < 10 or threshold > 90):
            await interaction.followup.send(
                "⚠️ Activity drop threshold should be between 10-90%.",
                ephemeral=True
            )
        
        guild_settings = await self.db.get_guild_settings(interaction.guild.id)
        if not guild_settings:
            await interaction.followup.send(
                "❌ Please run `/setup` first!",
                ephemeral=True
            )
            return
        
        # Update threshold
        alert_thresholds = guild_settings.get('alert_thresholds', {})
        alert_thresholds[alert_type] = threshold
        
        await self.db.upsert_guild_settings(interaction.guild.id, {
            'alert_thresholds': alert_thresholds
        })
        
        # Format response
        threshold_descriptions = {
            'join_raid': f"{threshold} joins per minute",
            'activity_drop': f"{threshold}% decrease in activity",
            'mass_delete': f"{threshold} deletions in 30 seconds",
            'voice_surge': f"{threshold}x normal voice activity"
        }
        
        await interaction.followup.send(
            f"✅ {alert_type.replace('_', ' ').title()} threshold set to: **{threshold_descriptions[alert_type]}**",
            ephemeral=True
        )
    
    @app_commands.command(name="set-digest", description="Configure AI digest frequency")
    @app_commands.describe(frequency="How often to generate AI digest reports")
    @app_commands.default_permissions(administrator=True)
    async def set_digest(self, interaction: discord.Interaction,
                        frequency: Literal['daily', 'weekly', 'disabled']):
        """Configure AI digest report frequency."""
        await interaction.response.defer(ephemeral=True)
        
        await self.db.upsert_guild_settings(interaction.guild.id, {
            'digest_frequency': frequency
        })
        
        if frequency == 'disabled':
            await interaction.followup.send(
                "🤖 AI digest reports disabled.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"🤖 AI digest reports will be generated **{frequency}**.",
                ephemeral=True
            )
    
    @app_commands.command(name="pulse-now", description="Generate an instant AI-powered server report")
    @app_commands.describe(period="Time period to analyze")
    async def pulse_now(self, interaction: discord.Interaction,
                       period: Literal['24h', '7d', '30d'] = '24h'):
        """Generate instant AI report."""
        await interaction.response.defer()
        
        guild_settings = await self.db.get_guild_settings(interaction.guild.id)
        if not guild_settings or not guild_settings.get('setup_completed', False):
            await interaction.followup.send(
                "❌ Please run `/setup` first to configure ServerPulse!"
            )
            return
        
        try:
            # Generate AI report
            report = await self.ai_manager.generate_instant_report(
                interaction.guild.id, period, self.db
            )
            
            if report:
                embed = discord.Embed(
                    title=f"🧠 ServerPulse AI Report - {interaction.guild.name}",
                    description=report,
                    color=discord.Color.blue(),
                    timestamp=datetime.utcnow()
                )
                
                embed.set_footer(
                    text=f"Generated by AI | Period: {period} | Instant Report"
                )
                
                await interaction.followup.send(embed=embed)
                
                # Save report to database
                await self.db.save_ai_report(
                    interaction.guild.id,
                    'instant',
                    report,
                    {'period': period, 'requested_by': interaction.user.id}
                )
            else:
                await interaction.followup.send(
                    "❌ Could not generate AI report. Please check your AI configuration and try again."
                )
        
        except Exception as e:
            self.logger.error(f"Error generating instant report: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while generating the report. Please try again later."
            )
    
    @app_commands.command(name="export-report", description="Export analytics data as CSV or JSON")
    @app_commands.describe(
        format="Export format",
        period="Time period to export",
        data_type="Type of data to export"
    )
    @app_commands.default_permissions(administrator=True)
    async def export_report(self, interaction: discord.Interaction,
                           format: Literal['csv', 'json'],
                           period: Literal['24h', '7d', '30d', 'all'] = '7d',
                           data_type: Literal['messages', 'leaderboard', 'summary'] = 'summary'):
        """Export analytics data."""
        await interaction.response.defer(ephemeral=True)
        
        guild_settings = await self.db.get_guild_settings(interaction.guild.id)
        if not guild_settings or not guild_settings.get('setup_completed', False):
            await interaction.followup.send(
                "❌ Please run `/setup` first!",
                ephemeral=True
            )
            return
        
        try:
            if data_type == 'leaderboard':
                data = await self._export_leaderboard_data(interaction.guild.id, period)
            elif data_type == 'summary':
                data = await self._export_summary_data(interaction.guild.id, period)
            else:
                await interaction.followup.send(
                    "❌ Message-level data export is not available to protect user privacy.",
                    ephemeral=True
                )
                return
            
            if not data:
                await interaction.followup.send(
                    "❌ No data available for the selected period.",
                    ephemeral=True
                )
                return
            
            # Generate file
            if format == 'csv':
                file_content = self._generate_csv(data, data_type)
                filename = f"{interaction.guild.name}_{data_type}_{period}.csv"
                file = discord.File(io.StringIO(file_content), filename=filename)
            else:
                file_content = json.dumps(data, indent=2, default=str)
                filename = f"{interaction.guild.name}_{data_type}_{period}.json"
                file = discord.File(io.StringIO(file_content), filename=filename)
            
            await interaction.followup.send(
                f"📊 **{data_type.title()}** data exported for **{period}** period.",
                file=file,
                ephemeral=True
            )
        
        except Exception as e:
            self.logger.error(f"Error exporting data: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while exporting data.",
                ephemeral=True
            )
    
    @app_commands.command(name="config", description="View current ServerPulse configuration")
    @app_commands.default_permissions(administrator=True)
    async def view_config(self, interaction: discord.Interaction):
        """Display current server configuration."""
        await interaction.response.defer(ephemeral=True)
        
        guild_settings = await self.db.get_guild_settings(interaction.guild.id)
        if not guild_settings:
            await interaction.followup.send(
                "❌ ServerPulse is not configured for this server. Run `/setup` to get started!",
                ephemeral=True
            )
            return
        
        embed = discord.Embed(
            title="⚙️ ServerPulse Configuration",
            description=f"Current settings for **{interaction.guild.name}**",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        # Basic setup
        setup_status = "✅ Complete" if guild_settings.get('setup_completed', False) else "❌ Incomplete"
        update_channel = guild_settings.get('update_channel_id')
        
        embed.add_field(
            name="📋 Basic Setup",
            value=f"**Status:** {setup_status}\n"
                  f"**Update Channel:** {f'<#{update_channel}>' if update_channel else 'Not set'}\n"
                  f"**Tracked Channels:** {len(guild_settings.get('tracked_channels', []))}",
            inline=True
        )
        
        # Alert configuration
        alerts_enabled = guild_settings.get('alerts_enabled', {})
        alert_thresholds = guild_settings.get('alert_thresholds', {})
        
        alerts_text = ""
        for alert_type in ['join_raid', 'activity_drop', 'mass_delete', 'voice_surge']:
            enabled = alerts_enabled.get(alert_type, True)
            threshold = alert_thresholds.get(alert_type, 'Default')
            status_emoji = "✅" if enabled else "❌"
            
            alerts_text += f"{status_emoji} {alert_type.replace('_', ' ').title()}: {threshold}\n"
        
        embed.add_field(
            name="🔔 Alert Settings",
            value=alerts_text,
            inline=True
        )
        
        # AI configuration
        ai_provider = guild_settings.get('ai_provider', settings.ai_provider)
        digest_frequency = guild_settings.get('digest_frequency', 'weekly')
        ai_keys = guild_settings.get('ai_api_keys', {})
        
        embed.add_field(
            name="🤖 AI Configuration",
            value=f"**Provider:** {ai_provider}\n"
                  f"**Digest:** {digest_frequency}\n"
                  f"**API Keys:** {len(ai_keys)} configured",
            inline=True
        )
        
        # Data retention
        embed.add_field(
            name="💾 Data Settings",
            value=f"**Retention:** {settings.data_retention_days} days\n"
                  f"**Cache TTL:** {settings.cache_ttl_leaderboard}s (leaderboard)\n"
                  f"**Created:** {guild_settings.get('created_at', 'Unknown')}",
            inline=False
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    async def _export_leaderboard_data(self, guild_id: int, period: str) -> List[dict]:
        """Export leaderboard data."""
        leaderboard = await self.bot.analytics_manager.get_leaderboard(
            guild_id, period, limit=100
        )
        
        # Add usernames for CSV export
        guild = self.bot.get_guild(guild_id)
        if guild:
            for entry in leaderboard:
                member = guild.get_member(entry['user_id'])
                entry['username'] = member.display_name if member else 'Unknown User'
                entry['user_id_str'] = str(entry['user_id'])
        
        return leaderboard
    
    async def _export_summary_data(self, guild_id: int, period: str) -> dict:
        """Export summary statistics."""
        stats = await self.bot.analytics_manager.get_server_stats(guild_id, period)
        channel_comparison = await self.bot.analytics_manager.get_channel_comparison(guild_id, period)
        
        # Add channel names
        guild = self.bot.get_guild(guild_id)
        if guild:
            for channel_data in channel_comparison:
                channel = guild.get_channel(channel_data['channel_id'])
                channel_data['channel_name'] = channel.name if channel else 'Unknown'
        
        return {
            'server_stats': stats,
            'channel_breakdown': channel_comparison,
            'export_timestamp': datetime.utcnow().isoformat(),
            'period': period
        }
    
    def _generate_csv(self, data: List[dict], data_type: str) -> str:
        """Generate CSV content from data."""
        output = io.StringIO()
        
        if data_type == 'leaderboard' and data:
            writer = csv.DictWriter(output, fieldnames=['rank', 'username', 'user_id_str', 'message_count', 'avg_length'])
            writer.writeheader()
            
            for i, entry in enumerate(data, 1):
                writer.writerow({
                    'rank': i,
                    'username': entry.get('username', 'Unknown'),
                    'user_id_str': entry.get('user_id_str', str(entry['user_id'])),
                    'message_count': entry['message_count'],
                    'avg_length': round(entry.get('avg_length', 0), 1)
                })
        
        return output.getvalue()


async def setup(bot):
    await bot.add_cog(AdminCommands(bot))
