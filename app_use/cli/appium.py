"""
Appium server management for app-use CLI.

Handles starting, stopping, and checking the Appium server.
"""

import os
import subprocess
import time
from typing import Optional

# Global variable to track appium server process
_appium_process: Optional[subprocess.Popen] = None


def is_appium_running() -> bool:
	"""Check if Appium server is already running."""
	try:
		import requests

		response = requests.get('http://localhost:4723/status', timeout=2)
		return response.status_code == 200
	except Exception:
		return False


def start_appium_server() -> bool:
	"""Start Appium server if not already running."""
	global _appium_process

	if is_appium_running():
		print('✅ Appium server is already running')
		return True

	print('🚀 Starting Appium server...')

	try:
		# Start appium server in background
		_appium_process = subprocess.Popen(
			['appium'],
			stdout=subprocess.DEVNULL,
			stderr=subprocess.DEVNULL,
			preexec_fn=os.setsid if os.name != 'nt' else None,  # Create new process group on Unix
		)

		# Wait for server to start
		for _ in range(10):  # Wait up to 10 seconds
			time.sleep(1)
			if is_appium_running():
				print('✅ Appium server started successfully')
				return True

		print('❌ Appium server failed to start within 10 seconds')
		return False

	except FileNotFoundError:
		print('❌ Appium not found. Please install it with: npm install -g appium')
		return False
	except Exception as e:
		print(f'❌ Error starting Appium server: {e}')
		return False


def stop_appium_server() -> None:
	"""Stop the Appium server if we started it."""
	global _appium_process

	if _appium_process:
		try:
			if os.name == 'nt':
				# Windows
				_appium_process.terminate()
			else:
				# Unix-like systems - kill the process group
				os.killpg(os.getpgid(_appium_process.pid), 15)  # SIGTERM

			_appium_process.wait(timeout=5)
			print('✅ Appium server stopped')
		except Exception as e:
			print(f'⚠️ Error stopping Appium server: {e}')
		finally:
			_appium_process = None
