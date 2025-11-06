#!/usr/bin/env python3
"""Data cleanup utility for ServerPulse."""

import asyncio
import argparse
from datetime import datetime, timedelta
from typing import Dict, Any

from src.config import settings
from src.database.mongodb import DatabaseManager
from src.database.redis_client import RedisManager
from src.utils.logger import setup_logging
import logging


async def cleanup_old_data(retention_days: int, dry_run: bool = False) -> Dict[str, int]:
    """Clean up old data based on retention policy."""
    logger = logging.getLogger(__name__)
    
    # Initialize database connection
    db_manager = DatabaseManager(settings.mongodb_uri)
    await db_manager.connect()
    
    try:
        if dry_run:
            logger.info(f"DRY RUN: Would clean up data older than {retention_days} days")
            
            # Count documents that would be deleted
            cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
            
            collections = ['messages', 'member_events', 'voice_events', 'ai_reports']
            stats = {}
            
            for collection_name in collections:
                collection = getattr(db_manager.db, collection_name)
                count = await collection.count_documents({"timestamp": {"$lt": cutoff_date}})
                stats[collection_name] = count
                logger.info(f"Would delete {count} documents from {collection_name}")
            
            return stats
        else:
            logger.info(f"Cleaning up data older than {retention_days} days...")
            stats = await db_manager.cleanup_old_data(retention_days)
            
            total_deleted = sum(stats.values())
            logger.info(f"Cleanup completed: {total_deleted} total documents deleted")
            
            return stats
    
    finally:
        await db_manager.close()


async def clear_cache(guild_id: int = None) -> None:
    """Clear Redis cache."""
    logger = logging.getLogger(__name__)
    
    redis_manager = RedisManager(settings.redis_url)
    await redis_manager.connect()
    
    try:
        if guild_id:
            logger.info(f"Clearing cache for guild {guild_id}...")
            count = await redis_manager.clear_guild_cache(guild_id)
            logger.info(f"Cleared {count} cache entries for guild {guild_id}")
        else:
            logger.info("Clearing all cache entries...")
            await redis_manager.client.flushall()
            logger.info("All cache cleared")
    
    finally:
        await redis_manager.close()


async def database_stats() -> Dict[str, Any]:
    """Get database statistics."""
    logger = logging.getLogger(__name__)
    
    db_manager = DatabaseManager(settings.mongodb_uri)
    await db_manager.connect()
    
    try:
        stats = {}
        collections = ['guild_settings', 'messages', 'member_events', 'voice_events', 'ai_reports']
        
        for collection_name in collections:
            collection = getattr(db_manager.db, collection_name)
            count = await collection.count_documents({})
            stats[collection_name] = count
        
        # Get database size
        db_stats = await db_manager.db.command("dbStats")
        stats['database_size_mb'] = round(db_stats['dataSize'] / (1024 * 1024), 2)
        stats['index_size_mb'] = round(db_stats['indexSize'] / (1024 * 1024), 2)
        
        logger.info("Database Statistics:")
        for key, value in stats.items():
            logger.info(f"  {key}: {value}")
        
        return stats
    
    finally:
        await db_manager.close()


async def optimize_database() -> None:
    """Optimize database indexes and collections."""
    logger = logging.getLogger(__name__)
    
    db_manager = DatabaseManager(settings.mongodb_uri)
    await db_manager.connect()
    
    try:
        logger.info("Optimizing database...")
        
        # Recreate indexes
        await db_manager._create_indexes()
        logger.info("Indexes recreated")
        
        # Compact collections (if supported)
        collections = ['messages', 'member_events', 'voice_events', 'ai_reports']
        
        for collection_name in collections:
            try:
                await db_manager.db.command("compact", collection_name)
                logger.info(f"Compacted {collection_name}")
            except Exception as e:
                logger.warning(f"Could not compact {collection_name}: {e}")
        
        logger.info("Database optimization completed")
    
    finally:
        await db_manager.close()


async def main():
    """Main cleanup utility."""
    parser = argparse.ArgumentParser(description="ServerPulse Data Cleanup Utility")
    parser.add_argument('action', choices=['cleanup', 'clear-cache', 'stats', 'optimize'],
                       help='Action to perform')
    parser.add_argument('--retention-days', type=int, default=settings.data_retention_days,
                       help='Data retention period in days')
    parser.add_argument('--guild-id', type=int,
                       help='Guild ID for cache clearing (optional)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be deleted without actually deleting')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = 'DEBUG' if args.verbose else 'INFO'
    setup_logging(log_level, args.verbose)
    
    logger = logging.getLogger(__name__)
    logger.info(f"Starting {args.action} operation...")
    
    try:
        if args.action == 'cleanup':
            stats = await cleanup_old_data(args.retention_days, args.dry_run)
            
            print("\n📊 Cleanup Results:")
            for collection, count in stats.items():
                print(f"  {collection}: {count} documents")
            
            if args.dry_run:
                print("\n🔍 This was a dry run. Use without --dry-run to actually delete data.")
        
        elif args.action == 'clear-cache':
            await clear_cache(args.guild_id)
            print("\n✅ Cache cleared successfully")
        
        elif args.action == 'stats':
            stats = await database_stats()
            
            print("\n📊 Database Statistics:")
            print(f"  Database Size: {stats['database_size_mb']} MB")
            print(f"  Index Size: {stats['index_size_mb']} MB")
            print("\n📋 Document Counts:")
            for collection, count in stats.items():
                if not collection.endswith('_mb'):
                    print(f"  {collection}: {count:,} documents")
        
        elif args.action == 'optimize':
            await optimize_database()
            print("\n✅ Database optimization completed")
    
    except Exception as e:
        logger.error(f"Error during {args.action}: {e}", exc_info=args.verbose)
        print(f"\n❌ Error: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    exit(asyncio.run(main()))
