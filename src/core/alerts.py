"""Alert system for ServerPulse."""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import discord
from discord.ext import commands

from src.database.mongodb import DatabaseManager
from src.database.redis_client import RedisManager
from src.utils.helpers import format_number, get_alert_emoji
from src.utils.logger import LoggerMixin


class AlertManager(LoggerMixin):
    """Manages real-time alerts and notifications."""
    
    def __init__(self, db_manager: DatabaseManager, redis_manager: RedisManager, 
                 bot: commands.Bot):
        self.db = db_manager
        self.redis = redis_manager
        self.bot = bot
        
        # Alert cooldowns (in seconds)
        self.alert_cooldowns = {
            'join_raid': 300,      # 5 minutes
            'activity_drop': 1800,  # 30 minutes
            'activity_spike': 1800, # 30 minutes
            'mass_delete': 600,     # 10 minutes
            'voice_surge': 900      # 15 minutes
        }
    
    async def check_join_raid_alert(self, guild_id: int) -> None:
        """Check for potential join raid and trigger alert if needed."""
        # Check if alert is on cooldown
        if await self.redis.is_alert_on_cooldown(guild_id, 'join_raid'):
            return
        
        # Get guild settings
        guild_settings = await self.db.get_guild_settings(guild_id)
        if not guild_settings or not guild_settings.get('alerts_enabled', {}).get('join_raid', True):
            return
        
        threshold = guild_settings.get('alert_thresholds', {}).get('join_raid', 10)
        
        # Count joins in the last 60 seconds
        recent_joins = await self._count_recent_member_events(guild_id, 'join', 1)
        
        if recent_joins >= threshold:
            await self._trigger_join_raid_alert(guild_id, recent_joins, threshold)
            await self.redis.set_alert_cooldown(guild_id, 'join_raid', self.alert_cooldowns['join_raid'])
    
    async def check_message_alerts(self, guild_id: int, channel_id: int) -> None:
        """Check for message-related alerts (activity spikes/drops)."""
        # Get current hour's message count
        current_hour = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        current_count_key = f"msg_count:{guild_id}:{current_hour.isoformat()}"
        current_count = int(await self.redis.get(current_count_key, 0))
        
        # Skip if too few messages to analyze
        if current_count < 5:
            return
        
        # Get historical average
        historical_avg = await self._get_hourly_historical_average(guild_id)
        
        if historical_avg == 0:
            return  # Not enough historical data
        
        # Calculate percentage change
        change_percent = ((current_count - historical_avg) / historical_avg) * 100
        
        guild_settings = await self.db.get_guild_settings(guild_id)
        if not guild_settings:
            return
        
        threshold = guild_settings.get('alert_thresholds', {}).get('activity_drop', 50)
        
        # Activity drop alert
        if (change_percent <= -threshold and 
            guild_settings.get('alerts_enabled', {}).get('activity_drop', True) and
            not await self.redis.is_alert_on_cooldown(guild_id, 'activity_drop')):
            
            await self._trigger_activity_drop_alert(guild_id, int(abs(change_percent)))
            await self.redis.set_alert_cooldown(guild_id, 'activity_drop', self.alert_cooldowns['activity_drop'])
        
        # Activity spike alert
        elif (change_percent >= threshold and 
              not await self.redis.is_alert_on_cooldown(guild_id, 'activity_spike')):
            
            await self._trigger_activity_spike_alert(guild_id, int(change_percent))
            await self.redis.set_alert_cooldown(guild_id, 'activity_spike', self.alert_cooldowns['activity_spike'])
    
    async def check_mass_delete_alert(self, guild_id: int, channel_id: int) -> None:
        """Check for mass message deletion."""
        # Track deletions in a rolling window
        delete_key = f"deletes:{guild_id}:{channel_id}"
        current_count = await self.redis.increment(delete_key, 1, ttl=30)  # 30 second window
        
        guild_settings = await self.db.get_guild_settings(guild_id)
        if not guild_settings or not guild_settings.get('alerts_enabled', {}).get('mass_delete', True):
            return
        
        threshold = guild_settings.get('alert_thresholds', {}).get('mass_delete', 5)
        
        if (current_count >= threshold and 
            not await self.redis.is_alert_on_cooldown(guild_id, 'mass_delete')):
            
            await self.trigger_mass_delete_alert(guild_id, channel_id, current_count)
            await self.redis.set_alert_cooldown(guild_id, 'mass_delete', self.alert_cooldowns['mass_delete'])
    
    async def trigger_mass_delete_alert(self, guild_id: int, channel_id: int, count: int) -> None:
        """Trigger mass deletion alert immediately (for bulk deletes)."""
        guild_settings = await self.db.get_guild_settings(guild_id)
        if not guild_settings or not guild_settings.get('alerts_enabled', {}).get('mass_delete', True):
            return
        
        if await self.redis.is_alert_on_cooldown(guild_id, 'mass_delete'):
            return
        
        await self._trigger_mass_delete_alert(guild_id, channel_id, count)
        await self.redis.set_alert_cooldown(guild_id, 'mass_delete', self.alert_cooldowns['mass_delete'])
    
    async def check_voice_surge_alert(self, guild_id: int) -> None:
        """Check for voice channel activity surge."""
        if await self.redis.is_alert_on_cooldown(guild_id, 'voice_surge'):
            return
        
        guild_settings = await self.db.get_guild_settings(guild_id)
        if not guild_settings or not guild_settings.get('alerts_enabled', {}).get('voice_surge', True):
            return
        
        # Get current voice channel activity
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        
        current_voice_users = sum(len(vc.members) for vc in guild.voice_channels)
        
        # Get historical average voice activity
        historical_avg = await self._get_voice_historical_average(guild_id)
        
        threshold_multiplier = guild_settings.get('alert_thresholds', {}).get('voice_surge', 3)
        
        if current_voice_users >= (historical_avg * threshold_multiplier) and current_voice_users >= 5:
            await self._trigger_voice_surge_alert(guild_id, current_voice_users, int(historical_avg))
            await self.redis.set_alert_cooldown(guild_id, 'voice_surge', self.alert_cooldowns['voice_surge'])
    
    async def _trigger_join_raid_alert(self, guild_id: int, join_count: int, threshold: int) -> None:
        """Send join raid alert."""
        embed = discord.Embed(
            title=f"{get_alert_emoji('join_raid')} Join Raid Detected",
            description=f"**{format_number(join_count)} members** joined in the last minute!\n\n"
                       f"This exceeds the threshold of {threshold} joins.",
            color=discord.Color.orange(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="Recommended Actions",
            value="• Check server security settings\n"
                  "• Review recent invites\n"
                  "• Consider temporary invite restrictions",
            inline=False
        )
        
        await self._send_alert(guild_id, embed)
    
    async def _trigger_activity_drop_alert(self, guild_id: int, drop_percent: int) -> None:
        """Send activity drop alert."""
        embed = discord.Embed(
            title=f"{get_alert_emoji('activity_drop')} Activity Drop Detected",
            description=f"Server activity has **decreased by {drop_percent}%** compared to usual.",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="Possible Causes",
            value="• Server outage or issues\n"
                  "• Community event ended\n"
                  "• Time zone differences\n"
                  "• External factors",
            inline=False
        )
        
        await self._send_alert(guild_id, embed)
    
    async def _trigger_activity_spike_alert(self, guild_id: int, spike_percent: int) -> None:
        """Send activity spike alert."""
        embed = discord.Embed(
            title=f"{get_alert_emoji('activity_spike')} Activity Spike Detected",
            description=f"Server activity has **increased by {spike_percent}%** compared to usual!",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="Great News!",
            value="• Increased community engagement\n"
                  "• Successful event or announcement\n"
                  "• New member influx\n"
                  "• Trending topic discussion",
            inline=False
        )
        
        await self._send_alert(guild_id, embed)
    
    async def _trigger_mass_delete_alert(self, guild_id: int, channel_id: int, count: int) -> None:
        """Send mass deletion alert."""
        channel = self.bot.get_channel(channel_id)
        channel_mention = channel.mention if channel else f"<#{channel_id}>"
        
        embed = discord.Embed(
            title=f"{get_alert_emoji('mass_delete')} Mass Deletion Detected",
            description=f"**{format_number(count)} messages** were deleted rapidly in {channel_mention}",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="Recommended Actions",
            value="• Check moderation logs\n"
                  "• Verify staff activity\n"
                  "• Review channel permissions\n"
                  "• Investigate potential spam cleanup",
            inline=False
        )
        
        await self._send_alert(guild_id, embed)
    
    async def _trigger_voice_surge_alert(self, guild_id: int, current_count: int, avg_count: int) -> None:
        """Send voice activity surge alert."""
        embed = discord.Embed(
            title=f"{get_alert_emoji('voice_surge')} Voice Activity Surge",
            description=f"**{format_number(current_count)} users** are currently in voice channels!\n\n"
                       f"This is significantly higher than the usual {format_number(avg_count)} users.",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="Community Boost!",
            value="• High voice engagement\n"
                  "• Active community events\n"
                  "• Gaming sessions or meetings\n"
                  "• Great time for announcements",
            inline=False
        )
        
        await self._send_alert(guild_id, embed)
    
    async def _send_alert(self, guild_id: int, embed: discord.Embed) -> None:
        """Send alert to configured update channel."""
        guild_settings = await self.db.get_guild_settings(guild_id)
        if not guild_settings:
            return
        
        update_channel_id = guild_settings.get('update_channel_id')
        if not update_channel_id:
            return
        
        channel = self.bot.get_channel(update_channel_id)
        if not channel:
            return
        
        try:
            await channel.send(embed=embed)
            self.logger.info(f"Alert sent to {guild_id} in channel {update_channel_id}")
        except discord.Forbidden:
            self.logger.warning(f"Cannot send alert to {guild_id} - no permissions")
        except Exception as e:
            self.logger.error(f"Failed to send alert to {guild_id}: {e}")
    
    async def _count_recent_member_events(self, guild_id: int, event_type: str, minutes: int) -> int:
        """Count recent member events within time window."""
        start_time = datetime.utcnow() - timedelta(minutes=minutes)
        
        count = await self.db.db.member_events.count_documents({
            "guild_id": guild_id,
            "event_type": event_type,
            "timestamp": {"$gte": start_time}
        })
        
        return count
    
    async def _get_hourly_historical_average(self, guild_id: int, hours_back: int = 168) -> float:
        """Get average hourly message count over past week."""
        start_time = datetime.utcnow() - timedelta(hours=hours_back)
        
        pipeline = [
            {
                "$match": {
                    "guild_id": guild_id,
                    "timestamp": {"$gte": start_time}
                }
            },
            {
                "$group": {
                    "_id": {
                        "year": {"$year": "$timestamp"},
                        "month": {"$month": "$timestamp"},
                        "day": {"$dayOfMonth": "$timestamp"},
                        "hour": {"$hour": "$timestamp"}
                    },
                    "hourly_count": {"$sum": 1}
                }
            },
            {
                "$group": {
                    "_id": None,
                    "avg_hourly": {"$avg": "$hourly_count"}
                }
            }
        ]
        
        result = await self.db.db.messages.aggregate(pipeline).to_list(1)
        return result[0]['avg_hourly'] if result else 0
    
    async def _get_voice_historical_average(self, guild_id: int) -> float:
        """Get historical average voice channel activity."""
        # Simple implementation - can be enhanced with more sophisticated tracking
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return 0
        
        # Use current member count as a baseline estimate
        # In a full implementation, you'd track historical voice data
        return max(1, guild.member_count * 0.05)  # Assume 5% average voice activity
