#!/usr/bin/env python3
"""
Setup Script for Things 3 MCP Server

Automated setup script that:
- Checks system requirements
- Verifies Things 3 installation
- Sets up configuration
- Installs dependencies
- Configures Claude Desktop integration
"""

import os
import sys
import json
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
import argparse


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


class ThingsMCPSetup:
    """Setup manager for Things 3 MCP Server"""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.project_root = Path(__file__).parent.parent
        self.config_dir = self.project_root / "config"
        self.src_dir = self.project_root / "src"
        
        # System information
        self.system_info = {
            "platform": sys.platform,
            "python_version": sys.version_info,
            "python_executable": sys.executable
        }
    
    def print_status(self, message: str, status: str = "INFO"):
        """Print colored status message"""
        colors = {
            "INFO": Colors.BLUE,
            "SUCCESS": Colors.GREEN,
            "WARNING": Colors.YELLOW,
            "ERROR": Colors.RED
        }
        
        color = colors.get(status, Colors.BLUE)
        print(f"{color}[{status}]{Colors.END} {message}")
    
    def run_command(self, command: List[str], check: bool = True) -> subprocess.CompletedProcess:
        """Run shell command with error handling"""
        if self.verbose:
            self.print_status(f"Running: {' '.join(command)}")
        
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=check
            )
            
            if self.verbose and result.stdout:
                print(result.stdout)
            
            return result
            
        except subprocess.CalledProcessError as e:
            self.print_status(f"Command failed: {e}", "ERROR")
            if e.stderr:
                print(e.stderr)
            raise
    
    def check_system_requirements(self) -> bool:
        """Check system requirements"""
        self.print_status("Checking system requirements...")
        
        issues = []
        
        # Check Python version
        if self.system_info["python_version"] < (3, 10):
            issues.append(f"Python 3.10+ required, found {sys.version}")
        else:
            self.print_status(f"Python version: {sys.version}", "SUCCESS")
        
        # Check macOS
        if self.system_info["platform"] != "darwin":
            issues.append("macOS is required for Things 3 integration")
        else:
            self.print_status("Platform: macOS", "SUCCESS")
        
        # Check Things 3 installation
        try:
            result = self.run_command([
                "osascript",
                "-e",
                'tell application "Things3" to return version'
            ])
            
            version = result.stdout.strip().strip('"')
            self.print_status(f"Things 3 version: {version}", "SUCCESS")
            
        except subprocess.CalledProcessError:
            issues.append("Things 3 not found or not accessible")
        
        # Check accessibility permissions
        self.check_accessibility_permissions()
        
        if issues:
            self.print_status("System requirements check failed:", "ERROR")
            for issue in issues:
                print(f"  - {issue}")
            return False
        
        self.print_status("System requirements check passed", "SUCCESS")
        return True
    
    def check_accessibility_permissions(self):
        """Check accessibility permissions"""
        self.print_status("Checking accessibility permissions...")
        
        try:
            # Try a simple accessibility operation
            self.run_command([
                "osascript",
                "-e",
                'tell application "System Events" to return name'
            ])
            self.print_status("Accessibility permissions: OK", "SUCCESS")
            
        except subprocess.CalledProcessError:
            self.print_status(
                "Accessibility permissions may be required. "
                "Go to System Preferences > Security & Privacy > Accessibility",
                "WARNING"
            )
    
    def install_dependencies(self) -> bool:
        """Install Python dependencies"""
        self.print_status("Installing Python dependencies...")
        
        requirements_file = self.project_root / "requirements.txt"
        
        if not requirements_file.exists():
            # Create basic requirements file
            requirements = [
                "fastmcp>=2.0.0",
                "pydantic>=2.0.0",
                "httpx>=0.24.0",
                "asyncio-cache>=0.1.0",
                "pyyaml>=6.0",
                "pytest>=7.0.0",
                "pytest-asyncio>=0.21.0"
            ]
            
            requirements_file.write_text("\n".join(requirements))
            self.print_status("Created requirements.txt", "SUCCESS")
        
        try:
            # Check if we're in a virtual environment
            if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
                self.print_status("Virtual environment detected", "SUCCESS")
            else:
                self.print_status("Not in virtual environment - consider using one", "WARNING")
            
            # Install dependencies
            self.run_command([
                sys.executable, "-m", "pip", "install", "-r", str(requirements_file)
            ])
            
            self.print_status("Dependencies installed successfully", "SUCCESS")
            return True
            
        except subprocess.CalledProcessError:
            self.print_status("Failed to install dependencies", "ERROR")
            return False
    
    def create_configuration(self, environment: str = "development") -> bool:
        """Create default configuration"""
        self.print_status(f"Creating {environment} configuration...")
        
        # Ensure config directory exists
        self.config_dir.mkdir(exist_ok=True)
        
        config_file = self.config_dir / f"{environment}.yaml"
        
        if config_file.exists():
            self.print_status(f"Configuration file already exists: {config_file}", "WARNING")
            return True
        
        # Create configuration using our config module
        try:
            sys.path.insert(0, str(self.src_dir))
            from things_mcp.config import create_default_config_file
            
            create_default_config_file(config_file, environment)
            self.print_status(f"Created configuration: {config_file}", "SUCCESS")
            
            return True
            
        except Exception as e:
            self.print_status(f"Failed to create configuration: {e}", "ERROR")
            return False
    
    def setup_claude_desktop_integration(self) -> bool:
        """Setup Claude Desktop integration"""
        self.print_status("Setting up Claude Desktop integration...")
        
        # Find Claude Desktop config file
        claude_config_paths = [
            Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
            Path.home() / ".config" / "claude" / "claude_desktop_config.json"
        ]
        
        claude_config_path = None
        for path in claude_config_paths:
            if path.parent.exists():
                claude_config_path = path
                break
        
        if not claude_config_path:
            self.print_status("Claude Desktop config directory not found", "WARNING")
            self.print_status("You'll need to manually configure Claude Desktop", "INFO")
            return False
        
        # Load existing config or create new one
        config = {}
        if claude_config_path.exists():
            try:
                with open(claude_config_path, 'r') as f:
                    config = json.load(f)
            except json.JSONDecodeError:
                self.print_status("Invalid Claude Desktop config file", "WARNING")
                config = {}
        
        # Add Things 3 MCP server configuration
        if "mcpServers" not in config:
            config["mcpServers"] = {}
        
        server_config = {
            "command": sys.executable,
            "args": [str(self.src_dir / "things_mcp" / "server.py")],
            "env": {
                "THINGS_MCP_LOG_LEVEL": "INFO"
            }
        }
        
        config["mcpServers"]["things3"] = server_config
        
        # Write updated config
        try:
            # Ensure directory exists
            claude_config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(claude_config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            self.print_status(f"Updated Claude Desktop config: {claude_config_path}", "SUCCESS")
            return True
            
        except Exception as e:
            self.print_status(f"Failed to update Claude Desktop config: {e}", "ERROR")
            return False
    
    def run_tests(self) -> bool:
        """Run test suite to verify setup"""
        self.print_status("Running test suite...")
        
        try:
            # Run basic tests
            test_command = [
                sys.executable, "-m", "pytest",
                str(self.project_root / "tests"),
                "-v",
                "--tb=short"
            ]
            
            if not self.verbose:
                test_command.append("-q")
            
            self.run_command(test_command)
            self.print_status("All tests passed", "SUCCESS")
            return True
            
        except subprocess.CalledProcessError:
            self.print_status("Some tests failed", "WARNING")
            return False
    
    def create_startup_script(self) -> bool:
        """Create startup script for the server"""
        self.print_status("Creating startup script...")
        
        startup_script = self.project_root / "start_server.py"
        
        script_content = f'''#!/usr/bin/env python3
"""
Things 3 MCP Server Startup Script
"""

import sys
import asyncio
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from things_mcp.server import main

if __name__ == "__main__":
    asyncio.run(main())
'''
        
        startup_script.write_text(script_content)
        startup_script.chmod(0o755)  # Make executable
        
        self.print_status(f"Created startup script: {startup_script}", "SUCCESS")
        return True
    
    def display_next_steps(self):
        """Display next steps for the user"""
        print(f"\n{Colors.BOLD}Setup Complete!{Colors.END}\n")
        
        print("Next steps:")
        print("1. Restart Claude Desktop to load the new server configuration")
        print("2. Test the integration by asking Claude to help with Things 3 tasks")
        print("3. Check the server logs if you encounter issues")
        print()
        
        print("Available commands:")
        print(f"  - Start server manually: python {self.project_root / 'start_server.py'}")
        print(f"  - Run tests: python -m pytest {self.project_root / 'tests'}")
        print(f"  - View configuration: {self.config_dir / 'development.yaml'}")
        print()
        
        print("For troubleshooting:")
        print("  - Check System Preferences > Security & Privacy > Accessibility")
        print("  - Ensure Things 3 is running and accessible")
        print("  - Check Claude Desktop logs for connection issues")
    
    def run_full_setup(self, environment: str = "development") -> bool:
        """Run complete setup process"""
        print(f"{Colors.BOLD}Things 3 MCP Server Setup{Colors.END}\n")
        
        steps = [
            ("System Requirements", self.check_system_requirements),
            ("Dependencies", self.install_dependencies),
            ("Configuration", lambda: self.create_configuration(environment)),
            ("Claude Desktop Integration", self.setup_claude_desktop_integration),
            ("Startup Script", self.create_startup_script),
            ("Tests", self.run_tests)
        ]
        
        for step_name, step_func in steps:
            self.print_status(f"Step: {step_name}")
            try:
                if not step_func():
                    self.print_status(f"Setup step failed: {step_name}", "ERROR")
                    return False
            except Exception as e:
                self.print_status(f"Setup step error: {step_name} - {e}", "ERROR")
                return False
            
            print()  # Add spacing between steps
        
        self.display_next_steps()
        return True


def main():
    """Main setup function"""
    parser = argparse.ArgumentParser(description="Things 3 MCP Server Setup")
    parser.add_argument(
        "--environment",
        choices=["development", "production", "testing"],
        default="development",
        help="Environment configuration to create"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--skip-claude",
        action="store_true",
        help="Skip Claude Desktop integration setup"
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip running tests"
    )
    
    args = parser.parse_args()
    
    setup = ThingsMCPSetup(verbose=args.verbose)
    
    # Run individual steps or full setup
    success = setup.run_full_setup(args.environment)
    
    if success:
        print(f"\n{Colors.GREEN}Setup completed successfully!{Colors.END}")
        sys.exit(0)
    else:
        print(f"\n{Colors.RED}Setup failed. Check the output above for details.{Colors.END}")
        sys.exit(1)


if __name__ == "__main__":
    main()