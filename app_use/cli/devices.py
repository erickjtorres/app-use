"""
Device and app discovery for app-use CLI.

Handles finding available devices and installed apps.
"""

import json
import subprocess
from typing import Dict, List


def get_devices_for_platform(platform: str) -> List[Dict[str, str]]:
	"""Get available devices for the specified platform."""
	if platform.lower() == 'android':
		return get_android_devices()
	elif platform.lower() == 'ios':
		return get_ios_devices()
	else:
		return []


def get_apps_for_device(device: Dict[str, str], platform: str) -> List[Dict[str, str]]:
	"""Get installed apps for the specified device."""
	if platform.lower() == 'android':
		return get_android_apps(device['id'])
	elif platform.lower() == 'ios':
		return get_ios_apps(device['id'], device['type'])
	else:
		return []


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
								'device_name': device['name'],
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
		# Get all packages
		result = subprocess.run(
			['adb', '-s', device_id, 'shell', 'pm', 'list', 'packages'], capture_output=True, text=True, timeout=20
		)
		if result.returncode == 0:
			packages = result.stdout.strip().split('\n')
			print(f'🔍 Found {len(packages)} packages, extracting app names...')

			# Skip system packages
			skip_packages = _get_android_system_packages()

			for package_line in packages:
				if package_line.startswith('package:'):
					package_name = package_line.replace('package:', '').strip()

					if any(package_name.startswith(skip) for skip in skip_packages):
						continue

					# Get app name
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

	except Exception as e:
		print(f'⚠️ Error getting Android apps: {e}')

	# Sort apps by name
	apps.sort(key=lambda x: x['name'].lower())

	return apps


def get_ios_apps(device_id: str, device_type: str) -> List[Dict[str, str]]:
	"""Get list of installed apps on iOS device."""
	apps = []
	try:
		if device_type == 'simulator':
			apps = _get_ios_simulator_apps(device_id)
		else:
			apps = _get_ios_device_apps(device_id)

	except Exception as e:
		print(f'⚠️ Error getting iOS apps: {e}')

	# Remove duplicates and sort
	seen = set()
	unique_apps = []
	for app in apps:
		if app['bundle_id'] not in seen:
			seen.add(app['bundle_id'])
			unique_apps.append(app)

	unique_apps.sort(key=lambda x: x['name'].lower())

	return unique_apps


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
		'com.google.android.gms',
		'com.google.android.gsf',
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


def _get_ios_simulator_apps(device_id: str) -> List[Dict[str, str]]:
	"""Get apps from iOS simulator."""
	apps = []

	try:
		# Get apps in plist format and convert to JSON using plutil
		result = subprocess.run(['xcrun', 'simctl', 'listapps', device_id], capture_output=True, text=True, timeout=20)
		if result.returncode == 0:
			# Convert plist to JSON using plutil
			plutil_result = subprocess.run(
				['plutil', '-convert', 'json', '-o', '-', '-'], input=result.stdout, capture_output=True, text=True, timeout=10
			)

			if plutil_result.returncode == 0:
				# Parse converted JSON
				data = json.loads(plutil_result.stdout)

				print(f'🔍 Processing {len(data)} apps from simulator...')

				# Skip system apps that aren't useful for testing
				skip_bundles = {
					'com.apple.Preferences',
					'com.apple.springboard',
					'com.apple.WebKit.WebContent',
					'com.apple.mobilesafari.SafariViewService',
					'com.apple.CoreSimulator.SimulatorTrampoline',
					'com.apple.AccountAuthenticationDialog',
					'com.apple.AuthKit.AuthKitUIService',
					'com.apple.datadetectors.DDActionsService',
					'com.apple.SIMSetupUIService',
					'com.apple.PreviewShell',  # Xcode Previews
				}

				for bundle_id, app_info in data.items():
					# Skip system/internal apps
					if bundle_id in skip_bundles or bundle_id.startswith('com.apple.WebKit'):
						continue

					# Get app name - prefer CFBundleDisplayName, fallback to CFBundleName
					app_name = app_info.get('CFBundleDisplayName') or app_info.get('CFBundleName') or bundle_id

					# Skip apps without meaningful names
					if not app_name or len(app_name.strip()) < 2:
						continue

					apps.append({'bundle_id': bundle_id, 'name': app_name.strip()})
			else:
				print(f'❌ Failed to convert plist to JSON: {plutil_result.stderr}')

		else:
			print(f'❌ Failed to list simulator apps: {result.stderr}')

	except json.JSONDecodeError as e:
		print(f'⚠️ Error parsing converted JSON: {e}')
	except Exception as e:
		print(f'⚠️ Error getting simulator apps: {e}')

	return apps


def _get_ios_device_apps(device_id: str) -> List[Dict[str, str]]:
	"""Get apps from iOS device."""
	apps = []

	result = subprocess.run(['ideviceinstaller', '-u', device_id, '-l'], capture_output=True, text=True, timeout=60)
	if result.returncode == 0:
		lines = result.stdout.strip().split('\n')
		print(f'🔍 Processing {len(lines)} lines from device...')

		for line in lines:
			line = line.strip()
			if not line or line.startswith('Total'):
				continue

			# Skip the header line
			if line.startswith('CFBundleIdentifier'):
				continue

			# Handle comma-separated format: bundle_id, "version", "app_name"
			if ',' in line:
				parts = [part.strip().strip('"') for part in line.split(',')]
				if len(parts) >= 3:
					bundle_id = parts[0].strip()
					app_name = parts[2].strip()  # Third part is the app name

					# Skip empty or invalid entries and system bundles
					if (
						bundle_id
						and app_name
						and len(app_name) > 1
						and not bundle_id.startswith('CFBundle')
						and app_name != 'CFBundleDisplayName'
					):
						apps.append({'bundle_id': bundle_id, 'name': app_name})
			# Handle dash-separated format: bundle_id - app_name (fallback)
			elif ' - ' in line:
				parts = line.split(' - ', 1)
				if len(parts) == 2:
					bundle_id = parts[0].strip()
					app_name = parts[1].strip()

					# Skip empty or invalid entries
					if bundle_id and app_name and len(app_name) > 1:
						apps.append({'bundle_id': bundle_id, 'name': app_name})
	else:
		print(f'❌ ideviceinstaller command failed with return code {result.returncode}')
		print(f'❌ Error: {result.stderr}')

	print(f'🔍 Found {len(apps)} apps total')
	return apps
