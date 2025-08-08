# Troubleshooting Guide

Common issues and solutions for the Things 3 MCP Server.

## 📋 Quick Diagnostics

Run our built-in diagnostic tool first:

```bash
# Comprehensive health check
python -m things_mcp.main --health-check

# Test AppleScript connectivity  
python -m things_mcp.main --test-applescript

# Verify Claude Desktop configuration
python -m things_mcp.main --verify-config
```

## 🚨 Common Issues

### Installation Problems

#### "Command not found: python"

**Problem**: Python not installed or not in PATH

**Solution**:
```bash
# macOS - Install Python via Homebrew
brew install python

# Or download from python.org
# Then verify installation
python --version
```

#### "No module named 'things_mcp'"

**Problem**: Package not installed or wrong Python environment

**Solutions**:
```bash
# Option 1: Reinstall package
pip uninstall things-mcp-server
pip install things-mcp-server

# Option 2: Check virtual environment
which python
pip list | grep things

# Option 3: Install in development mode
cd /path/to/things-mcp-server
pip install -e .
```

#### Permission denied during installation

**Problem**: Insufficient permissions to install packages

**Solution**:
```bash
# Use user installation
pip install --user things-mcp-server

# Or create virtual environment
python -m venv mcp-env
source mcp-env/bin/activate
pip install things-mcp-server
```

### Things 3 Integration Issues

#### "Things 3 not found" or "Application not running"

**Problem**: Things 3 not installed or not accessible

**Diagnostics**:
```bash
# Check if Things 3 is installed
ls -la /Applications/Things3.app

# Check if Things 3 is running
ps aux | grep -i things

# Test direct AppleScript
osascript -e 'tell application "Things3" to get name'
```

**Solutions**:
1. **Install Things 3** from Mac App Store
2. **Launch Things 3** manually
3. **Verify app name** (should be "Things3", not "Things 3")

#### Permission denied / Automation access

**Problem**: System hasn't granted automation permissions

**Symptoms**:
```
error "Application isn't running." number -600 from application "Things3"
error "Not authorized to send Apple events to Things3." number -1743
```

**Solution**:
1. Open **System Preferences** → **Security & Privacy**
2. Click **Privacy** tab
3. Select **Automation** from sidebar  
4. Find your terminal/IDE in the list
5. Check the box next to **Things3**
6. Restart your terminal/IDE

**Alternative Reset Method**:
```bash
# Reset automation permissions (requires admin)
sudo tccutil reset AppleEvents com.apple.Terminal
# Then retry - you'll be prompted for permission
```

#### AppleScript timeout errors

**Problem**: Operations taking too long

**Symptoms**:
```
AppleScript timeout after 30 seconds
```

**Solutions**:
```bash
# Increase timeout
export THINGS_MCP_TIMEOUT=60
python -m things_mcp.main

# Or use command line flag
python -m things_mcp.main --timeout 60
```

**Check Things 3 performance**:
1. Restart Things 3
2. Check available memory
3. Close other resource-intensive apps

### Claude Desktop Integration

#### Configuration not loading

**Problem**: Claude Desktop can't find or load MCP configuration

**Diagnostics**:
```bash
# Check config file exists
ls -la ~/Library/Application\ Support/Claude/claude_desktop_config.json

# Validate JSON syntax
python -m json.tool ~/Library/Application\ Support/Claude/claude_desktop_config.json

# Check file permissions
ls -la ~/Library/Application\ Support/Claude/
```

**Solutions**:

1. **Create missing directory**:
   ```bash
   mkdir -p ~/Library/Application\ Support/Claude/
   ```

2. **Fix JSON syntax**:
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

3. **Fix file permissions**:
   ```bash
   chmod 644 ~/Library/Application\ Support/Claude/claude_desktop_config.json
   ```

#### "MCP server failed to start"

**Problem**: Claude Desktop can't start the MCP server

**Diagnostics**:
```bash
# Test server startup manually
python -m things_mcp.main --debug

# Check Python path in config
which python

# Verify package installation
python -c "import things_mcp; print('OK')"
```

**Solutions**:

1. **Use absolute Python path**:
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

2. **Add environment variables**:
   ```json
   {
     "mcpServers": {
       "things": {
         "command": "python",
         "args": ["-m", "things_mcp.main"],
         "env": {
           "PYTHONPATH": "/path/to/your/site-packages"
         }
       }
     }
   }
   ```

#### Claude can access server but not Things 3

**Problem**: MCP server running but can't communicate with Things 3

**Solution**: This is usually the automation permission issue - see above section.

### Performance Issues

#### Slow response times

**Problem**: Operations taking longer than expected

**Diagnostics**:
```bash
# Run with debug logging
python -m things_mcp.main --debug

# Check system resources
top -l 1 | grep "CPU usage"
vm_stat
```

**Solutions**:

1. **Enable caching**:
   ```bash
   export THINGS_MCP_CACHE_TTL=300  # 5 minutes
   ```

2. **Reduce concurrency**:
   ```bash
   export THINGS_MCP_MAX_CONCURRENT=1
   ```

3. **Restart Things 3**: Sometimes Things 3 becomes sluggish

4. **Check disk space**: Low disk space affects performance

#### Memory usage growing over time

**Problem**: Memory leak or excessive caching

**Diagnostics**:
```bash
# Monitor memory usage
python -m things_mcp.main --monitor-memory

# Check cache stats
curl http://localhost:8080/health | grep cache
```

**Solutions**:

1. **Reduce cache TTL**:
   ```bash
   export THINGS_MCP_CACHE_TTL=60  # 1 minute
   ```

2. **Restart server periodically**:
   ```bash
   # Add to cron for daily restart
   0 2 * * * pkill -f things_mcp && sleep 5 && python -m things_mcp.main
   ```

### Network and Connectivity

#### "Connection refused" errors

**Problem**: Can't connect to MCP server

**Diagnostics**:
```bash
# Check if server is running
ps aux | grep things_mcp

# Check port availability
lsof -i :8080

# Test connection
curl http://localhost:8080/health
```

**Solutions**:

1. **Start server manually**:
   ```bash
   python -m things_mcp.main
   ```

2. **Use different port**:
   ```bash
   python -m things_mcp.main --port 8081
   ```

3. **Check firewall settings**:
   ```bash
   # macOS firewall check
   sudo /usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate
   ```

### Error Messages Reference

#### "execution error: Things3 got an error: Can't get..."

**Cause**: AppleScript syntax error or object doesn't exist

**Solution**: 
- Check Things 3 is running
- Verify object ID exists
- Update to latest server version

#### "operation_queue: Operation failed after 3 retries"

**Cause**: Persistent AppleScript failures

**Solution**:
- Check Things 3 stability
- Restart Things 3
- Check system resources

#### "Invalid date format" errors

**Cause**: Date parameter in wrong format

**Solution**: Use YYYY-MM-DD format for dates:
```python
# Correct
deadline="2024-01-30"

# Incorrect  
deadline="1/30/2024"
deadline="30-01-2024"
```

## 🔧 Advanced Troubleshooting

### Enable Debug Logging

```bash
# Method 1: Environment variable
export THINGS_MCP_LOG_LEVEL=DEBUG
python -m things_mcp.main

# Method 2: Command line
python -m things_mcp.main --log-level DEBUG

# Method 3: Configuration file
echo "log_level: DEBUG" > config.yaml
python -m things_mcp.main --config config.yaml
```

### Capture AppleScript Output

```bash
# Test specific AppleScript commands
osascript -e 'tell application "Things3" to get name of every to do of list "Today"' 2>&1

# Save AppleScript debug info
export THINGS_MCP_DEBUG_APPLESCRIPT=1
python -m things_mcp.main 2>&1 | tee debug.log
```

### Performance Profiling

```bash
# Profile memory usage
python -m memory_profiler -m things_mcp.main

# Profile CPU usage  
python -m cProfile -o profile.stats -m things_mcp.main

# Analyze profile
python -c "import pstats; pstats.Stats('profile.stats').sort_stats('cumulative').print_stats(10)"
```

### Database Issues (Things 3)

If Things 3 seems corrupted:

```bash
# Backup Things database
cp -r ~/Library/Containers/com.culturedcode.ThingsMac ~/Desktop/Things_Backup

# Reset Things 3 (CAUTION: This removes all data)
# Only do this as last resort and with backup
rm -rf ~/Library/Containers/com.culturedcode.ThingsMac
# Then restart Things 3 and restore from backup
```

## 🆘 When All Else Fails

### Collect Diagnostic Information

```bash
# Run comprehensive diagnostics
python -m things_mcp.main --full-diagnostics > diagnostics.txt

# Include system information
system_profiler SPSoftwareDataType >> diagnostics.txt
system_profiler SPHardwareDataType >> diagnostics.txt

# Include recent logs
tail -100 /var/log/system.log >> diagnostics.txt
```

### Clean Reinstallation

```bash
# 1. Uninstall everything
pip uninstall things-mcp-server
rm -rf ~/.things-mcp-server

# 2. Clear Python cache
find . -name "*.pyc" -delete
find . -name "__pycache__" -delete

# 3. Clear Claude Desktop config
rm ~/Library/Application\ Support/Claude/claude_desktop_config.json

# 4. Reinstall fresh
pip install things-mcp-server

# 5. Reconfigure Claude Desktop
# (See installation guide)
```

### Reset macOS Permissions

```bash
# Reset all automation permissions (requires restart)
sudo tccutil reset AppleEvents

# Reset specific app permissions
sudo tccutil reset AppleEvents com.anthropic.claude-desktop
sudo tccutil reset AppleEvents com.apple.Terminal
```

## 📞 Getting Help

If none of these solutions work:

### Before Asking for Help

1. **Search existing issues**: [GitHub Issues](https://github.com/yourusername/things-mcp-server/issues)
2. **Check discussions**: [GitHub Discussions](https://github.com/yourusername/things-mcp-server/discussions)
3. **Review documentation**: Ensure you've followed all setup steps

### When Requesting Help

Include this information:

```
## Environment
- macOS version: (e.g., macOS 13.2)
- Python version: (e.g., Python 3.11.1)
- Things 3 version: (e.g., 3.19.1)
- Server version: (e.g., 1.0.0)
- Claude Desktop version: (if applicable)

## Problem Description
(Clear description of issue)

## Steps to Reproduce
1. First step
2. Second step
3. Where it fails

## Error Messages
(Complete error messages, not just snippets)

## What You've Tried
(List troubleshooting steps you've already attempted)

## Diagnostic Output
```bash
python -m things_mcp.main --health-check
```
(Paste full output)
```

### Contact Options

- **GitHub Issues**: For bugs and technical problems
- **GitHub Discussions**: For usage questions and general help
- **Email Support**: support@yourdomain.com (include diagnostic info)

---

Most issues can be resolved with the steps above. The Things 3 MCP Server is designed to be robust and self-recovering, so persistent issues usually indicate configuration or permission problems that can be fixed with the right approach.