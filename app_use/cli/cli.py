"""
Main CLI entry point for app-use.

Orchestrates all CLI commands and handles argument parsing.
"""

import asyncio
import os
import sys

import click
from dotenv import load_dotenv

from .config import load_user_config, save_user_config, update_config_with_click_args
from .doctor import run_doctor_command
from .gui import run_textual_interface
from .setup import run_setup_command
from .start import run_start_command
from .utils import configure_logging, get_llm

# Load environment variables
load_dotenv()


async def run_prompt_mode(prompt: str, ctx: click.Context, debug: bool = False):
	"""Run app-use in non-interactive mode with a single prompt."""
	# Set up logging
	os.environ['APP_USE_LOGGING_LEVEL'] = 'result'
	configure_logging(debug)

	try:
		# Load and update config
		config = load_user_config()
		config = update_config_with_click_args(config, ctx)

		# Validate required parameters
		app_config = config.get('app', {})
		if not app_config.get('device_name'):
			print('❌ Error: device_name is required. Please set it in config or use --device-name')
			sys.exit(1)

		platform = app_config.get('platform_name', 'Android')
		if platform.lower() == 'android' and not app_config.get('app_package'):
			print('❌ Error: app_package is required for Android. Please set it in config or use --app-package')
			sys.exit(1)
		elif platform.lower() == 'ios' and not app_config.get('bundle_id'):
			print('❌ Error: bundle_id is required for iOS. Please set it in config or use --bundle-id')
			sys.exit(1)

		# Get LLM
		llm = get_llm(config)

		# Import here to avoid circular imports
		from app_use.agent.service import Agent
		from app_use.app.app import App
		from app_use.controller.service import Controller

		# Create components
		app_instance = App(**app_config)
		controller = Controller()

		# Create and run agent
		agent = Agent(
			task=prompt,
			llm=llm,
			app=app_instance,
			controller=controller,
		)

		await agent.run()
		app_instance.close()

	except Exception as e:
		if debug:
			import traceback

			traceback.print_exc()
		else:
			print(f'Error: {str(e)}', file=sys.stderr)
		sys.exit(1)


@click.group(invoke_without_command=True)
@click.option('--version', is_flag=True, help='Print version and exit')
@click.option('--model', type=str, help='Model to use (e.g., gpt-4o, claude-3-opus-20240229, gemini-pro)')
@click.option('--debug', is_flag=True, help='Enable verbose startup logging')
@click.option('--platform', type=click.Choice(['Android', 'iOS'], case_sensitive=False), help='Mobile platform')
@click.option('--device-name', type=str, help='Device name or ID for connection')
@click.option('--app-package', type=str, help='Android app package name (e.g., com.example.app)')
@click.option('--bundle-id', type=str, help='iOS app bundle ID (e.g., com.example.app)')
@click.option('--appium-server-url', type=str, help='Appium server URL (default: http://localhost:4723)')
@click.option('-p', '--prompt', type=str, help='Run a single task without the TUI')
@click.pass_context
def cli(ctx: click.Context, debug: bool = False, **kwargs):
	"""App-Use Interactive TUI or Command Line Executor

	Control mobile applications using AI agents through Appium.

	Examples:
	  app-use start                    # Interactive setup wizard
	  app-use setup                    # Install dependencies
	  app-use doctor                   # Check environment
	  app-use --platform Android ...  # Direct launch with parameters
	  app-use -p "task description"   # Command line mode

	Use 'app-use start' for an interactive setup wizard, or provide options directly for immediate launch.
	"""
	# If no subcommand was invoked, run the original main functionality
	if ctx.invoked_subcommand is None:
		_run_main_command(ctx, debug, **kwargs)


def _run_main_command(ctx: click.Context, debug: bool = False, **kwargs):
	"""Run the main command functionality."""
	if kwargs['version']:
		try:
			from importlib.metadata import version

			print(version('app-use'))
		except (ImportError, ModuleNotFoundError):
			print('app-use (development version)')
		sys.exit(0)

	# Check if prompt mode is activated
	if kwargs.get('prompt'):
		os.environ['APP_USE_LOGGING_LEVEL'] = 'result'
		asyncio.run(run_prompt_mode(kwargs['prompt'], ctx, debug))
		return

	# Configure logging for GUI mode
	configure_logging(debug)

	try:
		# Load and update configuration
		config = load_user_config()
		config = update_config_with_click_args(config, ctx)
		save_user_config(config)

		# Run the Textual GUI interface
		asyncio.run(run_textual_interface(config))

	except Exception as e:
		print(f'\nError launching App-Use: {str(e)}')
		if debug:
			import traceback

			traceback.print_exc()
		sys.exit(1)


@cli.command()
@click.option('--debug', is_flag=True, help='Enable verbose startup logging')
def start(debug: bool = False):
	"""Interactive setup wizard for App-Use.

	This command will:
	- Start Appium server if needed
	- Prompt for platform selection (Android/iOS)
	- Show available devices and emulators
	- List installed apps for selection
	- Launch the GUI with the configured settings
	"""
	if debug:
		configure_logging(debug=True)

	run_start_command()


@cli.command()
def setup():
	"""Install and configure dependencies for app-use.

	This command will:
	- Check for required tools (Node.js, Java, etc.)
	- Install Appium and drivers
	- Install iOS and Android development tools
	- Set up the environment for mobile app automation
	"""
	run_setup_command()


@cli.command()
def doctor():
	"""Verify that all dependencies are properly installed.

	Similar to 'flutter doctor', this command checks:
	- Core dependencies (Node.js, Java, Python)
	- Appium installation and drivers
	- iOS development setup (Xcode, simulators)
	- Android development setup (SDK, ADB)
	- Device connectivity
	"""
	run_doctor_command()


def main():
	"""Entry point for the CLI."""
	cli()


if __name__ == '__main__':
	main()
