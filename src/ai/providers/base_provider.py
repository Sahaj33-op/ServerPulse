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
        total_messages = data.get('total_messages', 0)
        active_users = data.get('active_users', 0)
        
        # Calculate additional metrics
        avg_per_user = total_messages / active_users if active_users > 0 else 0
        
        # Top users with percentages
        top_users_lines = []
        for i, user in enumerate(top_users[:5], 1):
            msg_count = user['message_count']
            percentage = (msg_count /total_messages * 100) if total_messages > 0 else 0
            avg_len = user.get('avg_length', 0)
            top_users_lines.append(
                f"  #{i}. User {user['user_id']}: {msg_count:,} messages ({percentage:.1f}%) | Avg length: {avg_len:.0f} chars"
            )
        
        top_users_text = "\n".join(top_users_lines) if top_users_lines else "  - No activity recorded"
        
        # Member growth context
        member_joins = data.get('member_joins', 0)
        member_leaves = data.get('member_leaves', 0)
        net_growth = data.get('net_member_growth', 0)
        growth_emoji = "📈" if net_growth > 0 else "📉" if net_growth < 0 else "➡️"
        
        # Trend context
        growth_rate = data.get('growth_rate', 0)
        trend = data.get('trend', 'stable')
        trend_direction = "increasing" if growth_rate > 10 else "decreasing" if growth_rate < -10 else "stable"
        
        context = f"""DISCORD SERVER ANALYTICS DATA:

📅 PERIOD: {data.get('period_display', 'Recent period')}
⏰ TIME RANGE: {data.get('start_time', 'N/A')} to {data.get('end_time', 'N/A')}

💬 MESSAGE ACTIVITY:
  - Total messages: {total_messages:,}
  - Active users: {active_users:,}
  - Messages per user: {avg_per_user:.1f}
  - Average message length: {data.get('avg_message_length', 0):.1f} characters
  - Attachments shared: {data.get('attachments', 0):,}

👥 MEMBER ACTIVITY:
  - New joins: {member_joins:,}
  - Members left: {member_leaves:,}
  - Net growth: {net_growth:+d} {growth_emoji}

📊 TRENDS & COMPARISONS:
  - Growth rate: {growth_rate:+.1f}% compared to historical average
  - Trend direction: {trend_direction.upper()}
  - Historical average: {data.get('historical_avg_messages', 0):.1f} messages per period
  - Activity level: {"HIGH" if total_messages > 1000 else "MODERATE" if total_messages > 100 else "LOW"}

🏆 TOP CONTRIBUTORS:
{top_users_text}
"""
        return context
    
    def _build_report_prompt(self, analytics_data: Dict[str, Any]) -> str:
        """Build prompt for report generation."""
        context = self._build_analytics_context(analytics_data)
        
        prompt = f"""{context}

TASK: Generate a comprehensive, professional Discord server activity report based on the analytics data above.

REQUIRED STRUCTURE:
You MUST include these sections in this exact order, using ## markdown headers:

## Activity Summary
(2-3 sentences) High-level overview of the period's activity, highlighting the most significant metric or trend.

## Community Highlights
• List 2-3 notable observations about contributor activity
• Mention any standout performers or unusual patterns
• Keep each point to one sentence

## Growth Analysis
• Compare current period to historical average
• Explain the growth rate and what it means
• Mention member retention (joins vs leaves)

## Insights &  Recommendations
• Provide 2-3 specific, actionable suggestions based on the data
• Focus on improving engagement or addressing concerns
• Be constructive and specific (not generic advice)

## Key Takeaways
• 2-3 bullet points summarizing the most important findings
• Each should be ONE concise sentence
• Focus on actionable insights

FORMATTING REQUIREMENTS:
1. Use Discord markdown formatting (**, __, *, ~, `, etc.)
2. Include relevant emojis (📈, 💬, 👥, ⭐, etc.) but don't overuse them
3. Use bullet points (•) for lists, NOT dashes (-)
4. Keep total length under 1200 words
5. Be specific with numbers - reference actual metrics from the data
6. Use an encouraging, professional tone
7. DO NOT include meta-text like "Generated by..." - that will be added automatically

CRITICAL:
- Base ALL observations on the provided data
- If activity is low, acknowledge it positively and offer constructive suggestions
- Reference specific metrics (e.g., "With 1,234 messages from 45 users...")
- Make it actionable for server administrators

Begin your response with: ## Activity Summary"""
        
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
