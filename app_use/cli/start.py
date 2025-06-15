"""
Interactive setup wizard for app-use CLI.

Handles device discovery, app selection, and configuration setup.
"""

import atexit
import json
import subprocess
import sys
import time
from typing import Dict, List, Optional

from .appium import start_appium_server, stop_appium_server
from .config import load_user_config, save_user_config


def get_android_devices() -> List[Dict[str, str]]:
	"""Get list of available Android devices and emulators."""
	devices = []

	# Get connected devices
	try:
		result = subprocess.run(['adb', 'devices'], capture_output=True, text=True, timeout=10)
		if result.returncode == 0:
			lines = result.stdout.strip().split('\n')[1:]  # Skip header
			for line in lines:
				if line.strip() and '\tdevice' in line:
					device_id = line.split('\t')[0]
					devices.append({'id': device_id, 'name': f'Device: {device_id}', 'type': 'device'})
	except Exception as e:
		print(f'⚠️ Error getting Android devices: {e}')

	# Get available emulators
	try:
		result = subprocess.run(['emulator', '-list-avds'], capture_output=True, text=True, timeout=10)
		if result.returncode == 0 and result.stdout.strip():
			emulators = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
			for emulator in emulators:
				devices.append({'id': emulator, 'name': f'Emulator: {emulator}', 'type': 'emulator'})
	except FileNotFoundError:
		print('⚠️ Android emulator command not found. Make sure Android SDK is installed and emulator is in PATH')
	except Exception as e:
		print(f'⚠️ Error getting Android emulators: {e}')

	return devices


def get_ios_devices() -> List[Dict[str, str]]:
	"""Get list of available iOS devices and simulators."""
	devices = []

	# Get simulators
	try:
		result = subprocess.run(['xcrun', 'simctl', 'list', 'devices', '--json'], capture_output=True, text=True, timeout=10)
		if result.returncode == 0:
			data = json.loads(result.stdout)
			for runtime, device_list in data['devices'].items():
				# Skip unavailable runtimes
				if 'unavailable' in runtime.lower():
					continue

				for device in device_list:
					if device['state'] == 'Booted':
						# Clean up runtime name for display
						runtime_display = runtime.replace('com.apple.CoreSimulator.SimRuntime.', '').replace('-', '.')

						devices.append(
							{
								'id': device['udid'],
								'name': f'Simulator: {device["name"]} ({runtime_display})',
								'type': 'simulator',
								'device_name': device['name'],  # Store original name for reference
								'runtime': runtime,
							}
						)

			print(f'📱 Found {len(devices)} booted iOS simulators')

	except FileNotFoundError:
		print('⚠️ Xcode command line tools not found. Please install with: xcode-select --install')
	except json.JSONDecodeError as e:
		print(f'⚠️ Error parsing iOS simulator data: {e}')
	except Exception as e:
		print(f'⚠️ Error getting iOS simulators: {e}')

	# Get real devices
	try:
		result = subprocess.run(['idevice_id', '-l'], capture_output=True, text=True, timeout=10)
		if result.returncode == 0 and result.stdout.strip():
			device_ids = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
			for device_id in device_ids:
				# Try to get device name
				try:
					name_result = subprocess.run(
						['ideviceinfo', '-u', device_id, '-k', 'DeviceName'], capture_output=True, text=True, timeout=5
					)
					device_name = name_result.stdout.strip() if name_result.returncode == 0 else device_id
				except Exception:
					device_name = device_id

				devices.append({'id': device_id, 'name': f'Device: {device_name}', 'type': 'device'})
	except FileNotFoundError:
		print('⚠️ iOS device tools not found. Make sure libimobiledevice is installed (brew install libimobiledevice)')
	except Exception as e:
		print(f'⚠️ Error getting iOS devices: {e}')

	return devices


def get_android_apps(device_id: str) -> List[Dict[str, str]]:
	"""Get list of installed apps on Android device."""
	apps = []

	try:
		# Get all packages first
		result = subprocess.run(
			['adb', '-s', device_id, 'shell', 'pm', 'list', 'packages'], capture_output=True, text=True, timeout=20
		)
		if result.returncode == 0:
			packages = result.stdout.strip().split('\n')
			print(f'🔍 Found {len(packages)} packages, extracting app names...')

			# Skip system packages that aren't useful for app control
			skip_packages = _get_android_system_packages()

			for package_line in packages:
				if package_line.startswith('package:'):
					package_name = package_line.replace('package:', '').strip()

					if any(package_name.startswith(skip) for skip in skip_packages):
						continue

					# Get the actual app name from dumpsys
					app_name = _get_android_app_name(device_id, package_name)

					apps.append(
						{
							'package': package_name,
							'name': app_name,
							'activity': None,  # Will be auto-detected
						}
					)
		else:
			print(f'❌ Failed to get packages: {result.stderr}')
			return apps

	except Exception as e:
		print(f'⚠️ Error getting Android apps: {e}')

	# Sort apps by name for better UX
	apps.sort(key=lambda x: x['name'].lower())

	return apps


def prompt_selection(
	prompt: str, options: List[str], allow_empty: bool = False, search_data: Optional[List[str]] = None
) -> Optional[int]:
	"""Prompt user to select from a list of options with search functionality."""
	if not options:
		if allow_empty:
			return None
		print('❌ No options available')
		return None

	# If there are many options, offer search functionality
	if len(options) > 10:
		return _prompt_with_search(prompt, options, allow_empty, search_data)
	else:
		return _prompt_simple(prompt, options, allow_empty)


def launch_emulator(emulator_name: str) -> bool:
	"""Launch an Android emulator."""
	print(f'🚀 Starting emulator: {emulator_name}')
	try:
		subprocess.Popen(
			['emulator', '-avd', emulator_name, '-no-snapshot-load'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
		)

		# Wait for emulator to boot
		print('⏳ Waiting for emulator to boot...')
		for _ in range(60):  # Wait up to 60 seconds
			time.sleep(2)
			result = subprocess.run(['adb', 'devices'], capture_output=True, text=True, timeout=5)
			if emulator_name in result.stdout or 'emulator-' in result.stdout:
				# Check if device is ready
				result = subprocess.run(
					['adb', 'shell', 'getprop', 'sys.boot_completed'], capture_output=True, text=True, timeout=5
				)
				if result.stdout.strip() == '1':
					print('✅ Emulator is ready')
					return True

		print('❌ Emulator failed to boot within 2 minutes')
		return False
	except Exception as e:
		print(f'❌ Error starting emulator: {e}')
		return False


def run_start_command() -> None:
	"""Run the interactive start command wizard."""
	print('🚀 Welcome to App-Use Setup Wizard!')
	print('=' * 50)

	# Step 0: Clean up any stuck iOS processes
	from .utils import cleanup_ios_processes

	cleanup_ios_processes()

	# Step 1: Start Appium server
	if not start_appium_server():
		sys.exit(1)

	try:
		# Register cleanup handler for appium server
		atexit.register(stop_appium_server)

		# Run the setup wizard
		config = _run_setup_wizard()

		if config:
			# Launch the GUI
			print('\n🚀 Launching App-Use GUI...')
			time.sleep(1)  # Brief pause before launching GUI

			import asyncio

			from .gui import run_textual_interface

			asyncio.run(run_textual_interface(config))

	except KeyboardInterrupt:
		print('\n❌ Setup cancelled by user')
	except Exception as e:
		print(f'❌ Error during setup: {e}')
	finally:
		# Clean up appium server if we started it
		stop_appium_server()


def _get_android_system_packages() -> List[str]:
	"""Get list of Android system packages to skip."""
	return [
		'android',
		'com.android.phone',
		'com.android.systemui',
		'com.android.keychain',
		'com.android.providers.',
		'com.android.server.',
		'com.qualcomm.',
		'com.google.android.permissioncontroller',
		'com.android.bluetooth',
		'com.android.nfc',
		'com.android.wallpaper',
		'com.android.inputmethod',
		'com.android.documentsui',
		'com.android.internal',
		'com.google.android.overlay',
		'com.android.backupconfirm',
		'com.android.bips',
		# ... (truncated for brevity, full list from original code)
	]


def _get_android_app_name(device_id: str, package_name: str) -> str:
	"""Get human-readable app name for Android package."""
	try:
		dumpsys_result = subprocess.run(
			['adb', '-s', device_id, 'shell', 'dumpsys', 'package', package_name], capture_output=True, text=True, timeout=5
		)

		app_name = package_name  # Default fallback

		if dumpsys_result.returncode == 0:
			# Parse dumpsys output to find application label
			lines = dumpsys_result.stdout.split('\n')
			for line in lines:
				if 'label=' in line:
					try:
						label = line.split('label=')[1].split()[0].strip('"\'')
						if label and label != package_name and len(label) > 1:
							app_name = label
							break
					except Exception:
						continue

		return app_name

	except Exception:
		return package_name


def _prompt_with_search(prompt: str, options: List[str], allow_empty: bool, search_data: Optional[List[str]]) -> Optional[int]:
	"""Handle selection with search functionality."""
	print(f'\n{prompt}')
	print(f'📋 Found {len(options)} options. You can:')
	print('  • Type a number to select directly')
	print('  • Type text to search/filter options' + (' (searches names and IDs)' if search_data else ''))
	print("  • Type 'list' to see all options")
	if allow_empty:
		print('  • Press Enter to skip')

	filtered_options = options.copy()
	original_indices = list(range(len(options)))

	while True:
		try:
			if allow_empty:
				user_input = input(f'\n🔍 Search or select (1-{len(filtered_options)} from filtered list): ').strip()
				if not user_input:
					return None
			else:
				user_input = input(f'\n🔍 Search or select (1-{len(filtered_options)} from filtered list): ').strip()

			# Check if it's a direct number selection
			if user_input.isdigit():
				choice_num = int(user_input)
				if 1 <= choice_num <= len(filtered_options):
					# Return the original index
					filtered_index = choice_num - 1
					return original_indices[filtered_index]
				else:
					print(f'❌ Please enter a number between 1 and {len(filtered_options)}')
					continue

			# Handle special commands and search
			elif user_input.lower() == 'list':
				print(f'\n📋 All {len(filtered_options)} options:')
				for i, option in enumerate(filtered_options, 1):
					print(f'  {i:2d}. {option}')
				continue

			# Search functionality
			elif user_input:
				search_term = user_input.lower()
				new_filtered = []
				new_indices = []

				for i, option in enumerate(options):
					# Search in the display option
					option_matches = search_term in option.lower()

					# Also search in additional search data if provided
					search_data_matches = False
					if search_data and i < len(search_data):
						search_data_matches = search_term in search_data[i].lower()

					if option_matches or search_data_matches:
						new_filtered.append(option)
						new_indices.append(i)

				if new_filtered:
					filtered_options = new_filtered
					original_indices = new_indices
					print(f'\n🔍 Found {len(filtered_options)} matches:')
					for i, option in enumerate(filtered_options, 1):
						print(f'  {i:2d}. {option}')
					print(f'\nType a number (1-{len(filtered_options)}) to select, or search again.')
				else:
					print(f"❌ No matches found for '{user_input}'. Try a different search term.")
				continue

			print('❌ Invalid input. Please try again.')

		except KeyboardInterrupt:
			print('\n❌ Setup cancelled')
			sys.exit(1)


def _prompt_simple(prompt: str, options: List[str], allow_empty: bool) -> Optional[int]:
	"""Handle simple selection without search."""
	print(f'\n{prompt}')
	for i, option in enumerate(options, 1):
		print(f'  {i}. {option}')

	while True:
		try:
			if allow_empty:
				choice = input(f'\nEnter choice (1-{len(options)}, or press Enter to skip): ').strip()
				if not choice:
					return None
			else:
				choice = input(f'\nEnter choice (1-{len(options)}): ').strip()

			if choice.isdigit():
				choice_num = int(choice)
				if 1 <= choice_num <= len(options):
					return choice_num - 1

			print('❌ Invalid choice. Please try again.')
		except KeyboardInterrupt:
			print('\n❌ Setup cancelled')
			sys.exit(1)


def _run_setup_wizard() -> Optional[Dict]:
	"""Run the main setup wizard flow."""
	from .devices import get_apps_for_device, get_devices_for_platform
	from .utils import prompt_selection

	# Step 2: Select platform
	platforms = ['Android', 'iOS']
	platform_choice = prompt_selection('📱 Select platform:', platforms)
	if platform_choice is None:
		print('❌ No platform selected')
		return None

	platform = platforms[platform_choice]
	print(f'✅ Selected platform: {platform}')

	# Step 3: Select device
	devices = get_devices_for_platform(platform)
	if not devices:
		print(f'❌ No {platform} devices found')
		return None

	device_names = [dev['name'] for dev in devices]
	device_choice = prompt_selection(f'📱 Select {platform} device:', device_names)
	if device_choice is None:
		print('❌ No device selected')
		return None

	selected_device = devices[device_choice]
	print(f'✅ Selected device: {selected_device["name"]}')

	# Step 4: Select app
	print(f'\n🔍 Getting apps from {selected_device["name"]}...')
	apps = get_apps_for_device(selected_device, platform)

	if not apps:
		print(f'❌ No apps found on {selected_device["name"]}')
		return None

	print(f'✅ Found {len(apps)} apps')
	app_names = [app['name'] for app in apps]
	app_choice = prompt_selection('📲 Select app to control:', app_names)
	if app_choice is None:
		print('❌ No app selected')
		return None

	selected_app = apps[app_choice]
	print(f'✅ Selected app: {selected_app["name"]}')

	# Step 5: Create and save configuration
	config = _create_config(platform, selected_device, selected_app)
	save_user_config(config)

	print('\n' + '=' * 50)
	print('🎉 Setup complete! Configuration saved.')
	print(f'Platform: {platform}')
	print(f'Device: {selected_device["name"]}')
	print(f'App: {selected_app["name"]}')
	print('=' * 50)

	return config


def _create_config(platform: str, selected_device: Dict, selected_app: Dict) -> Dict:
	"""Create configuration dictionary."""
	config = load_user_config()
	config['app']['platform_name'] = platform
	config['app']['device_name'] = selected_device['id']

	if platform == 'Android':
		config['app']['app_package'] = selected_app['package']
		config['app']['app_activity'] = selected_app.get('activity')
		config['app']['bundle_id'] = None
	else:  # iOS
		config['app']['bundle_id'] = selected_app['bundle_id']
		config['app']['app_package'] = None
		config['app']['app_activity'] = None

	return config
