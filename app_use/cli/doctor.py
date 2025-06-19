"""
Environment verification command for app-use CLI.

Similar to Flutter doctor, checks that all dependencies are properly installed.
"""

import json
import os
import re
import subprocess
from typing import List, Tuple


def run_doctor_command() -> None:
	"""Run the doctor command to verify the environment setup."""
	print('🩺 App-Use Doctor')
	print('=' * 30)
	print('Checking your app-use environment...\n')

	issues = []

	# Check core dependencies
	print('📋 Checking core dependencies...')
	core_issues = _check_core_dependencies()
	issues.extend(core_issues)

	# Check Appium installation
	print('\n🤖 Checking Appium installation...')
	appium_issues = _check_appium()
	issues.extend(appium_issues)

	# Check iOS development setup
	print('\n📱 Checking iOS development setup...')
	ios_issues = _check_ios_setup()
	issues.extend(ios_issues)

	# Check Android development setup
	print('\n🤖 Checking Android development setup...')
	android_issues = _check_android_setup()
	issues.extend(android_issues)

	# Check connectivity
	print('\n🔗 Checking device connectivity...')
	connectivity_issues = _check_device_connectivity()
	issues.extend(connectivity_issues)

	# Summary
	print('\n' + '=' * 50)
	if issues:
		print(f'❌ Found {len(issues)} issue(s):')
		for category, issue, solution in issues:
			print(f'\n  [{category}] {issue}')
			if solution:
				print(f'    💡 {solution}')

		print('\n💬 Need help? Join our Discord: https://discord.gg/V9mW8UJ6tx')
	else:
		print('✅ No issues found! Your app-use environment is ready.')
		print("🚀 Run 'app-use start' to begin using app-use.")


def _check_core_dependencies() -> List[Tuple[str, str, str]]:
	"""Check core dependencies like Node.js, Java, etc."""
	issues = []

	# Check Node.js
	if _check_command('node', '--version'):
		print('  ✅ Node.js')
	else:
		issues.append(('Core', 'Node.js not found', 'Install Node.js from https://nodejs.org'))

	# Check npm
	if _check_command('npm', '--version'):
		print('  ✅ npm')
	else:
		issues.append(('Core', 'npm not found', 'npm should come with Node.js'))

	# Check Java
	if _check_command('java', '-version'):
		print('  ✅ Java')
	else:
		issues.append(('Core', 'Java not found', 'Install Java JDK 8+'))

	# Check Python
	if _check_command('python3', '--version'):
		print('  ✅ Python')
	else:
		issues.append(('Core', 'Python not found', 'Install Python 3.8+'))

	return issues


def _check_appium() -> List[Tuple[str, str, str]]:
	"""Check Appium installation and drivers."""
	issues = []

	# Check Appium
	if _check_command('appium', '--version'):
		print('  ✅ Appium server')

		# Check Appium drivers
		try:
			result = subprocess.run(['appium', 'driver', 'list', '--installed'], capture_output=True, text=True, timeout=10)
			if result.returncode == 0:
				# Appium outputs to stderr, and includes ANSI color codes
				output = result.stderr if result.stderr else result.stdout
				# Strip ANSI color codes and convert to lowercase
				output = re.sub(r'\x1b\[[0-9;]*m', '', output).lower()

				# Check for xcuitest driver
				if 'xcuitest' in output:
					print('  ✅ XCUITest driver (iOS)')
				else:
					issues.append(('Appium', 'XCUITest driver not installed', 'Run: appium driver install xcuitest'))

				# Check for uiautomator2 driver
				if 'uiautomator2' in output:
					print('  ✅ UiAutomator2 driver (Android)')
				else:
					issues.append(('Appium', 'UiAutomator2 driver not installed', 'Run: appium driver install uiautomator2'))
			else:
				issues.append(('Appium', 'Cannot list Appium drivers', 'Check Appium installation'))
		except Exception as e:
			issues.append(('Appium', f'Error checking drivers: {e}', 'Reinstall Appium'))
	else:
		issues.append(('Appium', 'Appium not found', 'Run: npm install -g appium'))

	# Check if Appium server is running
	try:
		import requests

		response = requests.get('http://localhost:4723/status', timeout=2)
		if response.status_code == 200:
			print('  ✅ Appium server is running')
		else:
			print('  ⚠️  Appium server is not running (this is okay)')
	except Exception:
		print('  ⚠️  Appium server is not running (this is okay)')

	return issues


def _check_ios_setup() -> List[Tuple[str, str, str]]:
	"""Check iOS development setup."""
	issues = []

	# Check if on macOS
	import platform

	if platform.system() != 'Darwin':
		print('  ⚠️  iOS development requires macOS')
		return [('iOS', 'iOS development requires macOS', 'Use macOS for iOS testing')]

	# Check Xcode command line tools
	if _check_command('xcode-select', '-p'):
		print('  ✅ Xcode command line tools')
	else:
		issues.append(('iOS', 'Xcode command line tools not installed', 'Run: xcode-select --install'))

	# Check for simulators
	try:
		result = subprocess.run(['xcrun', 'simctl', 'list', 'devices', '--json'], capture_output=True, text=True, timeout=10)
		if result.returncode == 0:
			data = json.loads(result.stdout)
			booted_simulators = 0

			for runtime, device_list in data['devices'].items():
				if 'unavailable' not in runtime.lower():
					for device in device_list:
						if device['state'] == 'Booted':
							booted_simulators += 1

			print(f'  ✅ iOS simulators ({booted_simulators} booted)')
			if booted_simulators == 0:
				print('    ℹ️  No simulators are currently booted')
		else:
			issues.append(('iOS', 'Cannot list iOS simulators', 'Check Xcode installation'))
	except Exception as e:
		issues.append(('iOS', f'Error checking simulators: {e}', 'Check Xcode installation'))

	# Check libimobiledevice for real devices
	if _check_command('idevice_id', '-l'):
		print('  ✅ libimobiledevice (real device support)')
	else:
		print('  ⚠️  libimobiledevice not found (real device support)')
		print('    💡 Install with: brew install libimobiledevice')

	return issues


def _check_android_setup() -> List[Tuple[str, str, str]]:
	"""Check Android development setup."""
	issues = []

	# Check ADB
	if _check_command('adb', 'version'):
		print('  ✅ ADB (Android Debug Bridge)')
	else:
		issues.append(('Android', 'ADB not found', 'Install Android SDK platform tools'))

	# Check emulator command
	if _check_command('emulator', '-version'):
		print('  ✅ Android emulator')
	else:
		print('  ⚠️  Android emulator command not found')
		print('    💡 Make sure Android SDK is in PATH')

	# Check ANDROID_HOME
	android_home = os.environ.get('ANDROID_HOME')
	if android_home and os.path.exists(android_home):
		print(f'  ✅ ANDROID_HOME ({android_home})')
	else:
		issues.append(('Android', 'ANDROID_HOME not set or invalid', 'Set ANDROID_HOME environment variable'))

	# Check JAVA_HOME
	java_home = os.environ.get('JAVA_HOME')
	if java_home and os.path.exists(java_home):
		print(f'  ✅ JAVA_HOME ({java_home})')
	else:
		print('  ⚠️  JAVA_HOME not set')
		print('    💡 Set JAVA_HOME for better Android development')

	return issues


def _check_device_connectivity() -> List[Tuple[str, str, str]]:
	"""Check device connectivity."""
	issues = []

	# Check Android devices
	try:
		result = subprocess.run(['adb', 'devices'], capture_output=True, text=True, timeout=10)
		if result.returncode == 0:
			lines = result.stdout.strip().split('\n')[1:]  # Skip header
			android_devices = [line for line in lines if line.strip() and '\tdevice' in line]

			if android_devices:
				print(f'  ✅ Android devices ({len(android_devices)} connected)')
				for line in android_devices:
					device_id = line.split('\t')[0]
					print(f'    • {device_id}')
			else:
				print('  ℹ️  No Android devices connected')
		else:
			print('  ⚠️  Cannot check Android devices')
	except Exception:
		print('  ⚠️  Cannot check Android devices')

	# Check iOS devices (real devices)
	real_ios_devices = []
	try:
		result = subprocess.run(['idevice_id', '-l'], capture_output=True, text=True, timeout=5)
		if result.returncode == 0 and result.stdout.strip():
			real_ios_devices = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
	except Exception:
		pass

	# Check iOS simulators
	booted_simulators = []
	try:
		import platform

		if platform.system() == 'Darwin':  # Only on macOS
			result = subprocess.run(['xcrun', 'simctl', 'list', 'devices', '--json'], capture_output=True, text=True, timeout=10)
			if result.returncode == 0:
				data = json.loads(result.stdout)
				for runtime, device_list in data['devices'].items():
					if 'unavailable' not in runtime.lower():
						for device in device_list:
							if device['state'] == 'Booted':
								booted_simulators.append(f'{device["name"]} ({runtime.split(".")[-1]})')
	except Exception:
		pass

	# Report iOS connectivity
	total_ios = len(real_ios_devices) + len(booted_simulators)
	if total_ios > 0:
		print(f'  ✅ iOS devices/simulators ({total_ios} available)')
		for device_id in real_ios_devices:
			print(f'    • {device_id} (physical)')
		for simulator in booted_simulators:
			print(f'    • {simulator} (simulator)')
	else:
		print('  ℹ️  No iOS devices or simulators available')

	return issues


def _check_command(command: str, *args) -> bool:
	"""Check if a command exists and runs successfully."""
	try:
		result = subprocess.run([command] + list(args), capture_output=True, timeout=5)
		return result.returncode == 0
	except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
		return False
