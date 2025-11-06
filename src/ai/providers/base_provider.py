"""Base AI provider interface for ServerPulse."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

import aiohttp


class BaseAIProvider(ABC):
    """Base class for AI providers."""
    
    @abstractmethod
    async def test_connection(self, session: aiohttp.ClientSession, api_key: str) -> Dict[str, Any]:
        """Test the connection to the AI provider.
        
        Returns:
            Dict with 'success' (bool), 'error' (str, optional), 'model' (str, optional)
        """
        pass
    
    @abstractmethod
    async def generate_report(self, session: aiohttp.ClientSession, api_key: str, 
                            analytics_data: Dict[str, Any]) -> Optional[str]:
        """Generate an AI report based on analytics data.
        
        Args:
            session: HTTP client session
            api_key: API key for the provider
            analytics_data: Server analytics data
            
        Returns:
            Generated report text or None if failed
        """
        pass
    
    @abstractmethod
    async def generate_insight(self, session: aiohttp.ClientSession, api_key: str,
                             analytics_data: Dict[str, Any], question: str) -> Optional[str]:
        """Generate AI insight based on specific question.
        
        Args:
            session: HTTP client session
            api_key: API key for the provider
            analytics_data: Server analytics data
            question: Specific question to answer
            
        Returns:
            Generated insight text or None if failed
        """
        pass
    
    def _build_analytics_context(self, data: Dict[str, Any]) -> str:
        """Build analytics context for AI prompts."""
        top_users = data.get('top_messagers', [])
        top_users_text = "\n".join([
            f"- User {user['user_id']}: {user['message_count']} messages (avg {user.get('avg_length', 0):.0f} chars)"
            for user in top_users[:5]
        ])
        
        context = f"""DISCORD SERVER ANALYTICS DATA:

PERIOD: {data.get('period_display', 'Recent period')}
TIME RANGE: {data.get('start_time', 'N/A')} to {data.get('end_time', 'N/A')}

MESSAGE ACTIVITY:
- Total messages: {data.get('total_messages', 0)}
- Active users: {data.get('active_users', 0)}
- Average message length: {data.get('avg_message_length', 0):.1f} characters
- Attachments shared: {data.get('attachments', 0)}

MEMBER ACTIVITY:
- New joins: {data.get('member_joins', 0)}
- Members left: {data.get('member_leaves', 0)}
- Net growth: {data.get('net_member_growth', 0):+d}

TRENDS:
- Growth rate: {data.get('growth_rate', 0):.1f}% vs historical average
- Trend: {data.get('trend', 'stable').title()}
- Historical average: {data.get('historical_avg_messages', 0):.1f} messages/period

TOP CONTRIBUTORS:
{top_users_text if top_users_text else '- No activity recorded'}
"""
        return context
    
    def _build_report_prompt(self, analytics_data: Dict[str, Any]) -> str:
        """Build prompt for report generation."""
        context = self._build_analytics_context(analytics_data)
        
        prompt = f"""{context}

Please generate a comprehensive Discord server activity report based on this data. Include:

1. **Activity Summary**: Overview of message activity, user engagement, and key metrics
2. **Community Highlights**: Notable contributors and engagement patterns
3. **Growth Analysis**: Member growth trends and activity changes vs historical data
4. **Insights & Recommendations**: Actionable suggestions for community improvement
5. **Key Takeaways**: 2-3 bullet points summarizing the most important findings

Format the report in Discord-friendly markdown with appropriate emojis. Keep it engaging and actionable for server administrators. Limit to ~800 words.

Start with: **📊 ServerPulse Report - [Period]**"""
        
        return prompt
    
    def _build_insight_prompt(self, analytics_data: Dict[str, Any], question: str) -> str:
        """Build prompt for insight generation."""
        context = self._build_analytics_context(analytics_data)
        
        prompt = f"""{context}

Based on this Discord server analytics data, please answer the following question:

**Question:** {question}

Provide a detailed, data-driven answer that:
- References specific metrics from the data
- Offers actionable insights
- Includes relevant recommendations
- Uses Discord-friendly formatting with emojis

Keep the response focused and under 400 words."""
        
        return prompt
