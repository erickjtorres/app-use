import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, List, Dict, Optional, Tuple

from dotenv import load_dotenv

load_dotenv()

try:
	import click
	from textual import events
	from textual.app import App as TextualApp, ComposeResult
	from textual.binding import Binding
	from textual.containers import Container, HorizontalGroup, VerticalScroll
	from textual.widgets import Footer, Header, Input, Label, Link, RichLog, Static
except ImportError:
	print('⚠️ CLI addon is not installed. Please install it with: `pip install app-use[cli]` and try again.')
	sys.exit(1)

import langchain_anthropic
import langchain_google_genai
import langchain_openai

try:
	import readline

	READLINE_AVAILABLE = True
except ImportError:
	# readline not available on Windows by default
	READLINE_AVAILABLE = False


os.environ['APP_USE_LOGGING_LEVEL'] = 'result'

from app_use.agent.service import Agent
from app_use.controller.service import Controller
from app_use.app.app import App

# Paths
USER_CONFIG_DIR = Path.home() / '.config' / 'appuse'
USER_CONFIG_FILE = USER_CONFIG_DIR / 'config.json'
USER_DATA_DIR = USER_CONFIG_DIR / 'data'

# Default User settings
MAX_HISTORY_LENGTH = 100

# Ensure directories exist
USER_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Global variable to track appium server process
_appium_process: Optional[subprocess.Popen] = None

# Logo components with styling for rich panels
APP_USE_LOGO = """
[white]  █████╗ ██████╗ ██████╗         ██╗   ██╗███████╗███████╗[/]
[white] ██╔══██╗██╔══██╗██╔══██╗        ██║   ██║██╔════╝██╔════╝[/]
[white] ███████║██████╔╝██████╔╝        ██║   ██║███████╗█████╗[/]  
[white] ██╔══██║██╔═══╝ ██╔═══╝         ██║   ██║╚════██║██╔══╝[/]  
[white] ██║  ██║██║     ██║             ╚██████╔╝███████║███████╗[/]
[white] ╚═╝  ╚═╝╚═╝     ╚═╝              ╚═════╝ ╚══════╝╚══════╝[/]
"""


# Common UI constants
TEXTUAL_BORDER_STYLES = {'logo': 'blue', 'info': 'blue', 'input': 'orange3', 'working': 'yellow', 'completion': 'green'}


def get_default_config() -> dict[str, Any]:
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


def load_user_config() -> dict[str, Any]:
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


def save_user_config(config: dict[str, Any]) -> None:
	"""Save user configuration to file."""
	# Ensure command history doesn't exceed maximum length
	if 'command_history' in config and isinstance(config['command_history'], list):
		if len(config['command_history']) > MAX_HISTORY_LENGTH:
			config['command_history'] = config['command_history'][-MAX_HISTORY_LENGTH:]

	with open(USER_CONFIG_FILE, 'w') as f:
		json.dump(config, f, indent=2)


def update_config_with_click_args(config: dict[str, Any], ctx: click.Context) -> dict[str, Any]:
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


def setup_readline_history(history: list[str]) -> None:
	"""Set up readline with command history."""
	if not READLINE_AVAILABLE:
		return

	# Add history items to readline
	for item in history:
		readline.add_history(item)


def get_llm(config: dict[str, Any]):
	"""Get the language model based on config and available API keys."""
	# Set API keys from config if available
	api_keys = config.get('model', {}).get('api_keys', {})
	model_name = config.get('model', {}).get('name')
	temperature = config.get('model', {}).get('temperature', 0.0)

	# Set environment variables if they're in the config but not in the environment
	if api_keys.get('OPENAI_API_KEY') and not os.getenv('OPENAI_API_KEY'):
		os.environ['OPENAI_API_KEY'] = api_keys['OPENAI_API_KEY']
	if api_keys.get('ANTHROPIC_API_KEY') and not os.getenv('ANTHROPIC_API_KEY'):
		os.environ['ANTHROPIC_API_KEY'] = api_keys['ANTHROPIC_API_KEY']
	if api_keys.get('GOOGLE_API_KEY') and not os.getenv('GOOGLE_API_KEY'):
		os.environ['GOOGLE_API_KEY'] = api_keys['GOOGLE_API_KEY']

	if model_name:
		if model_name.startswith('gpt'):
			if not os.getenv('OPENAI_API_KEY'):
				print('⚠️  OpenAI API key not found. Please update your config or set OPENAI_API_KEY environment variable.')
				sys.exit(1)
			return langchain_openai.ChatOpenAI(model=model_name, temperature=temperature)
		elif model_name.startswith('claude'):
			if not os.getenv('ANTHROPIC_API_KEY'):
				print('⚠️  Anthropic API key not found. Please update your config or set ANTHROPIC_API_KEY environment variable.')
				sys.exit(1)
			return langchain_anthropic.ChatAnthropic(model=model_name, temperature=temperature)
		elif model_name.startswith('gemini'):
			if not os.getenv('GOOGLE_API_KEY'):
				print('⚠️  Google API key not found. Please update your config or set GOOGLE_API_KEY environment variable.')
				sys.exit(1)
			return langchain_google_genai.ChatGoogleGenerativeAI(model=model_name, temperature=temperature)

	# Auto-detect based on available API keys
	if os.getenv('OPENAI_API_KEY'):
		return langchain_openai.ChatOpenAI(model='gpt-4o', temperature=temperature)
	elif os.getenv('ANTHROPIC_API_KEY'):
		return langchain_anthropic.ChatAnthropic(model='claude-3.5-sonnet-exp', temperature=temperature)
	elif os.getenv('GOOGLE_API_KEY'):
		return langchain_google_genai.ChatGoogleGenerativeAI(model='gemini-2.0-flash-lite', temperature=temperature)
	else:
		print(
			'⚠️  No API keys found. Please update your config or set one of: OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY.'
		)
		sys.exit(1)


# =============================================================================
# Start Command Helper Functions
# =============================================================================

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
		print("✅ Appium server is already running")
		return True
	
	print("🚀 Starting Appium server...")
	
	try:
		# Start appium server in background
		_appium_process = subprocess.Popen(
			['appium'],
			stdout=subprocess.DEVNULL,
			stderr=subprocess.DEVNULL,
			preexec_fn=os.setsid if os.name != 'nt' else None  # Create new process group on Unix
		)
		
		# Wait for server to start
		for _ in range(10):  # Wait up to 10 seconds
			time.sleep(1)
			if is_appium_running():
				print("✅ Appium server started successfully")
				return True
		
		print("❌ Appium server failed to start within 10 seconds")
		return False
		
	except FileNotFoundError:
		print("❌ Appium not found. Please install it with: npm install -g appium")
		return False
	except Exception as e:
		print(f"❌ Error starting Appium server: {e}")
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
			print("✅ Appium server stopped")
		except Exception as e:
			print(f"⚠️ Error stopping Appium server: {e}")
		finally:
			_appium_process = None


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
					devices.append({
						'id': device_id,
						'name': f"Device: {device_id}",
						'type': 'device'
					})
	except Exception as e:
		print(f"⚠️ Error getting Android devices: {e}")
	
	# Get available emulators
	try:
		result = subprocess.run(['emulator', '-list-avds'], capture_output=True, text=True, timeout=10)
		if result.returncode == 0 and result.stdout.strip():
			emulators = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
			for emulator in emulators:
				devices.append({
					'id': emulator,
					'name': f"Emulator: {emulator}",
					'type': 'emulator'
				})
	except FileNotFoundError:
		print("⚠️ Android emulator command not found. Make sure Android SDK is installed and emulator is in PATH")
	except Exception as e:
		print(f"⚠️ Error getting Android emulators: {e}")
	
	return devices


def get_ios_devices() -> List[Dict[str, str]]:
	"""Get list of available iOS devices and simulators."""
	devices = []
	
	# Get simulators
	try:
		result = subprocess.run(['xcrun', 'simctl', 'list', 'devices', '--json'], capture_output=True, text=True, timeout=10)
		if result.returncode == 0:
			import json
			data = json.loads(result.stdout)
			for runtime, device_list in data['devices'].items():
				# Skip unavailable runtimes
				if 'unavailable' in runtime.lower():
					continue
					
				for device in device_list:
					if device['state'] == 'Booted':
						# Clean up runtime name for display
						runtime_display = runtime.replace('com.apple.CoreSimulator.SimRuntime.', '').replace('-', '.')
						
						devices.append({
							'id': device['udid'],
							'name': f"Simulator: {device['name']} ({runtime_display})",
							'type': 'simulator',
							'device_name': device['name'],  # Store original name for reference
							'runtime': runtime
						})
			
			print(f"📱 Found {len(devices)} booted iOS simulators")
			
	except FileNotFoundError:
		print("⚠️ Xcode command line tools not found. Please install with: xcode-select --install")
	except json.JSONDecodeError as e:
		print(f"⚠️ Error parsing iOS simulator data: {e}")
	except Exception as e:
		print(f"⚠️ Error getting iOS simulators: {e}")
	
	# Get real devices
	try:
		result = subprocess.run(['idevice_id', '-l'], capture_output=True, text=True, timeout=10)
		if result.returncode == 0 and result.stdout.strip():
			device_ids = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
			for device_id in device_ids:
				# Try to get device name
				try:
					name_result = subprocess.run(['ideviceinfo', '-u', device_id, '-k', 'DeviceName'], 
												capture_output=True, text=True, timeout=5)
					device_name = name_result.stdout.strip() if name_result.returncode == 0 else device_id
				except:
					device_name = device_id
				
				devices.append({
					'id': device_id,
					'name': f"Device: {device_name}",
					'type': 'device'
				})
	except FileNotFoundError:
		print("⚠️ iOS device tools not found. Make sure libimobiledevice is installed (brew install libimobiledevice)")
	except Exception as e:
		print(f"⚠️ Error getting iOS devices: {e}")
	
	return devices


def get_android_apps(device_id: str) -> List[Dict[str, str]]:
	"""Get list of installed apps on Android device."""
	apps = []
	
	try:
		# Get all packages first
		result = subprocess.run(['adb', '-s', device_id, 'shell', 'pm', 'list', 'packages'], 
							   capture_output=True, text=True, timeout=20)
		if result.returncode == 0:
			packages = result.stdout.strip().split('\n')
			print(f"🔍 Found {len(packages)} packages, extracting app names...")
			
			for package_line in packages:
				if package_line.startswith('package:'):
					package_name = package_line.replace('package:', '').strip()
					
					# Skip some system packages that aren't useful for app control
					skip_packages = [
						'android', 'com.android.phone', 'com.android.systemui',
						'com.android.keychain', 'com.android.providers.',
						'com.android.server.', 'com.qualcomm.', 'com.google.android.permissioncontroller',
						'com.android.bluetooth', 'com.android.nfc', 'com.android.wallpaper',
						'com.android.inputmethod', 'com.android.documentsui', 'com.android.internal', 'com.google.android.overlay',
						'com.android.backupconfirm', 'com.android.bips', 'com.android.bookmarkprovider',
						'com.android.calllogbackup', 'com.android.carrierconfig', 'com.android.carrierdefaultapp',
						'com.android.certinstaller', 'com.android.companiondevicemanager', 'com.android.credentialmanager',
						'com.android.cts.ctsshim', 'com.android.cts.priv.ctsshim', 'com.android.devicediagnostics',
						'com.android.cts.priv.ctsshim', 'com.android.devicediagnostics', 'com.android.dynsystem',
						'com.android.externalstorage', 'com.android.htmlviewer', 'com.android.imsserviceentitlement',
						'com.android.inputdevices', 'com.android.intentresolver', 'com.android.localtransport',
						'com.android.location.fused', 'com.android.managedprovisioning', 'com.android.mms.service',
						'com.android.mtp', 'com.android.networkstack.tethering.emulator', 'com.android.ons',
						'com.android.pacprocessor', 'com.android.printspooler', 'com.android.proxyhandler',
						'com.android.se', 'com.android.sharedstoragebackup', 'com.android.shell',
						'com.android.simappdialog', 'com.android.stk', 'com.android.virtualmachine.res',
						'com.android.vpndialogs'
						'com.android.devicelockcontroller', 'com.android.htmlviewer',
						'com.android.imsserviceentitlement', 'com.android.inputdevices',
						'com.android.intentresolver', 'com.android.localtransport',
						'com.android.location.fused', 'com.android.managedprovisioning',
						'com.android.mms.service', 'com.android.mtp', 'com.android.networkstack.tethering.emulator',
						'com.android.ons', 'com.android.pacprocessor', 'com.android.printspooler',
						'com.android.proxyhandler', 'com.android.se', 'com.android.sharedstoragebackup',
						'com.android.shell', 'com.android.simappdialog', 'com.android.stk',
						'com.android.virtualmachine.res', 'com.android.vpndialogs'
						'com.android.shell', 'com.android.simappdialog', 'com.android.stk',
						'com.android.virtualmachine.res', 'com.android.vpndialogs',
						'com.google.android.adservices.api', 'com.google.android.appsearch.apk',
						'com.google.android.as', 'com.google.android.as.oss',
						'com.google.android.captiveportallogin', 'com.google.android.cellbroadcastreceiver',
						'com.google.android.cellbroadcastservice', 'com.google.android.configupdater',
						'com.google.android.connectivity.resources', 'com.google.android.ext.services',
						'com.google.android.ext.shared', 'com.google.android.federatedcompute',
						'com.google.android.gms', 'com.google.android.gms.supervision',
						'com.google.android.googlesdksetup', 'com.google.android.gsf',
						'com.google.android.hotspot2.osulogin', 'com.google.android.modulemetadata',
						'com.google.android.networkstack', 'com.google.android.networkstack.tethering',
						'com.google.android.networkstack.tethering.emulator', 'com.google.android.odad',
						'com.google.android.ondevicepersonalization.services', 'com.google.android.onetimeinitializer',
						'com.google.android.partnersetup', 'com.google.android.printservice.recommendation',
						'com.google.android.providers.media.module', 'com.google.android.rkpdapp',
						'com.google.android.sdksandbox', 'com.google.android.server.deviceconfig.resources',
						'com.google.android.settings.intelligence', 'com.google.android.telephony.satellite',
						'com.google.android.uwb.resources', 'com.google.android.webview',
						'com.google.android.wifi.dialog', 'com.google.android.wifi.resources',
						'com.google.android.googlesdksetup', 'com.google.android.gsf',
						'com.google.android.hotspot2.osulogin', 'com.google.android.modulemetadata',
						'com.google.android.networkstack', 'com.google.android.networkstack.tethering',
						'com.google.android.networkstack.tethering.emulator', 'com.google.android.odad',
						'com.google.android.ondevicepersonalization.services', 'com.google.android.onetimeinitializer',
						'com.google.android.partnersetup', 'com.google.android.printservice.recommendation',
						'com.google.android.providers.media.module', 'com.google.android.rkpdapp',
						'com.google.android.safetycenter.resources', 'com.google.android.sdksandbox',
						'com.google.android.server.deviceconfig.resources', 'com.google.android.settings.intelligence',
						'com.google.android.telephony.satellite', 'com.google.android.uwb.resources',
						'com.google.android.webview', 'com.google.android.wifi.dialog',
						'com.google.android.wifi.resources', 'com.google.mainline.adservices',
						'com.google.mainline.telemetry'
					]
					
					if any(package_name.startswith(skip) for skip in skip_packages):
						continue
					
					# Get the actual app name from dumpsys
					try:
						dumpsys_result = subprocess.run([
							'adb', '-s', device_id, 'shell', 
							'dumpsys', 'package', package_name
						], capture_output=True, text=True, timeout=5)
						
						app_name = package_name  # Default fallback
						
						if dumpsys_result.returncode == 0:
							# Parse dumpsys output to find application label
							lines = dumpsys_result.stdout.split('\n')
							for line in lines:
								# Look for application label
								if 'applicationInfo' in line or 'Application Label' in line:
									# This is a simplified parser - dumpsys output can vary
									continue
								# Try to find the label in various formats
								if 'label=' in line:
									try:
										label = line.split('label=')[1].split()[0].strip('"\'')
										if label and label != package_name and len(label) > 1:
											app_name = label
											break
									except:
										continue
						
						# If we couldn't get a good name from dumpsys, try alternative method
						if app_name == package_name:
							try:
								# Try to get app info using cmd package query (Android 7+)
								query_result = subprocess.run([
									'adb', '-s', device_id, 'shell', 
									'cmd', 'package', 'query', package_name
								], capture_output=True, text=True, timeout=3)
								
								if query_result.returncode == 0 and query_result.stdout.strip():
									# If this doesn't work, fall back to package name
									pass
							except:
								pass
						
						apps.append({
							'package': package_name,
							'name': app_name,
							'activity': None  # Will be auto-detected
						})
						
					except Exception as e:
						# If we can't get detailed info, still include the package
						apps.append({
							'package': package_name,
							'name': package_name,
							'activity': None
						})
		else:
			print(f"❌ Failed to get packages: {result.stderr}")
			return apps
						
	except Exception as e:
		print(f"⚠️ Error getting Android apps: {e}")
	
	# Sort apps by name for better UX
	apps.sort(key=lambda x: x['name'].lower())
	
	return apps


def get_ios_apps(device_id: str, device_type: str) -> List[Dict[str, str]]:
	"""Get list of installed apps on iOS device."""
	apps = []
	
	try:
		if device_type == 'simulator':
			# For simulators, use simctl listapps
			result = subprocess.run(['xcrun', 'simctl', 'listapps', device_id], 
								   capture_output=True, text=True, timeout=20)
			if result.returncode == 0:
				try:
					# Parse the plist-style output from simctl listapps
					output = result.stdout
					print(f"🔍 Parsing simulator app list...")
					
					# Extract app entries using regex or string parsing
					import re
					
					# Find all bundle ID entries
					bundle_pattern = r'"([^"]+)"\s*=\s*\{'
					bundle_matches = re.findall(bundle_pattern, output)
					
					print(f"🔍 Found {len(bundle_matches)} apps on simulator, processing...")
					
					for bundle_id in bundle_matches:
						# Skip system-level apps that can't be meaningfully controlled
						skip_bundles = [
							'com.apple.springboard', 'com.apple.backboardd', 'com.apple.mobile.',
							'com.apple.accessibility.', 'com.apple.CoreAuthentication',
							'com.apple.datadetectors', 'com.apple.GameController', 'com.apple.GameKit',
							'com.apple.PassKit', 'com.apple.WebKit', 'com.apple.AuthKit',
							'com.apple.Spotlight', 'com.apple.searchd', 'com.apple.siri',
							'com.apple.CoreSimulator', 'com.apple.Preferences.CloudDocsDaemon'
						]
						
						# Skip if it's in the skip list
						if any(bundle_id.startswith(skip) for skip in skip_bundles):
							continue
						
						# Extract the app section for this bundle ID
						start_pattern = rf'"{re.escape(bundle_id)}"\s*=\s*\{{'
						end_pattern = r'^\s*\};\s*$'
						
						# Find the section for this bundle
						start_match = re.search(start_pattern, output, re.MULTILINE)
						if start_match:
							start_pos = start_match.end()
							
							# Find the end of this section
							lines = output[start_pos:].split('\n')
							app_section = []
							brace_count = 1
							
							for line in lines:
								if '{' in line:
									brace_count += line.count('{')
								if '}' in line:
									brace_count -= line.count('}')
								
								app_section.append(line)
								
								if brace_count <= 0:
									break
							
							app_section_text = '\n'.join(app_section)
							
							# Extract app name from the section
							app_name = bundle_id  # Default fallback
							
							# Look for CFBundleDisplayName first
							display_name_match = re.search(r'CFBundleDisplayName\s*=\s*([^;]+);', app_section_text)
							if display_name_match:
								app_name = display_name_match.group(1).strip().strip('"')
							else:
								# Fall back to CFBundleName
								bundle_name_match = re.search(r'CFBundleName\s*=\s*([^;]+);', app_section_text)
								if bundle_name_match:
									app_name = bundle_name_match.group(1).strip().strip('"')
						
						# Only include apps that have a meaningful name and length
						if app_name and len(app_name) > 1 and app_name != bundle_id:
							apps.append({
								'bundle_id': bundle_id,
								'name': app_name
							})
						elif app_name == bundle_id and not bundle_id.startswith('com.apple.'):
							# Include non-Apple apps even if we only have bundle ID
							apps.append({
								'bundle_id': bundle_id,
								'name': bundle_id
							})
							
				except Exception as e:
					print(f"⚠️ Failed to parse simulator app list: {e}")
					print(f"📋 Raw output sample: {result.stdout[:300]}...")
		else:
			# For real devices, use ideviceinstaller
			result = subprocess.run(['ideviceinstaller', '-u', device_id, '-l'], 
								   capture_output=True, text=True, timeout=20)
			if result.returncode == 0:
				lines = result.stdout.strip().split('\n')
				print(f"🔍 Processing {len(lines)} lines from device...")
				
				for line in lines:
					line = line.strip()
					if ' - ' in line and not line.startswith('Total'):
						parts = line.split(' - ', 1)
						if len(parts) == 2:
							bundle_id = parts[0].strip()
							app_name = parts[1].strip()
							
							# Skip empty or invalid entries
							if bundle_id and app_name and len(app_name) > 1:
								apps.append({
									'bundle_id': bundle_id,
									'name': app_name
								})
			else:
				print(f"⚠️ ideviceinstaller command failed with return code {result.returncode}")
				if result.stderr:
					print(f"Error: {result.stderr}")
					
	except Exception as e:
		print(f"⚠️ Error getting iOS apps: {e}")
	
	# Remove duplicates based on bundle_id
	seen = set()
	unique_apps = []
	for app in apps:
		if app['bundle_id'] not in seen:
			seen.add(app['bundle_id'])
			unique_apps.append(app)
	
	# Sort apps by name for better UX
	unique_apps.sort(key=lambda x: x['name'].lower())
	
	return unique_apps


def prompt_selection(prompt: str, options: List[str], allow_empty: bool = False, search_data: Optional[List[str]] = None) -> Optional[int]:
	"""Prompt user to select from a list of options with search functionality."""
	if not options:
		if allow_empty:
			return None
		print("❌ No options available")
		return None
	
	# If there are many options, offer search functionality
	if len(options) > 10:
		print(f"\n{prompt}")
		print(f"📋 Found {len(options)} options. You can:")
		print("  • Type a number to select directly")
		print("  • Type text to search/filter options" + (" (searches names and IDs)" if search_data else ""))
		print("  • Type 'list' to see all options")
		if allow_empty:
			print("  • Press Enter to skip")
		
		filtered_options = options.copy()
		original_indices = list(range(len(options)))
		
		while True:
			try:
				if allow_empty:
					user_input = input(f"\n🔍 Search or select (1-{len(filtered_options)} from filtered list): ").strip()
					if not user_input:
						return None
				else:
					user_input = input(f"\n🔍 Search or select (1-{len(filtered_options)} from filtered list): ").strip()
				
				# Check if it's a direct number selection
				if user_input.isdigit():
					choice_num = int(user_input)
					if 1 <= choice_num <= len(filtered_options):
						# Return the original index
						filtered_index = choice_num - 1
						return original_indices[filtered_index]
					else:
						print(f"❌ Please enter a number between 1 and {len(filtered_options)}")
						continue
				
				# Check for special commands
				elif user_input.lower() == 'list':
					print(f"\n📋 All {len(filtered_options)} options:")
					for i, option in enumerate(filtered_options, 1):
						print(f"  {i:2d}. {option}")
					continue
				
				# Otherwise, treat as search term
				elif user_input:
					search_term = user_input.lower()
					new_filtered = []
					new_indices = []
					
					for i, option in enumerate(options):
						# Search in the display option
						option_matches = search_term in option.lower()
						
						# Also search in additional search data if provided (e.g., package/bundle IDs)
						search_data_matches = False
						if search_data and i < len(search_data):
							search_data_matches = search_term in search_data[i].lower()
						
						if option_matches or search_data_matches:
							new_filtered.append(option)
							new_indices.append(i)
					
					if new_filtered:
						filtered_options = new_filtered
						original_indices = new_indices
						print(f"\n🔍 Found {len(filtered_options)} matches:")
						for i, option in enumerate(filtered_options, 1):
							# Show additional info if available
							original_idx = original_indices[i-1]
							display_option = option
							if search_data and original_idx < len(search_data) and search_data[original_idx]:
								# Only show additional data if it's different from display name
								if search_data[original_idx].lower() not in option.lower():
									display_option = f"{option} ({search_data[original_idx]})"
							print(f"  {i:2d}. {display_option}")
						print(f"\nType a number (1-{len(filtered_options)}) to select, or search again.")
					else:
						print(f"❌ No matches found for '{user_input}'. Try a different search term.")
					continue
				
				print("❌ Invalid input. Please try again.")
				
			except KeyboardInterrupt:
				print("\n❌ Setup cancelled")
				sys.exit(1)
	
	else:
		# For smaller lists, use the original simple approach
		print(f"\n{prompt}")
		for i, option in enumerate(options, 1):
			print(f"  {i}. {option}")
		
		while True:
			try:
				if allow_empty:
					choice = input(f"\nEnter choice (1-{len(options)}, or press Enter to skip): ").strip()
					if not choice:
						return None
				else:
					choice = input(f"\nEnter choice (1-{len(options)}): ").strip()
				
				if choice.isdigit():
					choice_num = int(choice)
					if 1 <= choice_num <= len(options):
						return choice_num - 1
				
				print("❌ Invalid choice. Please try again.")
			except KeyboardInterrupt:
				print("\n❌ Setup cancelled")
				sys.exit(1)


def launch_emulator(emulator_name: str) -> bool:
	"""Launch an Android emulator."""
	print(f"🚀 Starting emulator: {emulator_name}")
	try:
		subprocess.Popen(['emulator', '-avd', emulator_name, '-no-snapshot-load'], 
						stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
		
		# Wait for emulator to boot
		print("⏳ Waiting for emulator to boot...")
		for _ in range(60):  # Wait up to 60 seconds
			time.sleep(2)
			result = subprocess.run(['adb', 'devices'], capture_output=True, text=True, timeout=5)
			if emulator_name in result.stdout or 'emulator-' in result.stdout:
				# Check if device is ready
				result = subprocess.run(['adb', 'shell', 'getprop', 'sys.boot_completed'], 
									   capture_output=True, text=True, timeout=5)
				if result.stdout.strip() == '1':
					print("✅ Emulator is ready")
					return True
		
		print("❌ Emulator failed to boot within 2 minutes")
		return False
	except Exception as e:
		print(f"❌ Error starting emulator: {e}")
		return False


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
	
	#logo-panel, #links-panel, #paths-panel, #info-panels {
		border: solid $primary;
		margin: 0 0 0 0; 
		padding: 0;
	}
	
	#info-panels {
		display: none;
		layout: vertical;
		height: auto;
		min-height: 5;
	}
	
	#top-panels {
		layout: horizontal;
		height: auto;
		width: 100%;
		min-height: 5;
	}
	
	#app-panel, #model-panel {
		width: 1fr;
		height: auto;
		border: solid $primary-darken-2;
		padding: 1;
		overflow: auto;
		margin: 0 1 0 0;
		padding: 1;
	}
	
	#tasks-panel {
		width: 100%;
		height: 1fr;
		min-height: 20;
		max-height: 60vh;
		border: solid $primary-darken-2;
		padding: 1;
		overflow-y: scroll;
		margin: 1 0 0 0;
	}
	
	#app-panel {
		border-left: solid $primary-darken-2;
	}
	
	#results-container {
		display: none;
	}
	
	#logo-panel {
		width: 100%;
		height: auto;
		content-align: center middle;
		text-align: center;
	}
	
	#links-panel {
		width: 100%;
		padding: 1;
		border: solid $primary;
		height: auto;
	}
	
	.link-white {
		color: white;
	}
	
	.link-purple {
		color: purple;
	}
	
	.link-magenta {
		color: magenta;
	}
	
	.link-green {
		color: green;
	}

	HorizontalGroup {
		height: auto;
	}
	
	.link-label {
		width: auto;
	}
	
	.link-url {
		width: auto;
	}
	
	.link-row {
		width: 100%;
		height: auto;
	}
	
	#paths-panel {
		color: $text-muted;
	}
	
	#task-input-container {
		border: solid $accent;
		padding: 1;
		margin-bottom: 1;
		height: auto;
		dock: bottom;
	}
	
	#task-label {
		color: $accent;
		padding-bottom: 1;
	}
	
	#task-input {
		width: 100%;
	}
	
	#working-panel {
		border: solid $warning;
		padding: 1;
		margin: 1 0;
	}
	
	#completion-panel {
		border: solid $success;
		padding: 1;
		margin: 1 0;
	}
	
	#results-container {
		height: 1fr;
		overflow: auto;
		border: none;
	}
	
	#results-log {
		height: auto;
		overflow-y: scroll;
		background: $surface;
		color: $text;
		width: 100%;
	}
	
	.log-entry {
		margin: 0;
		padding: 0;
	}
	
	#app-info, #model-info, #tasks-info {
		height: auto;
		margin: 0;
		padding: 0;
		background: transparent;
		overflow-y: auto;
		min-height: 5;
	}
	"""

	BINDINGS = [
		Binding('ctrl+c', 'quit', 'Quit', priority=True, show=True),
		Binding('ctrl+q', 'quit', 'Quit', priority=True),
		Binding('ctrl+d', 'quit', 'Quit', priority=True),
		Binding('up', 'input_history_prev', 'Previous command', show=False),
		Binding('down', 'input_history_next', 'Next command', show=False),
	]

	def __init__(self, config: dict[str, Any], *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.config = config
		self.app_instance = None  # Will be set before app.run_async()
		self.controller = None  # Will be set before app.run_async()
		self.agent = None
		self.llm = None  # Will be set before app.run_async()
		self.task_history = config.get('command_history', [])
		# Track current position in history for up/down navigation
		self.history_index = len(self.task_history)

	def setup_richlog_logging(self) -> None:
		"""Set up logging to redirect to RichLog widget instead of stdout."""
		# Get the RichLog widget
		rich_log = self.query_one('#results-log')

		# Create and set up the custom handler
		log_handler = RichLogHandler(rich_log)
		log_type = os.getenv('APP_USE_LOGGING_LEVEL', 'result').lower()

		class AppUseFormatter(logging.Formatter):
			def format(self, record):
				return super().format(record)

		# Set up the formatter based on log type
		if log_type == 'result':
			log_handler.setLevel(logging.INFO)
			log_handler.setFormatter(AppUseFormatter('%(message)s'))
		else:
			log_handler.setFormatter(AppUseFormatter('%(levelname)-8s [%(name)s] %(message)s'))

		# Configure root logger - Replace ALL handlers, not just stdout handlers
		root = logging.getLogger()

		# Clear all existing handlers and add only our richlog handler
		root.handlers = []
		root.addHandler(log_handler)

		# Set log level based on environment variable
		if log_type == 'result':
			root.setLevel(logging.INFO)
		elif log_type == 'debug':
			root.setLevel(logging.DEBUG)
		else:
			root.setLevel(logging.INFO)

		# Configure app_use logger
		app_use_logger = logging.getLogger('app_use')
		app_use_logger.propagate = False  # Don't propagate to root logger
		app_use_logger.handlers = [log_handler]  # Replace any existing handlers
		app_use_logger.setLevel(root.level)

		# Silence third-party loggers
		for logger_name in [
			'WDM',
			'httpx',
			'selenium',
			'appium',
			'urllib3',
			'asyncio',
			'langchain',
			'openai',
			'httpcore',
			'charset_normalizer',
			'anthropic._base_client',
		]:
			third_party = logging.getLogger(logger_name)
			third_party.setLevel(logging.ERROR)
			third_party.propagate = False
			third_party.handlers = []  # Clear any existing handlers

	def on_mount(self) -> None:
		"""Set up components when app is mounted."""
		logger = logging.getLogger('app_use.on_mount')
		logger.debug('on_mount() method started')

		# Set up custom logging to RichLog
		logger.debug('Setting up RichLog logging...')
		try:
			self.setup_richlog_logging()
			logger.debug('RichLog logging set up successfully')
		except Exception as e:
			logger.error(f'Error setting up RichLog logging: {str(e)}', exc_info=True)
			raise RuntimeError(f'Failed to set up RichLog logging: {str(e)}')

		# Set up input history
		logger.debug('Setting up readline history...')
		try:
			if READLINE_AVAILABLE and self.task_history:
				for item in self.task_history:
					readline.add_history(item)
				logger.debug(f'Added {len(self.task_history)} items to readline history')
			else:
				logger.debug('No readline history to set up')
		except Exception as e:
			logger.error(f'Error setting up readline history: {str(e)}', exc_info=False)

		# Focus the input field
		logger.debug('Focusing input field...')
		try:
			input_field = self.query_one('#task-input')
			input_field.focus()
			logger.debug('Input field focused')
		except Exception as e:
			logger.error(f'Error focusing input field: {str(e)}', exc_info=True)

		# Start continuous info panel updates
		logger.debug('Starting info panel updates...')
		try:
			self.update_info_panels()
			logger.debug('Info panel updates started')
		except Exception as e:
			logger.error(f'Error starting info panel updates: {str(e)}', exc_info=True)

		logger.debug('on_mount() completed successfully')

	def on_input_key_up(self, event: events.Key) -> None:
		"""Handle up arrow key in the input field."""
		if event.sender.id != 'task-input':
			return

		if not self.task_history:
			return

		if self.history_index > 0:
			self.history_index -= 1
			self.query_one('#task-input').value = self.task_history[self.history_index]
			self.query_one('#task-input').cursor_position = len(self.query_one('#task-input').value)

		event.prevent_default()
		event.stop()

	def on_input_key_down(self, event: events.Key) -> None:
		"""Handle down arrow key in the input field."""
		if event.sender.id != 'task-input':
			return

		if not self.task_history:
			return

		if self.history_index < len(self.task_history) - 1:
			self.history_index += 1
			self.query_one('#task-input').value = self.task_history[self.history_index]
			self.query_one('#task-input').cursor_position = len(self.query_one('#task-input').value)
		elif self.history_index == len(self.task_history) - 1:
			self.history_index += 1
			self.query_one('#task-input').value = ''

		event.prevent_default()
		event.stop()

	async def on_key(self, event: events.Key) -> None:
		"""Handle key events at the app level to ensure graceful exit."""
		if event.key == 'ctrl+c' or event.key == 'ctrl+d' or event.key == 'ctrl+q':
			await self.action_quit()
			event.stop()
			event.prevent_default()

	def on_input_submitted(self, event: Input.Submitted) -> None:
		"""Handle task input submission."""
		if event.input.id == 'task-input':
			task = event.input.value
			if not task.strip():
				return

			# Add to history if it's new
			if task.strip() and (not self.task_history or task != self.task_history[-1]):
				self.task_history.append(task)
				self.config['command_history'] = self.task_history
				save_user_config(self.config)

			# Reset history index to point past the end of history
			self.history_index = len(self.task_history)

			# Hide logo, links, and paths panels
			self.hide_intro_panels()

			# Process the task
			self.run_task(task)

			# Clear the input
			event.input.value = ''

	def hide_intro_panels(self) -> None:
		"""Hide the intro panels, show info panels, and expand the log view."""
		try:
			# Get the panels
			logo_panel = self.query_one('#logo-panel')
			links_panel = self.query_one('#links-panel')
			paths_panel = self.query_one('#paths-panel')
			info_panels = self.query_one('#info-panels')
			tasks_panel = self.query_one('#tasks-panel')
			# Hide intro panels if they're visible and show info panels
			if logo_panel.display:
				logging.info('Hiding intro panels and showing info panels')

				logo_panel.display = False
				links_panel.display = False
				paths_panel.display = False

				# Show info panels
				info_panels.display = True
				tasks_panel.display = True

				# Make results container take full height
				results_container = self.query_one('#results-container')
				results_container.styles.height = '1fr'

				# Configure the log
				results_log = self.query_one('#results-log')
				results_log.styles.height = 'auto'

				logging.info('Panels should now be visible')
		except Exception as e:
			logging.error(f'Error in hide_intro_panels: {str(e)}')

	def update_info_panels(self) -> None:
		"""Update all information panels with current state."""
		try:
			self.update_app_panel()
			self.update_model_panel()
			self.update_tasks_panel()
		except Exception as e:
			logging.error(f'Error in update_info_panels: {str(e)}')
		finally:
			# Always schedule the next update
			self.set_timer(1.0, self.update_info_panels)

	def update_app_panel(self) -> None:
		"""Update app information panel with details about the mobile app."""
		app_info = self.query_one('#app-info')
		app_info.clear()

		app_instance = self.app_instance
		if hasattr(self, 'agent') and self.agent and hasattr(self.agent, 'app'):
			app_instance = self.agent.app

		if app_instance:
			try:
				# Get basic app info
				platform = app_instance.platform_name
				device_name = app_instance.device_name or 'Unknown'
				
				# Get app identifier
				app_identifier = 'Unknown'
				if platform.lower() == 'android':
					app_identifier = app_instance.app_package or 'Unknown'
				elif platform.lower() == 'ios':
					app_identifier = app_instance.bundle_id or 'Unknown'

				# Get connection status
				connection_status = '[green]Connected[/]' if app_instance.driver else '[red]Disconnected[/]'
				
				# Display app information
				app_info.write(f'[bold cyan]{platform}[/] App ({connection_status})')
				app_info.write(f'Device: [yellow]{device_name}[/]')
				app_info.write(f'App: [blue]{app_identifier}[/]')
				app_info.write(f'Appium: [dim]{app_instance.appium_server_url}[/]')

				# Show timeout settings
				app_info.write(f'Timeout: [magenta]{app_instance.timeout}s[/]')

				# Show current time
				current_time = time.strftime('%H:%M:%S', time.localtime())
				app_info.write(f'Last updated: [dim]{current_time}[/]')

			except Exception as e:
				app_info.write(f'[red]Error updating app info: {str(e)}[/]')
		else:
			app_info.write('[red]App not initialized[/]')

	def update_model_panel(self) -> None:
		"""Update model information panel with details about the LLM."""
		model_info = self.query_one('#model-info')
		model_info.clear()

		if self.llm:
			# Get model details
			model_name = 'Unknown'
			if hasattr(self.llm, 'model_name'):
				model_name = self.llm.model_name
			elif hasattr(self.llm, 'model'):
				model_name = self.llm.model

			# Show model name
			if self.agent:
				temp_str = f'{self.llm.temperature}ºC ' if self.llm.temperature else ''
				vision_str = '+ vision ' if self.agent.settings.use_vision else ''
				memory_str = '+ memory ' if self.agent.enable_memory else ''
				model_info.write(
					f'[white]LLM:[/] [blue]{self.llm.__class__.__name__} [yellow]{model_name}[/] {temp_str}{vision_str}{memory_str}'
				)
			else:
				model_info.write(f'[white]LLM:[/] [blue]{self.llm.__class__.__name__} [yellow]{model_name}[/]')

			# Show token usage statistics if agent exists and has history
			if self.agent and hasattr(self.agent, 'state') and hasattr(self.agent.state, 'history'):
				# Get total tokens used
				total_tokens = self.agent.state.history.total_input_tokens()
				model_info.write(f'[white]Input tokens:[/] [green]{total_tokens:,}[/]')

				# Calculate tokens per step
				num_steps = len(self.agent.state.history.history)
				if num_steps > 0:
					avg_tokens_per_step = total_tokens / num_steps
					model_info.write(f'[white]Avg tokens/step:[/] [green]{avg_tokens_per_step:,.1f}[/]')

				# Show total duration
				total_duration = self.agent.state.history.total_duration_seconds()
				if total_duration > 0:
					model_info.write(f'[white]Total Duration:[/] [magenta]{total_duration:.2f}s[/]')

				# Add current state information
				if hasattr(self.agent, 'state'):
					if hasattr(self.agent.state, 'paused') and self.agent.state.paused:
						model_info.write('[orange]LLM paused[/]')
					else:
						model_info.write('[green]LLM ready[/]')
		else:
			model_info.write('[red]Model not initialized[/]')

	def update_tasks_panel(self) -> None:
		"""Update tasks information panel with details about the tasks and steps hierarchy."""
		tasks_info = self.query_one('#tasks-info')
		tasks_info.clear()

		if self.agent:
			# Get task information
			task_text = self.agent.task if hasattr(self.agent, 'task') else 'Unknown task'
			
			tasks_info.write('[bold green]TASK:[/]')
			tasks_info.write(f'[white]{task_text}[/]')
			tasks_info.write('')

			# Get current state information
			current_step = self.agent.state.n_steps if hasattr(self.agent, 'state') else 0

			# Get all agent history items
			history_items = []
			if hasattr(self.agent, 'state') and hasattr(self.agent.state, 'history'):
				history_items = self.agent.state.history.history

				if history_items:
					tasks_info.write('[bold yellow]STEPS:[/]')

					for idx, item in enumerate(history_items, 1):
						# Determine step status
						step_style = '[green]✓[/]'

						# For the current step, show it as in progress
						if idx == current_step:
							step_style = '[yellow]⟳[/]'

						# Check if this step had an error
						if item.result and any(result.error for result in item.result):
							step_style = '[red]✗[/]'

						# Show step number
						tasks_info.write(f'{step_style} Step {idx}/{current_step}')

						# Show goal if available
						if item.model_output and hasattr(item.model_output, 'current_state'):
							# Show memory (context) for this step
							memory = item.model_output.current_state.memory
							if memory:
								memory_lines = memory.strip().split('\n')
								memory_summary = memory_lines[0]
								tasks_info.write(f'   [dim]Memory:[/] {memory_summary}')

							# Show goal for this step
							goal = item.model_output.current_state.next_goal
							if goal:
								goal_lines = goal.strip().split('\n')
								goal_summary = goal_lines[0]
								tasks_info.write(f'   [cyan]Goal:[/] {goal_summary}')

						# Show actions taken in this step
						if item.model_output and item.model_output.action:
							tasks_info.write('   [purple]Actions:[/]')
							for action_idx, action in enumerate(item.model_output.action, 1):
								if hasattr(action, 'model_dump'):
									action_dict = action.model_dump(exclude_unset=True)
									if action_dict:
										action_name = list(action_dict.keys())[0]
										tasks_info.write(f'     {action_idx}. [blue]{action_name}[/]')

						# Show results or errors from this step
						if item.result:
							for result in item.result:
								if result.error:
									error_text = result.error
									tasks_info.write(f'   [red]Error:[/] {error_text}')
								elif result.extracted_content:
									content = result.extracted_content
									tasks_info.write(f'   [green]Result:[/] {content}')

						# Add a space between steps for readability
						tasks_info.write('')

			# If agent is actively running, show a status indicator
			if hasattr(self.agent, 'state') and hasattr(self.agent.state, 'paused') and self.agent.state.paused:
				tasks_info.write('[orange]Agent is paused (press Enter to resume)[/]')
		else:
			tasks_info.write('[dim]Agent not initialized[/]')

		# Force scroll to bottom
		tasks_panel = self.query_one('#tasks-panel')
		tasks_panel.scroll_end(animate=False)

	def scroll_to_input(self) -> None:
		"""Scroll to the input field to ensure it's visible."""
		input_container = self.query_one('#task-input-container')
		input_container.scroll_visible()

	def run_task(self, task: str) -> None:
		"""Launch the task in a background worker."""
		logger = logging.getLogger('app_use.app')

		# Make sure intro is hidden and log is ready
		self.hide_intro_panels()

		# Start continuous updates of all info panels
		self.update_info_panels()

		# Clear the log to start fresh
		rich_log = self.query_one('#results-log')
		rich_log.clear()

		if self.agent is None:
			self.agent = Agent(
				task=task,
				llm=self.llm,
				app=self.app_instance,
				controller=self.controller,
			)
		else:
			# For subsequent tasks, we could modify the agent or create a new one
			self.agent = Agent(
				task=task,
				llm=self.llm,
				app=self.app_instance,
				controller=self.controller,
			)

		# Let the agent run in the background
		async def agent_task_worker() -> None:
			logger.debug('\n🚀 Working on task: %s', task)

			try:
				# Run the agent task
				await self.agent.run()
			except Exception as e:
				logger.error('\nError running agent: %s', str(e))
			finally:
				logger.debug('\n✅ Task completed!')

				# Make sure the task input container is visible
				task_input_container = self.query_one('#task-input-container')
				task_input_container.display = True

				# Refocus the input field
				input_field = self.query_one('#task-input')
				input_field.focus()

				# Ensure the input is visible by scrolling to it
				self.call_after_refresh(self.scroll_to_input)

		# Run the worker
		self.run_worker(agent_task_worker, name='agent_task')

	def action_input_history_prev(self) -> None:
		"""Navigate to the previous item in command history."""
		input_field = self.query_one('#task-input')
		if not input_field.has_focus or not self.task_history:
			return

		if self.history_index > 0:
			self.history_index -= 1
			input_field.value = self.task_history[self.history_index]
			input_field.cursor_position = len(input_field.value)

	def action_input_history_next(self) -> None:
		"""Navigate to the next item in command history or clear input."""
		input_field = self.query_one('#task-input')
		if not input_field.has_focus or not self.task_history:
			return

		if self.history_index < len(self.task_history) - 1:
			self.history_index += 1
			input_field.value = self.task_history[self.history_index]
			input_field.cursor_position = len(input_field.value)
		elif self.history_index == len(self.task_history) - 1:
			self.history_index += 1
			input_field.value = ''

	async def action_quit(self) -> None:
		"""Quit the application and clean up resources."""
		# Close the app instance if it exists
		if self.app_instance:
			try:
				self.app_instance.close()
				logging.debug('App instance closed successfully')
			except Exception as e:
				logging.error(f'Error closing app instance: {str(e)}')

		# Exit the application
		self.exit()
		print('\nThanks for using app-use!')

	def compose(self) -> ComposeResult:
		"""Create the UI layout."""
		yield Header()

		# Main container for app content
		with Container(id='main-container'):
			# Logo panel
			yield Static(APP_USE_LOGO, id='logo-panel', markup=True)

			# Information panels (hidden by default)
			with Container(id='info-panels'):
				# Top row with app and model panels side by side
				with Container(id='top-panels'):
					# App panel
					with Container(id='app-panel'):
						yield RichLog(id='app-info', markup=True, highlight=True, wrap=True)

					# Model panel
					with Container(id='model-panel'):
						yield RichLog(id='model-info', markup=True, highlight=True, wrap=True)

				# Tasks panel (full width, below app and model)
				with VerticalScroll(id='tasks-panel'):
					yield RichLog(id='tasks-info', markup=True, highlight=True, wrap=True, auto_scroll=True)

			# Links panel with URLs
			with Container(id='links-panel'):
				with HorizontalGroup(classes='link-row'):
					yield Static('Documentation & Examples: 📚 ', markup=True, classes='link-label')
					yield Link('https://github.com/app-use/app-use', url='https://github.com/app-use/app-use', classes='link-white link-url')

				yield Static('')  # Empty line

				with HorizontalGroup(classes='link-row'):
					yield Static('Chat & share on Discord:  🚀 ', markup=True, classes='link-label')
					yield Link(
						'https://discord.gg/2cez4s85', url='https://discord.gg/2cez4s85', classes='link-purple link-url'
					)

				with HorizontalGroup(classes='link-row'):
					yield Static('[dim]Report any issues:[/]        🐛 ', markup=True, classes='link-label')
					yield Link(
						'https://github.com/app-use/app-use/issues',
						url='https://github.com/app-use/app-use/issues',
						classes='link-green link-url',
					)

			# Paths panel
			yield Static(
				f' ⚙️  Settings & history saved to:    {str(USER_CONFIG_FILE.resolve()).replace(str(Path.home()), "~")}\n'
				f' 📁 Outputs saved to:               {str(Path(".").resolve()).replace(str(Path.home()), "~")}',
				id='paths-panel',
				markup=True,
			)

			# Results view with scrolling
			with VerticalScroll(id='results-container'):
				yield RichLog(highlight=True, markup=True, id='results-log', wrap=True, auto_scroll=True)

			# Task input container (at the bottom)
			with Container(id='task-input-container'):
				yield Label('📱 What would you like me to do on the mobile app?', id='task-label')
				yield Input(placeholder='Enter your task...', id='task-input')

		yield Footer()


async def run_prompt_mode(prompt: str, ctx: click.Context, debug: bool = False):
	"""Run app-use in non-interactive mode with a single prompt."""
	# Set up logging to only show results by default
	os.environ['APP_USE_LOGGING_LEVEL'] = 'result'
	
	# Configure logging
	logging.basicConfig(
		level=logging.INFO,
		format='%(message)s',
		handlers=[logging.StreamHandler(sys.stdout)]
	)

	try:
		# Load config
		config = load_user_config()
		config = update_config_with_click_args(config, ctx)

		# Get LLM
		llm = get_llm(config)

		# Create app instance with config parameters
		app_config = config.get('app', {})
		
		# Validate required parameters
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

		app_instance = App(**app_config)

		# Create controller
		controller = Controller()

		# Create and run agent
		agent = Agent(
			task=prompt,
			llm=llm,
			app=app_instance,
			controller=controller,
		)

		await agent.run()

		# Close app instance
		app_instance.close()

	except Exception as e:
		if debug:
			import traceback
			traceback.print_exc()
		else:
			print(f'Error: {str(e)}', file=sys.stderr)
		sys.exit(1)


async def textual_interface(config: dict[str, Any]):
	"""Run the Textual interface."""
	logger = logging.getLogger('app_use.startup')

	# Set up logging for Textual UI - prevent any logging to stdout
	def setup_textual_logging():
		# Replace all handlers with null handler
		root_logger = logging.getLogger()
		for handler in root_logger.handlers:
			root_logger.removeHandler(handler)

		# Add null handler to ensure no output to stdout/stderr
		null_handler = logging.NullHandler()
		root_logger.addHandler(null_handler)
		logger.debug('Logging configured for Textual UI')

	logger.debug('Setting up App, Controller, and LLM...')

	# Step 1: Initialize App with config
	logger.debug('Initializing App...')
	try:
		# Get app config from the config dict
		app_config = config.get('app', {})

		logger.info(f'App platform: {app_config.get("platform_name", "Android")}')
		if app_config.get('device_name'):
			logger.info(f'Target device: {app_config["device_name"]}')
		if app_config.get('app_package'):
			logger.info(f'Android package: {app_config["app_package"]}')
		if app_config.get('bundle_id'):
			logger.info(f'iOS bundle ID: {app_config["bundle_id"]}')

		# Create App instance with config parameters
		app_instance = App(**app_config)
		logger.debug('App initialized successfully')

	except Exception as e:
		logger.error(f'Error initializing App: {str(e)}', exc_info=True)
		raise RuntimeError(f'Failed to initialize App: {str(e)}')

	# Step 2: Initialize Controller
	logger.debug('Initializing Controller...')
	try:
		controller = Controller()
		logger.debug('Controller initialized successfully')
	except Exception as e:
		logger.error(f'Error initializing Controller: {str(e)}', exc_info=True)
		raise RuntimeError(f'Failed to initialize Controller: {str(e)}')

	# Step 3: Get LLM
	logger.debug('Getting LLM...')
	try:
		llm = get_llm(config)
		# Log LLM details
		model_name = getattr(llm, 'model_name', None) or getattr(llm, 'model', 'Unknown model')
		provider = llm.__class__.__name__
		temperature = getattr(llm, 'temperature', 0.0)
		logger.info(f'LLM: {provider} ({model_name}), temperature: {temperature}')
		logger.debug(f'LLM initialized successfully: {provider}')
	except Exception as e:
		logger.error(f'Error getting LLM: {str(e)}', exc_info=True)
		raise RuntimeError(f'Failed to initialize LLM: {str(e)}')

	logger.debug('Initializing AppUseApp instance...')
	try:
		app = AppUseApp(config)
		# Pass the initialized components to the app
		app.app_instance = app_instance
		app.controller = controller
		app.llm = llm

		# Configure logging for Textual UI before going fullscreen
		setup_textual_logging()

		# Log app and model configuration that will be used
		platform = config.get('app', {}).get('platform_name', 'Android')
		model_name = config.get('model', {}).get('name', 'auto-detected')

		logger.info(f'Preparing {platform} app control with {model_name} LLM')

		logger.debug('Starting Textual app with run_async()...')
		# No more logging after this point as we're in fullscreen mode
		await app.run_async()
	except Exception as e:
		logger.error(f'Error in textual_interface: {str(e)}', exc_info=True)
		# Make sure to close app instance if app initialization fails
		if 'app_instance' in locals():
			app_instance.close()
		raise


def run_start_command() -> None:
	"""Run the interactive start command wizard."""
	print("🚀 Welcome to App-Use Setup Wizard!")
	print("=" * 50)
	
	# Step 1: Start Appium server
	if not start_appium_server():
		sys.exit(1)
	
	try:
		# Step 2: Select platform
		platforms = ["Android", "iOS"]
		platform_choice = prompt_selection("📱 Select platform:", platforms)
		if platform_choice is None:
			print("❌ No platform selected")
			return
		
		platform = platforms[platform_choice]
		print(f"✅ Selected platform: {platform}")
		
		# Step 3: Select device
		if platform == "Android":
			devices = get_android_devices()
			device_names = [dev['name'] for dev in devices]
			
			# Also add option to start new emulator
			available_emulators = []
			try:
				result = subprocess.run(['emulator', '-list-avds'], capture_output=True, text=True, timeout=10)
				if result.returncode == 0:
					available_emulators = [name.strip() for name in result.stdout.strip().split('\n') if name.strip()]
			except:
				pass
			
			# Add unbooted emulators to the selection
			booted_emulator_names = {dev['id'] for dev in devices if dev['type'] == 'emulator'}
			for emulator in available_emulators:
				if emulator not in booted_emulator_names:
					device_names.append(f"Start Emulator: {emulator}")
					devices.append({
						'id': emulator,
						'name': f"Start Emulator: {emulator}",
						'type': 'emulator_start'
					})
		else:  # iOS
			devices = get_ios_devices()
			device_names = [dev['name'] for dev in devices]
		
		if not devices:
			print(f"❌ No {platform} devices found")
			return
		
		device_choice = prompt_selection(f"📱 Select {platform} device:", device_names)
		if device_choice is None:
			print("❌ No device selected")
			return
		
		selected_device = devices[device_choice]
		print(f"✅ Selected device: {selected_device['name']}")
		
		# If it's an emulator that needs to be started, start it
		if selected_device['type'] == 'emulator_start':
			if not launch_emulator(selected_device['id']):
				print("❌ Failed to start emulator")
				return
			# Update device info for the started emulator
			selected_device['type'] = 'emulator'
		
		# For iOS simulators, verify the device is actually booted and accessible
		if platform == "iOS" and selected_device['type'] == 'simulator':
			print(f"🔍 Verifying iOS simulator is accessible...")
			try:
				# Double-check the simulator is still booted
				result = subprocess.run(['xcrun', 'simctl', 'list', 'devices', '--json'], 
									   capture_output=True, text=True, timeout=10)
				if result.returncode == 0:
					import json
					data = json.loads(result.stdout)
					found_device = None
					
					for runtime, device_list in data['devices'].items():
						for device in device_list:
							if device['udid'] == selected_device['id'] and device['state'] == 'Booted':
								found_device = device
								break
						if found_device:
							break
					
					if found_device:
						print(f"✅ Simulator verified: {found_device['name']} (UDID: {found_device['udid'][:8]}...)")
						# Make sure we have the correct device information
						selected_device['device_name'] = found_device['name']
						selected_device['full_udid'] = found_device['udid']
					else:
						print(f"❌ Simulator {selected_device['name']} is no longer booted or accessible")
						print("💡 Please make sure the simulator is running and try again")
						return
				else:
					print("❌ Failed to verify simulator status")
					return
			except Exception as e:
				print(f"⚠️ Error verifying simulator: {e}")
				print("⚠️ Proceeding anyway, but connection may fail")
		
		# Step 4: Select app
		device_id = selected_device['id']
		
		print(f"\n🔍 Getting apps from {selected_device['name']}...")
		if platform == "Android":
			apps = get_android_apps(device_id)
			# Show package details for search/identification
			if len(apps) > 10:
				app_names = [f"{app['name']}" for app in apps]
				search_data = [app['package'] for app in apps]  # Enable searching by package name
			else:
				app_names = [f"{app['name']} ({app['package']})" for app in apps]
				search_data = None
		else:  # iOS
			apps = get_ios_apps(device_id, selected_device['type'])
			# Show bundle ID details for search/identification
			if len(apps) > 10:
				app_names = [f"{app['name']}" for app in apps]
				search_data = [app['bundle_id'] for app in apps]  # Enable searching by bundle ID
			else:
				app_names = [f"{app['name']} ({app['bundle_id']})" for app in apps]
				search_data = None
		
		if not apps:
			print(f"❌ No apps found on {selected_device['name']}")
			return
		
		print(f"✅ Found {len(apps)} apps")
		app_choice = prompt_selection("📲 Select app to control:", app_names, search_data=search_data)
		if app_choice is None:
			print("❌ No app selected")
			return
		
		selected_app = apps[app_choice]
		print(f"✅ Selected app: {selected_app['name']}")
		
		# Step 5: Create configuration
		config = load_user_config()
		config['app']['platform_name'] = platform
		config['app']['device_name'] = device_id
		
		if platform == "Android":
			config['app']['app_package'] = selected_app['package']
			config['app']['app_activity'] = selected_app.get('activity')  # Will be auto-detected if None
			# Clear iOS specific settings
			config['app']['bundle_id'] = None
		else:  # iOS
			config['app']['bundle_id'] = selected_app['bundle_id']
			# Clear Android specific settings
			config['app']['app_package'] = None
			config['app']['app_activity'] = None
		
		# Save configuration
		save_user_config(config)
		
		print("\n" + "=" * 50)
		print("🎉 Setup complete! Configuration saved.")
		print(f"Platform: {platform}")
		print(f"Device: {selected_device['name']}")
		print(f"App: {selected_app['name']}")
		print("=" * 50)
		
		# Step 6: Launch the GUI
		print("\n🚀 Launching App-Use GUI...")
		time.sleep(1)  # Brief pause before launching GUI
		
		# Register cleanup handler for appium server
		import atexit
		atexit.register(stop_appium_server)
		
		# Launch the textual interface
		asyncio.run(textual_interface(config))
		
	except KeyboardInterrupt:
		print("\n❌ Setup cancelled by user")
	except Exception as e:
		print(f"❌ Error during setup: {e}")
	finally:
		# Clean up appium server if we started it
		stop_appium_server()


@click.group(invoke_without_command=True)
@click.option('--version', is_flag=True, help='Print version and exit')
@click.option('--model', type=str, help='Model to use (e.g., gpt-4o, claude-3-opus-20240229, gemini-pro)')
@click.option('--debug', is_flag=True, help='Enable verbose startup logging')
@click.option('--platform', type=click.Choice(['Android', 'iOS'], case_sensitive=False), help='Mobile platform (Android or iOS)')
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
	  app-use --platform Android ...  # Direct launch with parameters
	  app-use -p "task description"   # Command line mode

	Use 'app-use start' for an interactive setup wizard, or provide options directly for immediate launch.
	"""
	# If no subcommand was invoked, run the original main functionality
	if ctx.invoked_subcommand is None:
		_run_main_command(ctx, debug, **kwargs)


def _run_main_command(ctx: click.Context, debug: bool = False, **kwargs):
	"""Run the main command functionality (original behavior)."""
	if kwargs['version']:
		try:
			from importlib.metadata import version
			print(version('app-use'))
		except:
			print('app-use (development version)')
		sys.exit(0)

	# Check if prompt mode is activated
	if kwargs.get('prompt'):
		# Set environment variable for prompt mode before running
		os.environ['APP_USE_LOGGING_LEVEL'] = 'result'
		# Run in non-interactive mode
		asyncio.run(run_prompt_mode(kwargs['prompt'], ctx, debug))
		return

	# Configure console logging
	console_handler = logging.StreamHandler(sys.stdout)
	console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', '%H:%M:%S'))

	# Configure root logger
	root_logger = logging.getLogger()
	root_logger.setLevel(logging.INFO if not debug else logging.DEBUG)
	root_logger.addHandler(console_handler)

	logger = logging.getLogger('app_use.startup')
	logger.info('Starting App-Use initialization')
	if debug:
		logger.debug(f'System info: Python {sys.version.split()[0]}, Platform: {sys.platform}')

	logger.debug('Loading environment variables from .env file...')
	load_dotenv()
	logger.debug('Environment variables loaded')

	# Load user configuration
	logger.debug('Loading user configuration...')
	try:
		config = load_user_config()
		logger.debug(f'User configuration loaded from {USER_CONFIG_FILE}')
	except Exception as e:
		logger.error(f'Error loading user configuration: {str(e)}', exc_info=True)
		print(f'Error loading configuration: {str(e)}')
		sys.exit(1)

	# Update config with command-line arguments
	logger.debug('Updating configuration with command line arguments...')
	try:
		config = update_config_with_click_args(config, ctx)
		logger.debug('Configuration updated')
	except Exception as e:
		logger.error(f'Error updating config with command line args: {str(e)}', exc_info=True)
		print(f'Error updating configuration: {str(e)}')
		sys.exit(1)

	# Save updated config
	logger.debug('Saving user configuration...')
	try:
		save_user_config(config)
		logger.debug('Configuration saved')
	except Exception as e:
		logger.error(f'Error saving user configuration: {str(e)}', exc_info=True)
		print(f'Error saving configuration: {str(e)}')
		sys.exit(1)

	# Setup handlers for console output before entering Textual UI
	logger.debug('Setting up handlers for Textual UI...')

	# Log app and model configuration that will be used
	platform = config.get('app', {}).get('platform_name', 'Android')
	model_name = config.get('model', {}).get('name', 'auto-detected')

	logger.info(f'Preparing {platform} app control with {model_name} LLM')

	try:
		# Run the Textual UI interface
		logger.debug('Starting Textual UI interface...')
		asyncio.run(textual_interface(config))
	except Exception as e:
		# Restore console logging for error reporting
		root_logger.setLevel(logging.INFO)
		for handler in root_logger.handlers:
			root_logger.removeHandler(handler)
		root_logger.addHandler(console_handler)

		logger.error(f'Error initializing App-Use: {str(e)}', exc_info=debug)
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
	# Configure console logging for start command
	if debug:
		logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
	
	run_start_command()

def main():
	"""Entry point for the CLI."""
	cli()


if __name__ == '__main__':
	main() 