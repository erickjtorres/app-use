"""
Configuration management for app-use CLI.

Handles loading, saving, and updating user configuration files.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict

import click

# Paths
USER_CONFIG_DIR = Path.home() / '.config' / 'appuse'
USER_CONFIG_FILE = USER_CONFIG_DIR / 'config.json'
USER_DATA_DIR = USER_CONFIG_DIR / 'data'

# Default User settings
MAX_HISTORY_LENGTH = 100

# Ensure directories exist
USER_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_default_config() -> Dict[str, Any]:
	"""Return default configuration dictionary."""
	return {
		'model': {
			'name': None,
			'temperature': 0.0,
			'api_keys': {
				'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY', ''),
				'ANTHROPIC_API_KEY': os.getenv('ANTHROPIC_API_KEY', ''),
				'GOOGLE_API_KEY': os.getenv('GOOGLE_API_KEY', ''),
			},
		},
		'agent': {},  # AgentSettings will use defaults
		'app': {
			'platform_name': 'Android',
			'device_name': None,
			'app_package': None,
			'app_activity': None,
			'bundle_id': None,
			'appium_server_url': 'http://localhost:4723',
			'timeout': 30,
		},
		'command_history': [],
	}


def load_user_config() -> Dict[str, Any]:
	"""Load user configuration from file."""
	if not USER_CONFIG_FILE.exists():
		# Create default config
		config = get_default_config()
		save_user_config(config)
		return config

	try:
		with open(USER_CONFIG_FILE) as f:
			data = json.load(f)
			# Ensure data is a dictionary, not a list
			if isinstance(data, list):
				# If it's a list, it's probably just command history from previous version
				config = get_default_config()
				config['command_history'] = data  # Use the list as command history
				return config
			return data
	except (json.JSONDecodeError, FileNotFoundError):
		# If file is corrupted, start with empty config
		return get_default_config()


def save_user_config(config: Dict[str, Any]) -> None:
	"""Save user configuration to file."""
	# Ensure command history doesn't exceed maximum length
	if 'command_history' in config and isinstance(config['command_history'], list):
		if len(config['command_history']) > MAX_HISTORY_LENGTH:
			config['command_history'] = config['command_history'][-MAX_HISTORY_LENGTH:]

	with open(USER_CONFIG_FILE, 'w') as f:
		json.dump(config, f, indent=2)


def update_config_with_click_args(config: Dict[str, Any], ctx: click.Context) -> Dict[str, Any]:
	"""Update configuration with command-line arguments."""
	# Ensure required sections exist
	if 'model' not in config:
		config['model'] = {}
	if 'app' not in config:
		config['app'] = {}

	# Update configuration with command-line args if provided
	if ctx.params.get('model'):
		config['model']['name'] = ctx.params['model']
	if ctx.params.get('platform'):
		config['app']['platform_name'] = ctx.params['platform']
	if ctx.params.get('device_name'):
		config['app']['device_name'] = ctx.params['device_name']
	if ctx.params.get('app_package'):
		config['app']['app_package'] = ctx.params['app_package']
	if ctx.params.get('bundle_id'):
		config['app']['bundle_id'] = ctx.params['bundle_id']
	if ctx.params.get('appium_server_url'):
		config['app']['appium_server_url'] = ctx.params['appium_server_url']

	return config
