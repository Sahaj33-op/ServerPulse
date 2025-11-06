"""Helper utilities for ServerPulse."""

import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, Any
from discord import Guild, Member, TextChannel, VoiceChannel, CategoryChannel


def format_time_duration(seconds: int) -> str:
    """Format seconds into human-readable duration."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        remaining_seconds = seconds % 60
        if remaining_seconds > 0:
            return f"{minutes}m {remaining_seconds}s"
        return f"{minutes}m"
    elif seconds < 86400:
        hours = seconds // 3600
        remaining_minutes = (seconds % 3600) // 60
        if remaining_minutes > 0:
            return f"{hours}h {remaining_minutes}m"
        return f"{hours}h"
    else:
        days = seconds // 86400
        remaining_hours = (seconds % 86400) // 3600
        if remaining_hours > 0:
            return f"{days}d {remaining_hours}h"
        return f"{days}d"


def format_number(number: int) -> str:
    """Format large numbers with appropriate suffixes."""
    if number < 1000:
        return str(number)
    elif number < 1000000:
        return f"{number / 1000:.1f}K"
    elif number < 1000000000:
        return f"{number / 1000000:.1f}M"
    else:
        return f"{number / 1000000000:.1f}B"


def sanitize_channel_name(name: str) -> str:
    """Sanitize text for Discord channel naming."""
    # Remove or replace invalid characters
    name = re.sub(r'[^a-zA-Z0-9\-_]', '-', name)
    # Remove multiple consecutive dashes
    name = re.sub(r'-+', '-', name)
    # Remove leading/trailing dashes
    name = name.strip('-')
    # Ensure max length
    return name[:100].lower()


def get_period_hours(period: str) -> int:
    """Convert period string to hours."""
    period_map = {
        '1h': 1,
        '6h': 6,
        '12h': 12,
        '24h': 24,
        '7d': 168,
        '30d': 720,
        'all': 8760  # 1 year
    }
    return period_map.get(period, 24)


def get_period_display_name(period: str) -> str:
    """Get human-readable period name."""
    period_names = {
        '1h': 'Last Hour',
        '6h': 'Last 6 Hours',
        '12h': 'Last 12 Hours', 
        '24h': 'Last 24 Hours',
        '7d': 'Last 7 Days',
        '30d': 'Last 30 Days',
        'all': 'All Time'
    }
    return period_names.get(period, 'Last 24 Hours')


def calculate_activity_score(message_count: int, unique_users: int, 
                           avg_message_length: float) -> int:
    """Calculate activity score based on various metrics."""
    # Base score from message count
    score = message_count * 1.0
    
    # Bonus for user diversity
    if unique_users > 0:
        diversity_bonus = min(unique_users * 0.5, message_count * 0.3)
        score += diversity_bonus
    
    # Bonus for meaningful messages (longer messages)
    if avg_message_length > 10:  # More than just short responses
        length_bonus = min(avg_message_length * 0.1, message_count * 0.2)
        score += length_bonus
    
    return int(score)


def detect_activity_anomaly(current_count: int, historical_avg: float, 
                          threshold_percent: float = 50.0) -> Optional[str]:
    """Detect if current activity is anomalous compared to historical average."""
    if historical_avg == 0:
        return None
    
    change_percent = ((current_count - historical_avg) / historical_avg) * 100
    
    if abs(change_percent) >= threshold_percent:
        if change_percent > 0:
            return f"spike_{int(change_percent)}"
        else:
            return f"drop_{int(abs(change_percent))}"
    
    return None


def create_progress_bar(percentage: float, length: int = 20) -> str:
    """Create a text progress bar."""
    filled = int(length * percentage / 100)
    bar = '█' * filled + '░' * (length - filled)
    return f"{bar} {percentage:.1f}%"


def truncate_text(text: str, max_length: int = 2000, suffix: str = "...") -> str:
    """Truncate text to fit Discord message limits."""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def get_emoji_for_rank(rank: int) -> str:
    """Get appropriate emoji for leaderboard ranking."""
    rank_emojis = {
        1: "🥇",
        2: "🥈", 
        3: "🥉",
        4: "4️⃣",
        5: "5️⃣",
        6: "6️⃣",
        7: "7️⃣",
        8: "8️⃣",
        9: "9️⃣",
        10: "🔟"
    }
    return rank_emojis.get(rank, f"{rank}.")


def get_activity_emoji(activity_type: str) -> str:
    """Get emoji for different activity types."""
    activity_emojis = {
        'message': '💬',
        'join': '👋',
        'leave': '👋',
        'voice_join': '🎙️',
        'voice_leave': '🔇',
        'reaction': '👍',
        'edit': '✏️',
        'delete': '🗑️'
    }
    return activity_emojis.get(activity_type, '📊')


def get_alert_emoji(alert_type: str) -> str:
    """Get emoji for different alert types."""
    alert_emojis = {
        'join_raid': '⚠️',
        'activity_drop': '📉',
        'activity_spike': '📈',
        'mass_delete': '🧹',
        'voice_surge': '🎙️'
    }
    return alert_emojis.get(alert_type, '🔔')


def format_member_mention(member: Optional[Member], user_id: int) -> str:
    """Format member mention, handling cases where member left."""
    if member:
        return member.mention
    return f"<@{user_id}>"


def format_channel_mention(channel: Optional[Union[TextChannel, VoiceChannel]], 
                         channel_id: int) -> str:
    """Format channel mention, handling deleted channels."""
    if channel:
        return channel.mention
    return f"<#{channel_id}>"


def extract_message_metadata(content: str) -> Dict[str, Any]:
    """Extract metadata from message content without storing the actual content."""
    metadata = {
        'length': len(content),
        'word_count': len(content.split()),
        'has_url': bool(re.search(r'https?://', content)),
        'has_mention': bool(re.search(r'<@[!&]?\d+>', content)),
        'has_emoji': bool(re.search(r'<:\w+:\d+>', content)),
        'has_code_block': '```' in content,
        'has_inline_code': '`' in content and '```' not in content
    }
    return metadata


def is_spam_pattern(content: str) -> bool:
    """Basic spam detection patterns."""
    # Check for excessive repetition
    if len(set(content.lower())) / len(content) < 0.3 and len(content) > 20:
        return True
    
    # Check for excessive caps
    caps_ratio = sum(1 for c in content if c.isupper()) / len(content) if content else 0
    if caps_ratio > 0.7 and len(content) > 10:
        return True
    
    # Check for excessive special characters
    special_ratio = sum(1 for c in content if not c.isalnum() and not c.isspace()) / len(content) if content else 0
    if special_ratio > 0.5 and len(content) > 10:
        return True
    
    return False


def get_time_bucket(timestamp: datetime, bucket_size_minutes: int = 60) -> datetime:
    """Round timestamp to time bucket for aggregation."""
    minutes = (timestamp.minute // bucket_size_minutes) * bucket_size_minutes
    return timestamp.replace(minute=minutes, second=0, microsecond=0)


def calculate_growth_rate(current_value: int, previous_value: int) -> float:
    """Calculate percentage growth rate."""
    if previous_value == 0:
        return 100.0 if current_value > 0 else 0.0
    
    return ((current_value - previous_value) / previous_value) * 100
