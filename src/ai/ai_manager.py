"""AI Manager for ServerPulse - Handles AI provider integration and reporting."""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

import aiohttp
import discord
from src.utils.logger import LoggerMixin
from src.ai.providers.openai_provider import OpenAIProvider
from src.ai.providers.gemini_provider import GeminiProvider
from src.ai.providers.openrouter_provider import OpenRouterProvider
from src.ai.providers.grok_provider import GrokProvider
from src.ai.providers.base_provider import BaseAIProvider
from src.ai.report_formatter import ReportFormatter


class AIManager(LoggerMixin):
    """Multi-provider AI manager for ServerPulse."""
    
    def __init__(self):
        self.providers: Dict[str, BaseAIProvider] = {
            'openai': OpenAIProvider(),
            'gemini': GeminiProvider(),
            'openrouter': OpenRouterProvider(),
            'grok': GrokProvider()
        }
        
        self.formatter = ReportFormatter()
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure HTTP session exists."""
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self.session
    
    async def close(self) -> None:
        """Close HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def test_provider(self, provider_name: str, api_key: str) -> Dict[str, Any]:
        """Test AI provider connection."""
        if provider_name not in self.providers:
            return {'success': False, 'error': f'Unknown provider: {provider_name}'}
        
        provider = self.providers[provider_name]
        session = await self._ensure_session()
        
        try:
            result = await provider.test_connection(session, api_key)
            return result
        except Exception as e:
            self.logger.error(f"Error testing {provider_name}: {e}")
            return {'success': False, 'error': str(e)}
    
    async def generate_pulse_report(self, guild_id: int, db_manager, 
                                  period: str = "24h", guild_name: str = None) -> Optional[discord.Embed]:
        """Generate AI-powered pulse report as a Discord embed."""
        try:
            # Get guild settings
            guild_settings = await db_manager.get_guild_settings(guild_id)
            if not guild_settings:
                return None
            
            provider_name = guild_settings.get('ai_provider')
            api_keys = guild_settings.get('ai_api_keys', {})
            
            if not provider_name or provider_name not in api_keys:
                self.logger.warning(f"No AI provider configured for guild {guild_id}")
                return None
            
            # Get analytics data
            analytics_data = await self._gather_analytics_data(guild_id, db_manager, period)
            
            if not analytics_data['has_activity']:
                # Return no-activity embed
                return self.formatter.create_no_activity_embed(
                    analytics_data.get('period_display', period),
                    analytics_data,
                    guild_name
                )
            
            # Generate AI report (plain text)
            provider = self.providers[provider_name]
            session = await self._ensure_session()
            
            report_text = await provider.generate_report(
                session,
                api_keys[provider_name],
                analytics_data
            )
            
            if report_text:
                # Parse sections from AI-generated text
                sections = self.formatter.parse_sections(report_text)
                
                # Create rich embed from sections
                period_display = analytics_data.get('period_display', period)
                embed = self.formatter.create_report_embed(
                    f"ServerPulse Report - {period_display}",
                    sections,
                   analytics_data,
                    guild_name
                )
                
                # Save report to database (still save text version)
                await db_manager.save_ai_report(
                    guild_id,
                    'pulse_report',
                    report_text,
                    {
                        'period': period,
                        'provider': provider_name,
                        'data_summary': {
                            'total_messages': analytics_data.get('total_messages', 0),
                            'active_users': analytics_data.get('active_users', 0)
                        }
                    }
                )
                
                return embed
            
        except Exception as e:
            self.logger.error(f"Error generating pulse report for guild {guild_id}: {e}")
        
        return None
    
    async def generate_daily_report(self, guild_id: int, db_manager, guild_name: str = None) -> Optional[discord.Embed]:
        """Generate daily AI report."""
        return await self.generate_pulse_report(guild_id, db_manager, "24h", guild_name)
    
    async def generate_weekly_report(self, guild_id: int, db_manager, guild_name: str = None) -> Optional[discord.Embed]:
        """Generate weekly AI report."""
        return await self.generate_pulse_report(guild_id, db_manager, "7d", guild_name)
    
    async def _gather_analytics_data(self, guild_id: int, db_manager, period: str) -> Dict[str, Any]:
        """Gather comprehensive analytics data for AI processing."""
        from src.utils.helpers import get_period_hours
        
        period_hours = get_period_hours(period)
        start_time = datetime.utcnow() - timedelta(hours=period_hours)
        
        # Get message statistics
        message_stats = await db_manager.get_message_stats(guild_id, period_hours)
        
        # Get top messagers
        top_messagers = await db_manager.get_top_messagers(guild_id, period_hours, 10)
        
        # Get member activity
        member_activity = await db_manager.get_member_activity(guild_id, period_hours)
        
        # Get historical comparison
        historical_period_hours = period_hours * 7  # Compare with same period over last week
        historical_start = start_time - timedelta(hours=historical_period_hours)
        historical_stats = await db_manager.get_message_stats(
            guild_id, historical_period_hours
        )
        
        # Calculate trends
        current_messages = message_stats.get('total_messages', 0)
        historical_avg = historical_stats.get('total_messages', 0) / 7 if historical_stats.get('total_messages', 0) > 0 else 0
        
        growth_rate = 0
        if historical_avg > 0:
            growth_rate = ((current_messages - historical_avg) / historical_avg) * 100
        
        return {
            'guild_id': guild_id,
            'period': period,
            'start_time': start_time.isoformat(),
            'end_time': datetime.utcnow().isoformat(),
            'has_activity': current_messages > 0,
            
            # Current period stats
            'total_messages': current_messages,
            'active_users': message_stats.get('unique_users', 0),
            'avg_message_length': message_stats.get('avg_message_length', 0),
            'attachments': message_stats.get('attachments', 0),
            
            # Member activity
            'member_joins': member_activity.get('joins', 0),
            'member_leaves': member_activity.get('leaves', 0),
            'net_member_growth': member_activity.get('joins', 0) - member_activity.get('leaves', 0),
            
            # Top contributors
            'top_messagers': top_messagers,
            
            # Trends and comparisons
            'historical_avg_messages': historical_avg,
            'growth_rate': growth_rate,
            'trend': 'increasing' if growth_rate > 10 else 'decreasing' if growth_rate < -10 else 'stable',
            
            # Additional context
            'period_display': self._get_period_display(period),
            'timestamp': datetime.utcnow().isoformat()
        }
    
    async def _generate_no_activity_report(self, guild_id: int, data: Dict[str, Any]) -> str:
        """Generate report for periods with no activity."""
        period_display = data.get('period_display', 'this period')
        
        return f"""**📊 ServerPulse Report - {period_display}**

**Activity Summary:**
🔕 No message activity detected during {period_display.lower()}

**Possible Reasons:**
• Quiet period - normal for some communities
• Most members in different time zones
• Weekend/holiday period
• Community focused on voice channels

**Suggestions:**
• Consider posting engaging discussion topics
• Share community highlights or achievements
• Plan interactive events or activities
• Check if members are active in voice channels

**Member Activity:**
👋 New joins: {data.get('member_joins', 0)}
🚪 Members left: {data.get('member_leaves', 0)}
📈 Net growth: {data.get('net_member_growth', 0):+d}

*This report was generated automatically by ServerPulse AI.*"""
    
    def _get_period_display(self, period: str) -> str:
        """Get human-readable period display."""
        period_map = {
            '1h': 'Last Hour',
            '6h': 'Last 6 Hours',
            '12h': 'Last 12 Hours',
            '24h': 'Last 24 Hours',
            '7d': 'Last 7 Days',
            '30d': 'Last 30 Days',
            'all': 'All Time'
        }
        return period_map.get(period, 'Recent Period')
    
    async def generate_insights(self, guild_id: int, db_manager, 
                              question: str) -> Optional[str]:
        """Generate AI insights based on specific questions."""
        try:
            guild_settings = await db_manager.get_guild_settings(guild_id)
            if not guild_settings:
                return None
            
            provider_name = guild_settings.get('ai_provider')
            api_keys = guild_settings.get('ai_api_keys', {})
            
            if not provider_name or provider_name not in api_keys:
                return None
            
            # Get relevant analytics data
            analytics_data = await self._gather_analytics_data(guild_id, db_manager, "7d")
            
            provider = self.providers[provider_name]
            session = await self._ensure_session()
            
            insight = await provider.generate_insight(
                session,
                api_keys[provider_name],
                analytics_data,
                question
            )
            
            return insight
            
        except Exception as e:
            self.logger.error(f"Error generating insights for guild {guild_id}: {e}")
            return None
