"""Configuration management for ServerPulse bot."""

import os
from typing import Optional, List
from pydantic import Field
from pydantic_settings import BaseSettings
from enum import Enum


class AIProvider(str, Enum):
    """Supported AI providers."""
    OPENROUTER = "openrouter"
    GEMINI = "gemini"
    OPENAI = "openai"
    GROK = "grok"


class LogLevel(str, Enum):
    """Logging levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Settings(BaseSettings):
    """Application settings."""
    
    # Discord Bot Configuration
    bot_token: str = Field(..., env="BOT_TOKEN")
    developer_guild_id: Optional[int] = Field(None, env="DEVELOPER_GUILD_ID")
    
    # Database Configuration
    mongodb_uri: str = Field("mongodb://localhost:27017/serverpulse", env="MONGODB_URI")
    redis_url: str = Field("redis://localhost:6379", env="REDIS_URL")
    
    # AI Provider Configuration
    ai_provider: AIProvider = Field(AIProvider.OPENROUTER, env="AI_PROVIDER")
    openai_api_key: Optional[str] = Field(None, env="OPENAI_API_KEY")
    gemini_api_key: Optional[str] = Field(None, env="GEMINI_API_KEY")
    grok_api_key: Optional[str] = Field(None, env="GROK_API_KEY")
    openrouter_api_key: Optional[str] = Field(None, env="OPENROUTER_API_KEY")
    
    # Bot Configuration
    debug: bool = Field(False, env="DEBUG")
    log_level: LogLevel = Field(LogLevel.INFO, env="LOG_LEVEL")
    data_retention_days: int = Field(90, env="DATA_RETENTION_DAYS")
    
    # Alert Thresholds
    default_alert_threshold_join_raid: int = Field(10, env="DEFAULT_ALERT_THRESHOLD_JOIN_RAID")
    default_alert_threshold_activity_drop: int = Field(50, env="DEFAULT_ALERT_THRESHOLD_ACTIVITY_DROP")
    default_alert_threshold_mass_delete: int = Field(5, env="DEFAULT_ALERT_THRESHOLD_MASS_DELETE")
    default_alert_threshold_voice_surge: int = Field(3, env="DEFAULT_ALERT_THRESHOLD_VOICE_SURGE")
    
    # Cache Configuration
    cache_ttl_leaderboard: int = Field(300, env="CACHE_TTL_LEADERBOARD")  # 5 minutes
    cache_ttl_stats: int = Field(600, env="CACHE_TTL_STATS")  # 10 minutes
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()
