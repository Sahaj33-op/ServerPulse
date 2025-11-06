"""Redis client manager for ServerPulse caching."""

import json
import logging
from typing import Any, Optional, Union
import redis.asyncio as redis
from redis.exceptions import ConnectionError, TimeoutError


class RedisManager:
    """Redis cache manager."""
    
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.client: Optional[redis.Redis] = None
        self.logger = logging.getLogger(__name__)
    
    async def connect(self) -> None:
        """Establish Redis connection."""
        try:
            self.client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_keepalive=True,
                socket_keepalive_options={}
            )
            
            # Test connection
            await self.client.ping()
            self.logger.info("Redis connection established")
            
        except (ConnectionError, TimeoutError) as e:
            self.logger.error(f"Redis connection failed: {e}")
            raise
    
    async def close(self) -> None:
        """Close Redis connection."""
        if self.client:
            await self.client.close()
            self.logger.info("Redis connection closed")
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set a cache value with optional TTL."""
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            
            if ttl:
                return await self.client.setex(key, ttl, value)
            else:
                return await self.client.set(key, value)
                
        except Exception as e:
            self.logger.error(f"Redis SET error for key {key}: {e}")
            return False
    
    async def get(self, key: str, default: Any = None) -> Any:
        """Get a cache value."""
        try:
            value = await self.client.get(key)
            if value is None:
                return default
            
            # Try to parse as JSON
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
                
        except Exception as e:
            self.logger.error(f"Redis GET error for key {key}: {e}")
            return default
    
    async def delete(self, key: str) -> bool:
        """Delete a cache key."""
        try:
            return bool(await self.client.delete(key))
        except Exception as e:
            self.logger.error(f"Redis DELETE error for key {key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        try:
            return bool(await self.client.exists(key))
        except Exception as e:
            self.logger.error(f"Redis EXISTS error for key {key}: {e}")
            return False
    
    async def increment(self, key: str, amount: int = 1, ttl: Optional[int] = None) -> int:
        """Increment a counter key."""
        try:
            pipeline = self.client.pipeline()
            pipeline.incrby(key, amount)
            
            if ttl:
                pipeline.expire(key, ttl)
            
            results = await pipeline.execute()
            return results[0]
            
        except Exception as e:
            self.logger.error(f"Redis INCREMENT error for key {key}: {e}")
            return 0
    
    async def get_leaderboard_key(self, guild_id: int, period: str, channel_id: Optional[int] = None) -> str:
        """Generate standardized leaderboard cache key."""
        if channel_id:
            return f"leaderboard:{guild_id}:{channel_id}:{period}"
        return f"leaderboard:{guild_id}:all:{period}"
    
    async def get_stats_key(self, guild_id: int, period: str) -> str:
        """Generate standardized stats cache key."""
        return f"stats:{guild_id}:{period}"
    
    async def clear_guild_cache(self, guild_id: int) -> int:
        """Clear all cached data for a guild."""
        try:
            pattern = f"*:{guild_id}:*"
            keys = await self.client.keys(pattern)
            
            if keys:
                return await self.client.delete(*keys)
            return 0
            
        except Exception as e:
            self.logger.error(f"Redis CLEAR GUILD CACHE error for guild {guild_id}: {e}")
            return 0
    
    async def get_alert_cooldown_key(self, guild_id: int, alert_type: str) -> str:
        """Generate alert cooldown cache key."""
        return f"alert_cooldown:{guild_id}:{alert_type}"
    
    async def set_alert_cooldown(self, guild_id: int, alert_type: str, cooldown_seconds: int) -> bool:
        """Set alert cooldown to prevent spam."""
        key = await self.get_alert_cooldown_key(guild_id, alert_type)
        return await self.set(key, "1", ttl=cooldown_seconds)
    
    async def is_alert_on_cooldown(self, guild_id: int, alert_type: str) -> bool:
        """Check if alert type is on cooldown."""
        key = await self.get_alert_cooldown_key(guild_id, alert_type)
        return await self.exists(key)
