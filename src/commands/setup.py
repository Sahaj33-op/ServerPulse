"""Setup and configuration commands for ServerPulse."""

import asyncio
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.config import settings, AIProvider
from src.utils.helpers import sanitize_channel_name
from src.utils.logger import LoggerMixin


class SetupCommands(commands.Cog, LoggerMixin):
    """Setup and configuration commands."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db_manager
        self.redis = bot.redis_manager
    
    @app_commands.command(name="setup", description="Interactive setup wizard for ServerPulse")
    @app_commands.describe()
    @app_commands.default_permissions(administrator=True)
    async def setup(self, interaction: discord.Interaction) -> None:
        """Interactive setup wizard."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You need administrator permissions to run setup.",
                ephemeral=True
            )
            return
        
        guild_id = interaction.guild.id
        
        # Check if already set up
        guild_settings = await self.db.get_guild_settings(guild_id)
        if guild_settings and guild_settings.get('setup_completed', False):
            embed = discord.Embed(
                title="🔧 ServerPulse Already Configured",
                description="Your server is already set up! Use individual commands to modify settings.",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="Current Configuration",
                value=(
                    f"📢 Update Channel: <#{guild_settings.get('update_channel_id', 'None')}>\n"
                    f"📊 Tracked Channels: {len(guild_settings.get('tracked_channels', []))}\n"
                    f"🤖 AI Provider: {guild_settings.get('ai_provider', 'Not set')}\n"
                    f"📅 Digest: {guild_settings.get('digest_frequency', 'weekly').title()}"
                ),
                inline=False
            )
            
            embed.add_field(
                name="Modify Settings",
                value=(
                    "`/set-update-channel` - Change alert channel\n"
                    "`/add-collect-channel` - Track more channels\n"
                    "`/ai-provider` - Configure AI settings\n"
                    "`/set-digest` - Change report frequency"
                ),
                inline=False
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Setup wizard embed
        setup_embed = discord.Embed(
            title="🚀 ServerPulse Setup Wizard",
            description="Let's configure ServerPulse for your server! This will take just a few steps.",
            color=discord.Color.green()
        )
        
        setup_embed.add_field(
            name="What we'll configure:",
            value=(
                "📢 **Update Channel** - Where alerts and reports are sent\n"
                "📊 **Tracking Channels** - Which channels to monitor\n"
                "🔔 **Alert Settings** - Real-time notifications\n"
                "🤖 **AI Provider** - For intelligent insights\n"
                "📅 **Report Frequency** - Daily/weekly summaries"
            ),
            inline=False
        )
        
        # Store reference to parent cog for nested classes
        parent_cog = self
        
        # Step 1: Update Channel Selection
        class UpdateChannelSelect(discord.ui.Select):
            def __init__(self):
                options = []
                for channel in interaction.guild.text_channels:
                    if channel.permissions_for(interaction.guild.me).send_messages:
                        options.append(discord.SelectOption(
                            label=f"#{channel.name}",
                            value=str(channel.id),
                            description=f"Category: {channel.category.name if channel.category else 'None'}"
                        ))
                
                if not options:
                    options.append(discord.SelectOption(
                        label="No available channels",
                        value="none",
                        description="Bot needs permission to send messages"
                    ))
                
                super().__init__(
                    placeholder="Choose where ServerPulse will send updates...",
                    options=options[:25],  # Discord limit
                    min_values=1,
                    max_values=1
                )
            
            async def callback(self, select_interaction: discord.Interaction):
                if select_interaction.data['values'][0] == "none":
                    await select_interaction.response.send_message(
                        "❌ Please give the bot permission to send messages in at least one channel.",
                        ephemeral=True
                    )
                    return
                
                selected_channel_id = int(select_interaction.data['values'][0])
                
                # Save update channel
                await parent_cog.db.upsert_guild_settings(guild_id, {
                    'update_channel_id': selected_channel_id
                })
                
                # Create or find the dedicated updates channel
                updates_channel = await parent_cog._ensure_updates_channel(interaction.guild)
                
                embed = discord.Embed(
                    title="✅ Update Channel Set",
                    description=f"Alerts will be sent to <#{selected_channel_id}>\n\n"
                               f"📊 Detailed reports will go to {updates_channel.mention if updates_channel else 'a dedicated channel'}",
                    color=discord.Color.green()
                )
                
                # Step 2: Channel tracking selection
                tracking_view = ChannelTrackingView(guild_id, parent_cog.db)
                
                embed.add_field(
                    name="Next: Select Channels to Track",
                    value="Choose which channels you want ServerPulse to monitor for analytics.",
                    inline=False
                )
                
                await select_interaction.response.edit_message(embed=embed, view=tracking_view)
        
        class UpdateChannelView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=300)
                self.add_item(UpdateChannelSelect())
        
        await interaction.followup.send(embed=setup_embed, view=UpdateChannelView(), ephemeral=True)
    
    async def _ensure_updates_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """Create or find the serverpulse-updates channel."""
        # Check if channel already exists
        for channel in guild.text_channels:
            if channel.name == "serverpulse-updates":
                return channel
        
        # Try to create the channel
        try:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(send_messages=False),
                guild.me: discord.PermissionOverwrite(send_messages=True, read_messages=True)
            }
            
            channel = await guild.create_text_channel(
                "serverpulse-updates",
                topic="📊 ServerPulse analytics, reports, and insights",
                overwrites=overwrites
            )
            
            # Send welcome message
            welcome_embed = discord.Embed(
                title="📊 ServerPulse Updates Channel",
                description=(
                    "Welcome to your dedicated ServerPulse channel!\n\n"
                    "**This channel will receive:**\n"
                    "📈 Daily and weekly server reports\n"
                    "🤖 AI-generated insights and recommendations\n"
                    "📊 Detailed analytics summaries\n\n"
                    "**For quick stats, use:**\n"
                    "`/topmessagers` - See most active users\n"
                    "`/leaderboard #channel` - Channel-specific stats"
                ),
                color=discord.Color.blue()
            )
            
            await channel.send(embed=welcome_embed)
            return channel
            
        except discord.Forbidden:
            self.logger.warning(f"Could not create serverpulse-updates channel in {guild.name}")
            return None
    
    @app_commands.command(name="set-update-channel", description="Set where ServerPulse sends alerts and updates")
    @app_commands.describe(channel="Channel for ServerPulse updates")
    @app_commands.default_permissions(administrator=True)
    async def set_update_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        """Set the update channel for alerts."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You need administrator permissions to change settings.",
                ephemeral=True
            )
            return
        
        # Check bot permissions
        if not channel.permissions_for(interaction.guild.me).send_messages:
            await interaction.response.send_message(
                f"❌ I don't have permission to send messages in {channel.mention}.",
                ephemeral=True
            )
            return
        
        await self.db.upsert_guild_settings(interaction.guild.id, {
            'update_channel_id': channel.id
        })
        
        embed = discord.Embed(
            title="✅ Update Channel Set",
            description=f"ServerPulse will now send alerts and updates to {channel.mention}",
            color=discord.Color.green()
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Send test message to the channel
        test_embed = discord.Embed(
            title="📊 ServerPulse Update Channel",
            description="This channel has been configured to receive ServerPulse alerts and reports.",
            color=discord.Color.blue()
        )
        
        try:
            await channel.send(embed=test_embed)
        except discord.Forbidden:
            pass
    
    @app_commands.command(name="add-collect-channel", description="Start tracking a channel for analytics")
    @app_commands.describe(channel="Channel to start tracking")
    @app_commands.default_permissions(administrator=True)
    async def add_collect_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        """Add a channel to tracking list."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You need administrator permissions to manage tracking.",
                ephemeral=True
            )
            return
        
        guild_settings = await self.db.get_guild_settings(interaction.guild.id)
        tracked_channels = guild_settings.get('tracked_channels', []) if guild_settings else []
        
        if channel.id in tracked_channels:
            await interaction.response.send_message(
                f"📊 {channel.mention} is already being tracked.",
                ephemeral=True
            )
            return
        
        tracked_channels.append(channel.id)
        
        await self.db.upsert_guild_settings(interaction.guild.id, {
            'tracked_channels': tracked_channels
        })
        
        embed = discord.Embed(
            title="✅ Channel Added to Tracking",
            description=f"Now monitoring {channel.mention} for analytics.",
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="What's tracked:",
            value=(
                "📝 Message count and frequency\n"
                "👥 User activity and engagement\n"
                "📊 Channel-specific statistics\n"
                "🔍 Activity patterns and trends"
            ),
            inline=False
        )
        
        embed.add_field(
            name="Privacy Note:",
            value="Only metadata is stored - no message content is saved.",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="remove-collect-channel", description="Stop tracking a channel")
    @app_commands.describe(channel="Channel to stop tracking")
    @app_commands.default_permissions(administrator=True)
    async def remove_collect_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        """Remove a channel from tracking list."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You need administrator permissions to manage tracking.",
                ephemeral=True
            )
            return
        
        guild_settings = await self.db.get_guild_settings(interaction.guild.id)
        tracked_channels = guild_settings.get('tracked_channels', []) if guild_settings else []
        
        if channel.id not in tracked_channels:
            await interaction.response.send_message(
                f"📊 {channel.mention} is not currently being tracked.",
                ephemeral=True
            )
            return
        
        tracked_channels.remove(channel.id)
        
        await self.db.upsert_guild_settings(interaction.guild.id, {
            'tracked_channels': tracked_channels
        })
        
        embed = discord.Embed(
            title="✅ Channel Removed from Tracking",
            description=f"No longer monitoring {channel.mention}.",
            color=discord.Color.orange()
        )
        
        embed.add_field(
            name="Historical Data",
            value="Previous analytics data will be retained according to your retention policy.",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="set-digest", description="Set report frequency")
    @app_commands.describe(frequency="How often to send AI reports")
    @app_commands.choices(frequency=[
        app_commands.Choice(name="None (Disable)", value="none"),
        app_commands.Choice(name="Daily", value="daily"),
        app_commands.Choice(name="Weekly", value="weekly")
    ])
    @app_commands.default_permissions(administrator=True)
    async def set_digest(self, interaction: discord.Interaction, frequency: str) -> None:
        """Set digest report frequency."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You need administrator permissions to change settings.",
                ephemeral=True
            )
            return
        
        await self.db.upsert_guild_settings(interaction.guild.id, {
            'digest_frequency': frequency
        })
        
        if frequency == "none":
            description = "AI reports have been disabled."
            color = discord.Color.orange()
        else:
            description = f"AI reports will be sent {frequency}."
            color = discord.Color.green()
        
        embed = discord.Embed(
            title="✅ Digest Frequency Updated",
            description=description,
            color=color
        )
        
        if frequency != "none":
            embed.add_field(
                name="AI Reports Include:",
                value=(
                    "📊 Activity summaries and trends\n"
                    "👥 Top contributors and engagement\n"
                    "💡 Community insights and suggestions\n"
                    "📈 Growth metrics and comparisons"
                ),
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="test-update", description="Send a test update to verify channel configuration")
    @app_commands.default_permissions(administrator=True)
    async def test_update(self, interaction: discord.Interaction) -> None:
        """Send a test update message."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You need administrator permissions to test updates.",
                ephemeral=True
            )
            return
        
        guild_settings = await self.db.get_guild_settings(interaction.guild.id)
        if not guild_settings or not guild_settings.get('update_channel_id'):
            await interaction.response.send_message(
                "❌ No update channel configured. Use `/set-update-channel` first.",
                ephemeral=True
            )
            return
        
        update_channel = self.bot.get_channel(guild_settings['update_channel_id'])
        if not update_channel:
            await interaction.response.send_message(
                "❌ Configured update channel not found. Please reconfigure with `/set-update-channel`.",
                ephemeral=True
            )
            return
        
        test_embed = discord.Embed(
            title="🧪 ServerPulse Test Update",
            description="This is a test message to verify your update channel is working correctly!",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        
        test_embed.add_field(
            name="Configuration Check ✅",
            value=(
                f"📢 Update Channel: {update_channel.mention}\n"
                f"🏗️ Requested by: {interaction.user.mention}\n"
                f"⚙️ Setup Status: {'Complete' if guild_settings.get('setup_completed') else 'In Progress'}"
            ),
            inline=False
        )
        
        try:
            await update_channel.send(embed=test_embed)
            await interaction.response.send_message(
                f"✅ Test update sent successfully to {update_channel.mention}!",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                f"❌ Cannot send messages to {update_channel.mention}. Check bot permissions.",
                ephemeral=True
            )


class ChannelTrackingView(discord.ui.View):
    """View for selecting channels to track."""
    
    def __init__(self, guild_id: int, db_manager):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.db = db_manager
    
    @discord.ui.button(label="Continue Setup", style=discord.ButtonStyle.green, emoji="➡️")
    async def continue_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Continue to final setup steps."""
        await self._complete_setup(interaction)
    
    async def _complete_setup(self, interaction: discord.Interaction):
        """Complete the setup process."""
        # Mark setup as completed
        await self.db.upsert_guild_settings(self.guild_id, {
            'setup_completed': True
        })
        
        final_embed = discord.Embed(
            title="🎉 ServerPulse Setup Complete!",
            description="Your server is now fully configured and ready to go!",
            color=discord.Color.green()
        )
        
        final_embed.add_field(
            name="🚀 What's Next?",
            value=(
                "• ServerPulse is now monitoring your selected channels\n"
                "• Real-time alerts are active\n"
                "• Use `/topmessagers` to see activity stats\n"
                "• Configure AI insights with `/ai-provider`"
            ),
            inline=False
        )
        
        final_embed.add_field(
            name="📚 Useful Commands",
            value=(
                "`/topmessagers` - View leaderboards\n"
                "`/leaderboard #channel` - Channel stats\n"
                "`/toggle-alert` - Manage alert types\n"
                "`/ai-provider` - Configure AI features"
            ),
            inline=False
        )
        
        await interaction.response.edit_message(embed=final_embed, view=None)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SetupCommands(bot))
