"""
Formatting utilities for professional Discord message presentation.
Provides consistent styling, number formatting, and embed creation.
"""
import discord
from datetime import datetime
from typing import Optional


# Color Palette - Professional Discord theme
class Colors:
    """Standardized color palette for embeds"""
    PRIMARY = 0x5865F2      # Discord Blurple (Info/Standard)
    SUCCESS = 0x57F287      # Green (Success/Positive)
    WARNING = 0xFEE75C      # Yellow (Warning/Caution)
    DANGER = 0xED4245       # Red (Error/Alert)
    NEUTRAL = 0x99AAB5      # Gray (Neutral/Inactive)
    PURPLE = 0x9B59B6       # Purple (Premium/Special)


# Number Formatting
def format_number(n: int) -> str:
    """
    Format number with commas for readability.
    
    Args:
        n: Number to format
        
    Returns:
        Formatted string (e.g., 1234 -> "1,234")
    """
    return f"{n:,}"


def format_percentage(value: float, decimals: int = 1) -> str:
    """
    Format percentage with proper sign.
    
    Args:
        value: Percentage as decimal (0.1234 = 12.34%)
        decimals: Number of decimal places
        
    Returns:
        Formatted percentage string (e.g., "+12.3%")
    """
    return f"{value:+.{decimals}f}%"


def format_change(current: int, previous: int) -> str:
    """
    Format change with percentage and arrow indicator.
    
    Args:
        current: Current value
        previous: Previous value
        
    Returns:
        Formatted change string (e.g., "+15.3% ↗" or "-5.2% ↘")
    """
    if previous == 0:
        return "+∞ ↗" if current > 0 else "No change"
    
    change_pct = ((current - previous) / previous) * 100
    arrow = "↗" if change_pct > 0 else "↘" if change_pct < 0 else "→"
    sign = "+" if change_pct > 0 else ""
    
    return f"{sign}{change_pct:.1f}% {arrow}"


def format_duration(hours: int) -> str:
    """
    Format duration in human-readable format.
    
    Args:
        hours: Duration in hours
        
    Returns:
        Human-readable string (e.g., "Last 7 days")
    """
    if hours < 24:
        return f"Last {hours} hours"
    elif hours == 24:
        return "Last 24 hours"
    else:
        days = hours // 24
        return f"Last {days} days" if days > 1 else "Last day"


# Progress Bars
def create_progress_bar(value: float, max_value: float, length: int = 10) -> str:
    """
    Create visual progress bar.
    
    Args:
        value: Current value
        max_value: Maximum value
        length: Bar length in characters
        
    Returns:
        Progress bar string (e.g., "▰▰▰▰▰▱▱▱▱▱ 50%")
    """
    if max_value == 0:
        filled = 0
    else:
        filled = int((value / max_value) * length)
    
    filled = min(filled, length)  # Cap at length
    empty = length - filled
    
    bar = "▰" * filled + "▱" * empty
    percentage = (value / max_value * 100) if max_value > 0 else 0
    
    return f"{bar} {percentage:.0f}%"


def create_rank_indicator(rank: int) -> str:
    """
    Create rank indicator with medal emoji.
    
    Args:
        rank: Rank position (1-indexed)
        
    Returns:
        Rank string with emoji (e.g., "🥇 #1")
    """
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    medal = medals.get(rank, "🏅")
    return f"{medal} #{rank}"


# Embed Builders
def create_standard_embed(
    title: str,
    description: Optional[str] = None,
    color: int = Colors.PRIMARY
) -> discord.Embed:
    """
    Create standardized embed with branding.
    
    Args:
        title: Embed title
        description: Optional description
        color: Embed color (default: Discord Blurple)
        
    Returns:
        Configured Discord embed
    """
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.utcnow()
    )
    return embed


def create_success_embed(title: str, description: str) -> discord.Embed:
    """Create success-themed embed"""
    return create_standard_embed(
        title=f"✅ {title}",
        description=description,
        color=Colors.SUCCESS
    )


def create_error_embed(title: str, description: str) -> discord.Embed:
    """Create error-themed embed"""
    return create_standard_embed(
        title=f"❌ {title}",
        description=description,
        color=Colors.DANGER
    )


def create_warning_embed(title: str, description: str) -> discord.Embed:
    """Create warning-themed embed"""
    return create_standard_embed(
        title=f"⚠️ {title}",
        description=description,
        color=Colors.WARNING
    )


def add_standard_footer(embed: discord.Embed, text: Optional[str] = None) -> discord.Embed:
    """
    Add consistent footer to embeds.
    
    Args:
        embed: Embed to modify
        text: Optional custom footer text
        
    Returns:
        Modified embed
    """
    footer_text = text or "ServerPulse Analytics"
    embed.set_footer(
        text=footer_text,
        icon_url="https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/1f4ca.png"
    )
    return embed


# Text Formatting
def truncate_text(text: str, max_length: int = 1024, suffix: str = "...") -> str:
    """
    Safely truncate text for embed fields.
    
    Args:
        text: Text to truncate
        max_length: Maximum length (Discord embed field limit is 1024)
        suffix: Suffix to add if truncated
        
    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


def format_user_mention(user_id: int) -> str:
    """Format user mention for Discord"""
    return f"<@{user_id}>"


def format_channel_mention(channel_id: int) -> str:
    """Format channel mention for Discord"""
    return f"<#{channel_id}>"


def format_timestamp(dt: datetime, style: str = "R") -> str:
    """
    Format timestamp for Discord dynamic display.
    
    Args:
        dt: DateTime object
        style: Discord timestamp style
            - t: Short time (16:20)
            - T: Long time (16:20:30)
            - d: Short date (20/04/2021)
            - D: Long date (20 April 2021)
            - f: Short date/time (20 April 2021 16:20)
            - F: Long date/time (Tuesday, 20 April 2021 16:20)
            - R: Relative time (2 months ago)
            
    Returns:
        Discord timestamp format
    """
    timestamp = int(dt.timestamp())
    return f"<t:{timestamp}:{style}>"
