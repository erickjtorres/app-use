"""
App-Use: AI-Powered Mobile App Automation

Control mobile applications using AI agents through Appium.
Support for iOS and Android apps with natural language instructions.
"""

__version__ = '0.1.0'

# Import main components
from .agent.service import Agent
from .app.app import App

# Import CLI main function
from .cli.cli import main as cli_main
from .controller.service import Controller

# Export main components
__all__ = ['App', 'Agent', 'Controller', 'cli_main', '__version__']
