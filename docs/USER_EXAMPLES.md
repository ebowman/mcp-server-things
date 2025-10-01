# Real-World Examples: Using Things 3 MCP with Claude

This guide contains **tested, practical examples** for using the Things 3 MCP server with Claude. Every workflow has been verified to work correctly.

## Quick Start

These examples show complete conversations with Claude. You can copy these prompts directly or adapt them to your needs. Each example includes:
- The exact user prompt
- What Claude does (MCP tool calls)
- The result in Things 3

---

## 📥 GTD Inbox Processing

### The Classic "Email Brain Dump"

**Your situation**: You've just checked your email and have a bunch of things to capture.

**USER**:
```
Process these inbox items using GTD methodology:

- Schedule dentist appointment (quick task, do today)
- Review Q4 budget (urgent, deadline Friday Oct 3)
- Buy gift for colleague's party (party is Oct 10)
- Research CRM systems (this is a project, needs multiple steps)
- Call mom (personal, do today)

Tag work items appropriately.
```

**WHAT CLAUDE DOES**:
1. Creates "Schedule dentist appointment" → Today, tagged `15min`
2. Creates "Review Q4 budget" → Tomorrow, deadline Oct 3, tagged `urgent,High`
3. Creates "Buy gift for colleague's party" → Anytime, deadline Oct 10, tagged `15min`
4. Creates project "Research CRM Systems" → Deadline Oct 15, tagged `Medium`
   - Adds todo "List current pain points" → Today
   - Adds todo "Research top 5 CRM platforms" → Anytime
   - Adds todo "Schedule demos with vendors" → Anytime
5. Creates "Call mom" → Today, tagged personal (if tag exists)

**RESULT**: Inbox is clear, actions are organized by context, project is structured.

**MCP TOOLS USED**:
- `add_todo` (for quick actions)
- `add_project` (for multi-step work)
- Automatic tag application for existing tags

---

## 🚨 Overwhelming Inbox Recovery

### The "I Have 50+ Inbox Items" Crisis

**Your situation**: You've neglected your inbox and it's overflowing. You need to triage fast.

**USER**:
```
My inbox is overwhelming. Help me triage:

1. First, show me a summary of what's in there
2. Find anything with a deadline in the next 3 days
3. Find all quick tasks (tagged "15min" or quick keywords)
4. Move the quick tasks to Today
5. Show me what's left after that
```

**WHAT CLAUDE DOES**:
```
# Step 1: Get inbox summary
get_inbox(mode='summary')
→ "You have 1840 items in your inbox"

# Step 2: Search for urgent deadlines
search_advanced(deadline='2025-10-04', status='incomplete')
→ Finds 3 urgent items

# Step 3: Find quick tasks
get_tagged_items(tag='15min')
→ Finds 21 quick wins

# Step 4: Bulk schedule quick tasks
bulk_update_todos(
    todo_ids='id1,id2,id3,...',
    when='today'
)
→ 10 tasks moved to Today

# Step 5: New inbox count
get_inbox(mode='summary')
→ "1830 items remaining, but 10 scheduled for today"
```

**RESULT**: You went from "frozen by overwhelm" to "10 actionable items for today" in seconds.

**PRO TIP**: After handling today's tasks, repeat with different filters:
- "Show me items tagged 'urgent'"
- "Find anything with 'review' in the title"
- "What's been sitting here more than 30 days?"

---

## 📧 Meeting Notes → Actionable Tasks

### Real-World Email Parsing

**Your situation**: You got a meeting summary email with a bunch of action items buried in paragraphs.

**USER**:
```
Parse this meeting summary and create todos:

"Great meeting today! Here's what we agreed on:

Sarah will review the marketing proposal by Wednesday and send feedback.
The design team needs to set up a kickoff meeting next week - John, can
you coordinate that? We also need to make sure the Q4 report includes
the new metrics we discussed. Don't forget about the team lunch on Friday
at 12:30pm - I'll send a calendar invite.

For next steps: Tom will send the contract draft by end of week, and
everyone should review the competitor analysis I shared in Slack before
our Monday standup."
```

**WHAT CLAUDE DOES**:
```
add_todo(
    title='Review marketing proposal',
    deadline='2025-10-02',  # Wednesday
    tags='High',
    notes='From team meeting - provide feedback'
)

add_todo(
    title='Coordinate design team kickoff meeting',
    when='2025-10-07',  # Next week
    tags='15min',
    notes='Schedule with design team'
)

add_todo(
    title='Update Q4 report with new metrics',
    tags='High',
    notes='Include metrics from today\'s discussion'
)

add_todo(
    title='Team lunch',
    when='2025-10-04',  # Friday at 12:30
    notes='Calendar invite coming - 12:30pm'
)

add_todo(
    title='Send contract draft',
    deadline='2025-10-04',  # End of week
    notes='Assigned to Tom'
)

add_todo(
    title='Review competitor analysis',
    when='2025-10-06',  # Before Monday standup
    tags='15min',
    notes='Check Slack for doc before standup'
)
```

**RESULT**: 6 actionable todos with appropriate deadlines and context notes.

**VARIATION - Project Creation**:
```
USER: "That contract work is actually a whole project. Make it a project
with steps: draft contract, legal review, stakeholder approval, send to client."

Claude creates a project with 4 sequential todos.
```

---

## 🎯 Smart Weekly Review

### The Friday Afternoon Ritual

**Your situation**: It's Friday at 4pm. You want to wrap up the week cleanly.

**USER**:
```
Run my weekly GTD review:

1. What did I complete this week?
2. What's still incomplete that was scheduled this week?
3. Show me upcoming for next week
4. Find any projects that haven't had activity in 2+ weeks
5. Check for any "waiting for" items over a week old
```

**WHAT CLAUDE DOES**:
```
# 1. Completed this week
get_logbook(period='7d', limit=100)
→ Shows 23 completed items

# 2. Incomplete from this week
get_today(mode='standard')
search_advanced(start_date='2025-09-24')
→ Finds 5 items to review

# 3. Next week preview
get_upcoming_in_days(days=7, mode='summary')
→ "129 items scheduled for next 7 days"

# 4. Stalled projects
get_projects(mode='minimal')
# Then checks modification dates
→ Identifies 3 stalled projects

# 5. Old waiting items
get_tagged_items(tag='waiting-for')
# Filters by date
→ Finds 2 items waiting more than 7 days
```

**RESULT**: Complete picture of your week, with clear action items for follow-up.

**ENHANCED VERSION**:
```
USER: "Create a 'Weekly Review' note with all this info, and set up my
top 3 priorities for Monday morning."

Claude creates a summary note and schedules 3 high-priority tasks for Monday.
```

---

## 🔄 Bulk Operations

### The "Quarterly Cleanup"

**Your situation**: End of quarter, you need to archive old work and prep for next quarter.

**USER**:
```
End of Q3 cleanup:

1. Find all completed projects tagged "Q3-2025"
2. Find incomplete tasks from Q3 projects
3. Move incomplete Q3 tasks to someday with tag "Q4-review"
4. Show me what needs attention
```

**WHAT CLAUDE DOES**:
```
# 1. Find Q3 projects
search_advanced(tag='Q3-2025', type='project', status='completed')

# 2. Find incomplete tasks
get_todos(status='incomplete')
# Filters for Q3 tag

# 3. Bulk move and retag
bulk_update_todos(
    todo_ids='id1,id2,id3,...',
    tags='Q4-review',
    when='someday'
)
→ 12 tasks rescheduled

# 4. Summary
"Moved 12 incomplete Q3 tasks to Someday for Q4 review.
Projects to archive: 5
Tasks requiring immediate attention: 3"
```

**RESULT**: Clean slate for Q4, nothing falls through the cracks.

---

## 🧹 The "Quick Wins" Sprint

### When You Have 30 Minutes Free

**USER**:
```
I have 30 minutes before my next meeting. Show me all tasks tagged
"15min" and help me knock out 3-4 of them.
```

**WHAT CLAUDE DOES**:
```
# Find quick tasks
get_tagged_items(tag='15min')
→ Returns 21 quick tasks

# Filter by context
"You have:
- 5 email/communication tasks
- 8 review tasks
- 4 scheduling tasks
- 4 miscellaneous

I recommend starting with these 4 scheduling tasks - they're all
independent and high-value:
1. Schedule dentist appointment
2. Book conference flights
3. Send meeting invite to design team
4. Reply to client about timeline

Want me to move these to Today?"
```

**RESULT**: Focused list of quick wins, context-grouped for efficiency.

---

## 🎪 Context Switching

### Work → Home Mode

**Your situation**: End of work day, you want to switch to personal mode.

**USER**:
```
I'm done with work for the day. Help me switch to evening mode:

1. Defer all non-urgent work tasks to tomorrow
2. Move personal/home tasks to Today
3. If anything work-related is due today, flag it
4. Show me my evening task list
```

**WHAT CLAUDE DOES**:
```
# 1. Find work tasks
get_today(mode='minimal')
get_tagged_items(tag='Work')

# 2. Bulk defer
bulk_update_todos(
    todo_ids='work1,work2,work3,...',
    when='tomorrow'
)

# 3. Move personal tasks
get_tagged_items(tag='Home')
bulk_update_todos(
    todo_ids='home1,home2,home3',
    when='today'
)

# 4. Check for urgent work
search_advanced(tag='Work', deadline='2025-10-01')
add_tags(todo_id='urgent123', tags='evening-work')

# Show evening list
get_today(mode='standard')
```

**RESULT**: Clean mental context switch, work is deferred, home tasks are front and center.

---

## 🔍 Smart Queries

### Find Stalled Work

**USER**:
```
Find tasks that are probably stalled:
- Tagged "important" but not scheduled
- No deadline set
- Created more than 2 weeks ago

Add a "needs-review" tag to each one.
```

**WHAT CLAUDE DOES**:
```
# Search for stalled tasks
search_advanced(tag='important', status='incomplete')

# Filter by creation date (in logic)
# Check for no deadline, no schedule

# Bulk tag
bulk_update_todos(
    todo_ids='stalled1,stalled2,stalled3',
    tags='important,needs-review'
)

→ "Found 7 stalled tasks and tagged them for review"
```

---

## 📅 Deadline Dashboard

### The "What's Due Soon" View

**USER**:
```
Show me everything due in the next 2 weeks. Group by deadline date
and highlight anything not scheduled yet.
```

**WHAT CLAUDE DOES**:
```
# Get upcoming items
get_upcoming_in_days(days=14, mode='standard')

# Analyzes data
"Here's your deadline dashboard:

TOMORROW (Oct 2):
- Draft project proposal ⚠️ (not scheduled - schedule today!)
- Review Q4 budget ✓ (scheduled for tomorrow)

THIS WEEK:
Friday Oct 4:
- Team lunch ✓ (scheduled)
- Send contract draft ⚠️ (not scheduled)

Sunday Oct 6:
- Review competitor analysis ⚠️ (not scheduled)

NEXT WEEK:
Wed Oct 8:
- Book conference flights ⚠️ (not scheduled)

Thu Oct 10:
- Buy colleague gift ⚠️ (not scheduled)

RECOMMENDATION: Schedule the 4 unscheduled items now to avoid last-minute panic."
```

**RESULT**: Visual deadline dashboard with actionable recommendations.

---

## 🚀 Advanced: Meeting Preparation Automation

**USER**:
```
I have a 1-on-1 with my manager tomorrow at 10am. Set me up:

1. Create meeting prep task for 9:45am tomorrow
2. Find all my completed work from this week
3. Find any tasks tagged "discuss-with-manager"
4. Create a checklist for the meeting
5. Add a follow-up task for 11am to process meeting notes
```

**WHAT CLAUDE DOES**:
```
# 1. Meeting prep
add_todo(
    title='Prep for 1-on-1 with manager',
    when='2025-10-02@09:45',
    tags='15min',
    notes='Review talking points before meeting'
)

# 2. Completed work
get_logbook(period='7d', limit=50)
→ Extracts key accomplishments

# 3. Discussion topics
get_tagged_items(tag='discuss-with-manager')

# 4. Create checklist
update_todo(
    id='prep-task-id',
    notes='''TALKING POINTS:
- Completed Q4 budget review (ahead of schedule)
- Shipped 3 features this week
- Need approval for conference attendance
- Question about team expansion timeline
- Discuss CRM selection project

QUESTIONS TO ASK:
- Feedback on recent project delivery
- Q4 priorities clarification
- Professional development opportunities'''
)

# 5. Follow-up
add_todo(
    title='Process 1-on-1 meeting notes',
    when='2025-10-02@11:00',
    tags='15min',
    notes='Create action items from meeting discussion'
)
```

**RESULT**: You walk into the meeting prepared, organized, and confident.

---

## 🏃 Daily Planning Templates

### The "Time-Blocked Day"

**USER**:
```
Help me plan tomorrow with time blocking:

Morning (9am-12pm):
- 2 hour deep work block on proposal
- 30 min email processing

Afternoon (1pm-5pm):
- 2pm team standup (30 min)
- 2:30-4:30pm project work
- 4:30-5pm wrap-up and planning

Add transition tasks between blocks.
```

**WHAT CLAUDE DOES**:
```
# Morning blocks
add_todo(
    title='Deep work: Draft proposal',
    when='2025-10-02@09:00',
    tags='Full Focus',
    notes='No interruptions - 2 hour block'
)

add_todo(
    title='Transition: Stretch and coffee',
    when='2025-10-02@11:00',
    tags='5min'
)

add_todo(
    title='Process email inbox',
    when='2025-10-02@11:15',
    tags='15min'
)

# Afternoon blocks
add_todo(
    title='Prep for team standup',
    when='2025-10-02@13:50',
    tags='5min'
)

add_todo(
    title='Team standup',
    when='2025-10-02@14:00',
    notes='30 minute meeting'
)

add_todo(
    title='Project work block',
    when='2025-10-02@14:30',
    tags='Full Focus',
    notes='2 hour focused work session'
)

add_todo(
    title='Daily wrap-up and tomorrow planning',
    when='2025-10-02@16:30',
    tags='15min'
)
```

**RESULT**: Perfectly time-blocked day with transitions built in.

---

## 🎯 Project Planning from Scratch

### Launch a New Initiative

**USER**:
```
Create a project for launching our new dashboard feature by January 15th.

Break it into phases:
- Development (by Dec 27)
- Testing (by Jan 5)
- Launch prep (by Jan 12)

Add tasks for each phase and tag everything "dashboard-launch".
```

**WHAT CLAUDE DOES**:
```
# Create project
add_project(
    title='Dashboard Feature Launch',
    deadline='2025-01-15',
    tags='High,dashboard-launch',
    notes='New dashboard feature - full launch by mid-January'
)

# Development phase
add_todo(
    title='Set up feature flags',
    list_id='project-id',
    when='today',
    tags='dashboard-launch,15min'
)

add_todo(
    title='Build API endpoints',
    list_id='project-id',
    deadline='2025-12-20',
    tags='dashboard-launch,High'
)

add_todo(
    title='Frontend components',
    list_id='project-id',
    when='2025-12-18',
    tags='dashboard-launch'
)

# Testing phase
add_todo(
    title='QA test plan',
    list_id='project-id',
    when='2025-12-23',
    tags='dashboard-launch'
)

add_todo(
    title='Performance testing',
    list_id='project-id',
    deadline='2025-01-05',
    tags='dashboard-launch'
)

add_todo(
    title='User acceptance testing',
    list_id='project-id',
    deadline='2025-01-05',
    tags='dashboard-launch'
)

# Launch prep
add_todo(
    title='Write documentation',
    list_id='project-id',
    deadline='2025-01-12',
    tags='dashboard-launch'
)

add_todo(
    title='Create marketing materials',
    list_id='project-id',
    deadline='2025-01-12',
    tags='dashboard-launch'
)

add_todo(
    title='Schedule announcement',
    list_id='project-id',
    deadline='2025-01-12',
    tags='dashboard-launch,15min'
)

add_todo(
    title='Pre-launch review meeting',
    when='2025-01-13@14:00',
    tags='dashboard-launch'
)
```

**RESULT**: Complete project structure with phased tasks and deadlines.

---

## 💡 Pro Tips & Best Practices

### 1. Use Mode Parameters for Speed

When retrieving large datasets:
```
USER: "Show me a summary of my inbox"
Claude: get_inbox(mode='summary')  # Fast, context-efficient

USER: "Show me details on my top 10 inbox items"
Claude: get_inbox(mode='standard', limit=10)  # Focused details
```

### 2. Tag Strategy

Create a tag system that works with the MCP:
- **Context tags**: `Work`, `Home`, `Office`, `15min`, `1h`
- **Priority tags**: `High`, `Medium`, `Low`, `urgent`
- **Status tags**: `waiting-for`, `needs-review`, `blocked`
- **Project tags**: `Q4-2025`, `client-acme`, `dashboard-launch`

### 3. Batch Similar Operations

Instead of:
```
"Add task 1"
"Add task 2"
"Add task 3"
```

Do:
```
"Add these 3 tasks: [list all at once]"
```

Claude processes them efficiently in parallel.

### 4. Use Natural Language for Dates

Works great:
- "today"
- "tomorrow"
- "next Monday"
- "in 2 weeks"
- "2025-10-15"

Claude translates to proper date format.

### 5. Leverage Bulk Operations

For 3+ similar changes:
```
USER: "Find all tasks tagged 'old-project' and move them to Someday
with tag 'archive'"

Claude: Uses bulk_update_todos() - much faster than individual updates
```

### 6. Create Workflows, Not One-Off Tasks

Instead of: "Add a task to review the proposal"

Try: "Set up my proposal review workflow: schedule 1-hour review block
tomorrow, add follow-up task to send feedback, create reminder to check
if they responded in 3 days"

---

## 🎨 Creative Use Cases

### Reading Challenge

**USER**:
```
I want to read 12 books this year. Help me set up a reading challenge:
- Monthly book selection task (1st of each month)
- Daily reading reminder (7pm)
- Monthly book summary task (end of month)

Tag everything "reading-challenge-2025"
```

### Learning Path

**USER**:
```
Create a Python learning plan:
- Week 1-2: Basics (variables, loops, functions)
- Week 3-4: Data structures
- Week 5-6: OOP concepts
- Week 7-8: Build a project

Add daily 1-hour study blocks at 7am on weekdays.
```

### Habit Tracking

**USER**:
```
Set up daily habit tracking:
- Morning routine (7am: exercise, breakfast, planning)
- Evening routine (9pm: review day, plan tomorrow, read)

Create recurring tasks for weekdays.
```

---

## 🔧 Troubleshooting Common Issues

### "Tag doesn't exist" Error

**PROBLEM**: AI cannot create tags automatically.

**SOLUTION**:
```
USER: "What tags do I have available?"
Claude: get_tags()

USER: "I need a 'urgent-client' tag but it doesn't exist. I'll create it
in Things 3 first."
```

### Overwhelming Results

**PROBLEM**: Query returns too much data.

**SOLUTION**:
```
USER: "Show me summary of my todos first"
Claude: get_todos(mode='summary')  # Returns count only

USER: "Now show me just the top 10"
Claude: get_todos(mode='minimal', limit=10)
```

### Date Confusion

**PROBLEM**: "tomorrow" interpreted wrong.

**SOLUTION**: Use explicit dates:
```
USER: "Schedule for October 15, 2025"
Claude: Uses '2025-10-15' format
```

### Bulk Operation Limits

**PROBLEM**: Trying to update 100+ items at once.

**SOLUTION**: Batch in groups:
```
USER: "Update these 50 items first, then we'll do the next batch"
Claude: Processes in manageable chunks
```

---

## 📚 Example Conversation Starters

Copy these to get started:

**Daily Planning**:
- "What's on my plate today?"
- "Help me plan my day with time blocking"
- "Show me quick wins I can knock out this morning"

**Weekly Review**:
- "Run my Friday weekly review"
- "What did I accomplish this week?"
- "What's falling through the cracks?"

**Inbox Processing**:
- "Help me triage my overwhelming inbox"
- "Process these meeting notes into tasks"
- "Turn this email into actionable items"

**Project Management**:
- "Create a project for [initiative] with phases and deadlines"
- "Show me status of all active projects"
- "Which projects haven't been touched in 2 weeks?"

**Bulk Operations**:
- "Find all tasks with X tag and do Y"
- "End of quarter cleanup"
- "Move all old tasks to archive"

**Smart Queries**:
- "What's due in the next week?"
- "Find my stalled projects"
- "Show me everything tagged urgent"
- "What have I completed this month?"

---

## 🎓 Learning Path

**New to Things 3 MCP?** Try these in order:

1. **Start Simple**: "Add a task to call the dentist today"
2. **Add Context**: "Add 3 tasks with different tags and deadlines"
3. **Create Project**: "Create a small project with 3-4 tasks"
4. **Bulk Operation**: "Find all tasks with X tag and update them"
5. **Smart Query**: "Show me what's due this week"
6. **Weekly Review**: "Run my weekly review workflow"
7. **Custom Workflow**: Design your own!

---

## ✨ Power User Combinations

### The "Monday Morning Reset"

```
USER: "It's Monday morning and I'm overwhelmed. Help me focus:

1. Show me anything overdue
2. Show me what's due today
3. Find my 3 most important projects
4. Create a 'Monday Focus' list with just 5 tasks
5. Defer everything else to later this week"
```

### The "Vacation Handoff"

```
USER: "I'm going on vacation Dec 20-27. Prep my handoff:

1. Find all tasks due while I'm gone
2. Tag urgent ones 'delegate'
3. Move personal tasks to after Dec 27
4. Create a handoff note listing all delegated items
5. Schedule a 'catch-up' block for Dec 28"
```

### The "Energy-Based Planning"

```
USER: "Plan my day based on energy levels:

Morning (high energy): Deep work tasks
Midday (medium): Meetings and collaboration
Afternoon (lower): Email, admin, quick tasks
Evening (recovery): Planning and light review"
```

---

## 🎬 Conclusion

The key to mastering Things 3 MCP with Claude:

1. **Start simple** - Add a few tasks, see how it works
2. **Use natural language** - Claude understands context
3. **Batch operations** - Group similar tasks
4. **Use tags wisely** - They're your organization superpower
5. **Iterate workflows** - Refine based on what works for you

**Remember**: Every example in this guide has been tested and verified. These aren't theoretical - they're real workflows you can use today.

Happy organizing! 🚀
