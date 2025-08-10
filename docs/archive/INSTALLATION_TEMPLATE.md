# Installation Guide

Complete installation instructions for the Things 3 MCP Server across different platforms and use cases.

## 📋 Table of Contents

1. [Requirements](#requirements)
2. [Quick Installation](#quick-installation)
3. [Claude Desktop Setup](#claude-desktop-setup)
4. [Development Installation](#development-installation)
5. [Docker Installation](#docker-installation)
6. [Troubleshooting](#troubleshooting)
7. [Verification](#verification)

## 🔧 Requirements

### System Requirements
- **Operating System**: macOS 12.0 or later
- **Python**: 3.8 or higher
- **Things 3**: Installed and licensed
- **Memory**: 50MB+ available RAM
- **Disk**: 100MB+ free space

### Permissions Required
- **Automation Access**: Terminal/IDE must have permission to control Things 3
- **AppleScript**: System must allow AppleScript execution

### Optional Dependencies
- **Claude Desktop**: For AI assistant integration
- **Docker**: For containerized deployment
- **Git**: For development installation

## ⚡ Quick Installation

### Option 1: PyPI Installation (Recommended for Users)

```bash
# Install from PyPI
pip install things-mcp-server

# Verify installation
python -m things_mcp.main --version
```

### Option 2: Direct Download

```bash
# Download and install latest release
curl -L https://github.com/yourusername/things-mcp-server/releases/latest/download/things-mcp-server.tar.gz | tar xz
cd things-mcp-server
pip install .
```

## 🤖 Claude Desktop Setup

### Step 1: Install Claude Desktop

Download Claude Desktop from [official website](https://claude.ai/desktop).

### Step 2: Locate Configuration File

```bash
# macOS configuration location
~/Library/Application Support/Claude/claude_desktop_config.json
```

### Step 3: Add MCP Server Configuration

Create or edit `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "things": {
      "command": "python",
      "args": ["-m", "things_mcp.main"],
      "env": {
        "THINGS_MCP_TIMEOUT": "30",
        "THINGS_MCP_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

### Step 4: Grant Automation Permissions

1. Open **System Preferences** → **Security & Privacy**
2. Navigate to **Privacy** → **Automation**
3. Find **Claude Desktop** in the list
4. Check the box next to **Things3**
5. Restart Claude Desktop

![Automation Permissions](media/automation-permissions.png)

### Step 5: Test Configuration

1. Open Claude Desktop
2. Start a new conversation
3. Ask: "Can you show me my Things 3 inbox?"
4. Claude should respond with your inbox contents

## 👨‍💻 Development Installation

### Prerequisites

```bash
# Ensure you have development tools
xcode-select --install

# Install Python 3.8+ if not already installed
brew install python@3.11
```

### Clone and Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/things-mcp-server.git
cd things-mcp-server

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On macOS/Linux

# Install development dependencies
pip install -e ".[dev]"
```

### Development Configuration

```bash
# Copy example configuration
cp config/example.yaml config/local.yaml

# Edit configuration as needed
editor config/local.yaml
```

Example `config/local.yaml`:

```yaml
server:
  debug: true
  timeout: 60
  cache_ttl: 60  # Shorter cache for development
  log_level: DEBUG

things:
  app_name: "Things3"
  url_scheme: "things"

logging:
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file: "logs/things_mcp_dev.log"
```

### Run Development Server

```bash
# Start with debug logging
python -m things_mcp.main --debug --config config/local.yaml

# Or use the development script
./scripts/dev_server.sh
```

### Development Tools

```bash
# Run tests
pytest

# Run tests with coverage
pytest --cov=src/things_mcp --cov-report=html

# Format code
black src/ tests/
isort src/ tests/

# Lint code
flake8 src/ tests/
mypy src/

# Pre-commit hooks (recommended)
pre-commit install
pre-commit run --all-files
```

## 🐳 Docker Installation

### Using Pre-built Image

```bash
# Pull the latest image
docker pull yourusername/things-mcp-server:latest

# Run container with volume mount for Things 3 access
docker run -d \
  --name things-mcp \
  -v ~/Library/Containers/com.culturedcode.ThingsMac:/things-data:ro \
  -p 8080:8080 \
  yourusername/things-mcp-server:latest
```

### Building from Source

```bash
# Clone repository
git clone https://github.com/yourusername/things-mcp-server.git
cd things-mcp-server

# Build Docker image
docker build -t things-mcp-server .

# Run container
docker run -d \
  --name things-mcp \
  -v ~/Library/Containers/com.culturedcode.ThingsMac:/things-data:ro \
  -e THINGS_MCP_LOG_LEVEL=INFO \
  -p 8080:8080 \
  things-mcp-server
```

### Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'
services:
  things-mcp:
    image: yourusername/things-mcp-server:latest
    container_name: things-mcp
    volumes:
      - ~/Library/Containers/com.culturedcode.ThingsMac:/things-data:ro
      - ./logs:/app/logs
    ports:
      - "8080:8080"
    environment:
      - THINGS_MCP_LOG_LEVEL=INFO
      - THINGS_MCP_TIMEOUT=30
    restart: unless-stopped
```

Run with:

```bash
docker-compose up -d
```

## 🔍 Troubleshooting

### Common Installation Issues

#### Python Version Errors

```bash
# Check Python version
python --version

# If too old, install newer version
brew install python@3.11
python3.11 -m pip install things-mcp-server
```

#### Permission Denied

```bash
# If you see permission errors:
error: Microsoft Visual C++ 14.0 is required

# Solution: Install build tools
xcode-select --install
```

#### Module Not Found

```bash
# If you see "No module named 'things_mcp'"
ModuleNotFoundError: No module named 'things_mcp'

# Solution: Reinstall with proper path
pip uninstall things-mcp-server
pip install things-mcp-server

# Or check your PYTHONPATH
echo $PYTHONPATH
```

### Claude Desktop Issues

#### Configuration Not Loading

1. **Check file location**:
   ```bash
   ls -la ~/Library/Application\ Support/Claude/claude_desktop_config.json
   ```

2. **Validate JSON syntax**:
   ```bash
   python -m json.tool ~/Library/Application\ Support/Claude/claude_desktop_config.json
   ```

3. **Check permissions**:
   ```bash
   chmod 644 ~/Library/Application\ Support/Claude/claude_desktop_config.json
   ```

#### Automation Permissions

If Claude can't access Things 3:

1. **Reset permissions**:
   - Go to **System Preferences** → **Security & Privacy** → **Privacy** → **Automation**
   - Remove Claude Desktop from the list
   - Restart Claude Desktop
   - Try accessing Things 3 again - you'll be prompted to grant permission

2. **Alternative method**:
   ```bash
   # Reset TCC database (requires restart)
   sudo tccutil reset AppleEvents com.anthropic.claude-desktop
   ```

### Things 3 Issues

#### Things Not Found

```bash
# Check if Things 3 is installed
ls -la /Applications/Things3.app

# Check if Things 3 is running
ps aux | grep -i things
```

#### AppleScript Errors

```bash
# Test AppleScript manually
osascript -e 'tell application "Things3" to get name of to dos of list "Today"'
```

If this fails:
1. Ensure Things 3 is running
2. Check automation permissions
3. Try restarting Things 3

### Network and Connectivity

#### Port Conflicts

```bash
# Check if port 8080 is in use
lsof -i :8080

# Use different port if needed
python -m things_mcp.main --port 8081
```

#### Firewall Issues

```bash
# Check firewall status
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate

# Add exception if needed
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add python
```

## ✅ Verification

### Basic Functionality Test

```bash
# Run built-in health check
python -m things_mcp.main --health-check
```

Expected output:
```
✅ Python version: 3.11.x
✅ Things 3 installed and accessible
✅ AppleScript permissions granted
✅ MCP server can start successfully
✅ All core tools available
```

### Integration Test

```python
# Create test script: test_installation.py
import asyncio
from things_mcp import ThingsMCPServer

async def test_basic_operations():
    server = ThingsMCPServer()
    
    # Test health check
    health = await server.health_check()
    assert health['server_status'] == 'healthy'
    
    # Test basic operation
    inbox = await server.get_inbox()
    print(f"✅ Successfully retrieved {len(inbox)} inbox items")
    
    print("✅ All tests passed!")

if __name__ == "__main__":
    asyncio.run(test_basic_operations())
```

Run test:
```bash
python test_installation.py
```

### Claude Desktop Integration Test

1. Open Claude Desktop
2. Start new conversation
3. Run these test commands:

```
# Test 1: Health check
"Can you check if Things 3 MCP server is working?"

# Test 2: Basic data access
"Show me my Things 3 inbox"

# Test 3: Simple operation
"Add a test todo titled 'MCP Installation Test'"

# Test 4: Search
"Search for todos containing 'test'"
```

All commands should work without errors.

## 🔄 Updates and Maintenance

### Updating the Package

```bash
# Update to latest version
pip install --upgrade things-mcp-server

# Check version
python -m things_mcp.main --version
```

### Development Updates

```bash
# Pull latest changes
git pull origin main

# Update dependencies
pip install -e ".[dev]" --upgrade

# Run tests to ensure everything works
pytest
```

### Configuration Migration

When updating between major versions, check the [Migration Guide](MIGRATION.md) for any configuration changes required.

## 🆘 Getting Help

If you encounter issues not covered here:

1. **Search existing issues**: [GitHub Issues](https://github.com/yourusername/things-mcp-server/issues)
2. **Ask the community**: [GitHub Discussions](https://github.com/yourusername/things-mcp-server/discussions)
3. **Read documentation**: [Full Documentation](README.md)
4. **Contact support**: support@yourdomain.com

When reporting issues, please include:
- Operating system and version
- Python version
- Things 3 version
- Complete error messages
- Steps to reproduce

---

**Next Steps**: Once installation is complete, check out the [Quick Start Guide](QUICK_START.md) to begin using your new Things 3 MCP server!