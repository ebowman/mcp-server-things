# Tag Creation Control API Documentation

## Overview

The Tag Creation Control feature provides fine-grained control over how the Things 3 MCP Server handles non-existing tags when they are referenced in API operations. This feature allows administrators and AI systems to configure the behavior based on their specific needs and security requirements.

## Configuration Options

### Environment Variables

Configure tag creation behavior using environment variables:

```bash
# Tag creation policy (default: CREATE)
THINGS_MCP_TAG_CREATION_POLICY=CREATE|ERROR|WARN|IGNORE

# Maximum number of auto-created tags per operation (default: 10)
THINGS_MCP_MAX_AUTO_CREATED_TAGS=10

# Enable tag creation audit logging (default: false)
THINGS_MCP_AUDIT_TAG_CREATION=true

# Allowed tag patterns (regex, default: all allowed)
THINGS_MCP_ALLOWED_TAG_PATTERNS="^[a-zA-Z0-9_-]+$"

# Restricted tag prefixes (comma-separated, default: none)
THINGS_MCP_RESTRICTED_TAG_PREFIXES="admin,system,internal"
```

### Configuration File

Add to your `config.yaml`:

```yaml
tag_creation:
  policy: CREATE  # CREATE, ERROR, WARN, IGNORE
  max_auto_created_per_operation: 10
  enable_audit_logging: true
  allowed_patterns:
    - "^[a-zA-Z0-9_-]+$"
    - "^[a-zA-Z0-9_.]+$"  # Allow dots
  restricted_prefixes:
    - "admin"
    - "system"
    - "internal"
  auto_approval:
    enable: false
    max_length: 20
    require_alphanumeric: true
```

## Tag Creation Policies

### 1. CREATE (Default)
Automatically creates non-existing tags when referenced.

**Use Cases:**
- AI assistants that need flexible tag management
- Dynamic tagging systems
- Rapid prototyping environments

**Behavior:**
- Missing tags are created automatically
- Returns success with creation details
- No user intervention required

### 2. ERROR
Returns an error when non-existing tags are referenced.

**Use Cases:**
- Strict environments with predefined tag vocabularies
- Production systems requiring explicit tag management
- Compliance-focused deployments

**Behavior:**
- Operation fails if any tag doesn't exist
- Returns detailed error information
- No partial operations

### 3. WARN
Creates tags but logs warnings for tracking.

**Use Cases:**
- Development environments
- Systems requiring audit trails
- Gradual migration to strict tag management

**Behavior:**
- Tags are created with warning logs
- Operations succeed with metadata about created tags
- Provides visibility into tag creation patterns

### 4. IGNORE
Silently skips non-existing tags without creating them.

**Use Cases:**
- Systems where tags are optional metadata
- Importing data with inconsistent tag references
- Fault-tolerant operations

**Behavior:**
- Non-existing tags are omitted from the operation
- No errors or warnings
- Operations proceed with existing tags only

## API Behavior Matrix

### add_todo Endpoint

| Policy | Non-existing Tag | Response | Creates Tag | Includes Warning |
|--------|------------------|----------|-------------|------------------|
| CREATE | "urgent"         | Success  | Yes         | No               |
| ERROR  | "urgent"         | Error    | No          | No               |
| WARN   | "urgent"         | Success  | Yes         | Yes              |
| IGNORE | "urgent"         | Success  | No          | No               |

### add_tags Endpoint

| Policy | Non-existing Tag | Response | Creates Tag | Includes Warning |
|--------|------------------|----------|-------------|------------------|
| CREATE | "priority"       | Success  | Yes         | No               |
| ERROR  | "priority"       | Error    | No          | No               |
| WARN   | "priority"       | Success  | Yes         | Yes              |
| IGNORE | "priority"       | Partial  | No          | No               |

## Response Format Changes

### Success Response with CREATE Policy

```json
{
  "success": true,
  "todo_id": "ABC123",
  "title": "Review documentation",
  "tags": ["review", "documentation", "urgent"],
  "tag_operations": {
    "existing_tags": ["review", "documentation"],
    "created_tags": ["urgent"],
    "total_tags": 3
  },
  "message": "Todo created successfully. Created new tag: urgent"
}
```

### Success Response with WARN Policy

```json
{
  "success": true,
  "todo_id": "ABC123",
  "title": "Review documentation",
  "tags": ["review", "documentation", "urgent"],
  "tag_operations": {
    "existing_tags": ["review", "documentation"],
    "created_tags": ["urgent"],
    "total_tags": 3
  },
  "warnings": [
    {
      "type": "TAG_CREATED",
      "message": "Created new tag 'urgent' - consider using existing tags",
      "tag": "urgent",
      "timestamp": "2024-08-10T10:30:00Z"
    }
  ],
  "message": "Todo created successfully. Warning: Created new tag: urgent"
}
```

### Error Response with ERROR Policy

```json
{
  "success": false,
  "error": "TAG_NOT_FOUND",
  "message": "Cannot create todo: tags do not exist",
  "details": {
    "non_existing_tags": ["urgent", "priority"],
    "existing_tags": ["review", "documentation"],
    "policy": "ERROR"
  },
  "suggestions": {
    "available_similar_tags": ["important", "high-priority"],
    "create_tags_first": [
      "Use add_tag endpoint to create tags first",
      "Or change policy to CREATE mode"
    ]
  }
}
```

### Partial Success Response with IGNORE Policy

```json
{
  "success": true,
  "todo_id": "ABC123",
  "title": "Review documentation",
  "tags": ["review", "documentation"],
  "tag_operations": {
    "existing_tags": ["review", "documentation"],
    "ignored_tags": ["urgent", "priority"],
    "applied_tags": 2,
    "ignored_count": 2
  },
  "message": "Todo created successfully. Ignored 2 non-existing tags"
}
```

## Endpoint-Specific Behavior

### add_todo

```json
{
  "title": "Review project",
  "tags": "review,urgent,priority",
  "notes": "High priority review needed"
}
```

**CREATE Policy:**
- Creates todo with all tags
- Auto-creates "urgent" and "priority" if they don't exist
- Returns success with tag creation details

**ERROR Policy:**
- Fails if "urgent" or "priority" don't exist
- Returns error with list of missing tags
- No todo is created

**WARN Policy:**
- Creates todo and missing tags
- Logs warnings for created tags
- Returns success with warning metadata

**IGNORE Policy:**
- Creates todo with only existing tags
- Silently ignores "urgent" and "priority"
- Returns success with applied tags only

### add_tags

```json
{
  "todo_id": "ABC123",
  "tags": "urgent,priority,review"
}
```

**Policy Behaviors:**
- **CREATE**: Adds all tags, creating missing ones
- **ERROR**: Fails if any tag doesn't exist
- **WARN**: Adds all tags with warnings for created ones
- **IGNORE**: Adds only existing tags

### update_todo

When updating tags on existing todos:

```json
{
  "id": "ABC123",
  "tags": "updated,review,new-tag"
}
```

**Policy Behaviors:**
- **CREATE**: Replaces tags, creating "new-tag" if needed
- **ERROR**: Fails if "new-tag" doesn't exist, keeps original tags
- **WARN**: Updates tags, warns about "new-tag" creation
- **IGNORE**: Updates with existing tags only, omits "new-tag"

## Decision Tree for Policy Selection

```
┌─ AI System or Automated Process?
│  ├─ Yes ──► WARN (track auto-created tags)
│  └─ No ───┐
│           │
├─ Strict Environment?
│  ├─ Yes ──► ERROR (prevent unexpected tags)
│  └─ No ───┐
│           │
├─ Tags Optional?
│  ├─ Yes ──► IGNORE (flexible tagging)
│  └─ No ───┐
│           │
└─ Default ──► CREATE (user-friendly)
```

## Best Practices by Use Case

### For AI Systems
**Recommended Policy:** WARN
```yaml
tag_creation:
  policy: WARN
  enable_audit_logging: true
  max_auto_created_per_operation: 5
```

**Benefits:**
- Tracks AI-generated tags for analysis
- Allows automatic tag creation for flexibility
- Provides audit trail for tag management

### For Production Environments
**Recommended Policy:** ERROR
```yaml
tag_creation:
  policy: ERROR
  allowed_patterns: ["^[a-zA-Z0-9_-]{1,20}$"]
  restricted_prefixes: ["admin", "system"]
```

**Benefits:**
- Prevents unauthorized tag creation
- Maintains clean tag vocabulary
- Enforces explicit tag management

### For Data Import/Migration
**Recommended Policy:** IGNORE
```yaml
tag_creation:
  policy: IGNORE
  enable_audit_logging: true
```

**Benefits:**
- Handles inconsistent tag references gracefully
- Avoids creating unwanted tags during import
- Logs ignored tags for cleanup

### For Development
**Recommended Policy:** CREATE
```yaml
tag_creation:
  policy: CREATE
  max_auto_created_per_operation: 20
```

**Benefits:**
- Maximum flexibility for testing
- No blocking on tag creation
- Rapid prototyping support

## Migration Guide

### From Auto-Creation to Strict Control

1. **Assessment Phase**
   ```bash
   # Enable audit logging to understand current tag usage
   export THINGS_MCP_TAG_CREATION_POLICY=WARN
   export THINGS_MCP_AUDIT_TAG_CREATION=true
   ```

2. **Analysis**
   - Review audit logs to identify frequently created tags
   - Create standardized tags in advance
   - Document approved tag vocabulary

3. **Transition**
   ```bash
   # Switch to error mode
   export THINGS_MCP_TAG_CREATION_POLICY=ERROR
   ```

4. **Monitoring**
   - Monitor error rates and patterns
   - Create missing tags that are valid
   - Update documentation and training

### From Strict to Flexible

1. **Gradual Relaxation**
   ```bash
   # Start with warnings
   export THINGS_MCP_TAG_CREATION_POLICY=WARN
   ```

2. **Monitor Usage**
   - Track created tags for quality
   - Identify useful auto-created tags
   - Clean up low-value tags

3. **Full Flexibility**
   ```bash
   # Enable full auto-creation
   export THINGS_MCP_TAG_CREATION_POLICY=CREATE
   ```

## Troubleshooting Guide

### Common Issues

#### "Tag creation failed" with CREATE policy
**Causes:**
- Tag name contains invalid characters
- Tag name exceeds maximum length
- System resource constraints

**Solutions:**
- Check `allowed_patterns` configuration
- Verify tag name length limits
- Review system resources

#### High tag creation volume with AI systems
**Symptoms:**
- Many similar tags being created
- Tag vocabulary becoming unwieldy
- Performance impact from tag operations

**Solutions:**
- Switch to WARN policy for visibility
- Implement tag normalization pre-processing
- Set lower `max_auto_created_per_operation`

#### Partial failures with ERROR policy
**Symptoms:**
- Operations failing unexpectedly
- Users frustrated by tag requirements
- Workflow interruptions

**Solutions:**
- Pre-create commonly used tags
- Provide tag suggestion UI
- Consider switching to WARN policy temporarily

#### Tags ignored silently with IGNORE policy
**Symptoms:**
- Expected tags not appearing
- Inconsistent tagging
- Lost tag information

**Solutions:**
- Enable audit logging to track ignored tags
- Review and create important missing tags
- Consider WARN policy for better visibility

### Debugging Commands

#### Check Current Policy
```bash
curl -X GET "http://localhost:8080/health_check" | jq '.tag_creation_policy'
```

#### List Created Tags in Last Hour
```bash
curl -X GET "http://localhost:8080/audit/created_tags?since=1h"
```

#### Test Tag Creation
```bash
curl -X POST "http://localhost:8080/test_tag_creation" \
  -H "Content-Type: application/json" \
  -d '{"tags": ["test-tag-1", "test-tag-2"]}'
```

## Security Considerations

### Tag Name Validation
- Implement strict patterns for tag names
- Prevent injection attacks through tag names
- Limit tag name length to prevent resource exhaustion

### Audit Requirements
- Log all tag creation activities
- Include user/system context in logs
- Implement log rotation and retention policies

### Access Control
- Consider role-based tag creation permissions
- Implement tag namespace restrictions
- Monitor for suspicious tag creation patterns

## Performance Impact

### CREATE Policy
- **Latency**: +50-100ms per new tag
- **Memory**: Minimal impact
- **Disk**: Audit logs grow if enabled

### ERROR Policy
- **Latency**: Fastest (no tag creation)
- **Memory**: Minimal impact
- **Disk**: Error logs only

### WARN Policy
- **Latency**: Same as CREATE
- **Memory**: Minimal impact
- **Disk**: Higher log volume

### IGNORE Policy
- **Latency**: Minimal overhead
- **Memory**: Minimal impact
- **Disk**: Audit logs if enabled

## Examples

### Python Client with Different Policies

```python
import os
import requests

# Configure policy
os.environ['THINGS_MCP_TAG_CREATION_POLICY'] = 'WARN'

client = ThingsMCPClient()

# This will create tags with warnings
result = client.add_todo(
    title="Review documentation",
    tags=["review", "urgent", "new-tag"],
    notes="Important review task"
)

print(f"Created todo: {result['todo_id']}")
print(f"Created tags: {result['tag_operations']['created_tags']}")
if 'warnings' in result:
    for warning in result['warnings']:
        print(f"Warning: {warning['message']}")
```

### Error Handling by Policy

```python
def handle_add_todo(title, tags, policy):
    try:
        result = client.add_todo(title=title, tags=tags)
        return result
    except TagNotFoundError as e:
        if policy == 'ERROR':
            print(f"Tags don't exist: {e.missing_tags}")
            print(f"Suggestions: {e.suggestions}")
            return None
        else:
            raise
```

### Configuration Validation

```python
def validate_tag_config():
    config = load_config()
    
    if config.tag_creation.policy == 'ERROR':
        # Ensure tag vocabulary is well-defined
        existing_tags = client.get_tags()
        if len(existing_tags) < 10:
            print("WARNING: Few tags exist for ERROR policy")
    
    if config.tag_creation.max_auto_created_per_operation > 20:
        print("WARNING: High auto-creation limit may impact performance")
```

## Conclusion

The Tag Creation Control feature provides flexible, configurable behavior for handling non-existing tags in the Things 3 MCP Server. By choosing the appropriate policy and configuration for your use case, you can ensure optimal behavior for AI systems, production environments, and development workflows while maintaining security and performance requirements.

For additional support or questions about tag creation control, please refer to the main API documentation or submit an issue to the project repository.