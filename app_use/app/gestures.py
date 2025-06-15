import logging

from selenium.webdriver.common.actions import interaction
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.pointer_input import PointerInput

logger = logging.getLogger(__name__)


class GestureService:
	"""
	Handles advanced touch gestures beyond basic taps and scrolls
	"""

	def __init__(self, driver):
		"""
		Initialize the gesture service with an Appium driver

		Args:
		    driver: Appium WebDriver instance
		"""
		self.driver = driver
		# Detect if this is an iOS driver (XCUITest doesn't support mobile gestures)
		self.is_ios = False
		try:
			caps = driver.capabilities
			self.is_ios = caps.get('platformName', '').lower() == 'ios'
		except AttributeError as attr_err:
			# Driver object may not expose a `capabilities` attribute (e.g. mocks during tests)
			logger.debug(f'Could not inspect driver capabilities: {attr_err}')
			self.is_ios = False
		except KeyError:
			# `platformName` not present in capabilities; assume non-iOS for safety
			self.is_ios = False
		except Exception as err:  # noqa: BLE001  # fallback, keep stack trace
			logger.warning(f'Unexpected error while detecting platformName: {err}')
			self.is_ios = False

	def swipe(self, start_x, start_y, end_x, end_y, duration: int = 300, percent: float = 0.2):
		"""
		Perform a swipe gesture

		Args:
		    start_x: Starting x coordinate
		    start_y: Starting y coordinate
		    end_x: Ending x coordinate
		    end_y: Ending y coordinate
		    duration: Duration of the swipe in milliseconds
		    percent: Percentage of the target region height to swipe (0.0 - 1.0)

		Returns:
		    bool: True if the swipe was performed successfully
		"""
		try:
			logger.info(
				f'Performing swipe from ({start_x}, {start_y}) to ({end_x}, {end_y}) '
				f'with duration {duration}ms and percent {percent:.2f}'
			)

			# For iOS, skip mobile gestures and go directly to W3C Actions
			if self.is_ios:
				return self._swipe_with_w3c_actions(start_x, start_y, end_x, end_y, duration)

			# Try W3C Mobile Gestures Commands first for Android
			try:
				self.driver.execute_script(
					'mobile: swipeGesture',
					{
						'left': min(start_x, end_x),
						'top': min(start_y, end_y),
						'width': abs(end_x - start_x),
						'height': abs(end_y - start_y),
						'direction': 'up' if start_y > end_y else 'down',
						'percent': percent,
					},
				)
				logger.info('Swipe gesture completed successfully using mobile gestures')
				return True
			except Exception as mobile_error:
				logger.info(f'Mobile gesture failed, trying W3C Actions: {mobile_error}')
				return self._swipe_with_w3c_actions(start_x, start_y, end_x, end_y, duration)

		except Exception as e:
			logger.error(f'All swipe methods failed: {str(e)}')
			return False

	def _swipe_with_w3c_actions(self, start_x, start_y, end_x, end_y, duration):
		"""Helper method to perform swipe using W3C Actions API"""
		try:
			touch_input = PointerInput(interaction.POINTER_TOUCH, 'touch')
			action_builder = ActionBuilder(self.driver, mouse=touch_input)

			# Create the swipe sequence
			action_builder.pointer_action.move_to_location(start_x, start_y)
			action_builder.pointer_action.pointer_down()
			action_builder.pointer_action.pause(duration / 1000)  # Convert ms to seconds
			action_builder.pointer_action.move_to_location(end_x, end_y)
			action_builder.pointer_action.pointer_up()

			action_builder.perform()
			logger.info('Swipe gesture completed successfully using W3C Actions')
			return True
		except Exception as w3c_error:
			logger.info(f'W3C Actions failed, trying legacy method: {w3c_error}')

			# Final fallback to older Appium method
			self.driver.swipe(start_x, start_y, end_x, end_y, duration)
			logger.info('Swipe gesture completed successfully using fallback method')
			return True

	def pinch(self, element=None, percent=50, steps=10):
		"""
		Perform a pinch gesture

		Args:
		    element: Element to pinch (optional)
		    percent: Pinch percentage (0-100)
		    steps: Number of steps in the gesture

		Returns:
		    bool: True if the pinch was performed successfully
		"""
		try:
			if element:
				rect = element.rect
				center_x = rect['x'] + rect['width'] // 2
				center_y = rect['y'] + rect['height'] // 2

				distance = min(rect['width'], rect['height']) // 4
				left_x = center_x - distance
				left_y = center_y
				right_x = center_x + distance
				right_y = center_y
			else:
				# Use screen center and dimensions
				size = self.driver.get_window_size()
				center_x = size['width'] // 2
				center_y = size['height'] // 2

				# Calculate pinch coordinates
				distance = min(size['width'], size['height']) // 4
				left_x = center_x - distance
				left_y = center_y
				right_x = center_x + distance
				right_y = center_y

			# For iOS, skip mobile gestures and use dual swipe approach
			if self.is_ios:
				return self._pinch_with_dual_swipe(center_x, center_y, left_x, left_y, right_x, right_y, percent)

			# Try mobile gesture first for Android
			try:
				gesture_type = 'pinchCloseGesture' if percent < 50 else 'pinchOpenGesture'
				self.driver.execute_script(
					f'mobile: {gesture_type}',
					{
						'left': left_x,
						'top': center_y - distance // 2,
						'width': distance * 2,
						'height': distance,
						'percent': abs(percent - 50) / 50,
					},
				)
				return True
			except Exception:
				logger.info('Mobile pinch gesture failed, using dual swipe approach')
				return self._pinch_with_dual_swipe(center_x, center_y, left_x, left_y, right_x, right_y, percent)

		except Exception as e:
			logger.error(f'Error performing pinch: {str(e)}')
			return False

	def _pinch_with_dual_swipe(self, center_x, center_y, left_x, left_y, right_x, right_y, percent):
		"""Helper method to perform pinch using dual swipe approach"""
		if percent < 50:  # Pinch in - swipe from sides to center
			# Perform two simultaneous swipes toward center
			success1 = self.swipe(left_x, left_y, center_x, center_y, 500)
			success2 = self.swipe(right_x, right_y, center_x, center_y, 500)
			return success1 and success2
		else:  # Pinch out - swipe from center to sides
			# Perform two simultaneous swipes away from center
			success1 = self.swipe(center_x, center_y, left_x, left_y, 500)
			success2 = self.swipe(center_x, center_y, right_x, right_y, 500)
			return success1 and success2

	def zoom(self, element=None, percent=200, steps=10):
		"""
		Perform a zoom gesture

		Args:
		    element: Element to zoom (optional)
		    percent: Zoom percentage (100-300)
		    steps: Number of steps in the gesture

		Returns:
		    bool: True if the zoom was performed successfully
		"""
		try:
			# Zoom is essentially a pinch out
			return self.pinch(element, 100, steps)
		except Exception as e:
			logger.error(f'Error performing zoom: {str(e)}')
			return False

	def long_press(self, x, y, duration=1000):
		"""
		Perform a long press gesture

		Args:
		    x: x coordinate
		    y: y coordinate
		    duration: Duration of the long press in milliseconds

		Returns:
		    bool: True if the long press was performed successfully
		"""
		try:
			# For iOS, skip mobile gestures and go directly to W3C Actions
			if self.is_ios:
				return self._long_press_with_w3c_actions(x, y, duration)

			# Try mobile gesture first for Android
			try:
				self.driver.execute_script('mobile: longClickGesture', {'x': x, 'y': y, 'duration': duration})
				return True
			except Exception:
				return self._long_press_with_w3c_actions(x, y, duration)

		except Exception as e:
			logger.error(f'Error performing long press: {str(e)}')
			return False

	def _long_press_with_w3c_actions(self, x, y, duration):
		"""Helper method to perform long press using W3C Actions API"""
		try:
			touch_input = PointerInput(interaction.POINTER_TOUCH, 'touch')
			action_builder = ActionBuilder(self.driver, mouse=touch_input)

			# Perform long press
			action_builder.pointer_action.move_to_location(x, y)
			action_builder.pointer_action.pointer_down()
			action_builder.pointer_action.pause(duration / 1000)  # Convert ms to seconds
			action_builder.pointer_action.pointer_up()

			action_builder.perform()
			return True
		except Exception as e:
			logger.error(f'Error performing long press with W3C Actions: {e}')
			return False

	def drag_and_drop(self, start_x, start_y, end_x, end_y, duration=1000):
		"""
		Perform a drag and drop gesture

		Args:
		    start_x: Starting x coordinate
		    start_y: Starting y coordinate
		    end_x: Ending x coordinate
		    end_y: Ending y coordinate
		    duration: Duration of the drag in milliseconds

		Returns:
		    bool: True if the drag and drop was performed successfully
		"""
		try:
			# For iOS, skip mobile gestures and go directly to W3C Actions
			if self.is_ios:
				return self._drag_and_drop_with_w3c_actions(start_x, start_y, end_x, end_y, duration)

			# Try mobile gesture first for Android
			try:
				self.driver.execute_script(
					'mobile: dragGesture',
					{
						'startX': start_x,
						'startY': start_y,
						'endX': end_x,
						'endY': end_y,
						'speed': 500,
					},
				)
				return True
			except Exception:
				return self._drag_and_drop_with_w3c_actions(start_x, start_y, end_x, end_y, duration)

		except Exception as e:
			logger.error(f'Error performing drag and drop: {str(e)}')
			return False

	def _drag_and_drop_with_w3c_actions(self, start_x, start_y, end_x, end_y, duration):
		"""Helper method to perform drag and drop using W3C Actions API"""
		try:
			touch_input = PointerInput(interaction.POINTER_TOUCH, 'touch')
			action_builder = ActionBuilder(self.driver, mouse=touch_input)

			# Perform drag and drop
			action_builder.pointer_action.move_to_location(start_x, start_y)
			action_builder.pointer_action.pointer_down()
			action_builder.pointer_action.pause(0.1)  # Brief pause after touch down
			action_builder.pointer_action.move_to_location(end_x, end_y)
			action_builder.pointer_action.pointer_up()

			action_builder.perform()
			return True
		except Exception as e:
			logger.error(f'Error performing drag and drop with W3C Actions: {e}')
			return False

	def send_keys(self, keys: str) -> bool:
		"""
		Send keyboard keys like Enter, Back, Home, etc. for mobile navigation and text input completion

		Args:
		    keys: String representing the key(s) to send. Supports:
		        - Single keys: "Enter", "Back", "Delete"

		Returns:
		    bool: True if keys were sent successfully
		"""
		try:
			logger.info(f'Sending keys: {keys}')

			# Handle multiple keys separated by commas
			if ',' in keys:
				key_list = [key.strip() for key in keys.split(',')]
				success = True
				for key in key_list:
					if not self._send_single_key(key):
						success = False
				return success
			else:
				return self._send_single_key(keys)

		except Exception as e:
			logger.error(f'Error sending keys "{keys}": {str(e)}')
			return False

	def _send_single_key(self, key: str) -> bool:
		"""
		Send a single key to the device

		Args:
		    key: The key to send

		Returns:
		    bool: True if key was sent successfully
		"""
		try:
			# Platform-specific key mappings
			if self.is_ios:
				return self._send_ios_key(key.lower())
			else:  # Assume Android for non-iOS
				return self._send_android_key(key.lower())

		except Exception as e:
			logger.error(f'Error sending single key "{key}": {str(e)}')
			return False

	def _send_android_key(self, key: str) -> bool:
		"""
		Send a key using Android-specific methods

		Args:
		    key: The key to send

		Returns:
		    bool: True if key was sent successfully
		"""
		try:
			# Android key code mappings
			android_keycodes = {
				'enter': 66,  # KEYCODE_ENTER
				'back': 4,  # KEYCODE_BACK
				'delete': 67,  # KEYCODE_DEL
				'backspace': 67,  # KEYCODE_DEL (alias)
			}

			# Check if it's a known Android keycode
			if key in android_keycodes:
				keycode = android_keycodes[key]
				logger.info(f'Sending Android keycode {keycode} for key "{key}"')
				self.driver.press_keycode(keycode)
				return True

			# Handle regular text input (send as characters)
			if len(key) > 1 and key not in android_keycodes:
				logger.info(f'Sending text input: "{key}"')
				# Use the driver's type method for text input
				self.driver.execute_script('mobile: type', {'text': key})
				return True

			# Handle single characters
			if len(key) == 1:
				logger.info(f'Sending single character: "{key}"')
				self.driver.execute_script('mobile: type', {'text': key})
				return True

			logger.warning(f'Unknown Android key: "{key}"')
			return False

		except Exception as e:
			logger.error(f'Error sending Android key "{key}": {str(e)}')
			return False

	def _send_ios_key(self, key: str) -> bool:
		"""
		Send a key using iOS-specific methods

		Args:
		    key: The key to send

		Returns:
		    bool: True if key was sent successfully
		"""
		try:
			# iOS doesn't have direct keycode support like Android
			# We use XCUITest keyboard commands for special keys

			# Handle special keys using mobile commands
			if key in ['enter', 'delete', 'backspace']:
				logger.info(f'Sending iOS keyboard key: "{key}"')
				if key == 'enter':
					# Send return key using mobile: keys
					self.driver.execute_script('mobile: keys', {'keys': [{'key': 'return'}]})
				elif key in ['delete', 'backspace']:
					# Send delete key using mobile: keys
					self.driver.execute_script('mobile: keys', {'keys': [{'key': 'delete'}]})
				return True

			# Handle text strings - send as text instead of individual keys
			if len(key) > 1 and key not in ['enter', 'delete', 'backspace']:
				logger.info(f'Sending iOS text: "{key}"')
				try:
					# Try mobile: type first (newer method)
					self.driver.execute_script('mobile: type', {'text': key})
					return True
				except Exception as type_error:
					logger.warning(f'mobile: type failed: {type_error}, trying character-by-character')
					# Send each character individually using mobile: keys
					try:
						for char in key:
							if char == ' ':
								self.driver.execute_script('mobile: keys', {'keys': [{'key': 'space'}]})
							elif char == '\n':
								self.driver.execute_script('mobile: keys', {'keys': [{'key': 'return'}]})
							else:
								self.driver.execute_script('mobile: keys', {'keys': [{'key': char}]})
						return True
					except Exception as char_error:
						logger.error(f'Character-by-character input failed: {char_error}')
						return False

			# Handle single characters
			if len(key) == 1:
				logger.info(f'Sending iOS single character: "{key}"')
				try:
					# Try mobile: type first
					self.driver.execute_script('mobile: type', {'text': key})
					return True
				except Exception:
					# Fallback to mobile: keys with proper key format
					if key == ' ':
						self.driver.execute_script('mobile: keys', {'keys': [{'key': 'space'}]})
					else:
						self.driver.execute_script('mobile: keys', {'keys': [{'key': key}]})
					return True

			logger.warning(f'Unknown iOS key: "{key}"')
			return False

		except Exception as e:
			logger.error(f'Error sending iOS key "{key}": {str(e)}')
			return False
