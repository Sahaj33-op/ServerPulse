"""MongoDB database manager for ServerPulse."""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError


class DatabaseManager:
    """MongoDB database manager."""
    
    def __init__(self, connection_uri: str):
        self.connection_uri = connection_uri
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None
        self.logger = logging.getLogger(__name__)
    
    async def connect(self) -> None:
        """Establish MongoDB connection."""
        try:
            self.client = AsyncIOMotorClient(self.connection_uri)
            
            # Test connection
            await self.client.admin.command('ping')
            self.db = self.client.serverpulse
            
            # Create indexes for optimal performance
            await self._create_indexes()
            
            self.logger.info("MongoDB connection established")
            
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            self.logger.error(f"MongoDB connection failed: {e}")
            raise
    
    async def close(self) -> None:
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            self.logger.info("MongoDB connection closed")
    
    async def _create_indexes(self) -> None:
        """Create database indexes for optimal performance."""
        # Guild settings collection
        await self.db.guild_settings.create_index("guild_id", unique=True)
        
        # Messages collection - compound indexes for analytics queries
        await self.db.messages.create_index([("guild_id", 1), ("timestamp", -1)])
        await self.db.messages.create_index([("guild_id", 1), ("channel_id", 1), ("timestamp", -1)])
        await self.db.messages.create_index([("guild_id", 1), ("user_id", 1), ("timestamp", -1)])
        
        # Member events collection
        await self.db.member_events.create_index([("guild_id", 1), ("timestamp", -1)])
        await self.db.member_events.create_index([("guild_id", 1), ("event_type", 1), ("timestamp", -1)])
        
        # Voice events collection
        await self.db.voice_events.create_index([("guild_id", 1), ("timestamp", -1)])
        
        # AI reports collection
        await self.db.ai_reports.create_index([("guild_id", 1), ("timestamp", -1)])
        
        self.logger.info("Database indexes created")
    
    # Guild Settings Management
    async def get_guild_settings(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """Get guild configuration settings."""
        return await self.db.guild_settings.find_one({"guild_id": guild_id})
    
    async def upsert_guild_settings(self, guild_id: int, settings: Dict[str, Any]) -> None:
        """Update or insert guild settings."""
        settings["guild_id"] = guild_id
        settings["updated_at"] = datetime.utcnow()
        
        await self.db.guild_settings.update_one(
            {"guild_id": guild_id},
            {"$set": settings},
            upsert=True
        )
    
    # Message Analytics
    async def record_message(self, guild_id: int, channel_id: int, user_id: int, 
                           message_length: int, has_attachment: bool = False) -> None:
        """Record message analytics data."""
        document = {
            "guild_id": guild_id,
            "channel_id": channel_id,
            "user_id": user_id,
            "timestamp": datetime.utcnow(),
            "message_length": message_length,
            "has_attachment": has_attachment
        }
        
        await self.db.messages.insert_one(document)
    
    async def get_message_stats(self, guild_id: int, period_hours: int = 24, 
                               channel_id: Optional[int] = None) -> Dict[str, Any]:
        """Get message statistics for a time period."""
        start_time = datetime.utcnow() - timedelta(hours=period_hours)
        
        pipeline = [
            {
                "$match": {
                    "guild_id": guild_id,
                    "timestamp": {"$gte": start_time}
                }
            }
        ]
        
        if channel_id:
            pipeline[0]["$match"]["channel_id"] = channel_id
        
        pipeline.extend([
            {
                "$group": {
                    "_id": None,
                    "total_messages": {"$sum": 1},
                    "unique_users": {"$addToSet": "$user_id"},
                    "total_length": {"$sum": "$message_length"},
                    "attachments": {"$sum": {"$cond": ["$has_attachment", 1, 0]}}
                }
            },
            {
                "$project": {
                    "total_messages": 1,
                    "unique_users": {"$size": "$unique_users"},
                    "avg_message_length": {"$divide": ["$total_length", "$total_messages"]},
                    "attachments": 1
                }
            }
        ])
        
        result = await self.db.messages.aggregate(pipeline).to_list(1)
        return result[0] if result else {"total_messages": 0, "unique_users": 0}
    
    async def get_top_messagers(self, guild_id: int, period_hours: int = 24, 
                               limit: int = 10, channel_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get top message senders for a time period."""
        start_time = datetime.utcnow() - timedelta(hours=period_hours)
        
        pipeline = [
            {
                "$match": {
                    "guild_id": guild_id,
                    "timestamp": {"$gte": start_time}
                }
            }
        ]
        
        if channel_id:
            pipeline[0]["$match"]["channel_id"] = channel_id
        
        pipeline.extend([
            {
                "$group": {
                    "_id": "$user_id",
                    "message_count": {"$sum": 1},
                    "total_length": {"$sum": "$message_length"}
                }
            },
            {
                "$sort": {"message_count": -1}
            },
            {
                "$limit": limit
            },
            {
                "$project": {
                    "user_id": "$_id",
                    "message_count": 1,
                    "avg_length": {"$divide": ["$total_length", "$message_count"]},
                    "_id": 0
                }
            }
        ])
        
        return await self.db.messages.aggregate(pipeline).to_list(limit)
    
    # Member Events
    async def record_member_event(self, guild_id: int, user_id: int, event_type: str) -> None:
        """Record member join/leave events."""
        document = {
            "guild_id": guild_id,
            "user_id": user_id,
            "event_type": event_type,  # 'join' or 'leave'
            "timestamp": datetime.utcnow()
        }
        
        await self.db.member_events.insert_one(document)
    
    async def get_member_activity(self, guild_id: int, period_hours: int = 24) -> Dict[str, int]:
        """Get member join/leave activity for time period."""
        start_time = datetime.utcnow() - timedelta(hours=period_hours)
        
        pipeline = [
            {
                "$match": {
                    "guild_id": guild_id,
                    "timestamp": {"$gte": start_time}
                }
            },
            {
                "$group": {
                    "_id": "$event_type",
                    "count": {"$sum": 1}
                }
            }
        ]
        
        results = await self.db.member_events.aggregate(pipeline).to_list(10)
        activity = {"joins": 0, "leaves": 0}
        
        for result in results:
            if result["_id"] == "join":
                activity["joins"] = result["count"]
            elif result["_id"] == "leave":
                activity["leaves"] = result["count"]
        
        return activity
    
    # Voice Events
    async def record_voice_event(self, guild_id: int, user_id: int, channel_id: Optional[int], 
                               event_type: str) -> None:
        """Record voice channel events."""
        document = {
            "guild_id": guild_id,
            "user_id": user_id,
            "channel_id": channel_id,
            "event_type": event_type,  # 'join', 'leave', 'move'
            "timestamp": datetime.utcnow()
        }
        
        await self.db.voice_events.insert_one(document)
    
    # AI Reports
    async def save_ai_report(self, guild_id: int, report_type: str, content: str, 
                           metadata: Optional[Dict] = None) -> None:
        """Save AI-generated report."""
        document = {
            "guild_id": guild_id,
            "report_type": report_type,
            "content": content,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow()
        }
        
        await self.db.ai_reports.insert_one(document)
    
    # Data Cleanup
    async def cleanup_old_data(self, retention_days: int) -> Dict[str, int]:
        """Remove data older than retention period."""
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        
        cleanup_stats = {}
        
        # Cleanup collections with timestamp field
        collections = ['messages', 'member_events', 'voice_events', 'ai_reports']
        
        for collection_name in collections:
            collection = getattr(self.db, collection_name)
            result = await collection.delete_many({"timestamp": {"$lt": cutoff_date}})
            cleanup_stats[collection_name] = result.deleted_count
        
        return cleanup_stats
