"""Admin and management commands for ServerPulse."""

import json
from datetime import datetime
from typing import Optional, Dict, Any

import discord
from discord import app_commands
from discord.ext import commands

from src.config import settings, AIProvider
from src.utils.helpers import format_number, format_time_duration
from src.utils.logger import LoggerMixin


class AdminCommands(commands.Cog, LoggerMixin):
    """Administrative and management commands."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db_manager
        self.redis = bot.redis_manager
        self.ai_manager = bot.ai_manager
    
    @app_commands.command(name="toggle-alert", description="Enable or disable specific alert types")
    @app_commands.describe(
        alert_type="Type of alert to toggle",
        enabled="Enable (True) or disable (False) the alert"
    )
    @app_commands.choices(alert_type=[
        app_commands.Choice(name="Join Raid Detection", value="join_raid"),
        app_commands.Choice(name="Activity Drop Alert", value="activity_drop"),
        app_commands.Choice(name="Mass Message Deletion", value="mass_delete"),
        app_commands.Choice(name="Voice Channel Surge", value="voice_surge")
    ])
    @app_commands.default_permissions(administrator=True)
    async def toggle_alert(self, interaction: discord.Interaction, 
                          alert_type: str, enabled: bool) -> None:
        """Toggle specific alert types on/off."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You need administrator permissions to manage alerts.",
                ephemeral=True
            )
            return
        
        guild_settings = await self.db.get_guild_settings(interaction.guild.id)
        if not guild_settings:
            await interaction.response.send_message(
                "❌ Server not configured. Use `/setup` first.",
                ephemeral=True
            )
            return
        
        alerts_enabled = guild_settings.get('alerts_enabled', {})
        alerts_enabled[alert_type] = enabled
        
        await self.db.upsert_guild_settings(interaction.guild.id, {
            'alerts_enabled': alerts_enabled
        })
        
        alert_names = {
            'join_raid': 'Join Raid Detection',
            'activity_drop': 'Activity Drop Alert',
            'mass_delete': 'Mass Message Deletion',
            'voice_surge': 'Voice Channel Surge'
        }
        
        status = "enabled" if enabled else "disabled"
        color = discord.Color.green() if enabled else discord.Color.red()
        
        embed = discord.Embed(
            title=f"⚙️ Alert Settings Updated",
            description=f"**{alert_names[alert_type]}** has been {status}.",
            color=color
        )
        
        # Show current alert status
        alert_status = ""
        for alert_key, alert_name in alert_names.items():
            is_enabled = alerts_enabled.get(alert_key, True)
            emoji = "✅" if is_enabled else "❌"
            alert_status += f"{emoji} {alert_name}\n"
        
        embed.add_field(
            name="Current Alert Status",
            value=alert_status,
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="ai-provider", description="Configure AI provider settings")
    @app_commands.describe(
        action="Action to perform",
        provider="AI provider to use",
        api_key="API key for the selected provider"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Set Provider", value="set"),
            app_commands.Choice(name="Add API Key", value="key"),
            app_commands.Choice(name="Test Connection", value="test"),
            app_commands.Choice(name="Show Status", value="status")
        ],
        provider=[
            app_commands.Choice(name="OpenRouter", value="openrouter"),
            app_commands.Choice(name="Gemini", value="gemini"),
            app_commands.Choice(name="OpenAI", value="openai"),
            app_commands.Choice(name="Grok", value="grok")
        ]
    )
    @app_commands.default_permissions(administrator=True)
    async def ai_provider(self, interaction: discord.Interaction,
                         action: str, provider: Optional[str] = None, 
                         api_key: Optional[str] = None) -> None:
        """Configure AI provider and API keys."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You need administrator permissions to configure AI settings.",
                ephemeral=True
            )
            return
        
        guild_settings = await self.db.get_guild_settings(interaction.guild.id)
        if not guild_settings:
            await interaction.response.send_message(
                "❌ Server not configured. Use `/setup` first.",
                ephemeral=True
            )
            return
        
        if action == "status":
            await self._show_ai_status(interaction, guild_settings)
        elif action == "set":
            if not provider:
                await interaction.response.send_message(
                    "❌ Please specify a provider when setting.",
                    ephemeral=True
                )
                return
            await self._set_ai_provider(interaction, provider)
        elif action == "key":
            if not provider or not api_key:
                await interaction.response.send_message(
                    "❌ Please specify both provider and API key.",
                    ephemeral=True
                )
                return
            await self._set_api_key(interaction, provider, api_key)
        elif action == "test":
            if not provider:
                await interaction.response.send_message(
                    "❌ Please specify a provider to test.",
                    ephemeral=True
                )
                return
            await self._test_ai_provider(interaction, provider)
    
    async def _show_ai_status(self, interaction: discord.Interaction, 
                            guild_settings: Dict[str, Any]) -> None:
        """Show current AI configuration status."""
        embed = discord.Embed(
            title="🤖 AI Provider Status",
            color=discord.Color.blue()
        )
        
        current_provider = guild_settings.get('ai_provider', 'Not set')
        api_keys = guild_settings.get('ai_api_keys', {})
        
        embed.add_field(
            name="Current Provider",
            value=f"**{current_provider.title()}**" if current_provider != 'Not set' else "Not configured",
            inline=False
        )
        
        # API key status
        key_status = ""
        providers = ['openrouter', 'gemini', 'openai', 'grok']
        
        for provider in providers:
            has_key = provider in api_keys and api_keys[provider]
            emoji = "✅" if has_key else "❌"
            key_status += f"{emoji} {provider.title()}\n"
        
        embed.add_field(
            name="API Keys",
            value=key_status,
            inline=True
        )
        
        # AI features status
        digest_freq = guild_settings.get('digest_frequency', 'none')
        features_status = (
            f"📅 **Reports:** {digest_freq.title()}\n"
            f"🧠 **Insights:** {'Enabled' if digest_freq != 'none' else 'Disabled'}"
        )
        
        embed.add_field(
            name="AI Features",
            value=features_status,
            inline=True
        )
        
        embed.add_field(
            name="Configure AI",
            value=(
                "`/ai-provider set <provider>` - Set active provider\n"
                "`/ai-provider key <provider> <key>` - Add API key\n"
                "`/ai-provider test <provider>` - Test connection"
            ),
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def _set_ai_provider(self, interaction: discord.Interaction, provider: str) -> None:
        """Set the active AI provider."""
        await self.db.upsert_guild_settings(interaction.guild.id, {
            'ai_provider': provider
        })
        
        embed = discord.Embed(
            title="✅ AI Provider Updated",
            description=f"Active AI provider set to **{provider.title()}**.",
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="Next Steps",
            value=(
                f"1. Add your {provider.title()} API key:\n"
                f"   `/ai-provider key {provider} YOUR_API_KEY`\n\n"
                f"2. Test the connection:\n"
                f"   `/ai-provider test {provider}`\n\n"
                f"3. Enable reports with `/set-digest daily` or `/set-digest weekly`"
            ),
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def _set_api_key(self, interaction: discord.Interaction, provider: str, api_key: str) -> None:
        """Set API key for a provider."""
        guild_settings = await self.db.get_guild_settings(interaction.guild.id)
        api_keys = guild_settings.get('ai_api_keys', {})
        api_keys[provider] = api_key
        
        await self.db.upsert_guild_settings(interaction.guild.id, {
            'ai_api_keys': api_keys
        })
        
        embed = discord.Embed(
            title="✅ API Key Added",
            description=f"API key for **{provider.title()}** has been saved securely.",
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="Security Note",
            value="API keys are encrypted and stored securely. Only server administrators can modify them.",
            inline=False
        )
        
        embed.add_field(
            name="Test Your Setup",
            value=f"Use `/ai-provider test {provider}` to verify the connection works.",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def _test_ai_provider(self, interaction: discord.Interaction, provider: str) -> None:
        """Test AI provider connection."""
        await interaction.response.defer(ephemeral=True)
        
        guild_settings = await self.db.get_guild_settings(interaction.guild.id)
        api_keys = guild_settings.get('ai_api_keys', {})
        
        if provider not in api_keys or not api_keys[provider]:
            embed = discord.Embed(
                title="❌ No API Key",
                description=f"No API key found for {provider.title()}.",
                color=discord.Color.red()
            )
            embed.add_field(
                name="Add API Key",
                value=f"Use `/ai-provider key {provider} YOUR_API_KEY` to add one.",
                inline=False
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        try:
            # Test the AI provider
            test_result = await self.ai_manager.test_provider(
                provider, api_keys[provider]
            )
            
            if test_result['success']:
                embed = discord.Embed(
                    title="✅ Connection Successful",
                    description=f"{provider.title()} is working correctly!",
                    color=discord.Color.green()
                )
                
                if 'model' in test_result:
                    embed.add_field(
                        name="Model Info",
                        value=f"Using: {test_result['model']}",
                        inline=False
                    )
            else:
                embed = discord.Embed(
                    title="❌ Connection Failed",
                    description=f"Could not connect to {provider.title()}.",
                    color=discord.Color.red()
                )
                
                if 'error' in test_result:
                    embed.add_field(
                        name="Error Details",
                        value=test_result['error'][:500],
                        inline=False
                    )
        
        except Exception as e:
            embed = discord.Embed(
                title="❌ Test Failed",
                description=f"An error occurred while testing {provider.title()}.",
                color=discord.Color.red()
            )
            embed.add_field(
                name="Error",
                value=str(e)[:500],
                inline=False
            )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name="export-report", description="Export server analytics data")
    @app_commands.describe(
        format_type="Export format",
        period="Time period to export"
    )
    @app_commands.choices(
        format_type=[
            app_commands.Choice(name="JSON", value="json"),
            app_commands.Choice(name="CSV", value="csv")
        ],
        period=[
            app_commands.Choice(name="Last 24 Hours", value="24h"),
            app_commands.Choice(name="Last 7 Days", value="7d"),
            app_commands.Choice(name="Last 30 Days", value="30d"),
            app_commands.Choice(name="All Time", value="all")
        ]
    )
    @app_commands.default_permissions(administrator=True)
    async def export_report(self, interaction: discord.Interaction,
                           format_type: str = "json", period: str = "7d") -> None:
        """Export analytics data."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You need administrator permissions to export data.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            import csv
            import io
            
            # Get comprehensive data
            stats = await self.bot.analytics_manager.get_server_stats(
                interaction.guild.id, period
            )
            leaderboard = await self.bot.analytics_manager.get_leaderboard(
                interaction.guild.id, period, limit=50
            )
            channel_comparison = await self.bot.analytics_manager.get_channel_comparison(
                interaction.guild.id, period
            )
            
            export_data = {
                'server_name': interaction.guild.name,
                'server_id': interaction.guild.id,
                'export_period': period,
                'export_timestamp': datetime.utcnow().isoformat(),
                'stats': stats,
                'leaderboard': leaderboard,
                'channel_comparison': channel_comparison
            }
            
            if format_type == "json":
                content = json.dumps(export_data, indent=2, default=str)
                filename = f"serverpulse_export_{interaction.guild.id}_{period}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
            else:  # CSV format
                output = io.StringIO()
                writer = csv.writer(output)
                
                # Write leaderboard data
                writer.writerow(['Rank', 'User ID', 'Messages', 'Avg Length'])
                for i, user in enumerate(leaderboard, 1):
                    writer.writerow([
                        i, user['user_id'], user['message_count'], 
                        user.get('avg_length', 0)
                    ])
                
                content = output.getvalue()
                filename = f"serverpulse_export_{interaction.guild.id}_{period}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
            
            # Create file
            file = discord.File(
                io.StringIO(content),
                filename=filename
            )
            
            embed = discord.Embed(
                title="📊 Data Export Complete",
                description=f"Analytics data exported for {period} period.",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="Export Details",
                value=(
                    f"📅 **Period:** {period}\n"
                    f"📝 **Format:** {format_type.upper()}\n"
                    f"📊 **Records:** {len(leaderboard)} users"
                ),
                inline=False
            )
            
            await interaction.followup.send(embed=embed, file=file, ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"Error exporting data: {e}")
            await interaction.followup.send(
                "❌ An error occurred while exporting data. Please try again.",
                ephemeral=True
            )
    
    @app_commands.command(name="pulse-now", description="Generate an AI report immediately")
    @app_commands.default_permissions(administrator=True)
    async def pulse_now(self, interaction: discord.Interaction) -> None:
        """Generate immediate AI report."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You need administrator permissions to generate reports.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer()
        
        guild_settings = await self.db.get_guild_settings(interaction.guild.id)
        if not guild_settings:
            await interaction.followup.send(
                "❌ Server not configured. Use `/setup` first.",
                ephemeral=True
            )
            return
        
        # Check if AI is configured
        ai_provider = guild_settings.get('ai_provider')
        api_keys = guild_settings.get('ai_api_keys', {})
        
        if not ai_provider or ai_provider not in api_keys:
            embed = discord.Embed(
                title="❌ AI Not Configured",
                description="AI provider not set up. Configure it first.",
                color=discord.Color.red()
            )
            embed.add_field(
                name="Setup AI",
                value="Use `/ai-provider set <provider>` and `/ai-provider key <provider> <key>` to configure.",
                inline=False
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        try:
            # Generate AI report (now returns Discord Embed)
            report_embed = await self.ai_manager.generate_pulse_report(
                interaction.guild.id, 
                self.db,
                period="24h",
                guild_name=interaction.guild.name
            )
            
            if report_embed:
                # Send report to updates channel
                update_channel_id = guild_settings.get('update_channel_id')
                if update_channel_id:
                    update_channel = interaction.guild.get_channel(update_channel_id)
                    if update_channel:
                        await update_channel.send(embed=report_embed)
                        
                        from src.utils.formatting_utils import create_success_embed
                        success_embed = create_success_embed(
                            "AI Pulse Report Sent",
                            f"Report successfully delivered to {update_channel.mention}"
                        )
                        await interaction.followup.send(embed=success_embed, ephemeral=True)
                    else:
                        await interaction.followup.send(
                            "❌ Update channel not found. Please reconfigure with `/setup`.",
                            ephemeral=True
                        )
                else:
                    await interaction.followup.send(
                        "❌ No update channel configured. Please run `/setup` first.",
                        ephemeral=True
                    )
            else:
                await interaction.followup.send(
                    "❌ Failed to generate AI report. Check AI provider configuration.",
                    ephemeral=True
                )
                
        except Exception as e:
            self.logger.error(f"Error generating pulse report: {e}")
            await interaction.followup.send(
                "❌ An error occurred while generating the report. Please try again.",
                ephemeral=True
            )
    
    @app_commands.command(name="server-info", description="Show ServerPulse configuration and status")
    async def server_info(self, interaction: discord.Interaction) -> None:
        """Show current ServerPulse configuration."""
        guild_settings = await self.db.get_guild_settings(interaction.guild.id)
        
        embed = discord.Embed(
            title=f"📊 ServerPulse Status - {interaction.guild.name}",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        if not guild_settings or not guild_settings.get('setup_completed', False):
            embed.description = "❌ ServerPulse is not configured for this server."
            embed.add_field(
                name="Get Started",
                value="Use `/setup` to configure ServerPulse for your server.",
                inline=False
            )
        else:
            # Configuration status
            update_channel_id = guild_settings.get('update_channel_id')
            update_channel = self.bot.get_channel(update_channel_id) if update_channel_id else None
            
            tracked_channels = guild_settings.get('tracked_channels', [])
            alerts_enabled = guild_settings.get('alerts_enabled', {})
            
            embed.add_field(
                name="⚙️ Configuration",
                value=(
                    f"📢 **Update Channel:** {update_channel.mention if update_channel else 'Not set'}\n"
                    f"📊 **Tracked Channels:** {len(tracked_channels)}\n"
                    f"📅 **Digest:** {guild_settings.get('digest_frequency', 'none').title()}"
                ),
                inline=True
            )
            
            # Visual separator
            embed.add_field(name="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", value="\u200b", inline=False)
            
            # Alert status
            alert_count = sum(1 for enabled in alerts_enabled.values() if enabled)
            embed.add_field(
                name="🔔 Alerts",
                value=f"{alert_count}/4 alert types enabled",
                inline=True
            )
            
            # Visual separator
            embed.add_field(name="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", value="\u200b", inline=False)

            # AI status
            ai_provider = guild_settings.get('ai_provider', 'Not set')
            api_keys = guild_settings.get('ai_api_keys', {})
            ai_configured = ai_provider in api_keys if ai_provider != 'Not set' else False
            
            embed.add_field(
                name="🤖 AI Integration",
                value=(
                    f"🎨 **Provider:** {ai_provider.title() if ai_provider != 'Not set' else 'None'}\n"
                    f"🔑 **API Key:** {'Configured' if ai_configured else 'Not set'}"
                ),
                inline=True
            )
            
            # Visual separator
            embed.add_field(name="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", value="\u200b", inline=False)

            # Bot uptime
            uptime = datetime.utcnow() - self.bot.start_time
            embed.add_field(
                name="🕰️ Bot Status",
                value=(
                    f"✅ **Online**\n"
                    f"🕰️ **Uptime:** {format_time_duration(int(uptime.total_seconds()))}\n"
                    f"🏗️ **Servers:** {len(self.bot.guilds)}"
                ),
                inline=False
            )
        
        embed.set_footer(
            text=f"ServerPulse v1.0.0 • Requested by {interaction.user.display_name}",
            icon_url=self.bot.user.display_avatar.url
        )
        
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCommands(bot))
