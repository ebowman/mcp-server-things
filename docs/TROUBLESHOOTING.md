# Troubleshooting Guide

Common issues and solutions for the Things 3 MCP Server.

## 🚨 Common Issues

### Things 3 Integration

#### Permission Denied / Automation Access

**Problem**: System hasn't granted automation permissions

**Symptoms**:
```
error "Not authorized to send Apple events to Things3." number -1743
```

**Solution**:
1. Open **System Settings** → **Privacy & Security**
2. Click **Privacy** tab → **Automation**
3. Find your terminal/IDE in the list
4. Check the box next to **Things3**
5. Restart your terminal/IDE

**Alternative Reset**:
```bash
# Reset automation permissions (requires admin)
sudo tccutil reset AppleEvents com.apple.Terminal
```

#### Things 3 Not Found

**Problem**: Things 3 not installed or not accessible

**Check**:
```bash
# Verify Things 3 is installed
ls -la /Applications/Things3.app

# Test direct AppleScript
osascript -e 'tell application "Things3" to get name'
```

**Solutions**:
1. Install Things 3 from Mac App Store
2. Launch Things 3 manually
3. Verify app name is "Things3" (not "Things 3")

### Claude Desktop Integration

#### Configuration Not Loading

**Problem**: Claude Desktop can't find MCP configuration

**Check Config**:
```bash
# Validate JSON syntax
python -m json.tool ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

**Correct Configuration**:
```json
{
  "mcpServers": {
    "things": {
      "command": "python",
      "args": ["-m", "things_mcp.main"]
    }
  }
}
```

#### MCP Server Failed to Start

**Test Manually**:
```bash
# Verify package installation
python -c "import things_mcp; print('OK')"
```

**Use Absolute Path**:
```json
{
  "mcpServers": {
    "things": {
      "command": "/usr/local/bin/python3",
      "args": ["-m", "things_mcp.main"]
    }
  }
}
```

### Performance Issues

#### Slow Operations

**Solutions**:
1. Restart Things 3 (it can become sluggish)
2. Check available system memory
3. Reduce concurrent operations if needed

#### AppleScript Timeouts

**Increase Timeout**:
```bash
export THINGS_MCP_TIMEOUT=60
```

### Error Messages Reference

| Error | Cause | Solution |
|-------|-------|----------|
| "Can't get..." | Object doesn't exist | Verify item ID in Things 3 |
| "Invalid date format" | Wrong date format | Use YYYY-MM-DD format |
| "Operation failed after 3 retries" | AppleScript failures | Restart Things 3 |

## 🔧 Advanced Diagnostics

### Enable Debug Logging
```bash
export THINGS_MCP_LOG_LEVEL=DEBUG
python -m things_mcp.main
```

### Test AppleScript Directly
```bash
osascript -e 'tell application "Things3" to get name of every to do of list "Today"'
```

## 🆘 Getting Help

### Before Asking for Help
1. Check [GitHub Issues](https://github.com/ebowman/things-applescript-mcp/issues)
2. Review this troubleshooting guide
3. Verify Things 3 and Python are properly installed

### When Requesting Help

Include:
- macOS version
- Python version (`python --version`)
- Things 3 version
- Complete error messages
- Steps to reproduce

### Contact
- **GitHub Issues**: For bugs and technical problems
- **Email**: ebowman@boboco.ie