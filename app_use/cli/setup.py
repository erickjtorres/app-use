"""
Environment setup command for app-use CLI.

Handles installation of dependencies and environment setup.
"""

import os
import platform
import subprocess


def run_setup_command() -> None:
	"""Run the setup command to install dependencies."""
	print('🔧 App-Use Environment Setup')
	print('=' * 40)

	# Check platform
	system = platform.system()
	if system != 'Darwin':
		print('⚠️  This setup is optimized for macOS. Some steps may not work on other platforms.')
		print('📖 Please refer to the documentation for manual setup instructions.')
		return

	print(f'📱 Detected system: {system}')

	# Check for required tools
	missing_tools = []
	required_tools = [
		('node', 'Node.js (required for Appium)'),
		('npm', 'npm (required for Appium)'),
		('java', 'Java JDK (required for Android)'),
		('brew', 'Homebrew (recommended for macOS)'),
	]

	print('\n🔍 Checking required tools...')
	for tool, description in required_tools:
		if not _check_command_exists(tool):
			missing_tools.append((tool, description))
			print(f'  ❌ {tool} - {description}')
		else:
			print(f'  ✅ {tool} - {description}')

	if missing_tools:
		print('\n⚠️  Missing required tools:')
		for tool, description in missing_tools:
			print(f'   • {tool} - {description}')
		print('\n💡 Please install missing tools manually and run setup again.')
		return

	# Install Appium
	print('\n📦 Installing Appium...')
	if _install_appium():
		print('✅ Appium installed successfully')
	else:
		print('❌ Failed to install Appium')
		return

	# Install Appium drivers
	print('\n🔧 Installing Appium drivers...')
	drivers = [('xcuitest', 'iOS automation'), ('uiautomator2', 'Android automation')]

	for driver, description in drivers:
		print(f'  Installing {driver} driver ({description})...')
		if _install_appium_driver(driver):
			print(f'  ✅ {driver} driver installed')
		else:
			print(f'  ❌ Failed to install {driver} driver')

	# Install iOS tools if on macOS
	if system == 'Darwin':
		print('\n📱 Installing iOS development tools...')
		if _install_ios_tools():
			print('✅ iOS tools installed successfully')
		else:
			print('⚠️  Some iOS tools may not have installed correctly')

	# Install Android tools
	print('\n🤖 Installing Android development tools...')
	if _install_android_tools():
		print('✅ Android tools installed successfully')
	else:
		print('⚠️  Some Android tools may not have installed correctly')

	print('\n🎉 Setup completed!')
	print('💡 Next steps:')
	print("  1. Run 'app-use doctor' to verify your setup")
	print("  2. Run 'app-use start' to begin using app-use")


def _check_command_exists(command: str) -> bool:
	"""Check if a command exists in the system PATH."""
	try:
		subprocess.run([command, '--version'], capture_output=True, timeout=5)
		return True
	except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
		return False


def _install_appium() -> bool:
	"""Install Appium using npm."""
	try:
		# Check if already installed
		result = subprocess.run(['appium', '--version'], capture_output=True, timeout=5)
		if result.returncode == 0:
			print('  ℹ️  Appium is already installed')
			return True

		# Install Appium
		result = subprocess.run(['npm', 'install', '-g', 'appium'], timeout=120)
		return result.returncode == 0
	except Exception as e:
		print(f'  ❌ Error installing Appium: {e}')
		return False


def _install_appium_driver(driver: str) -> bool:
	"""Install an Appium driver."""
	try:
		# Check if already installed
		result = subprocess.run(['appium', 'driver', 'list'], capture_output=True, timeout=10)
		if result.returncode == 0 and driver in result.stdout.decode():
			print(f'    ℹ️  {driver} driver is already installed')
			return True

		# Install driver
		result = subprocess.run(['appium', 'driver', 'install', driver], timeout=60)
		return result.returncode == 0
	except Exception as e:
		print(f'    ❌ Error installing {driver} driver: {e}')
		return False


def _install_ios_tools() -> bool:
	"""Install iOS development tools."""
	success = True

	# Check Xcode command line tools
	try:
		result = subprocess.run(['xcode-select', '-p'], capture_output=True, timeout=5)
		if result.returncode != 0:
			print('  Installing Xcode command line tools...')
			subprocess.run(['xcode-select', '--install'], timeout=30)
		else:
			print('  ✅ Xcode command line tools are installed')
	except Exception as e:
		print(f'  ⚠️  Error checking Xcode tools: {e}')
		success = False

	# Install libimobiledevice for real device support
	try:
		if _check_command_exists('brew'):
			print('  Installing libimobiledevice...')
			result = subprocess.run(['brew', 'install', 'libimobiledevice'], timeout=120)
			if result.returncode == 0:
				print('  ✅ libimobiledevice installed')
			else:
				print('  ⚠️  Failed to install libimobiledevice')
				success = False
		else:
			print('  ⚠️  Homebrew not found, skipping libimobiledevice installation')
	except Exception as e:
		print(f'  ⚠️  Error installing libimobiledevice: {e}')
		success = False

	return success


def _install_android_tools() -> bool:
	"""Install Android development tools."""
	success = True

	# Install Android platform tools
	try:
		if _check_command_exists('brew'):
			print('  Installing Android platform tools...')
			result = subprocess.run(['brew', 'install', 'android-platform-tools'], timeout=120)
			if result.returncode == 0:
				print('  ✅ Android platform tools installed')
			else:
				print('  ⚠️  Failed to install Android platform tools')
				success = False
		else:
			print('  ⚠️  Homebrew not found, skipping Android platform tools installation')
	except Exception as e:
		print(f'  ⚠️  Error installing Android platform tools: {e}')
		success = False

	# Check for Android SDK
	android_home = os.environ.get('ANDROID_HOME')
	if not android_home:
		print('  ⚠️  ANDROID_HOME environment variable not set')
		print('      Please install Android Studio and set ANDROID_HOME')
		success = False
	else:
		print(f'  ✅ ANDROID_HOME is set to: {android_home}')

	return success
