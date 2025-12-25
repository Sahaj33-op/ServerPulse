"""Task monitoring and health check commands for ServerPulse."""

from datetime import datetime, timedelta
from typing import Dict, Any

import discord
from discord import app_commands
from discord.ext import commands

from src.utils.helpers import format_time_duration
from src.utils.logger import LoggerMixin


class TaskMonitoringCommands(commands.Cog, LoggerMixin):
    """Commands for monitoring scheduled task health."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = bot.db_manager
        self.redis = bot.redis_manager
    
    @app_commands.command(name="task-status", description="View status of scheduled tasks")
    @app_commands.default_permissions(administrator=True)
    async def task_status(self, interaction: discord.Interaction) -> None:
        """Show the health and status of all scheduled tasks."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You need administrator permissions to view task status.",
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Task names to monitor
        tasks = [
            "cleanup_task",
            "hourly_reports_task",
            "daily_reports_task",
            "weekly_reports_task"
        ]
        
        embed = discord.Embed(
            title="📊 Scheduled Task Status",
            description="Health monitoring for ServerPulse background tasks",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        
        
        for i, task_name in enumerate(tasks):
            try:
                status_info = await self._get_task_status(task_name)
                embed.add_field(
                    name=f"🔄 {task_name.replace('_', ' ').title()}",
                    value=self._format_task_status(status_info),
                    inline=False
                )
                
                # Add separator between tasks (but not after the last one)
                if i < len(tasks) - 1:
                    embed.add_field(name="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", value="\u200b", inline=False)
                    
            except Exception as e:
                self.logger.error(f"Error getting status for {task_name}: {e}")
                embed.add_field(
                    name=f"❌ {task_name.replace('_', ' ').title()}",
                    value="Error retrieving status",
                    inline=False
                )
                
                # Add separator between tasks (but not after the last one)
                if i < len(tasks) - 1:
                    embed.add_field(name="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", value="\u200b", inline=False)
        
        embed.set_footer(text="Use this to monitor task health and diagnose issues")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    async def _get_task_status(self, task_name: str) -> Dict[str, Any]:
        """Get status information for a specific task."""
        # Get all task metrics from Redis
        last_attempt = await self.redis.get(f"task:{task_name}:last_attempt")
        last_success = await self.redis.get(f"task:{task_name}:last_success")
        last_error = await self.redis.get(f"task:{task_name}:last_error")
        
        success_count = await self.redis.get(f"task:{task_name}:success_count")
        error_count = await self.redis.get(f"task:{task_name}:error_count")
        critical_error_count = await self.redis.get(f"task:{task_name}:critical_error_count")
        
        return {
            'last_attempt': last_attempt,
            'last_success': last_success,
            'last_error': last_error,
            'success_count': int(success_count) if success_count else 0,
            'error_count': int(error_count) if error_count else 0,
            'critical_error_count': int(critical_error_count) if critical_error_count else 0
        }
    
    def _format_task_status(self, status: Dict[str, Any]) -> str:
        """Format task status information for display."""
        lines = []
        
        # Last attempt
        if status['last_attempt']:
            try:
                last_attempt = datetime.fromisoformat(status['last_attempt'])
                time_ago = datetime.utcnow() - last_attempt
                lines.append(f"⏰ Last Run: {format_time_duration(time_ago.total_seconds())} ago")
            except:
                lines.append(f"⏰ Last Run: {status['last_attempt']}")
        else:
            lines.append("⏰ Last Run: Never")
        
        # Last success
        if status['last_success']:
            try:
                last_success = datetime.fromisoformat(status['last_success'])
                time_ago = datetime.utcnow() - last_success
                lines.append(f"✅ Last Success: {format_time_duration(time_ago.total_seconds())} ago")
            except:
                lines.append(f"✅ Last Success: {status['last_success']}")
        else:
            lines.append("✅ Last Success: Never")
        
        # Counts
        total_runs = status['success_count'] + status['critical_error_count']
        if total_runs > 0:
            success_rate = (status['success_count'] / total_runs) * 100
            lines.append(f"📈 Success Rate: {success_rate:.1f}% ({status['success_count']}/{total_runs})")
        else:
            lines.append("📈 Success Rate: No data")
        
        # Errors
        if status['error_count'] > 0:
            lines.append(f"⚠️ Individual Errors: {status['error_count']}")
        
        if status['critical_error_count'] > 0:
            lines.append(f"❌ Critical Errors: {status['critical_error_count']}")
            
        # Last error message
        if status['last_error']:
            error_msg = status['last_error']
            if len(error_msg) > 100:
                error_msg = error_msg[:97] + "..."
            lines.append(f"🔴 Last Error: {error_msg}")
        
        # Health indicator
        if status['critical_error_count'] > status['success_count']:
            lines.insert(0, "🔴 **Status: UNHEALTHY**")
        elif status['last_success'] and not status['last_error']:
            lines.insert(0, "🟢 **Status: HEALTHY**")
        elif status['error_count'] > 0:
            lines.insert(0, "🟡 **Status: DEGRADED**")
        else:
            lines.insert(0, "⚪ **Status: UNKNOWN**")
        
        return "\n".join(lines)
    
    @app_commands.command(name="reset-task-stats", description="Reset task monitoring statistics")
    @app_commands.describe(task="Task to reset (leave empty for all)")
    @app_commands.choices(task=[
        app_commands.Choice(name="All Tasks", value="all"),
        app_commands.Choice(name="Cleanup Task", value="cleanup_task"),
        app_commands.Choice(name="Hourly Reports", value="hourly_reports_task"),
        app_commands.Choice(name="Daily Reports", value="daily_reports_task"),
        app_commands.Choice(name="Weekly Reports", value="weekly_reports_task")
    ])
    @app_commands.default_permissions(administrator=True)
    async def reset_task_stats(self, interaction: discord.Interaction, task: str = "all") -> None:
        """Reset task monitoring statistics."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ You need administrator permissions to reset task stats.",
                ephemeral=True
            )
            return
        
        tasks_to_reset = []
        
        if task == "all":
            tasks_to_reset = [
                "cleanup_task",
                "hourly_reports_task",
                "daily_reports_task",
                "weekly_reports_task"
            ]
        else:
            tasks_to_reset = [task]
        
        for task_name in tasks_to_reset:
            # Clear all metrics except last_attempt (keep for monitoring)
            await self.redis.delete(f"task:{task_name}:last_error")
            await self.redis.delete(f"task:{task_name}:success_count")
            await self.redis.delete(f"task:{task_name}:error_count")
            await self.redis.delete(f"task:{task_name}:critical_error_count")
        
        embed = discord.Embed(
            title="✅ Task Statistics Reset",
            description=f"Successfully reset statistics for: **{task.replace('_', ' ').title()}**",
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="What was cleared:",
            value=(
                "• Error counts\n"
                "• Success counts\n"
                "• Last error messages"
            ),
            inline=False
        )
        
        # Separator
        embed.add_field(name="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", value="\u200b", inline=False)
        
        embed.add_field(
            name="What was kept:",
            value="• Last attempt timestamps\n• Last success timestamps",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TaskMonitoringCommands(bot))
