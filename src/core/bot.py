"""Main ServerPulse bot implementation."""

import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime

import discord
from discord.ext import commands, tasks

from src.database.mongodb import DatabaseManager
from src.database.redis_client import RedisManager
from src.config import settings
from src.utils.logger import LoggerMixin
from src.core.analytics import AnalyticsManager
from src.core.alerts import AlertManager
from src.ai.ai_manager import AIManager


class ServerPulseBot(commands.Bot, LoggerMixin):
    """Main ServerPulse Discord bot."""
    
    def __init__(self, db_manager: DatabaseManager, redis_manager: RedisManager, **kwargs):
        super().__init__(**kwargs)
        
        self.db_manager = db_manager
        self.redis_manager = redis_manager
        
        # Initialize managers
        self.analytics_manager = AnalyticsManager(db_manager, redis_manager)
        self.alert_manager = AlertManager(db_manager, redis_manager, self)
        self.ai_manager = AIManager()
        
        # Bot state
        self.start_time = datetime.utcnow()
        self.is_ready = False
        
        # Start background tasks
        self.cleanup_task.start()
        self.daily_reports_task.start()
    
    async def setup_hook(self) -> None:
        """Setup hook called when bot is starting up."""
        self.logger.info("Setting up bot...")
        
        # Load cogs/commands
        await self.load_extension('src.commands.setup')
        await self.load_extension('src.commands.analytics')
        await self.load_extension('src.commands.admin')
        
        # Sync slash commands if in development
        if settings.developer_guild_id:
            guild = discord.Object(id=settings.developer_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            self.logger.info(f"Synced commands to development guild {settings.developer_guild_id}")
        else:
            await self.tree.sync()
            self.logger.info("Synced global commands")
    
    async def on_ready(self) -> None:
        """Called when the bot is ready."""
        self.logger.info(f"{self.user} has connected to Discord!")
        self.logger.info(f"Bot is in {len(self.guilds)} guilds")
        
        # Update presence
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(self.guilds)} servers | /setup to get started"
        )
        await self.change_presence(activity=activity)
        
        self.is_ready = True
    
    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Handle bot joining a new guild."""
        self.logger.info(f"Joined new guild: {guild.name} ({guild.id})")
        
        # Initialize default guild settings
        default_settings = {
            'guild_name': guild.name,
            'setup_completed': False,
            'update_channel_id': None,
            'tracked_channels': [],
            'alerts_enabled': {
                'join_raid': True,
                'activity_drop': True,
                'mass_delete': True,
                'voice_surge': True
            },
            'alert_thresholds': {
                'join_raid': settings.default_alert_threshold_join_raid,
                'activity_drop': settings.default_alert_threshold_activity_drop,
                'mass_delete': settings.default_alert_threshold_mass_delete,
                'voice_surge': settings.default_alert_threshold_voice_surge
            },
            'ai_provider': settings.ai_provider,
            'ai_api_keys': {},
            'digest_frequency': 'weekly',
            'created_at': datetime.utcnow()
        }
        
        await self.db_manager.upsert_guild_settings(guild.id, default_settings)
        
        # Update presence
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(self.guilds)} servers | /setup to get started"
        )
        await self.change_presence(activity=activity)
        
        # Try to send welcome message to first available text channel
        await self._send_welcome_message(guild)
    
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """Handle bot leaving a guild."""
        self.logger.info(f"Left guild: {guild.name} ({guild.id})")
        
        # Clear cached data
        await self.redis_manager.clear_guild_cache(guild.id)
        
        # Update presence
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(self.guilds)} servers | /setup to get started"
        )
        await self.change_presence(activity=activity)
    
    async def on_message(self, message: discord.Message) -> None:
        """Handle message events for analytics."""
        # Ignore bot messages
        if message.author.bot:
            return
        
        # Only track messages from guilds with tracking enabled
        if not message.guild:
            return
        
        # Check if channel is tracked
        guild_settings = await self.db_manager.get_guild_settings(message.guild.id)
        if not guild_settings or not guild_settings.get('setup_completed', False):
            return
        
        tracked_channels = guild_settings.get('tracked_channels', [])
        if message.channel.id not in tracked_channels:
            return
        
        # Record message analytics
        await self.analytics_manager.record_message(
            message.guild.id,
            message.channel.id,
            message.author.id,
            len(message.content),
            bool(message.attachments)
        )
        
        # Check for potential alerts
        await self.alert_manager.check_message_alerts(
            message.guild.id,
            message.channel.id
        )
        
        # Process commands (for prefix commands if any)
        await self.process_commands(message)
    
    async def on_member_join(self, member: discord.Member) -> None:
        """Handle member join events."""
        # Record member event
        await self.db_manager.record_member_event(
            member.guild.id,
            member.id,
            'join'
        )
        
        # Check for join raid alert
        await self.alert_manager.check_join_raid_alert(member.guild.id)
    
    async def on_member_remove(self, member: discord.Member) -> None:
        """Handle member leave events."""
        # Record member event
        await self.db_manager.record_member_event(
            member.guild.id,
            member.id,
            'leave'
        )
    
    async def on_voice_state_update(self, member: discord.Member, 
                                  before: discord.VoiceState, 
                                  after: discord.VoiceState) -> None:
        """Handle voice state changes."""
        # Joining voice channel
        if before.channel is None and after.channel is not None:
            await self.db_manager.record_voice_event(
                member.guild.id,
                member.id,
                after.channel.id,
                'join'
            )
            await self.alert_manager.check_voice_surge_alert(member.guild.id)
        
        # Leaving voice channel
        elif before.channel is not None and after.channel is None:
            await self.db_manager.record_voice_event(
                member.guild.id,
                member.id,
                before.channel.id,
                'leave'
            )
        
        # Moving between voice channels
        elif before.channel != after.channel:
            await self.db_manager.record_voice_event(
                member.guild.id,
                member.id,
                after.channel.id,
                'move'
            )
    
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        """Handle message deletion events."""
        if not payload.guild_id:
            return
        
        # Check for mass deletion alert
        await self.alert_manager.check_mass_delete_alert(payload.guild_id, payload.channel_id)
    
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent) -> None:
        """Handle bulk message deletion events."""
        if not payload.guild_id:
            return
        
        # Definitely trigger mass deletion alert for bulk deletes
        await self.alert_manager.trigger_mass_delete_alert(
            payload.guild_id,
            payload.channel_id,
            len(payload.message_ids)
        )
    
    async def on_error(self, event: str, *args, **kwargs) -> None:
        """Handle bot errors."""
        self.logger.error(f"Error in event {event}", exc_info=True)
    
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        """Handle command errors."""
        if isinstance(error, commands.CommandNotFound):
            return  # Ignore unknown commands
        
        self.logger.error(f"Command error in {ctx.command}: {error}", exc_info=True)
        
        if ctx.interaction:
            # For slash commands
            try:
                await ctx.interaction.response.send_message(
                    f"❌ An error occurred: {str(error)}",
                    ephemeral=True
                )
            except discord.InteractionResponse:
                await ctx.interaction.followup.send(
                    f"❌ An error occurred: {str(error)}",
                    ephemeral=True
                )
    
    async def _send_welcome_message(self, guild: discord.Guild) -> None:
        """Send welcome message to guild."""
        welcome_embed = discord.Embed(
            title="🧠 ServerPulse - Welcome!",
            description=(
                "Thanks for adding ServerPulse to your server!\n\n"
                "**Get Started:**\n"
                "• Use `/setup` to configure the bot\n"
                "• Choose channels to track with `/add-collect-channel`\n"
                "• Set up alerts and AI insights\n\n"
                "**Features:**\n"
                "📊 Real-time server analytics\n"
                "🚨 Instant activity alerts\n"
                "🧠 AI-powered insights\n"
                "🏆 Member leaderboards\n\n"
                "Need help? Check out our [documentation](https://github.com/Sahaj33-op/ServerPulse)"
            ),
            color=discord.Color.green()
        )
        
        # Try to send to system channel first, then first available channel
        target_channel = guild.system_channel
        
        if not target_channel or not target_channel.permissions_for(guild.me).send_messages:
            # Find first available text channel
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    target_channel = channel
                    break
        
        if target_channel:
            try:
                await target_channel.send(embed=welcome_embed)
            except discord.Forbidden:
                self.logger.warning(f"Could not send welcome message to {guild.name}")
    
    @tasks.loop(hours=24)
    async def cleanup_task(self) -> None:
        """Daily cleanup task."""
        if not self.is_ready:
            return
        
        self.logger.info("Running daily cleanup task")
        
        try:
            # Clean up old data based on retention policy
            cleanup_stats = await self.db_manager.cleanup_old_data(settings.data_retention_days)
            self.logger.info(f"Cleanup completed: {cleanup_stats}")
            
        except Exception as e:
            self.logger.error(f"Error in cleanup task: {e}", exc_info=True)
    
    @tasks.loop(hours=24)
    async def daily_reports_task(self) -> None:
        """Generate and send daily reports."""
        if not self.is_ready:
            return
        
        self.logger.info("Running daily reports task")
        
        try:
            for guild in self.guilds:
                guild_settings = await self.db_manager.get_guild_settings(guild.id)
                
                if not guild_settings or not guild_settings.get('setup_completed', False):
                    continue
                
                # Generate AI report if enabled and configured
                if guild_settings.get('digest_frequency') == 'daily':
                    await self.ai_manager.generate_daily_report(guild.id, self.db_manager)
                    
        except Exception as e:
            self.logger.error(f"Error in daily reports task: {e}", exc_info=True)
    
    @cleanup_task.before_loop
    @daily_reports_task.before_loop
    async def before_loops(self) -> None:
        """Wait for bot to be ready before starting loops."""
        await self.wait_until_ready()


    async def close(self) -> None:
        """Cleanup when bot is shutting down."""
        self.logger.info("Shutting down ServerPulse Bot...")
        
        # Cancel background tasks
        self.cleanup_task.cancel()
        self.daily_reports_task.cancel()
        
        # Close managers
        if hasattr(self, 'ai_manager'):
            await self.ai_manager.close()
        
        await super().close()
