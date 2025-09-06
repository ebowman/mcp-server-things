#!/usr/bin/env python3
"""Daily review script for Things 3 todos.

This script provides a comprehensive daily review of your Things 3 tasks,
including today's agenda, overdue items, inbox processing, and recent completions.

Usage:
    python daily_review.py
    python daily_review.py --detailed
    python daily_review.py --export report.txt
"""

import asyncio
import argparse
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Any
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class ThingsDailyReview:
    """Daily review manager for Things 3."""
    
    def __init__(self, detailed: bool = False):
        self.detailed = detailed
        self.report_lines = []
    
    def add_line(self, line: str = "", level: int = 0):
        """Add a line to the report."""
        indent = "  " * level
        full_line = f"{indent}{line}"
        self.report_lines.append(full_line)
        print(full_line)
    
    async def run_review(self) -> str:
        """Run the complete daily review."""
        server_params = StdioServerParameters(
            command="python",
            args=["-m", "things_mcp.main"],
            env={"THINGS_MCP_LOG_LEVEL": "ERROR"}  # Quiet mode
        )
        
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                # Header
                today = datetime.now().strftime("%A, %B %d, %Y")
                self.add_line("Things 3 Daily Review")
                self.add_line("=" * 50)
                self.add_line(f"{today}")
                self.add_line()
                
                # Health check
                await self._check_health(session)
                
                # Today's agenda
                await self._review_today(session)
                
                # Overdue items
                await self._review_overdue(session)
                
                # Inbox processing
                await self._review_inbox(session)
                
                # Recent completions
                await self._review_completions(session)
                
                # Project status
                if self.detailed:
                    await self._review_projects(session)
                
                # Summary and recommendations
                await self._generate_summary(session)
                
                return "\n".join(self.report_lines)
    
    async def _check_health(self, session):
        """Check system health."""
        try:
            health = await session.call_tool("health_check")
            if health.get("things_running"):
                self.add_line("Things 3 is running and accessible")
            else:
                self.add_line("Things 3 is not accessible")
                return
        except Exception as e:
            self.add_line(f"Health check failed: {e}")
            return
        
        self.add_line()
    
    async def _review_today(self, session):
        """Review today's scheduled tasks."""
        self.add_line("TODAY'S AGENDA")
        self.add_line("-" * 20)
        
        try:
            today_todos = await session.call_tool("get_today")
            
            if not today_todos:
                self.add_line("No tasks scheduled for today!")
                self.add_line()
                return
            
            self.add_line(f"{len(today_todos)} tasks scheduled for today:")
            self.add_line()
            
            # Group by project if detailed
            if self.detailed:
                project_groups = {}
                for todo in today_todos:
                    project = todo.get("project_title", "No Project")
                    if project not in project_groups:
                        project_groups[project] = []
                    project_groups[project].append(todo)
                
                for project, todos in project_groups.items():
                    if project != "No Project":
                        self.add_line(f"{project}:", 1)
                    
                    for todo in todos:
                        status_icon = self._get_status_icon(todo)
                        deadline = self._format_deadline(todo)
                        self.add_line(f"{status_icon} {todo['title']}{deadline}", 2 if project != "No Project" else 1)
            else:
                # Simple list
                for i, todo in enumerate(today_todos[:10], 1):
                    status_icon = self._get_status_icon(todo)
                    deadline = self._format_deadline(todo)
                    self.add_line(f"{status_icon} {todo['title']}{deadline}", 1)
                
                if len(today_todos) > 10:
                    self.add_line(f"... and {len(today_todos) - 10} more tasks", 1)
            
        except Exception as e:
            self.add_line(f"Error retrieving today's tasks: {e}", 1)
        
        self.add_line()
    
    async def _review_overdue(self, session):
        """Review overdue tasks."""
        self.add_line("OVERDUE ITEMS")
        self.add_line("-" * 20)
        
        try:
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            overdue = await session.call_tool(
                "search_advanced",
                status="incomplete",
                deadline=yesterday
            )
            
            if not overdue:
                self.add_line("No overdue items!")
                self.add_line()
                return
            
            self.add_line(f"{len(overdue)} overdue tasks need attention:")
            self.add_line()
            
            # Sort by deadline (oldest first)
            overdue_sorted = sorted(
                overdue,
                key=lambda x: x.get("deadline", "9999-12-31")
            )
            
            for todo in overdue_sorted[:10]:
                deadline = todo.get("deadline", "unknown")
                days_overdue = self._calculate_days_overdue(deadline)
                priority_icon = "HIGH" if days_overdue > 7 else "WARN"
                
                self.add_line(
                    f"{priority_icon} {todo['title']} (due: {deadline}, {days_overdue}d overdue)",
                    1
                )
            
            if len(overdue) > 10:
                self.add_line(f"... and {len(overdue) - 10} more overdue tasks", 1)
        
        except Exception as e:
            self.add_line(f"Error retrieving overdue items: {e}", 1)
        
        self.add_line()
    
    async def _review_inbox(self, session):
        """Review inbox items."""
        self.add_line("INBOX PROCESSING")
        self.add_line("-" * 20)
        
        try:
            inbox = await session.call_tool("get_inbox")
            
            if not inbox:
                self.add_line("Inbox is empty - great job!")
                self.add_line()
                return
            
            self.add_line(f"{len(inbox)} items in inbox need processing:")
            self.add_line()
            
            for i, todo in enumerate(inbox[:5], 1):
                creation_date = self._format_creation_date(todo)
                self.add_line(f"{i}. {todo['title']}{creation_date}", 1)
            
            if len(inbox) > 5:
                self.add_line(f"... and {len(inbox) - 5} more items", 1)
            
            self.add_line()
            self.add_line("Consider scheduling or organizing these items", 1)
        
        except Exception as e:
            self.add_line(f"Error retrieving inbox: {e}", 1)
        
        self.add_line()
    
    async def _review_completions(self, session):
        """Review recent completions."""
        self.add_line("RECENT COMPLETIONS")
        self.add_line("-" * 20)
        
        try:
            completed = await session.call_tool("get_logbook", period="1d", limit=10)
            
            if not completed:
                self.add_line("No completions in the last 24 hours")
                self.add_line()
                return
            
            self.add_line(f"{len(completed)} tasks completed in the last 24 hours:")
            self.add_line()
            
            for todo in completed[:5]:
                completion_time = self._format_completion_time(todo)
                self.add_line(f"DONE {todo['title']}{completion_time}", 1)
            
            if len(completed) > 5:
                self.add_line(f"... and {len(completed) - 5} more completions", 1)
        
        except Exception as e:
            self.add_line(f"Error retrieving completions: {e}", 1)
        
        self.add_line()
    
    async def _review_projects(self, session):
        """Review active projects (detailed mode only)."""
        self.add_line("PROJECT STATUS")
        self.add_line("-" * 20)
        
        try:
            projects = await session.call_tool("get_projects", include_items=True)
            
            if not projects:
                self.add_line("No active projects")
                self.add_line()
                return
            
            active_projects = [p for p in projects if p.get("status") == "open"]
            self.add_line(f"{len(active_projects)} active projects:")
            self.add_line()
            
            for project in active_projects[:10]:
                project_todos = project.get("todos", [])
                open_todos = [t for t in project_todos if t.get("status") == "open"]
                completed_todos = [t for t in project_todos if t.get("status") == "completed"]
                
                completion_rate = 0
                if project_todos:
                    completion_rate = len(completed_todos) / len(project_todos) * 100
                
                progress_bar = self._create_progress_bar(completion_rate)
                
                self.add_line(
                    f"{project['title']} {progress_bar} "
                    f"({len(completed_todos)}/{len(project_todos)} tasks)",
                    1
                )
                
                if len(open_todos) > 0:
                    next_task = open_todos[0]
                    self.add_line(f"   Next: {next_task['title']}", 1)
        
        except Exception as e:
            self.add_line(f"Error retrieving projects: {e}", 1)
        
        self.add_line()
    
    async def _generate_summary(self, session):
        """Generate summary and recommendations."""
        self.add_line("SUMMARY & RECOMMENDATIONS")
        self.add_line("-" * 30)
        
        try:
            # Get key metrics
            today_count = len(await session.call_tool("get_today"))
            inbox_count = len(await session.call_tool("get_inbox"))
            
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            overdue_count = len(await session.call_tool(
                "search_advanced", status="incomplete", deadline=yesterday
            ))
            
            completed_count = len(await session.call_tool("get_logbook", period="1d"))
            
            # Priority recommendations
            recommendations = []
            
            if overdue_count > 0:
                recommendations.append(f"HIGH PRIORITY: Address {overdue_count} overdue items first")
            
            if inbox_count > 10:
                recommendations.append(f"Process {inbox_count} inbox items (consider batch processing)")
            elif inbox_count > 0:
                recommendations.append(f"Process {inbox_count} inbox items")
            
            if today_count > 8:
                recommendations.append(f"Today's agenda is busy ({today_count} tasks) - prioritize ruthlessly")
            elif today_count == 0:
                recommendations.append("No tasks scheduled for today - check upcoming items")
            
            if completed_count > 0:
                recommendations.append(f"Great job completing {completed_count} tasks yesterday!")
            
            # Productivity score
            productivity_score = self._calculate_productivity_score(
                today_count, overdue_count, inbox_count, completed_count
            )
            
            score_emoji = "EXCELLENT" if productivity_score >= 8 else "GOOD" if productivity_score >= 6 else "NEEDS IMPROVEMENT"
            
            self.add_line(f"{score_emoji} Productivity Score: {productivity_score}/10")
            self.add_line()
            
            if recommendations:
                self.add_line("Top Recommendations:")
                for rec in recommendations[:3]:
                    self.add_line(rec, 1)
            else:
                self.add_line("You're well organized! Keep up the great work!")
        
        except Exception as e:
            self.add_line(f"Error generating summary: {e}")
        
        self.add_line()
        self.add_line("Have a productive day!")
    
    def _get_status_icon(self, todo: Dict) -> str:
        """Get status icon for a todo."""
        status = todo.get("status", "open")
        return {"open": "TODO", "completed": "DONE", "canceled": "CANCELED"}.get(status, "TODO")
    
    def _format_deadline(self, todo: Dict) -> str:
        """Format deadline information."""
        deadline = todo.get("deadline")
        if not deadline:
            return ""
        
        try:
            deadline_date = datetime.strptime(deadline, "%Y-%m-%d")
            today = datetime.now().date()
            
            if deadline_date.date() == today:
                return " (due today)"
            elif deadline_date.date() < today:
                days_overdue = (today - deadline_date.date()).days
                return f" (overdue {days_overdue}d)"
            else:
                return f" (due {deadline})"
        except:
            return f" (due {deadline})"
    
    def _format_creation_date(self, todo: Dict) -> str:
        """Format creation date information."""
        creation_date = todo.get("creation_date")
        if not creation_date:
            return ""
        
        try:
            created = datetime.fromisoformat(creation_date.replace("Z", "+00:00"))
            days_ago = (datetime.now() - created).days
            
            if days_ago == 0:
                return " (today)"
            elif days_ago == 1:
                return " (yesterday)"
            else:
                return f" ({days_ago}d ago)"
        except:
            return ""
    
    def _format_completion_time(self, todo: Dict) -> str:
        """Format completion time information."""
        completion_date = todo.get("completion_date")
        if not completion_date:
            return ""
        
        try:
            completed = datetime.fromisoformat(completion_date.replace("Z", "+00:00"))
            hours_ago = (datetime.now() - completed).total_seconds() / 3600
            
            if hours_ago < 1:
                return " (just now)"
            elif hours_ago < 24:
                return f" ({int(hours_ago)}h ago)"
            else:
                return f" ({int(hours_ago/24)}d ago)"
        except:
            return ""
    
    def _calculate_days_overdue(self, deadline: str) -> int:
        """Calculate days overdue."""
        try:
            deadline_date = datetime.strptime(deadline, "%Y-%m-%d").date()
            today = datetime.now().date()
            return (today - deadline_date).days
        except:
            return 0
    
    def _create_progress_bar(self, percentage: float, width: int = 10) -> str:
        """Create a text progress bar."""
        filled = int(percentage / 100 * width)
        bar = "█" * filled + "░" * (width - filled)
        return f"[{bar}] {percentage:.0f}%"
    
    def _calculate_productivity_score(self, today: int, overdue: int, inbox: int, completed: int) -> int:
        """Calculate productivity score out of 10."""
        score = 10
        
        # Deduct for overdue items
        score -= min(overdue * 0.5, 3)
        
        # Deduct for large inbox
        if inbox > 20:
            score -= 2
        elif inbox > 10:
            score -= 1
        
        # Deduct for too many today items
        if today > 15:
            score -= 2
        elif today > 10:
            score -= 1
        
        # Add for recent completions
        score += min(completed * 0.5, 2)
        
        return max(1, min(10, int(score)))


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Things 3 Daily Review")
    parser.add_argument("--detailed", action="store_true", help="Show detailed project information")
    parser.add_argument("--export", type=str, help="Export report to file")
    
    args = parser.parse_args()
    
    try:
        reviewer = ThingsDailyReview(detailed=args.detailed)
        report = await reviewer.run_review()
        
        if args.export:
            with open(args.export, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"\nReport exported to {args.export}")
    
    except KeyboardInterrupt:
        print("\nReview cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError running daily review: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())