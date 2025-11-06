"""Setup and configuration commands for ServerPulse."""

import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, List

from src.utils.logger import LoggerMixin
from src.utils.helpers import sanitize_channel_name


class SetupCommands(commands.Cog, LoggerMixin):
    """Setup and configuration commands."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db_manager
        self.redis = bot.redis_manager
    
    @app_commands.command(name="setup", description="Interactive setup wizard for ServerPulse")
    @app_commands.default_permissions(administrator=True)
    async def setup_command(self, interaction: discord.Interaction):
        """Interactive setup wizard."""
        await interaction.response.defer(ephemeral=True)
        
        guild_id = interaction.guild.id
        guild_settings = await self.db.get_guild_settings(guild_id)
        
        if guild_settings and guild_settings.get('setup_completed', False):
            embed = discord.Embed(
                title="🧠 ServerPulse - Setup Status",
                description="ServerPulse is already configured for this server!",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="Current Configuration",
                value=f"📢 **Update Channel:** <#{guild_settings.get('update_channel_id')}>\n"
                      f"📊 **Tracked Channels:** {len(guild_settings.get('tracked_channels', []))}\n"
                      f"🔔 **Alerts Enabled:** {sum(guild_settings.get('alerts_enabled', {}).values())}\n"
                      f"🤖 **AI Provider:** {guild_settings.get('ai_provider', 'Not set')}",
                inline=False
            )
            
            embed.add_field(
                name="Next Steps",
                value="• Use `/add-collect-channel` to track more channels\n"
                      "• Use `/toggle-alert` to customize alerts\n"
                      "• Use `/topmessagers` to view analytics",
                inline=False
            )
            
            await interaction.followup.send(embed=embed)
            return
        
        # Start setup process
        setup_embed = discord.Embed(
            title="🧠 ServerPulse - Setup Wizard",
            description="Welcome to ServerPulse! Let's get you set up.\n\n"
                       "**Step 1:** Create or select an update channel where I'll send alerts and reports.",
            color=discord.Color.blue()
        )
        
        view = SetupView(self.bot, guild_id)
        await interaction.followup.send(embed=setup_embed, view=view)
    
    @app_commands.command(name="set-update-channel", description="Set the channel for ServerPulse updates")
    @app_commands.describe(channel="Channel to receive ServerPulse updates and alerts")
    @app_commands.default_permissions(administrator=True)
    async def set_update_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the update channel."""
        await interaction.response.defer(ephemeral=True)
        
        # Check permissions
        permissions = channel.permissions_for(interaction.guild.me)
        if not (permissions.send_messages and permissions.embed_links):
            await interaction.followup.send(
                "❌ I need `Send Messages` and `Embed Links` permissions in that channel!",
                ephemeral=True
            )
            return
        
        # Update settings
        await self.db.upsert_guild_settings(interaction.guild.id, {
            'update_channel_id': channel.id
        })
        
        # Send test message
        test_embed = discord.Embed(
            title="✅ ServerPulse Update Channel Set",
            description="This channel will now receive ServerPulse alerts and reports!",
            color=discord.Color.green()
        )
        
        try:
            await channel.send(embed=test_embed)
            
            await interaction.followup.send(
                f"✅ Update channel set to {channel.mention}!",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I couldn't send a test message to that channel. Please check my permissions!",
                ephemeral=True
            )
    
    @app_commands.command(name="add-collect-channel", description="Start collecting analytics from a channel")
    @app_commands.describe(channel="Channel to start tracking")
    @app_commands.default_permissions(administrator=True)
    async def add_collect_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Add a channel to analytics collection."""
        await interaction.response.defer(ephemeral=True)
        
        guild_settings = await self.db.get_guild_settings(interaction.guild.id)
        if not guild_settings:
            await interaction.followup.send(
                "❌ Please run `/setup` first!",
                ephemeral=True
            )
            return
        
        tracked_channels = guild_settings.get('tracked_channels', [])
        
        if channel.id in tracked_channels:
            await interaction.followup.send(
                f"📊 {channel.mention} is already being tracked!",
                ephemeral=True
            )
            return
        
        # Add channel to tracking
        tracked_channels.append(channel.id)
        await self.db.upsert_guild_settings(interaction.guild.id, {
            'tracked_channels': tracked_channels
        })
        
        await interaction.followup.send(
            f"✅ Now tracking analytics for {channel.mention}!",
            ephemeral=True
        )
    
    @app_commands.command(name="remove-collect-channel", description="Stop collecting analytics from a channel")
    @app_commands.describe(channel="Channel to stop tracking")
    @app_commands.default_permissions(administrator=True)
    async def remove_collect_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Remove a channel from analytics collection."""
        await interaction.response.defer(ephemeral=True)
        
        guild_settings = await self.db.get_guild_settings(interaction.guild.id)
        if not guild_settings:
            await interaction.followup.send(
                "❌ Please run `/setup` first!",
                ephemeral=True
            )
            return
        
        tracked_channels = guild_settings.get('tracked_channels', [])
        
        if channel.id not in tracked_channels:
            await interaction.followup.send(
                f"📊 {channel.mention} is not being tracked!",
                ephemeral=True
            )
            return
        
        # Remove channel from tracking
        tracked_channels.remove(channel.id)
        await self.db.upsert_guild_settings(interaction.guild.id, {
            'tracked_channels': tracked_channels
        })
        
        # Clear cached data for this channel
        await self.redis.clear_guild_cache(interaction.guild.id)
        
        await interaction.followup.send(
            f"✅ Stopped tracking analytics for {channel.mention}!",
            ephemeral=True
        )


class SetupView(discord.ui.View):
    """Interactive setup view."""
    
    def __init__(self, bot, guild_id: int):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild_id = guild_id
        self.step = 1
    
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        
        try:
            await self.message.edit(view=self)
        except:
            pass
    
    @discord.ui.button(label="Create #serverpulse-updates", style=discord.ButtonStyle.primary, emoji="➕")
    async def create_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Create updates channel."""
        guild = interaction.guild
        
        # Check if channel already exists
        existing_channel = discord.utils.get(guild.text_channels, name="serverpulse-updates")
        if existing_channel:
            await self._set_update_channel(interaction, existing_channel)
            return
        
        # Create channel
        try:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.me: discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    embed_links=True,
                    read_message_history=True
                )
            }
            
            # Add admin roles to overwrites
            for role in guild.roles:
                if role.permissions.administrator:
                    overwrites[role] = discord.PermissionOverwrite(read_messages=True)
            
            channel = await guild.create_text_channel(
                "serverpulse-updates",
                topic="ServerPulse alerts and analytics reports",
                overwrites=overwrites
            )
            
            await self._set_update_channel(interaction, channel)
            
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to create channels! Please create a channel manually and select it.",
                ephemeral=True
            )
    
    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text],
        placeholder="Or select an existing channel...",
        min_values=1,
        max_values=1
    )
    async def select_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        """Select existing channel."""
        channel = select.values[0]
        await self._set_update_channel(interaction, channel)
    
    async def _set_update_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the update channel and continue setup."""
        # Check permissions
        permissions = channel.permissions_for(interaction.guild.me)
        if not (permissions.send_messages and permissions.embed_links):
            await interaction.response.send_message(
                "❌ I need `Send Messages` and `Embed Links` permissions in that channel!",
                ephemeral=True
            )
            return
        
        # Update database
        await self.bot.db_manager.upsert_guild_settings(self.guild_id, {
            'update_channel_id': channel.id,
            'setup_completed': True
        })
        
        # Continue to step 2
        embed = discord.Embed(
            title="✅ Update Channel Set!",
            description=f"Great! I'll send alerts and reports to {channel.mention}\n\n"
                       "**Step 2:** Select channels to track for analytics.",
            color=discord.Color.green()
        )
        
        # Clear view and add channel selection
        self.clear_items()
        self.add_item(ChannelTrackingSelect())
        self.add_item(CompleteSetupButton())
        
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Send welcome message to the channel
        welcome_embed = discord.Embed(
            title="🧠 ServerPulse is Online!",
            description="This channel will receive real-time alerts and AI-powered insights about your server.",
            color=discord.Color.green()
        )
        
        try:
            await channel.send(embed=welcome_embed)
        except:
            pass


class ChannelTrackingSelect(discord.ui.ChannelSelect):
    """Channel selection for tracking."""
    
    def __init__(self):
        super().__init__(
            channel_types=[discord.ChannelType.text],
            placeholder="Select channels to track (up to 10)...",
            min_values=1,
            max_values=10
        )
    
    async def callback(self, interaction: discord.Interaction):
        bot = interaction.client
        guild_settings = await bot.db_manager.get_guild_settings(interaction.guild.id)
        
        channel_ids = [channel.id for channel in self.values]
        tracked_channels = guild_settings.get('tracked_channels', [])
        
        # Add new channels
        for channel_id in channel_ids:
            if channel_id not in tracked_channels:
                tracked_channels.append(channel_id)
        
        await bot.db_manager.upsert_guild_settings(interaction.guild.id, {
            'tracked_channels': tracked_channels
        })
        
        channel_mentions = [f"<#{channel_id}>" for channel_id in channel_ids]
        
        await interaction.response.send_message(
            f"✅ Now tracking: {', '.join(channel_mentions)}",
            ephemeral=True
        )


class CompleteSetupButton(discord.ui.Button):
    """Complete setup button."""
    
    def __init__(self):
        super().__init__(
            label="Complete Setup",
            style=discord.ButtonStyle.success,
            emoji="✅"
        )
    
    async def callback(self, interaction: discord.Interaction):
        guild_settings = await interaction.client.db_manager.get_guild_settings(interaction.guild.id)
        
        embed = discord.Embed(
            title="🎉 ServerPulse Setup Complete!",
            description="Your server is now configured and ready for analytics!",
            color=discord.Color.green()
        )
        
        tracked_count = len(guild_settings.get('tracked_channels', []))
        
        embed.add_field(
            name="Configuration Summary",
            value=f"📢 **Update Channel:** <#{guild_settings.get('update_channel_id')}>\n"
                  f"📊 **Tracked Channels:** {tracked_count}\n"
                  f"🔔 **Alerts:** Enabled (join raids, activity changes, etc.)\n"
                  f"🤖 **AI Insights:** Ready (configure API keys for enhanced reports)",
            inline=False
        )
        
        embed.add_field(
            name="Next Steps",
            value="• `/topmessagers` - View server leaderboards\n"
                  "• `/pulse-now` - Generate instant AI report\n"
                  "• `/toggle-alert` - Customize alert preferences\n"
                  "• Configure AI API keys for enhanced insights",
            inline=False
        )
        
        # Clear the view
        self.view.clear_items()
        
        await interaction.response.edit_message(embed=embed, view=self.view)


async def setup(bot):
    await bot.add_cog(SetupCommands(bot))
