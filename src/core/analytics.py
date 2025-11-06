"""Analytics manager for ServerPulse."""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

from src.database.mongodb import DatabaseManager
from src.database.redis_client import RedisManager
from src.utils.helpers import (
    get_period_hours, calculate_activity_score, detect_activity_anomaly,
    format_number, get_time_bucket
)
from src.utils.logger import LoggerMixin


class AnalyticsManager(LoggerMixin):
    """Manages server analytics and caching."""
    
    def __init__(self, db_manager: DatabaseManager, redis_manager: RedisManager):
        self.db = db_manager
        self.redis = redis_manager
    
    async def record_message(self, guild_id: int, channel_id: int, user_id: int, 
                           message_length: int, has_attachment: bool = False) -> None:
        """Record message analytics with caching optimization."""
        # Record in database
        await self.db.record_message(
            guild_id, channel_id, user_id, message_length, has_attachment
        )
        
        # Update real-time counters in cache
        current_hour = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        
        # Increment hourly counters
        await asyncio.gather(
            self.redis.increment(f"msg_count:{guild_id}:{current_hour.isoformat()}", 1, ttl=3600*48),
            self.redis.increment(f"user_activity:{guild_id}:{user_id}:{current_hour.isoformat()}", 1, ttl=3600*48),
            self.redis.increment(f"channel_activity:{guild_id}:{channel_id}:{current_hour.isoformat()}", 1, ttl=3600*48)
        )
        
        # Invalidate relevant cache keys
        await self._invalidate_stats_cache(guild_id, channel_id)
    
    async def get_leaderboard(self, guild_id: int, period: str = '24h', 
                            channel_id: Optional[int] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Get cached or fresh leaderboard data."""
        cache_key = await self.redis.get_leaderboard_key(guild_id, period, channel_id)
        
        # Try cache first
        cached_data = await self.redis.get(cache_key)
        if cached_data:
            return cached_data
        
        # Generate fresh data
        period_hours = get_period_hours(period)
        leaderboard = await self.db.get_top_messagers(
            guild_id, period_hours, limit, channel_id
        )
        
        # Cache for 5 minutes (configurable via settings)
        from src.config import settings
        await self.redis.set(cache_key, leaderboard, ttl=settings.cache_ttl_leaderboard)
        
        return leaderboard
    
    async def get_server_stats(self, guild_id: int, period: str = '24h', 
                             channel_id: Optional[int] = None) -> Dict[str, Any]:
        """Get comprehensive server statistics with caching."""
        cache_key = await self.redis.get_stats_key(guild_id, f"{period}_{channel_id or 'all'}")
        
        # Try cache first
        cached_stats = await self.redis.get(cache_key)
        if cached_stats:
            return cached_stats
        
        # Generate fresh stats
        period_hours = get_period_hours(period)
        
        # Get message stats
        message_stats = await self.db.get_message_stats(guild_id, period_hours, channel_id)
        
        # Get member activity
        member_activity = await self.db.get_member_activity(guild_id, period_hours)
        
        # Calculate activity score
        activity_score = calculate_activity_score(
            message_stats.get('total_messages', 0),
            message_stats.get('unique_users', 0),
            message_stats.get('avg_message_length', 0)
        )
        
        # Get historical comparison for anomaly detection
        historical_avg = await self._get_historical_average(
            guild_id, period_hours, channel_id
        )
        
        anomaly = detect_activity_anomaly(
            message_stats.get('total_messages', 0),
            historical_avg
        )
        
        stats = {
            'period': period,
            'channel_id': channel_id,
            'message_stats': message_stats,
            'member_activity': member_activity,
            'activity_score': activity_score,
            'anomaly': anomaly,
            'historical_avg': historical_avg,
            'generated_at': datetime.utcnow().isoformat()
        }
        
        # Cache for 10 minutes (configurable via settings)
        from src.config import settings
        await self.redis.set(cache_key, stats, ttl=settings.cache_ttl_stats)
        
        return stats
    
    async def get_activity_timeline(self, guild_id: int, period_hours: int = 24, 
                                  bucket_minutes: int = 60, 
                                  channel_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get activity timeline data for visualizations."""
        start_time = datetime.utcnow() - timedelta(hours=period_hours)
        
        # Generate time buckets
        timeline = []
        current_time = start_time
        
        while current_time <= datetime.utcnow():
            bucket_start = get_time_bucket(current_time, bucket_minutes)
            bucket_end = bucket_start + timedelta(minutes=bucket_minutes)
            
            # Get cached or calculate bucket stats
            bucket_key = f"timeline:{guild_id}:{bucket_start.isoformat()}:{channel_id or 'all'}"
            bucket_stats = await self.redis.get(bucket_key)
            
            if not bucket_stats:
                bucket_stats = await self._calculate_bucket_stats(
                    guild_id, bucket_start, bucket_end, channel_id
                )
                await self.redis.set(bucket_key, bucket_stats, ttl=3600)  # Cache 1 hour
            
            timeline.append({
                'timestamp': bucket_start.isoformat(),
                'stats': bucket_stats
            })
            
            current_time += timedelta(minutes=bucket_minutes)
        
        return timeline
    
    async def get_channel_comparison(self, guild_id: int, period: str = '24h') -> List[Dict[str, Any]]:
        """Compare activity across different channels."""
        period_hours = get_period_hours(period)
        
        # Get guild settings to find tracked channels
        guild_settings = await self.db.get_guild_settings(guild_id)
        if not guild_settings:
            return []
        
        tracked_channels = guild_settings.get('tracked_channels', [])
        
        channel_stats = []
        
        for channel_id in tracked_channels:
            stats = await self.get_server_stats(guild_id, period, channel_id)
            channel_stats.append({
                'channel_id': channel_id,
                'stats': stats['message_stats'],
                'activity_score': stats['activity_score']
            })
        
        # Sort by activity score
        channel_stats.sort(key=lambda x: x['activity_score'], reverse=True)
        
        return channel_stats
    
    async def get_user_engagement_stats(self, guild_id: int, user_id: int, 
                                      period: str = '24h') -> Dict[str, Any]:
        """Get detailed engagement stats for a specific user."""
        period_hours = get_period_hours(period)
        start_time = datetime.utcnow() - timedelta(hours=period_hours)
        
        # MongoDB aggregation for user-specific stats
        pipeline = [
            {
                "$match": {
                    "guild_id": guild_id,
                    "user_id": user_id,
                    "timestamp": {"$gte": start_time}
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_messages": {"$sum": 1},
                    "total_length": {"$sum": "$message_length"},
                    "channels_used": {"$addToSet": "$channel_id"},
                    "hourly_distribution": {
                        "$push": {
                            "hour": {"$hour": "$timestamp"},
                            "count": 1
                        }
                    }
                }
            },
            {
                "$project": {
                    "total_messages": 1,
                    "avg_message_length": {"$divide": ["$total_length", "$total_messages"]},
                    "channels_count": {"$size": "$channels_used"},
                    "channels_used": 1,
                    "hourly_distribution": 1
                }
            }
        ]
        
        result = await self.db.db.messages.aggregate(pipeline).to_list(1)
        
        if not result:
            return {
                'user_id': user_id,
                'total_messages': 0,
                'avg_message_length': 0,
                'channels_count': 0,
                'channels_used': [],
                'hourly_distribution': []
            }
        
        return result[0]
    
    async def _get_historical_average(self, guild_id: int, period_hours: int, 
                                    channel_id: Optional[int] = None) -> float:
        """Get historical average for anomaly detection."""
        # Calculate average for the same time period over the last 7 days
        historical_periods = []
        
        for days_back in range(1, 8):  # 7 historical periods
            start_time = datetime.utcnow() - timedelta(days=days_back, hours=period_hours)
            end_time = datetime.utcnow() - timedelta(days=days_back)
            
            pipeline = [
                {
                    "$match": {
                        "guild_id": guild_id,
                        "timestamp": {"$gte": start_time, "$lt": end_time}
                    }
                }
            ]
            
            if channel_id:
                pipeline[0]["$match"]["channel_id"] = channel_id
            
            pipeline.append({
                "$count": "message_count"
            })
            
            result = await self.db.db.messages.aggregate(pipeline).to_list(1)
            count = result[0]['message_count'] if result else 0
            historical_periods.append(count)
        
        return sum(historical_periods) / len(historical_periods) if historical_periods else 0
    
    async def _calculate_bucket_stats(self, guild_id: int, start_time: datetime, 
                                    end_time: datetime, 
                                    channel_id: Optional[int] = None) -> Dict[str, Any]:
        """Calculate stats for a specific time bucket."""
        pipeline = [
            {
                "$match": {
                    "guild_id": guild_id,
                    "timestamp": {"$gte": start_time, "$lt": end_time}
                }
            }
        ]
        
        if channel_id:
            pipeline[0]["$match"]["channel_id"] = channel_id
        
        pipeline.extend([
            {
                "$group": {
                    "_id": None,
                    "message_count": {"$sum": 1},
                    "unique_users": {"$addToSet": "$user_id"}
                }
            },
            {
                "$project": {
                    "message_count": 1,
                    "unique_users": {"$size": "$unique_users"}
                }
            }
        ])
        
        result = await self.db.db.messages.aggregate(pipeline).to_list(1)
        
        if result:
            return {
                'message_count': result[0]['message_count'],
                'unique_users': result[0]['unique_users']
            }
        else:
            return {'message_count': 0, 'unique_users': 0}
    
    async def _invalidate_stats_cache(self, guild_id: int, channel_id: int) -> None:
        """Invalidate relevant cache keys when new data is recorded."""
        # Patterns to invalidate
        patterns = [
            f"leaderboard:{guild_id}:*",
            f"stats:{guild_id}:*",
            f"timeline:{guild_id}:*"
        ]
        
        for pattern in patterns:
            try:
                keys = await self.redis.client.keys(pattern)
                if keys:
                    await self.redis.client.delete(*keys)
            except Exception as e:
                self.logger.warning(f"Failed to invalidate cache pattern {pattern}: {e}")
