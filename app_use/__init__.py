"""
App-Use: AI-Powered Mobile App Automation

Control mobile applications using AI agents through Appium.
Support for iOS and Android apps with natural language instructions.
"""

__version__ = '0.0.3'

# Import main components
from .agent.prompts import SystemPrompt
from .agent.service import Agent
from .agent.views import ActionModel, ActionResult
from .app.app import App
from .controller.service import Controller

# Export main components
__all__ = ['App', 'Agent', 'Controller', 'ActionResult', 'ActionModel', 'SystemPrompt']
