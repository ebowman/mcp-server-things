# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | ✅ Active support  |
| < 1.0   | ❌ Pre-release     |

## Reporting Security Vulnerabilities

Please report security vulnerabilities to **ebowman@boboco.ie**

### What to Include
- Description of the vulnerability
- Steps to reproduce the issue
- Potential impact assessment
- Suggested fix (if any)

### Response Time
- Initial response within 48 hours
- Security patches prioritized for immediate release

## Security Considerations

### AppleScript Execution
- All user inputs are sanitized before AppleScript execution
- Commands are constructed using parameterized templates
- No remote code execution possible (local-only operation)
- Sandboxed within macOS security model

### Authentication & Data Privacy
- Things 3 authentication tokens stored locally only
- No network requests to external services
- All Things 3 data remains on your Mac
- MCP server runs locally without internet access
- No telemetry or usage tracking

### macOS Permissions
- Requires Automation permission for Things 3
- No elevated privileges needed
- Follows macOS sandboxing guidelines
- User must explicitly grant permissions

### Best Practices
- Store auth tokens in environment variables, not files
- Use `.env` files for local configuration (never commit)
- Regular security audits of AppleScript commands
- Input validation on all MCP tool parameters

## Security Features

- **Local-only operation**: No cloud dependencies
- **Sandboxed execution**: AppleScript runs in macOS sandbox
- **No persistent storage**: Beyond Things 3's own database
- **Minimal dependencies**: Only FastMCP and Pydantic required
- **Type-safe operations**: Pydantic validation on all inputs