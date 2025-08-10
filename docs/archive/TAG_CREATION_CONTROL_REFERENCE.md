# Tag Creation Control Quick Reference

## Policy Decision Matrix

| Scenario | Recommended Policy | Configuration | Benefits | Considerations |
|----------|-------------------|---------------|----------|----------------|
| **AI/Claude Integration** | `WARN` | `enable_audit_logging: true`<br>`max_auto_created_per_operation: 5` | • Tracks AI tag patterns<br>• Flexible for AI creativity<br>• Audit trail for analysis | • Higher log volume<br>• Requires log monitoring |
| **Production Environment** | `ERROR` | `allowed_patterns: strict`<br>`restricted_prefixes: ["admin", "sys"]` | • Prevents tag pollution<br>• Maintains clean vocabulary<br>• Explicit control | • May block valid operations<br>• Requires pre-created tags |
| **Development/Testing** | `CREATE` | `max_auto_created_per_operation: 20`<br>`enable_debug_logging: true` | • Maximum flexibility<br>• No operation blocking<br>• Rapid prototyping | • Can create many tags<br>• Needs cleanup |
| **Data Migration** | `IGNORE` | `enable_audit_logging: true`<br>Log ignored tags for cleanup | • Fault tolerant<br>• Handles inconsistent data<br>• No unwanted tag creation | • May lose tag information<br>• Requires post-processing |
| **Compliance/Strict** | `ERROR` | Very restrictive patterns<br>Audit all operations | • Full control<br>• Compliance ready<br>• No surprises | • May be too restrictive<br>• High maintenance |
| **Learning/Analysis** | `WARN` | `enable_audit_logging: true`<br>Analyze patterns over time | • Data-driven decisions<br>• Gradual transition<br>• Pattern recognition | • Requires analysis work<br>• Temporary solution |

## Configuration Templates

### AI Assistant (Recommended for Claude)
```yaml
tag_creation:
  policy: WARN
  max_auto_created_per_operation: 5
  enable_audit_logging: true
  allowed_patterns:
    - "^[a-zA-Z0-9_-]{1,30}$"
  restricted_prefixes:
    - "admin"
    - "system"
  max_tag_length: 30
```

```bash
# Environment variables
export THINGS_MCP_TAG_CREATION_POLICY=warn
export THINGS_MCP_TAG_MAX_AUTO_CREATED_PER_OPERATION=5
export THINGS_MCP_TAG_ENABLE_AUDIT_LOGGING=true
export THINGS_MCP_TAG_RESTRICTED_PREFIXES="admin,system"
```

### Production Environment
```yaml
tag_creation:
  policy: ERROR
  max_auto_created_per_operation: 0
  enable_audit_logging: true
  allowed_patterns:
    - "^[a-zA-Z][a-zA-Z0-9_-]{0,19}$"  # Start with letter, max 20 chars
  restricted_prefixes:
    - "admin"
    - "system"
    - "internal"
    - "temp"
  case_sensitivity: false
```

### Development Environment
```yaml
tag_creation:
  policy: CREATE
  max_auto_created_per_operation: 50
  enable_audit_logging: false
  allowed_patterns:
    - ".*"  # Allow everything
  restricted_prefixes: []
  max_tag_length: 100
```

### Migration/Import
```yaml
tag_creation:
  policy: IGNORE
  max_auto_created_per_operation: 0
  enable_audit_logging: true
  # Log what gets ignored for later analysis
```

## Response Format Examples

### CREATE Policy Response
```json
{
  "success": true,
  "todo_id": "ABC123",
  "title": "Review documentation", 
  "tags": ["review", "urgent", "documentation"],
  "tag_operations": {
    "existing_tags": ["review", "documentation"],
    "created_tags": ["urgent"],
    "ignored_tags": [],
    "total_applied": 3,
    "total_created": 1,
    "total_ignored": 0
  },
  "message": "Todo created successfully. Created new tag: urgent"
}
```

### ERROR Policy Response (Error)
```json
{
  "success": false,
  "error": "TAG_NOT_FOUND",
  "message": "Tags do not exist: ['urgent', 'priority']",
  "details": {
    "non_existing_tags": ["urgent", "priority"],
    "existing_tags": ["review", "documentation"], 
    "policy": "error"
  },
  "suggestions": {
    "available_similar_tags": {
      "urgent": ["important", "high-priority"],
      "priority": ["high-priority", "low-priority"]
    },
    "create_tags_first": [
      "Use add_tag endpoint to create tags first",
      "Or change policy from ERROR to CREATE mode"
    ]
  }
}
```

### WARN Policy Response
```json
{
  "success": true,
  "todo_id": "ABC123",
  "title": "Review documentation",
  "tags": ["review", "urgent", "documentation"],
  "tag_operations": {
    "existing_tags": ["review", "documentation"],
    "created_tags": ["urgent"],
    "ignored_tags": [],
    "total_applied": 3,
    "total_created": 1,
    "total_ignored": 0
  },
  "warnings": [
    {
      "type": "TAG_CREATED",
      "message": "Auto-created tag 'urgent' - consider using existing tags",
      "tag": "urgent",
      "timestamp": "2024-08-10T10:30:00Z"
    }
  ],
  "message": "Todo created successfully. Warning: Created new tag: urgent"
}
```

### IGNORE Policy Response
```json
{
  "success": true,
  "todo_id": "ABC123", 
  "title": "Review documentation",
  "tags": ["review", "documentation"],
  "tag_operations": {
    "existing_tags": ["review", "documentation"],
    "created_tags": [],
    "ignored_tags": ["urgent", "priority"],
    "total_applied": 2,
    "total_created": 0,
    "total_ignored": 2
  },
  "message": "Todo created successfully. Ignored 2 non-existing tags"
}
```

## Common Patterns & Restrictions

### Tag Name Patterns

#### Alphanumeric Only
```yaml
allowed_patterns:
  - "^[a-zA-Z0-9]+$"
```

#### Alphanumeric with Hyphens/Underscores
```yaml
allowed_patterns:
  - "^[a-zA-Z0-9_-]+$"
```

#### Allow Dots (for hierarchical tags)
```yaml
allowed_patterns:
  - "^[a-zA-Z0-9._-]+$"
```

#### Must Start with Letter
```yaml
allowed_patterns:
  - "^[a-zA-Z][a-zA-Z0-9_-]*$"
```

#### Length Constraints
```yaml
allowed_patterns:
  - "^[a-zA-Z0-9_-]{3,20}$"  # 3-20 characters
```

### Common Restricted Prefixes
```yaml
restricted_prefixes:
  - "admin"      # Administrative tags
  - "system"     # System-generated tags  
  - "internal"   # Internal use only
  - "temp"       # Temporary tags
  - "test"       # Testing tags
  - "debug"      # Debug tags
  - "auto"       # Auto-generated tags
```

## API Endpoint Behavior Summary

| Endpoint | CREATE | ERROR | WARN | IGNORE |
|----------|--------|-------|------|--------|
| `add_todo` | Creates missing tags | Fails if any tag missing | Creates + warns | Uses existing only |
| `add_tags` | Creates missing tags | Fails if any tag missing | Creates + warns | Adds existing only |
| `update_todo` | Creates missing tags | Fails if any tag missing | Creates + warns | Updates with existing only |
| `add_project` | Creates missing tags | Fails if any tag missing | Creates + warns | Uses existing only |

## Monitoring & Troubleshooting

### Key Metrics to Monitor

#### Tag Creation Volume
```bash
# Count auto-created tags per hour
grep "Auto-created tags" logs/app.log | 
  grep "$(date '+%Y-%m-%d %H')" | 
  wc -l
```

#### Most Common Created Tags
```bash
# Analyze audit logs for patterns
grep "TAG_CREATED" logs/audit.log | 
  grep -o "tag.*" | 
  sort | uniq -c | sort -rn | head -10
```

#### Policy Violations
```bash
# Count ERROR policy rejections
grep "TAG_NOT_FOUND" logs/app.log | 
  grep "$(date '+%Y-%m-%d')" | 
  wc -l
```

### Health Check Extensions

Add to health check endpoint:
```json
{
  "server_status": "healthy",
  "tag_creation": {
    "policy": "warn",
    "auto_created_today": 15,
    "policy_violations_today": 3,
    "most_created_tags": ["urgent", "important", "review"]
  }
}
```

## Migration Checklist

### From Auto-Creation to Strict Control

- [ ] Enable WARN policy with audit logging
- [ ] Run for 1-2 weeks to collect data
- [ ] Analyze most commonly created tags  
- [ ] Pre-create approved tags in Things
- [ ] Test ERROR policy in non-production
- [ ] Update documentation and user guides
- [ ] Switch to ERROR policy
- [ ] Monitor error rates and user feedback

### From Strict to Flexible

- [ ] Document current approved tag vocabulary
- [ ] Switch to WARN policy first
- [ ] Monitor tag creation quality
- [ ] Adjust patterns and restrictions based on data
- [ ] Consider CREATE policy if appropriate
- [ ] Update user training materials

## Best Practices

### For AI Systems
1. Start with WARN policy to understand patterns
2. Set reasonable auto-creation limits (5-10 tags)
3. Use descriptive patterns to maintain quality
4. Monitor and analyze created tags regularly
5. Provide feedback to AI about preferred tags

### For Production Systems
1. Use ERROR policy for maximum control
2. Pre-create a comprehensive tag vocabulary
3. Document tag naming conventions
4. Implement tag approval workflows
5. Regular tag cleanup and maintenance

### for Development
1. Use CREATE policy for flexibility
2. Set high auto-creation limits
3. Regular cleanup of test tags
4. Document tag categories and purposes
5. Consider tag migration tools

This quick reference provides the essential information needed to configure and use the Tag Creation Control feature effectively.