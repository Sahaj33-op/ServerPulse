"""Main entry point for ServerPulse bot."""

import asyncio
import logging
import signal
import sys
from pathlib import Path

import discord
from discord.ext import commands

from src.config import settings
from src.utils.logger import setup_logging
from src.database.mongodb import DatabaseManager
from src.database.redis_client import RedisManager
from src.core.bot import ServerPulseBot


async def main():
    """Main application entry point."""
    # Setup logging
    setup_logging(settings.log_level.value, settings.debug)
    logger = logging.getLogger(__name__)
    
    logger.info("Starting ServerPulse Bot v1.0.0")
    
    # Setup graceful shutdown
    shutdown_event = asyncio.Event()
    
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        shutdown_event.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Initialize database connections
        logger.info("Initializing database connections...")
        db_manager = DatabaseManager(settings.mongodb_uri)
        redis_manager = RedisManager(settings.redis_url)
        
        await db_manager.connect()
        await redis_manager.connect()
        
        logger.info("Database connections established")
        
        # Create bot instance
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.presences = True
        intents.voice_states = True
        
        bot = ServerPulseBot(
            command_prefix="!",  # Slash commands primarily used
            intents=intents,
            db_manager=db_manager,
            redis_manager=redis_manager,
            help_command=None
        )
        
        # Start bot with graceful shutdown handling
        bot_task = asyncio.create_task(bot.start(settings.bot_token))
        shutdown_task = asyncio.create_task(shutdown_event.wait())
        
        done, pending = await asyncio.wait(
            [bot_task, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # Cancel pending tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        # Close bot gracefully
        if not bot.is_closed():
            await bot.close()
        
        logger.info("ServerPulse Bot shutdown complete")
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    
    finally:
        # Cleanup database connections
        try:
            await db_manager.close()
            await redis_manager.close()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown complete.")
