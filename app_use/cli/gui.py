"""
Textual GUI interface for app-use CLI.

Contains the main TUI application and interface components.
"""

import logging
from typing import Any, Dict

from textual.app import App as TextualApp
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Footer, Header, Input, Label, RichLog, Static

from app_use.agent.service import Agent
from app_use.app.app import App
from app_use.controller.service import Controller

from .config import save_user_config
from .utils import APP_USE_LOGO, get_llm


class RichLogHandler(logging.Handler):
	"""Custom logging handler that redirects logs to a RichLog widget."""

	def __init__(self, rich_log: RichLog):
		super().__init__()
		self.rich_log = rich_log

	def emit(self, record):
		try:
			msg = self.format(record)
			self.rich_log.write(msg)
		except Exception:
			self.handleError(record)


class AppUseApp(TextualApp):
	"""App-use TUI application."""

	CSS = """
    #main-container {
        height: 100%;
        layout: vertical;
    }
    
    #logo-panel {
        width: 100%;
        height: auto;
        content-align: center middle;
        text-align: center;
        border: solid $primary;
        margin: 0 0 1 0;
    }
    
    #task-input-container {
        border: solid $accent;
        padding: 1;
        margin-bottom: 1;
        height: auto;
        dock: bottom;
    }
    
    #task-input {
        width: 100%;
    }
    
    #results-log {
        height: 1fr;
        background: $surface;
        color: $text;
        width: 100%;
        border: solid $primary;
        margin: 1 0;
    }
    """

	BINDINGS = [
		Binding('ctrl+c', 'quit', 'Quit', priority=True, show=True),
		Binding('ctrl+q', 'quit', 'Quit', priority=True),
		Binding('ctrl+d', 'quit', 'Quit', priority=True),
	]

	def __init__(self, config: Dict[str, Any], *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.config = config
		self.app_instance = None
		self.controller = None
		self.agent = None
		self.llm = None
		self.task_history = config.get('command_history', [])

	def setup_richlog_logging(self) -> None:
		"""Set up logging to redirect to RichLog widget."""
		rich_log = self.query_one('#results-log')
		log_handler = RichLogHandler(rich_log)

		# Configure logging
		root = logging.getLogger()
		root.handlers = []
		root.addHandler(log_handler)
		root.setLevel(logging.INFO)

	def on_mount(self) -> None:
		"""Set up components when app is mounted."""
		self.setup_richlog_logging()
		input_field = self.query_one('#task-input')
		input_field.focus()

	def on_input_submitted(self, event: Input.Submitted) -> None:
		"""Handle task input submission."""
		if event.input.id == 'task-input':
			task = event.input.value
			if not task.strip():
				return

			# Add to history
			if task.strip() and (not self.task_history or task != self.task_history[-1]):
				self.task_history.append(task)
				self.config['command_history'] = self.task_history
				save_user_config(self.config)

			self.run_task(task)
			event.input.value = ''

	def run_task(self, task: str) -> None:
		"""Launch the task in a background worker."""
		rich_log = self.query_one('#results-log')
		rich_log.clear()

		self.agent = Agent(
			task=task,
			llm=self.llm,
			app=self.app_instance,
			controller=self.controller,
		)

		async def agent_task_worker() -> None:
			logger = logging.getLogger('app_use.app')
			logger.info(f'🚀 Working on task: {task}')

			try:
				await self.agent.run()
			except Exception as e:
				logger.error(f'Error running agent: {str(e)}')
			finally:
				logger.info('✅ Task completed!')

				input_field = self.query_one('#task-input')
				input_field.focus()

		self.run_worker(agent_task_worker, name='agent_task')

	async def action_quit(self) -> None:
		"""Quit the application."""
		if self.app_instance:
			try:
				self.app_instance.close()
			except Exception:
				pass

		self.exit()
		print('\nThanks for using app-use!')

	def compose(self) -> ComposeResult:
		"""Create the UI layout."""
		yield Header()

		with Container(id='main-container'):
			# Logo panel
			yield Static(APP_USE_LOGO, id='logo-panel', markup=True)

			# Results log
			yield RichLog(highlight=True, markup=True, id='results-log', wrap=True, auto_scroll=True)

			# Task input container
			with Container(id='task-input-container'):
				yield Label('📱 What would you like me to do on the mobile app?', id='task-label')
				yield Input(placeholder='Enter your task...', id='task-input')

		yield Footer()


async def run_textual_interface(config: Dict[str, Any]):
	"""Run the Textual interface with the given configuration."""
	logger = logging.getLogger('app_use.startup')

	try:
		# Clean up any stuck iOS processes before initializing
		from .utils import cleanup_ios_processes

		cleanup_ios_processes()

		# Initialize components
		app_config = config.get('app', {})
		app_instance = App(**app_config)
		controller = Controller()
		llm = get_llm(config)

		# Initialize GUI
		app = AppUseApp(config)
		app.app_instance = app_instance
		app.controller = controller
		app.llm = llm

		# Set up logging for Textual
		root_logger = logging.getLogger()
		for handler in root_logger.handlers:
			root_logger.removeHandler(handler)
		root_logger.addHandler(logging.NullHandler())

		# Run the app
		await app.run_async()

	except Exception as e:
		logger.error(f'Error in textual_interface: {str(e)}')
		if 'app_instance' in locals():
			app_instance.close()
		raise
