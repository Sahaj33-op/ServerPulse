"""AI Manager for ServerPulse with multi-provider support."""

import asyncio
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import aiohttp

from src.config import settings, AIProvider
from src.database.mongodb import DatabaseManager
from src.utils.logger import LoggerMixin
from src.utils.helpers import format_number, get_period_display_name, get_period_hours


class AIManager(LoggerMixin):
    """Manages AI-powered insights and report generation."""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.providers = {
            AIProvider.OPENAI: OpenAIProvider(),
            AIProvider.GEMINI: GeminiProvider(),
            AIProvider.GROK: GrokProvider(),
            AIProvider.OPENROUTER: OpenRouterProvider()
        }
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=60),
            headers={'User-Agent': 'ServerPulse/1.0.0'}
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def close(self):
        """Close HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def generate_instant_report(self, guild_id: int, period: str, 
                                    db_manager: DatabaseManager) -> Optional[str]:
        """Generate instant AI-powered server report."""
        try:
            # Get guild settings for AI configuration
            guild_settings = await db_manager.get_guild_settings(guild_id)
            if not guild_settings:
                return None
            
            # Collect analytics data
            analytics_data = await self._collect_analytics_data(guild_id, period, db_manager)
            
            # Select AI provider
            provider = await self._get_ai_provider(guild_settings)
            if not provider:
                self.logger.warning(f"No AI provider available for guild {guild_id}")
                return None
            
            # Generate report
            prompt = self._generate_report_prompt(analytics_data, period)
            response = await provider.generate_completion(
                prompt=prompt,
                max_tokens=1500,
                temperature=0.7,
                session=self.session
            )
            
            return response
            
        except Exception as e:
            self.logger.error(f"Error generating instant report: {e}", exc_info=True)
            return None
    
    async def generate_daily_report(self, guild_id: int, db_manager: DatabaseManager) -> Optional[str]:
        """Generate daily AI digest report."""
        try:
            guild_settings = await db_manager.get_guild_settings(guild_id)
            if not guild_settings or guild_settings.get('digest_frequency') != 'daily':
                return None
            
            # Get comprehensive data for daily report
            analytics_data = await self._collect_comprehensive_data(guild_id, '24h', db_manager)
            
            provider = await self._get_ai_provider(guild_settings)
            if not provider:
                return None
            
            # Generate detailed daily report
            prompt = self._generate_daily_digest_prompt(analytics_data)
            response = await provider.generate_completion(
                prompt=prompt,
                max_tokens=2000,
                temperature=0.6,
                session=self.session
            )
            
            # Save and send report
            if response:
                await db_manager.save_ai_report(
                    guild_id, 'daily_digest', response, {'generated_at': datetime.utcnow()}
                )
                
                # Send to update channel if configured
                await self._send_digest_report(guild_id, response, 'Daily', db_manager)
            
            return response
            
        except Exception as e:
            self.logger.error(f"Error generating daily report: {e}", exc_info=True)
            return None
    
    async def generate_weekly_report(self, guild_id: int, db_manager: DatabaseManager) -> Optional[str]:
        """Generate weekly AI digest report."""
        try:
            guild_settings = await db_manager.get_guild_settings(guild_id)
            if not guild_settings or guild_settings.get('digest_frequency') != 'weekly':
                return None
            
            # Get comprehensive weekly data
            analytics_data = await self._collect_comprehensive_data(guild_id, '7d', db_manager)
            
            provider = await self._get_ai_provider(guild_settings)
            if not provider:
                return None
            
            # Generate detailed weekly report
            prompt = self._generate_weekly_digest_prompt(analytics_data)
            response = await provider.generate_completion(
                prompt=prompt,
                max_tokens=2500,
                temperature=0.6,
                session=self.session
            )
            
            if response:
                await db_manager.save_ai_report(
                    guild_id, 'weekly_digest', response, {'generated_at': datetime.utcnow()}
                )
                
                await self._send_digest_report(guild_id, response, 'Weekly', db_manager)
            
            return response
            
        except Exception as e:
            self.logger.error(f"Error generating weekly report: {e}", exc_info=True)
            return None
    
    async def _collect_analytics_data(self, guild_id: int, period: str, 
                                    db_manager: DatabaseManager) -> Dict[str, Any]:
        """Collect analytics data for AI processing."""
        period_hours = get_period_hours(period)
        
        # Get message stats
        message_stats = await db_manager.get_message_stats(guild_id, period_hours)
        
        # Get member activity
        member_activity = await db_manager.get_member_activity(guild_id, period_hours)
        
        # Get top messagers
        top_messagers = await db_manager.get_top_messagers(guild_id, period_hours, 10)
        
        return {
            'period': period,
            'period_display': get_period_display_name(period),
            'message_stats': message_stats,
            'member_activity': member_activity,
            'top_messagers': top_messagers,
            'guild_id': guild_id
        }
    
    async def _collect_comprehensive_data(self, guild_id: int, period: str, 
                                        db_manager: DatabaseManager) -> Dict[str, Any]:
        """Collect comprehensive data for detailed reports."""
        basic_data = await self._collect_analytics_data(guild_id, period, db_manager)
        
        # Add trend analysis (compare with previous period)
        previous_period_hours = get_period_hours(period)
        previous_start = datetime.utcnow() - timedelta(hours=previous_period_hours * 2)
        previous_end = datetime.utcnow() - timedelta(hours=previous_period_hours)
        
        # Get previous period stats for comparison
        previous_stats = await self._get_period_stats(
            guild_id, previous_start, previous_end, db_manager
        )
        
        # Add growth calculations
        current_messages = basic_data['message_stats'].get('total_messages', 0)
        previous_messages = previous_stats.get('total_messages', 0)
        
        growth_rate = 0
        if previous_messages > 0:
            growth_rate = ((current_messages - previous_messages) / previous_messages) * 100
        
        basic_data.update({
            'previous_period_stats': previous_stats,
            'growth_rate': growth_rate,
            'trend_analysis': self._analyze_trends(basic_data, previous_stats)
        })
        
        return basic_data
    
    async def _get_period_stats(self, guild_id: int, start_time: datetime, 
                              end_time: datetime, db_manager: DatabaseManager) -> Dict[str, Any]:
        """Get statistics for a specific time period."""
        # Calculate hours between start and end
        period_hours = int((end_time - start_time).total_seconds() / 3600)
        
        # Adjust the current time reference for the query
        original_utcnow = datetime.utcnow
        datetime.utcnow = lambda: end_time
        
        try:
            stats = await db_manager.get_message_stats(guild_id, period_hours)
            return stats
        finally:
            datetime.utcnow = original_utcnow
    
    def _analyze_trends(self, current_data: Dict[str, Any], 
                       previous_data: Dict[str, Any]) -> List[str]:
        """Analyze trends between current and previous periods."""
        trends = []
        
        current_msg = current_data['message_stats'].get('total_messages', 0)
        previous_msg = previous_data.get('total_messages', 0)
        
        if previous_msg > 0:
            change = ((current_msg - previous_msg) / previous_msg) * 100
            if abs(change) >= 20:
                direction = 'increased' if change > 0 else 'decreased'
                trends.append(f"Message activity {direction} by {abs(change):.1f}%")
        
        current_users = current_data['message_stats'].get('unique_users', 0)
        previous_users = previous_data.get('unique_users', 0)
        
        if previous_users > 0:
            user_change = ((current_users - previous_users) / previous_users) * 100
            if abs(user_change) >= 15:
                direction = 'increased' if user_change > 0 else 'decreased'
                trends.append(f"Active users {direction} by {abs(user_change):.1f}%")
        
        # Analyze member activity trends
        current_joins = current_data['member_activity'].get('joins', 0)
        current_leaves = current_data['member_activity'].get('leaves', 0)
        
        if current_joins > current_leaves * 2:
            trends.append("Strong member growth observed")
        elif current_leaves > current_joins * 2:
            trends.append("Member retention challenges detected")
        
        return trends
    
    def _generate_report_prompt(self, data: Dict[str, Any], period: str) -> str:
        """Generate AI prompt for server report."""
        prompt = f"""Generate a concise Discord server analytics report for the {data['period_display'].lower()}.

Server Statistics:
- Total Messages: {format_number(data['message_stats'].get('total_messages', 0))}
- Unique Active Users: {format_number(data['message_stats'].get('unique_users', 0))}
- Average Message Length: {data['message_stats'].get('avg_message_length', 0):.1f} characters
- Member Joins: {data['member_activity'].get('joins', 0)}
- Member Leaves: {data['member_activity'].get('leaves', 0)}

Top Contributors:
"""
        
        for i, user in enumerate(data.get('top_messagers', [])[:5], 1):
            prompt += f"{i}. User ID {user['user_id']}: {user['message_count']} messages\n"
        
        prompt += """
Please provide:
1. A brief activity summary
2. Key insights about community engagement
3. Notable trends or patterns
4. 2-3 actionable recommendations for server growth

Keep the response under 1000 characters, professional but engaging. Focus on actionable insights."""
        
        return prompt
    
    def _generate_daily_digest_prompt(self, data: Dict[str, Any]) -> str:
        """Generate AI prompt for daily digest."""
        prompt = f"""Create a comprehensive daily digest for this Discord server's activity.

Daily Statistics:
- Messages: {format_number(data['message_stats'].get('total_messages', 0))}
- Active Users: {format_number(data['message_stats'].get('unique_users', 0))}
- New Members: {data['member_activity'].get('joins', 0)}
- Members Left: {data['member_activity'].get('leaves', 0)}
- Net Growth: {data['member_activity'].get('joins', 0) - data['member_activity'].get('leaves', 0)}
"""
        
        if 'growth_rate' in data:
            prompt += f"- Growth Rate: {data['growth_rate']:+.1f}% vs yesterday\n"
        
        if data.get('trend_analysis'):
            prompt += "\nKey Trends:\n"
            for trend in data['trend_analysis']:
                prompt += f"- {trend}\n"
        
        prompt += """
Provide:
1. Daily activity summary with highlights
2. Community engagement analysis
3. Growth trends and member retention insights
4. Recommendations for tomorrow's engagement
5. Celebrate achievements and milestones

Tone: Professional but warm. Focus on community building insights."""
        
        return prompt
    
    def _generate_weekly_digest_prompt(self, data: Dict[str, Any]) -> str:
        """Generate AI prompt for weekly digest."""
        prompt = f"""Create a comprehensive weekly server digest with strategic insights.

Weekly Performance:
- Total Messages: {format_number(data['message_stats'].get('total_messages', 0))}
- Active Users: {format_number(data['message_stats'].get('unique_users', 0))}
- New Members: {data['member_activity'].get('joins', 0)}
- Member Retention: {((data['member_activity'].get('joins', 0) - data['member_activity'].get('leaves', 0)) / max(data['member_activity'].get('joins', 0), 1) * 100):.1f}%
"""
        
        if 'growth_rate' in data:
            prompt += f"- Week-over-Week Growth: {data['growth_rate']:+.1f}%\n"
        
        prompt += "\nTop Contributors This Week:\n"
        for i, user in enumerate(data.get('top_messagers', [])[:10], 1):
            prompt += f"{i}. User {user['user_id']}: {user['message_count']} messages (avg: {user.get('avg_length', 0):.0f} chars)\n"
        
        if data.get('trend_analysis'):
            prompt += "\nWeek's Key Trends:\n"
            for trend in data['trend_analysis']:
                prompt += f"- {trend}\n"
        
        prompt += """
Generate a strategic weekly digest including:
1. Week's achievements and milestones
2. Deep community engagement analysis
3. Member growth and retention insights
4. Channel performance breakdown
5. Strategic recommendations for next week
6. Celebrate top contributors
7. Identify opportunities for improvement

Tone: Strategic and insightful. Focus on long-term community building."""
        
        return prompt
    
    async def _get_ai_provider(self, guild_settings: Dict[str, Any]) -> Optional['BaseAIProvider']:
        """Get configured AI provider for guild."""
        provider_name = guild_settings.get('ai_provider', settings.ai_provider)
        provider = self.providers.get(AIProvider(provider_name))
        
        if not provider:
            return None
        
        # Configure provider with guild's API keys or global settings
        guild_keys = guild_settings.get('ai_api_keys', {})
        await provider.configure(guild_keys)
        
        return provider
    
    async def _send_digest_report(self, guild_id: int, report: str, 
                                report_type: str, db_manager: DatabaseManager) -> None:
        """Send digest report to configured channel."""
        try:
            guild_settings = await db_manager.get_guild_settings(guild_id)
            if not guild_settings:
                return
            
            update_channel_id = guild_settings.get('update_channel_id')
            if not update_channel_id:
                return
            
            # This would need bot instance to send message
            # For now, just log that we would send it
            self.logger.info(f"Would send {report_type.lower()} digest to guild {guild_id} channel {update_channel_id}")
            
        except Exception as e:
            self.logger.error(f"Error sending digest report: {e}", exc_info=True)


class BaseAIProvider:
    """Base class for AI providers."""
    
    def __init__(self):
        self.api_key: Optional[str] = None
        self.configured = False
    
    async def configure(self, api_keys: Dict[str, str]) -> bool:
        """Configure provider with API keys."""
        raise NotImplementedError
    
    async def generate_completion(self, prompt: str, max_tokens: int = 1000, 
                               temperature: float = 0.7, 
                               session: Optional[aiohttp.ClientSession] = None) -> Optional[str]:
        """Generate AI completion."""
        raise NotImplementedError


class OpenAIProvider(BaseAIProvider):
    """OpenAI GPT provider."""
    
    async def configure(self, api_keys: Dict[str, str]) -> bool:
        """Configure OpenAI provider."""
        self.api_key = api_keys.get('openai') or settings.openai_api_key
        self.configured = bool(self.api_key)
        return self.configured
    
    async def generate_completion(self, prompt: str, max_tokens: int = 1000, 
                               temperature: float = 0.7, 
                               session: Optional[aiohttp.ClientSession] = None) -> Optional[str]:
        """Generate completion using OpenAI API."""
        if not self.configured or not session:
            return None
        
        try:
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'model': 'gpt-3.5-turbo',
                'messages': [
                    {'role': 'system', 'content': 'You are ServerPulse AI, a helpful Discord server analytics assistant. Provide concise, actionable insights.'},
                    {'role': 'user', 'content': prompt}
                ],
                'max_tokens': max_tokens,
                'temperature': temperature
            }
            
            async with session.post('https://api.openai.com/v1/chat/completions', 
                                  json=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return data['choices'][0]['message']['content'].strip()
                else:
                    error_text = await response.text()
                    raise Exception(f"OpenAI API error {response.status}: {error_text}")
        
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"OpenAI completion error: {e}")
            return None


class GeminiProvider(BaseAIProvider):
    """Google Gemini provider."""
    
    async def configure(self, api_keys: Dict[str, str]) -> bool:
        """Configure Gemini provider."""
        self.api_key = api_keys.get('gemini') or settings.gemini_api_key
        self.configured = bool(self.api_key)
        return self.configured
    
    async def generate_completion(self, prompt: str, max_tokens: int = 1000, 
                               temperature: float = 0.7, 
                               session: Optional[aiohttp.ClientSession] = None) -> Optional[str]:
        """Generate completion using Gemini API."""
        if not self.configured or not session:
            return None
        
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={self.api_key}"
            
            payload = {
                'contents': [{
                    'parts': [{'text': f"You are ServerPulse AI, a Discord server analytics assistant. {prompt}"}]
                }],
                'generationConfig': {
                    'maxOutputTokens': max_tokens,
                    'temperature': temperature
                }
            }
            
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    return data['candidates'][0]['content']['parts'][0]['text'].strip()
                else:
                    error_text = await response.text()
                    raise Exception(f"Gemini API error {response.status}: {error_text}")
        
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Gemini completion error: {e}")
            return None


class GrokProvider(BaseAIProvider):
    """Grok AI provider."""
    
    async def configure(self, api_keys: Dict[str, str]) -> bool:
        """Configure Grok provider."""
        self.api_key = api_keys.get('grok') or settings.grok_api_key
        self.configured = bool(self.api_key)
        return self.configured
    
    async def generate_completion(self, prompt: str, max_tokens: int = 1000, 
                               temperature: float = 0.7, 
                               session: Optional[aiohttp.ClientSession] = None) -> Optional[str]:
        """Generate completion using Grok API."""
        if not self.configured or not session:
            return None
        
        try:
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'model': 'grok-beta',
                'messages': [
                    {'role': 'system', 'content': 'You are ServerPulse AI, providing Discord server analytics insights.'},
                    {'role': 'user', 'content': prompt}
                ],
                'max_tokens': max_tokens,
                'temperature': temperature
            }
            
            async with session.post('https://api.x.ai/v1/chat/completions', 
                                  json=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return data['choices'][0]['message']['content'].strip()
                else:
                    error_text = await response.text()
                    raise Exception(f"Grok API error {response.status}: {error_text}")
        
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Grok completion error: {e}")
            return None


class OpenRouterProvider(BaseAIProvider):
    """OpenRouter provider (multiple models)."""
    
    async def configure(self, api_keys: Dict[str, str]) -> bool:
        """Configure OpenRouter provider."""
        self.api_key = api_keys.get('openrouter') or settings.openrouter_api_key
        self.configured = bool(self.api_key)
        return self.configured
    
    async def generate_completion(self, prompt: str, max_tokens: int = 1000, 
                               temperature: float = 0.7, 
                               session: Optional[aiohttp.ClientSession] = None) -> Optional[str]:
        """Generate completion using OpenRouter API."""
        if not self.configured or not session:
            return None
        
        try:
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
                'HTTP-Referer': 'https://github.com/Sahaj33-op/ServerPulse',
                'X-Title': 'ServerPulse Discord Analytics Bot'
            }
            
            payload = {
                'model': 'meta-llama/llama-3.1-8b-instruct:free',  # Free tier model
                'messages': [
                    {'role': 'system', 'content': 'You are ServerPulse AI, a Discord server analytics assistant providing actionable insights.'},
                    {'role': 'user', 'content': prompt}
                ],
                'max_tokens': max_tokens,
                'temperature': temperature
            }
            
            async with session.post('https://openrouter.ai/api/v1/chat/completions', 
                                  json=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return data['choices'][0]['message']['content'].strip()
                else:
                    error_text = await response.text()
                    raise Exception(f"OpenRouter API error {response.status}: {error_text}")
        
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"OpenRouter completion error: {e}")
            return None
