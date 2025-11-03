**ServerPulse** — Open Source Discord Analytics Bot
Real-time insights & AI-powered summaries, directly in Discord

***

## Overview

ServerPulse is an open source Discord bot that delivers **real-time server analytics** and **AI-generated insights** without external dashboards. Admins get instant alerts, activity leaderboards, and weekly summaries—all inside Discord channels.

**Key differentiator**: AI-native design with multi-provider support (Gemini, OpenAI, Grok, OpenRouter). No locked-in APIs—bring your own keys.

***

## Core Features

### ⚡ Real-Time Monitoring
- Tracks messages, joins, leaves, reactions across whitelisted channels
- Instant alerts for unusual activity (join raids, mass deletions, engagement drops)
- Auto-posts to dedicated `#serverpulse-updates` channel

### 🏆 Activity Leaderboards
- `/topmessagers [24h|7d|30d|all]` — most active members by message count
- `/leaderboard #channel` — channel-specific rankings
- Live updates without manual refresh

### 🧠 AI-Powered Insights
- Weekly "Pulse Report" with sentiment analysis, engagement trends, and admin suggestions
- Pluggable AI adapter supporting multiple providers (Gemini, OpenAI, OpenRouter, Grok)
- Per-guild provider selection with automatic fallback on rate limits
- **Privacy-first**: only counts and sanitized summaries analyzed—no raw message content stored

### 📊 Automated Digest System
- Configurable frequency: hourly, daily, weekly, or disabled
- Posts summaries with top users, busiest channels, emoji trends
- AI-generated actionable recommendations ("Host events Fridays at 8 PM—peak activity time")

### 🔒 Privacy & Data Control
- Admins whitelist channels via `/add-collect-channel` (opt-in tracking)
- 90-day retention policy (configurable)
- No message content stored—only metadata (counts, timestamps, user IDs)
- `/export-report` for GDPR compliance

***

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| **Language** | Python 3.11+ | Mature Discord ecosystem, easy async |
| **Discord Library** | discord.py v2.4+ | Industry standard, slash commands built-in |
| **Database** | MongoDB 6.0+ | Schema flexibility, one-command setup via Atlas free tier |
| **Task Scheduler** | discord.ext.tasks | Native to discord.py, handles reconnects automatically |
| **AI Integration** | Unified adapter | Abstracts Gemini/OpenAI/OpenRouter/Grok APIs |
| **Deployment** | Self-hosted | VPS, Raspberry Pi, local machine—anywhere Python runs |

***

## Commands Reference

| Command | Description |
|---------|-------------|
| `/setup` | Initial bot configuration wizard |
| `/set-update-channel #channel` | Choose where bot posts reports |
| `/add-collect-channel #channel` | Enable tracking for channel |
| `/remove-collect-channel #channel` | Disable tracking |
| `/topmessagers [period]` | Show activity leaderboard |
| `/leaderboard #channel` | Channel-specific stats |
| `/toggle-alert <type> <on/off>` | Configure alert types (raid, drop, deletion) |
| `/set-digest <frequency>` | Set report schedule (hourly/daily/weekly/none) |
| `/ai-provider set <provider>` | Choose AI model (gemini/openai/grok/openrouter) |
| `/ai-provider key <api_key>` | Store AI API key (encrypted in DB) |
| `/export-report <format>` | Download CSV/JSON data export |

***

## Installation

### Prerequisites
- Python 3.11+
- MongoDB (local or MongoDB Atlas free tier)
- Discord bot token ([Discord Developer Portal](https://discord.com/developers/applications))
- AI API key (optional, for summaries)

### Quick Start

```bash
# Clone repository
git clone https://github.com/sahaj33-op/serverpulse.git
cd serverpulse

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your bot token and MongoDB URI

# Run bot
python -m serverpulse
```

### MongoDB Setup (Free)

1. Create [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register) account (no credit card)
2. Create free cluster (512MB storage)
3. Add IP whitelist: `0.0.0.0/0` (allow all) or your server IP
4. Get connection string: `mongodb+srv://user:pass@cluster.mongodb.net/`
5. Paste into `.env` as `MONGODB_URI`

***

## Architecture

### Database Collections

**guild_settings**
```python
{
  "guild_id": int,
  "update_channel_id": int,
  "whitelisted_channels": [int],
  "alerts_enabled": {"raid": bool, "drop": bool, "deletion": bool},
  "digest_frequency": str,  # "hourly", "daily", "weekly", "none"
  "ai_provider": str,  # "gemini", "openai", "grok", "openrouter"
  "ai_key_encrypted": str
}
```

**hourly_metrics**
```python
{
  "guild_id": int,
  "channel_id": int,
  "timestamp": datetime,
  "message_count": int,
  "reaction_count": int,
  "unique_users": [int]
}
```

**leaderboard_cache**
```python
{
  "guild_id": int,
  "period": str,  # "24h", "7d", "30d", "all"
  "rankings": [{"user_id": int, "count": int}],
  "last_updated": datetime
}
```

**ai_summaries**
```python
{
  "guild_id": int,
  "period": str,
  "summary_text": str,
  "generated_at": datetime,
  "provider": str,
  "token_count": int
}
```

### AI Adapter Pattern

Unified interface for swapping AI providers:

```python
class AIProvider(ABC):
    @abstractmethod
    async def generate_summary(self, metrics: dict) -> str:
        pass

class GeminiProvider(AIProvider): ...
class OpenAIProvider(AIProvider): ...
class GroqProvider(AIProvider): ...
```

Per-guild provider selection with automatic fallback on rate limits. Caches recent summaries to reduce API costs.

***

## Alert System

### Thresholds (Configurable per Guild)

| Alert Type | Default Trigger | Customizable |
|-----------|----------------|--------------|
| **Join Raid** | 10+ joins in 60 seconds | Yes |
| **Activity Drop** | 50% decrease vs 24h average | Yes |
| **Mass Deletion** | 5+ deletes in 30 seconds | Yes |
| **Voice Surge** | 3x increase in VC users | Yes |

Alerts auto-post to updates channel with:
- Event type and severity
- Affected channels/users (anonymized if needed)
- Timestamp and duration
- Context (e.g., "Usually 50 messages/hour, now 15")

***

## Privacy & Compliance

**What We Store:**
- Message counts, timestamps, channel/user IDs
- Reaction counts and emoji types
- Join/leave events
- AI summaries (sanitized, no raw content)

**What We DON'T Store:**
- Message text content
- Attachments or embeds
- Voice chat audio
- DMs or private channels (unless explicitly whitelisted)

**Retention:**
- Raw metrics: 90 days (configurable)
- Leaderboards: 30 days
- AI summaries: 180 days
- Exports available anytime via `/export-report`

***

## Contributing

We welcome contributions! Priority areas:

- Additional AI provider integrations (Anthropic Claude, Cohere)
- Advanced analytics (engagement scoring, churn prediction)
- Web dashboard (optional companion app)
- Localization (non-English language support)

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

***

## Roadmap

**v1.0 (Current)**
- ✅ Real-time tracking & alerts
- ✅ Leaderboards & digest system
- ✅ Multi-provider AI adapter

**v1.1 (Next 3 months)**
- Voice channel analytics
- Custom alert threshold configuration
- Historical trend comparisons

**v2.0 (Future)**
- AI chatbot mode (`/askpulse "Why is engagement down?"`)
- Engagement goal predictions
- Multi-server dashboard (manage 10+ guilds)

***

## License

MIT License — see [LICENSE](LICENSE) for details.

***

## Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/serverpulse/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/serverpulse/discussions)
- **Discord**: [Join our support server](https://discord.gg/yourlink)

***

**ServerPulse** — Your server's AI brain, fully open source.
No dashboards, no vendor lock-in — just smart insights where your community lives.
