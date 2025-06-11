import atexit
import logging
import os
import re
import subprocess
import time

from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.options.ios import XCUITestOptions
from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import (
	NoSuchElementException,
	StaleElementReferenceException,
	TimeoutException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.pointer_input import PointerInput
from selenium.webdriver.common.actions import interaction
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from app_use.app.gestures import GestureService
from app_use.nodes.app_node import AppElementNode, AppState
from app_use.nodes.appium_tree_builder import AppiumElementTreeBuilder
from app_use.utils import time_execution_sync

logger = logging.getLogger(__name__)


class App:
	"""
	Implementation of App for native mobile applications using Appium
	"""

	def __init__(
		self,
		platform_name='Android',
		device_name=None,
		app_package=None,
		app_activity=None,
		bundle_id=None,
		app_path=None,
		appium_server_url='http://localhost:4723/wd/hub',
		timeout=30,
		**capabilities,
	):
		self.platform_name = platform_name
		self.device_name = device_name
		self.app_package = app_package
		self.app_activity = app_activity
		self.bundle_id = bundle_id
		self.app_path = app_path
		self.appium_server_url = appium_server_url
		self.timeout = timeout
		self.additional_capabilities = capabilities

		self.driver = None
		self.element_tree_builder = None
		self.gesture_service = None
		self._cached_state = None

		if platform_name.lower() == 'android':
			if not device_name:
				raise ValueError('device_name is required for Android')
			if not app_path:
				if not app_package:
					raise ValueError('app_package is required for Android when not using app_path')
				# Auto-detect app_activity if not provided
				if not app_activity:
					logger.info(f'Auto-detecting main activity for package: {app_package}')
					detected_activity = self.detect_android_app_activity(app_package, device_name)
					if detected_activity:
						self.app_activity = detected_activity
						logger.info(f'Using detected activity: {detected_activity}')
					else:
						raise ValueError(
							f'Could not auto-detect app_activity for {app_package}. Please provide app_activity manually.'
						)
		elif platform_name.lower() == 'ios':
			if not device_name:
				raise ValueError('device_name is required for iOS')
			if not bundle_id and not app_path:
				raise ValueError('Either bundle_id or app_path is required for iOS')
		else:
			raise ValueError("platform_name must be 'Android' or 'iOS'")

		self._initialize_driver()
		atexit.register(self.close)

	def _initialize_driver(self):
		try:
			desired_caps = {
				'platformName': self.platform_name,
				'customSnapshotTimeout': 12000,
				'snapshotMaxDepth': 100,
			}

			if self.device_name:
				desired_caps['deviceName'] = self.device_name

			if self.platform_name.lower() == 'android':
				if self.app_path:
					desired_caps['app'] = os.path.abspath(self.app_path)
				else:
					desired_caps['appPackage'] = self.app_package
					desired_caps['appActivity'] = self.app_activity
				desired_caps['automationName'] = 'UiAutomator2'
				desired_caps['autoGrantPermissions'] = True
			elif self.platform_name.lower() == 'ios':
				if self.app_path:
					desired_caps['app'] = os.path.abspath(self.app_path)
				else:
					desired_caps['bundleId'] = self.bundle_id
				desired_caps['automationName'] = 'XCUITest'
				desired_caps['autoAcceptAlerts'] = True

			desired_caps.update(self.additional_capabilities)

			logger.info(f'Initializing Appium driver with capabilities: {desired_caps}')
			if self.platform_name.lower() == 'android':
				options = UiAutomator2Options().load_capabilities(desired_caps)
			else:
				options = XCUITestOptions().load_capabilities(desired_caps)
			self.driver = webdriver.Remote(self.appium_server_url, options=options)
			self.driver.implicitly_wait(self.timeout)

			self.element_tree_builder = AppiumElementTreeBuilder(self.driver)
			self.gesture_service = GestureService(self.driver)

			logger.info('Appium driver initialized successfully')
		except Exception as e:
			logger.error(f'Error initializing Appium driver: {str(e)}')
			raise

	def _wait_for_page_and_frames_load(self, wait_time: float = 2.0) -> bool:
		"""
		Wait for the app UI to stabilize after potential page transitions.
		
		Simple approach: just wait a few seconds to allow transitions to complete.
		
		Args:
		    wait_time: Time to wait in seconds (default: 2.0)
		    
		Returns:
		    bool: Always returns True after waiting
		"""
		logger.debug(f'Waiting {wait_time}s for UI transitions to complete')
		time.sleep(wait_time)
		logger.debug('Wait completed')
		return True
	
	@time_execution_sync('--get_state_summary') 
	def get_app_state(
		self,
		viewport_expansion: int = 0,
		debug_mode: bool = False,
		include_highlights: bool = True,
	) -> AppState:
		"""
		Get the current app state, optionally waiting for UI stability first.
		
		Args:
		    viewport_expansion: Expand viewport bounds by this many pixels
		    debug_mode: Enable debug mode for tree building
		    include_highlights: Whether to include highlight indices
		    wait_for_stability: Whether to wait for UI stability before capturing state
		    
		Returns:
		    AppState: Current application state
		"""
		self._wait_for_page_and_frames_load()
		
		app_state = self.element_tree_builder.build_element_tree(
			self.platform_name.lower(),
			viewport_expansion=viewport_expansion,
			debug_mode=debug_mode,
			include_highlights=include_highlights,
		)
		# Screenshot is now handled by the tree builder
		self._cached_state = app_state
		return app_state

	def get_selector_map(self, viewport_expansion: int = 0, debug_mode: bool = False):
		if self._cached_state:
			logger.debug('Using cached app state')
			return self._cached_state.selector_map
		state = self.get_app_state(viewport_expansion=viewport_expansion, debug_mode=debug_mode)
		return state.selector_map


	def enter_text_with_highlight_index(self, highlight_index: int, text: str) -> bool:
		selector_map = self.get_selector_map()
		target_node = selector_map.get(highlight_index)

		if not target_node:
			logger.error(f'No element found with highlight_index: {highlight_index}')
			return False

		self.ensure_element_visible_by_highlight_index(highlight_index)
		logger.info(f'Attempting to enter text in {target_node.tag_name}')

		# Note: All text input methods below include clearing existing text before entering new text
		# Coordinate-based method uses triple-tap + delete, element-based methods use .clear()

		# Priority 1: Try coordinate-based text input if viewport coordinates are available
		if target_node.viewport_coordinates:
			try:
				logger.info(
					f'Trying coordinate-based text input for element at ({target_node.viewport_coordinates.x}, {target_node.viewport_coordinates.y})'
				)
				center_x, center_y = self.get_element_center_coordinates(target_node)
				if self.input_text_at_coordinates(center_x, center_y, text):
					logger.info('Successfully entered text using coordinates')
					return True
				else:
					logger.warning('Coordinate-based text input failed, continuing with other methods')
			except Exception as e:
				logger.error(f'Error with coordinate-based text input: {str(e)}')

		# Priority 2: Try by key/semantics first (most reliable)
		if target_node.key:
			try:
				logger.info(f'Trying to enter text by key: {target_node.key}')
				if self.platform_name.lower() == 'android':
					element = self.driver.find_element(AppiumBy.ID, target_node.key)
				else:
					# For iOS, try multiple selectors for the key
					try:
						element = self.driver.find_element(AppiumBy.ACCESSIBILITY_ID, target_node.key)
					except NoSuchElementException:
						# Try by name attribute
						element = self.driver.find_element(AppiumBy.NAME, target_node.key)
				element.clear()
				element.send_keys(text)
				logger.info('Successfully entered text using key')
				return True
			except Exception as e:
				logger.error(f'Error entering text by key: {str(e)}')

		# Priority 3: Try by element type and other attributes for iOS text fields
		if self.platform_name.lower() == 'ios' and target_node.tag_name in ['XCUIElementTypeSearchField', 'XCUIElementTypeTextField', 'XCUIElementTypeSecureTextField']:
			try:
				logger.info(f'Trying to find iOS text field by type: {target_node.tag_name}')
				# Try to find by element type and any available attribute
				xpath_parts = [f'name()="{target_node.tag_name}"']
				
				if target_node.key:
					xpath_parts.append(f'(@name="{target_node.key}" or @accessibilityIdentifier="{target_node.key}")')
				
				if target_node.text:
					xpath_parts.append(f'(@value="{target_node.text}" or @label="{target_node.text}")')
				
				# If we have coordinates, try to find elements near them
				if target_node.viewport_coordinates:
					# Build a more flexible xpath
					xpath = f'//{target_node.tag_name}'
					if len(xpath_parts) > 1:
						xpath += f'[{" and ".join(xpath_parts[1:])}]'
				else:
					xpath = f'//*[{" and ".join(xpath_parts)}]'
				
				logger.info(f'Using xpath: {xpath}')
				element = self.driver.find_element(AppiumBy.XPATH, xpath)
				element.clear()
				element.send_keys(text)
				logger.info('Successfully entered text using iOS text field type')
				return True
			except Exception as e:
				logger.error(f'Error entering text by iOS text field type: {str(e)}')

		# Priority 4: Try by text content
		if target_node.text:
			try:
				logger.info(f"Trying to enter text by text: '{target_node.text}'")
				if self.platform_name.lower() == 'android':
					element = self.driver.find_element(
						AppiumBy.ANDROID_UIAUTOMATOR,
						f'new UiSelector().text("{target_node.text}")',
					)
				else:
					element = self.driver.find_element(
						AppiumBy.XPATH,
						f'//*[@name="{target_node.text}" or @label="{target_node.text}" or @value="{target_node.text}"]',
					)
				element.clear()
				element.send_keys(text)
				logger.info('Successfully entered text using text content')
				return True
			except Exception as e:
				logger.error(f'Error entering text by text: {str(e)}')

		# Priority 5: Final fallback - click coordinates and use focused element
		if target_node.viewport_coordinates:
			try:
				logger.info('Trying final fallback: click coordinates and send to focused element')
				center_x, center_y = self.get_element_center_coordinates(target_node)
				
				# Click to focus the element
				if self.click_coordinates(center_x, center_y):
					time.sleep(0.5)  # Wait for focus
					
					# Try to get the currently focused element and send text to it
					try:
						focused_element = self.driver.switch_to.active_element
						if focused_element:
							focused_element.clear()
							focused_element.send_keys(text)
							logger.info('Successfully entered text using focused element fallback')
							return True
					except Exception as focus_error:
						logger.warning(f'Focused element method failed: {focus_error}')
						
					# If focused element doesn't work, try sending keys to the app
					if self.platform_name.lower() == 'ios':
						logger.info('Trying to send keys directly to iOS app')
						self.driver.execute_script('mobile: keys', {'keys': [{'text': text}]})
						logger.info('Successfully sent text using direct keys')
						return True
						
			except Exception as e:
				logger.error(f'Error with final fallback method: {str(e)}')

		logger.error(f'Failed to enter text in element with highlight_index: {highlight_index}')
		return False

	def click_element_by_highlight_index(self, highlight_index: int) -> bool:
		selector_map = self.get_selector_map()
		target_node = selector_map.get(highlight_index)

		if not target_node:
			logger.error(f'No element found with highlight_index: {highlight_index}')
			return False

		if not target_node:
			logger.error(f'No element found with highlight_index: {highlight_index}')
			return False

		self.ensure_element_visible_by_highlight_index(highlight_index)
		logger.info(f'Attempting to click on {target_node.tag_name}')

		# Priority 1: Try coordinate-based click if viewport coordinates are available
		if target_node.viewport_coordinates:
			try:
				logger.info(
					f'Trying coordinate-based click for element at ({target_node.viewport_coordinates.x}, {target_node.viewport_coordinates.y})'
				)
				if self.click_element_by_coordinates(target_node):
					logger.info('Successfully clicked using coordinates')
					return True
				else:
					logger.warning('Coordinate-based click failed, continuing with other methods')
			except Exception as e:
				logger.error(f'Error with coordinate-based click: {str(e)}')

		# Priority 2: Try by key/semantics first
		if target_node.key:
			try:
				logger.info(f'Trying to click by key: {target_node.key}')
				if self.platform_name.lower() == 'android':
					element = self.driver.find_element(AppiumBy.ID, target_node.key)
				else:
					element = self.driver.find_element(AppiumBy.ACCESSIBILITY_ID, target_node.key)
				element.click()
				logger.info('Successfully clicked using key')
				return True
			except Exception as e:
				logger.error(f'Error clicking by key: {str(e)}')


		# Priority 3: Try by text content
		if target_node.text:
			try:
				logger.info(f"Trying to click by text: '{target_node.text}'")
				if self.platform_name.lower() == 'android':
					element = self.driver.find_element(
						AppiumBy.ANDROID_UIAUTOMATOR,
						f'new UiSelector().text("{target_node.text}")',
					)
				else:
					if target_node.tag_name == 'XCUIElementTypeCell':
						cell_xpath = f'//XCUIElementTypeCell[@label="{target_node.text}" or @name="{target_node.text}" or @value="{target_node.text}"]'
						logger.info(f'Trying to click iOS cell with XPath: {cell_xpath}')
						element = self.driver.find_element(AppiumBy.XPATH, cell_xpath)
					else:
						element = self.driver.find_element(
							AppiumBy.XPATH,
							f'//*[@name="{target_node.text}" or @label="{target_node.text}" or @value="{target_node.text}"]',
						)
				element.click()
				logger.info('Successfully clicked using text content')
				return True
			except Exception as e:
				logger.error(f'Error clicking by text: {str(e)}')

		logger.error(f'Failed to click on element with highlight_index: {highlight_index}')
		return False

	def scroll_into_view_by_highlight_index(self, highlight_index: int) -> bool:
		selector_map = self.get_selector_map()
		target_node = selector_map.get(highlight_index)

		if not target_node:
			logger.error(f'No element found with highlight_index: {highlight_index}')
			return False

		logger.info(f'Attempting to scroll into view: {target_node.tag_name}')

		# Priority 1: Try by key/semantics first (most reliable)
		if target_node.key:
			try:
				logger.info(f'Trying to scroll by key: {target_node.key}')
				if self.platform_name.lower() == 'android':
					self.driver.find_element(
						AppiumBy.ANDROID_UIAUTOMATOR,
						f'new UiScrollable(new UiSelector().scrollable(true)).scrollIntoView(new UiSelector().resourceId("{target_node.key}"))',
					)
					logger.info('Successfully scrolled using key')
					return True
				else:
					# For iOS, use accessibility identifier in the predicate
					self.driver.execute_script(
						'mobile: scroll',
						{
							'direction': 'down',
							'predicateString': f'identifier == "{target_node.key}"',
						},
					)
					logger.info('Successfully scrolled using key')
					return True
			except Exception as e:
				logger.error(f'Error scrolling by key: {str(e)}')

		# Priority 2: Try coordinate-based scrolling if viewport coordinates are available
		if target_node.viewport_coordinates:
			try:
				logger.info(
					f'Trying coordinate-based scroll into view for element at ({target_node.viewport_coordinates.x}, {target_node.viewport_coordinates.y})'
				)
				if self.scroll_element_into_view_by_coordinates(target_node):
					logger.info('Successfully scrolled using coordinates')
					return True
				else:
					logger.warning('Coordinate-based scroll failed, continuing with other methods')
			except Exception as e:
				logger.error(f'Error with coordinate-based scroll: {str(e)}')

		# Priority 3: Try by text content
		if target_node.text:
			try:
				logger.info(f"Trying to scroll by text: '{target_node.text}'")
				if self.platform_name.lower() == 'android':
					self.driver.find_element(
						AppiumBy.ANDROID_UIAUTOMATOR,
						f'new UiScrollable(new UiSelector().scrollable(true)).scrollIntoView(new UiSelector().text("{target_node.text}"))',
					)
					logger.info('Successfully scrolled using text content')
					return True
				else:
					self.driver.execute_script(
						'mobile: scroll',
						{
							'direction': 'down',
							'predicateString': f'label == "{target_node.text}" OR name == "{target_node.text}" OR value == "{target_node.text}"',
						},
					)
					logger.info('Successfully scrolled using text content')
					return True
			except Exception as e:
				logger.error(f'Error scrolling by text: {str(e)}')

		# Priority 4: Try by element type
		try:
			logger.info(f'Trying to scroll by type: {target_node.tag_name}')
			if self.platform_name.lower() == 'android':
				self.driver.find_element(
					AppiumBy.ANDROID_UIAUTOMATOR,
					f'new UiScrollable(new UiSelector().scrollable(true)).scrollIntoView(new UiSelector().className("{target_node.tag_name}"))',
				)
				logger.info('Successfully scrolled using type')
				return True
			else:
				self.driver.execute_script(
					'mobile: scroll',
					{
						'direction': 'down',
						'predicateString': f'type == "{target_node.tag_name}"',
					},
				)
				logger.info('Successfully scrolled using type')
				return True
		except Exception as e:
			logger.error(f'Error scrolling by type: {str(e)}')

		# Priority 5: Generic scroll fallback
		try:
			logger.info('Trying generic scroll down')
			size = self.driver.get_window_size()
			start_x = size['width'] // 2
			start_y = size['height'] * 3 // 4
			end_x = size['width'] // 2
			end_y = size['height'] // 4
			self.gesture_service.swipe(start_x, start_y, end_x, end_y, 300)

			new_app_state = self.get_app_state()
			if highlight_index in new_app_state.selector_map:
				logger.info('Successfully scrolled element into view')
				return True

			logger.info('Trying generic scroll up')
			self.gesture_service.swipe(start_x, end_y, start_x, start_y, 300)

			new_app_state = self.get_app_state()
			if highlight_index in new_app_state.selector_map:
				logger.info('Successfully scrolled element into view')
				return True
		except Exception as e:
			logger.error(f'Error with generic scroll: {str(e)}')

		logger.error(f'Failed to scroll element with highlight_index: {highlight_index} into view')
		return False

	def ensure_element_visible_by_highlight_index(self, highlight_index: int, timeout: int = 5) -> bool:
		selector_map = self.get_selector_map()
		target_node = selector_map.get(highlight_index)

		if not target_node:
			logger.error(f'No element found with highlight_index: {highlight_index}')
			return False

		logger.info(f'Ensuring element is visible: {target_node.tag_name}')

		# First try coordinate-based visibility check if available
		if target_node.viewport_coordinates and target_node.viewport_info:
			if self.is_element_in_viewport(target_node):
				logger.info('Element is already visible based on coordinates')
				return True

		# Try to find element with shorter timeout to avoid long waits
		max_attempts = 3
		attempt = 0

		while attempt < max_attempts:
			try:
				element_found = False

				# Try key-based lookup first (most reliable)
				if target_node.key and not element_found:
					try:
						wait = WebDriverWait(self.driver, timeout=2)
						if self.platform_name.lower() == 'android':
							element = wait.until(EC.presence_of_element_located((AppiumBy.ID, target_node.key)))
						else:
							element = wait.until(EC.presence_of_element_located((AppiumBy.ACCESSIBILITY_ID, target_node.key)))
						element_found = True
					except (
						TimeoutException,
						StaleElementReferenceException,
						NoSuchElementException,
					):
						pass

				# Try text-based lookup if key didn't work
				if target_node.text and not element_found:
					try:
						wait = WebDriverWait(self.driver, timeout=2)
						if self.platform_name.lower() == 'android':
							element = wait.until(
								EC.presence_of_element_located(
									(
										AppiumBy.ANDROID_UIAUTOMATOR,
										f'new UiSelector().text("{target_node.text}")',
									)
								)
							)
						else:
							element = wait.until(
								EC.presence_of_element_located(
									(
										AppiumBy.XPATH,
										f'//*[@name="{target_node.text}" or @label="{target_node.text}" or @value="{target_node.text}"]',
									)
								)
							)
						element_found = True
					except (
						TimeoutException,
						StaleElementReferenceException,
						NoSuchElementException,
					):
						pass

				# If element was found but not visible, try scrolling
				if element_found:
					logger.info('Element found but not visible, attempting to scroll into view')
					if self.scroll_into_view_by_highlight_index(highlight_index):
						return True

				# If no element found at all, it might be off-screen, try generic scroll
				if not element_found:
					logger.info('Element not found, attempting generic scroll to bring it into view')
					size = self.driver.get_window_size()
					start_x = size['width'] // 2
					start_y = size['height'] * 3 // 4
					end_x = size['width'] // 2
					end_y = size['height'] // 4
					self.gesture_service.swipe(start_x, start_y, end_x, end_y, 300)

					# Small wait for UI to settle
					time.sleep(0.5)

				attempt += 1

			except Exception as e:
				logger.warning(f'Attempt {attempt + 1} failed: {str(e)}')
				attempt += 1
				if attempt < max_attempts:
					time.sleep(0.5)  # Brief pause before retry

		# Final attempt - assume element is visible if we've tried everything
		logger.warning(
			f'Could not definitively ensure element {highlight_index} is visible after {max_attempts} attempts, proceeding anyway'
		)
		return True  # Return True to allow interaction to proceed

	def take_screenshot(self) -> str:
		"""
		Returns a base64 encoded screenshot of the current page.
		"""
		try:
			screenshot = self.driver.get_screenshot_as_base64()
			logger.info('Screenshot taken succesfully')
			return screenshot
		except Exception as e:
			logger.error(f'Error taking screenshot: {str(e)}')
			return ''

	def _build_xpath_for_node(self, node):
		xpath_parts = []
		if self.platform_name.lower() == 'android':
			xpath_parts.append(f"@class='{node.tag_name}'")
		else:
			xpath_parts.append(f"@type='{node.tag_name}'")

		if node.key:
			if self.platform_name.lower() == 'android':
				xpath_parts.append(f"@resource-id='{node.key}'")
			else:
				xpath_parts.append(f"@name='{node.key}'")

		if node.text:
			if self.platform_name.lower() == 'android':
				xpath_parts.append(f"@text='{node.text}'")
			else:
				xpath_parts.append(f"(@name='{node.text}' or @label='{node.text}' or @value='{node.text}')")

		xpath_condition = ' and '.join(xpath_parts)
		return f'//*[{xpath_condition}]'

	def close(self) -> None:
		if self.driver:
			try:
				self.driver.quit()
				logger.info('Appium driver closed')
			except Exception as e:
				logger.error(f'Error closing Appium driver: {str(e)}')
			finally:
				self.driver = None

	def click_coordinates(self, x: int, y: int) -> bool:
		"""
		Click at specific coordinates

		Args:
		    x: X coordinate
		    y: Y coordinate

		Returns:
		    bool: True if click was successful
		"""
		try:
			logger.info(f'Clicking at coordinates ({x}, {y})')
			finger = PointerInput('touch', 'finger')
			actions = ActionChains(self.driver)
			actions.w3c_actions = ActionBuilder(self.driver, mouse=finger)

			actions.w3c_actions.pointer_action.move_to_location(x, y)
			actions.w3c_actions.pointer_action.pointer_down()
			actions.w3c_actions.pointer_action.release()

			actions.perform()
			logger.info(f'Successfully clicked at coordinates ({x}, {y})')
			return True
		except Exception as e:
			logger.error(f'Error clicking at coordinates ({x}, {y}): {str(e)}')
			return False

	def click_element_by_coordinates(self, node: AppElementNode) -> bool:
		"""
		Click an element using its viewport coordinates

		Args:
		    node: AppElementNode with viewport coordinates

		Returns:
		    bool: True if click was successful
		"""
		if not node.viewport_coordinates:
			logger.error(f'Node {node.highlight_index} has no viewport coordinates')
			return False

		# Click at the center of the element
		center_x = int(node.viewport_coordinates.x + node.viewport_coordinates.width / 2)
		center_y = int(node.viewport_coordinates.y + node.viewport_coordinates.height / 2)

		return self.click_coordinates(center_x, center_y)

	def scroll_to_coordinates(self, x: int, y: int, direction: str = 'down', distance: int = 300) -> bool:
		"""
		Scroll at specific coordinates

		Args:
		    x: X coordinate
		    y: Y coordinate
		    direction: Scroll direction ("up", "down", "left", "right")
		    distance: Scroll distance in pixels

		Returns:
		    bool: True if scroll was successful
		"""
		try:
			logger.info(f'Scrolling {direction} at coordinates ({x}, {y}) with distance {distance}')

			# To scroll "down" (show content below), swipe up (finger moves up)
			# To scroll "up" (show content above), swipe down (finger moves down)
			if direction == 'down':
				end_x, end_y = x, y + distance  # Swipe up to scroll down
			elif direction == 'up':
				end_x, end_y = x, y - distance  # Swipe down to scroll up
			elif direction == 'left':
				end_x, end_y = x + distance, y
			elif direction == 'right':
				end_x, end_y = x - distance, y
			else:
				logger.error(f'Invalid scroll direction: {direction}')
				return False

			return self.gesture_service.swipe(x, y, end_x, end_y, 300)
		except Exception as e:
			logger.error(f'Error scrolling at coordinates ({x}, {y}): {str(e)}')
			return False

	def long_press_coordinates(self, x: int, y: int, duration: int = 1000) -> bool:
		"""
		Long press at specific coordinates

		Args:
		    x: X coordinate
		    y: Y coordinate
		    duration: Duration of long press in milliseconds

		Returns:
		    bool: True if long press was successful
		"""
		try:
			logger.info(f'Long pressing at coordinates ({x}, {y}) for {duration}ms')
			return self.gesture_service.long_press(x, y, duration)
		except Exception as e:
			logger.error(f'Error long pressing at coordinates ({x}, {y}): {str(e)}')
			return False

	def input_text_at_coordinates(self, x: int, y: int, text: str) -> bool:
		"""
		Click at coordinates and input text

		Args:
		    x: X coordinate
		    y: Y coordinate
		    text: Text to input

		Returns:
		    bool: True if text input was successful
		"""
		try:
			logger.info(f'Inputting text at coordinates ({x}, {y}): {text}')

			# First click at the coordinates to focus the input field
			if not self.click_coordinates(x, y):
				return False

			# Wait a moment for the field to focus
			time.sleep(0.5)

			# Clear any existing text - use more efficient methods
			try:
				logger.debug('Attempting to clear existing text')
				
				if self.platform_name.lower() == 'android':
					# For Android, try to use active element clear first
					try:
						active_element = self.driver.switch_to.active_element
						if active_element:
							active_element.clear()
							logger.debug('Successfully cleared text using active element')
						else:
							# Fallback to keycode delete
							self.driver.press_keycode(67)  # KEYCODE_DEL
					except Exception:
						self.driver.press_keycode(67)  # KEYCODE_DEL
				else:
					# For iOS, try more efficient clearing methods
					cleared = False
					
					# Method 1: Try to use active element clear (most efficient)
					try:
						active_element = self.driver.switch_to.active_element
						if active_element:
							active_element.clear()
							logger.debug('Successfully cleared text using active element')
							cleared = True
					except Exception as clear_error:
						logger.debug(f'Active element clear failed: {clear_error}')
					
					# Method 2: If element clear failed, try select all + delete
					if not cleared:
						try:
							# Use proper iOS select all command
							self.driver.execute_script('mobile: selectText', {})
							time.sleep(0.1)
							self.driver.execute_script('mobile: keys', {'keys': [{'key': 'delete'}]})
							logger.debug('Successfully cleared text using select all + delete')
							cleared = True
						except Exception as select_error:
							logger.debug(f'Select all method failed: {select_error}')
					
					# Method 3: Fallback to multiple deletes only if other methods failed
					if not cleared:
						try:
							logger.debug('Using multiple delete fallback')
							# Send fewer deletes to be more efficient
							for _ in range(20):  # Reduced from 50 to 20
								self.driver.execute_script('mobile: keys', {'keys': [{'key': 'delete'}]})
								time.sleep(0.01)
							logger.debug('Completed multiple delete fallback')
						except Exception as delete_error:
							logger.debug(f'Multiple delete method failed: {delete_error}')
			except Exception as e:
				logger.debug(f'Could not clear existing text: {str(e)}')

			# Input the text
			if self.platform_name.lower() == 'android':
				self.driver.execute_script('mobile: type', {'text': text})
			else:
				# For iOS, try multiple methods
				try:
					# Method 1: Use element.send_keys if we can find the focused element
					active_element = self.driver.switch_to.active_element
					if active_element:
						active_element.send_keys(text)
						logger.info('Successfully used active element send_keys')
					else:
						raise Exception("No active element found")
				except Exception as fallback_error:
					logger.warning(f'Active element method failed: {fallback_error}, trying mobile type')
					try:
						# Method 2: Use mobile type for iOS (UiAutomation2 style)
						self.driver.execute_script('mobile: type', {'text': text})
						logger.info('Successfully used mobile: type')
					except Exception as type_error:
						logger.warning(f'mobile: type failed: {type_error}, trying character-by-character')
						# Method 3: Send each character individually using mobile: keys with proper format
						try:
							for char in text:
								# Send each character as a separate key press
								if char == ' ':
									# Handle space character
									self.driver.execute_script('mobile: keys', {'keys': [{'key': 'space'}]})
								elif char == '\n':
									# Handle newline
									self.driver.execute_script('mobile: keys', {'keys': [{'key': 'return'}]})
								else:
									# For regular characters, iOS expects them as individual key presses
									# Use the character code approach for compatibility
									self.driver.execute_script('mobile: keys', {'keys': [{'key': char}]})
							logger.info('Successfully used character-by-character input')
						except Exception as char_error:
							logger.warning(f'Character-by-character failed: {char_error}, using W3C actions as final fallback')
							# Method 4: Use W3C Actions to type character by character
							from selenium.webdriver.common.actions.action_builder import ActionBuilder
							from selenium.webdriver.common.actions.pointer_input import PointerInput
							from selenium.webdriver.common.actions import interaction
							
							actions = ActionBuilder(self.driver)
							for char in text:
								actions.key_action.key_down(char)
								actions.key_action.key_up(char)
							actions.perform()
							logger.info('Successfully used W3C actions fallback')
			logger.info('Successfully input text')
			return True
		except Exception as e:
			logger.error(f'Error inputting text at coordinates ({x}, {y}): {str(e)}')
			return False

	def swipe_coordinates(self, start_x: int, start_y: int, end_x: int, end_y: int, duration: int = 300) -> bool:
		"""
		Swipe from start coordinates to end coordinates

		Args:
		    start_x: Starting X coordinate
		    start_y: Starting Y coordinate
		    end_x: Ending X coordinate
		    end_y: Ending Y coordinate
		    duration: Swipe duration in milliseconds

		Returns:
		    bool: True if swipe was successful
		"""
		try:
			logger.info(f'Swiping from ({start_x}, {start_y}) to ({end_x}, {end_y})')
			return self.gesture_service.swipe(start_x, start_y, end_x, end_y, duration)
		except Exception as e:
			logger.error(f'Error swiping from ({start_x}, {start_y}) to ({end_x}, {end_y}): {str(e)}')
			return False

	def drag_and_drop_coordinates(self, start_x: int, start_y: int, end_x: int, end_y: int, duration: int = 1000) -> bool:
		"""
		Drag and drop from start coordinates to end coordinates

		Args:
		    start_x: Starting X coordinate
		    start_y: Starting Y coordinate
		    end_x: Ending X coordinate
		    end_y: Ending Y coordinate
		    duration: Drag duration in milliseconds

		Returns:
		    bool: True if drag and drop was successful
		"""
		try:
			logger.info(f'Dragging from ({start_x}, {start_y}) to ({end_x}, {end_y})')
			return self.gesture_service.drag_and_drop(start_x, start_y, end_x, end_y, duration)
		except Exception as e:
			logger.error(f'Error dragging from ({start_x}, {start_y}) to ({end_x}, {end_y}): {str(e)}')
			return False

	def is_element_in_viewport(self, node: AppElementNode, viewport_expansion: int = 0) -> bool:
		"""
		Check if an element is in the viewport

		Args:
		    node: AppElementNode to check
		    viewport_expansion: Viewport expansion in pixels

		Returns:
		    bool: True if element is in viewport
		"""
		if not node.viewport_coordinates or not node.viewport_info:
			return False

		coords = node.viewport_coordinates
		viewport = node.viewport_info

		# Calculate expanded viewport bounds
		expanded_top = -viewport_expansion
		expanded_bottom = viewport.height + viewport_expansion
		expanded_left = -viewport_expansion
		expanded_right = viewport.width + viewport_expansion

		# Check if element is within expanded viewport
		return (
			coords.x + coords.width > expanded_left
			and coords.x < expanded_right
			and coords.y + coords.height > expanded_top
			and coords.y < expanded_bottom
		)

	def get_element_center_coordinates(self, node: AppElementNode) -> tuple[int, int]:
		"""
		Get the center coordinates of an element

		Args:
		    node: AppElementNode

		Returns:
		    tuple: (x, y) center coordinates, or (0, 0) if no coordinates available
		"""
		if not node.viewport_coordinates:
			logger.warning(f'Node {node.highlight_index} has no viewport coordinates')
			return (0, 0)

		center_x = int(node.viewport_coordinates.x + node.viewport_coordinates.width / 2)
		center_y = int(node.viewport_coordinates.y + node.viewport_coordinates.height / 2)

		return (center_x, center_y)

	def scroll_element_into_view_by_coordinates(self, node: AppElementNode, viewport_expansion: int = 0) -> bool:
		"""
		Scroll an element into view using coordinate-based scrolling

		Args:
		    node: AppElementNode to scroll into view
		    viewport_expansion: Viewport expansion in pixels

		Returns:
		    bool: True if element was successfully scrolled into view
		"""
		if not node.viewport_coordinates or not node.viewport_info:
			logger.error(f'Node {node.highlight_index} has no coordinate information')
			return False

		# Check if element is already in viewport
		if self.is_element_in_viewport(node, viewport_expansion):
			logger.info(f'Element {node.highlight_index} is already in viewport')
			return True

		coords = node.viewport_coordinates
		viewport = node.viewport_info

		# Calculate scroll direction and distance
		center_x = viewport.width // 2
		center_y = viewport.height // 2

		# Determine scroll direction based on element position
		if coords.y < 0:
			# Element is above viewport, scroll up
			scroll_distance = min(abs(coords.y) + 100, viewport.height // 2)
			return self.scroll_to_coordinates(center_x, center_y, 'up', scroll_distance)
		elif coords.y > viewport.height:
			# Element is below viewport, scroll down
			scroll_distance = min(coords.y - viewport.height + 100, viewport.height // 2)
			return self.scroll_to_coordinates(center_x, center_y, 'down', scroll_distance)
		elif coords.x < 0:
			# Element is to the left of viewport, scroll left
			scroll_distance = min(abs(coords.x) + 100, viewport.width // 2)
			return self.scroll_to_coordinates(center_x, center_y, 'left', scroll_distance)
		elif coords.x > viewport.width:
			# Element is to the right of viewport, scroll right
			scroll_distance = min(coords.x - viewport.width + 100, viewport.width // 2)
			return self.scroll_to_coordinates(center_x, center_y, 'right', scroll_distance)

		logger.warning(f'Could not determine scroll direction for element {node.highlight_index}')
		return False

	def pinch_gesture(self, center_x: int = None, center_y: int = None, percent: int = 50) -> bool:
		"""
		Perform a pinch gesture (pinch in/out)

		Args:
		    center_x: Center X coordinate (optional, uses screen center if None)
		    center_y: Center Y coordinate (optional, uses screen center if None)
		    percent: Pinch percentage (0-50 = pinch in, 50-100 = pinch out)

		Returns:
		    bool: True if pinch was successful
		"""
		try:
			logger.info(f'Performing pinch gesture at ({center_x}, {center_y}) with {percent}% intensity')

			# If no coordinates provided, use screen center
			if center_x is None or center_y is None:
				size = self.driver.get_window_size()
				center_x = size['width'] // 2
				center_y = size['height'] // 2

			return self.gesture_service.pinch(percent=percent)
		except Exception as e:
			logger.error(f'Error performing pinch gesture: {str(e)}')
			return False

	@staticmethod
	def detect_android_app_activity(package_name: str, device_name: str = None) -> str:
		"""
		Detect the main activity of an Android app by its package name.

		Args:
		    package_name: The package name of the app (e.g., 'com.example.myapp')
		    device_name: The device ID/name (optional)

		Returns:
		    The main activity of the app, or an empty string if not found.
		"""
		try:
			# Build the adb command with device specification if provided
			device_flag = f'-s {device_name}' if device_name else ''

			# Try multiple approaches to find the main activity
			commands = [
				# Method 1: Get launcher activity using monkey
				f"adb {device_flag} shell monkey -p {package_name} -c android.intent.category.LAUNCHER 1 2>&1 | grep 'Starting:' | head -1",
				# Method 2: Use resolve-activity to get the launcher intent
				f'adb {device_flag} shell cmd package resolve-activity --brief {package_name} | tail -n 1',
				# Method 3: Get the default activity from dumpsys with better filtering
				f"adb {device_flag} shell dumpsys package {package_name} | grep -A 10 'android.intent.action.MAIN' | grep -A 5 'android.intent.category.LAUNCHER'",
				# Method 4: Query package manager for launcher activities
				f"adb {device_flag} shell pm query-activities -a android.intent.action.MAIN -c android.intent.category.LAUNCHER | grep -A 5 '{package_name}'",
			]

			for i, command in enumerate(commands):
				try:
					logger.info(f'Trying method {i + 1} to detect activity for {package_name}')
					result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=15)

					if result.returncode == 0 and result.stdout.strip():
						output = result.stdout.strip()
						logger.debug(f'Command output: {output}')

						# Parse the output based on the method used
						if i == 0:  # monkey method - most reliable for launcher activities
							# Look for "Starting: Intent { ... cmp=package/activity }"
							activity_match = re.search(r'cmp=([^/]+)/([^}]+)', output)
							if activity_match:
								package, activity = activity_match.groups()
								if package == package_name:
									# Handle relative activity names (starting with .)
									if activity.startswith('.'):
										full_activity = package_name + activity
									else:
										full_activity = activity
									logger.info(f'Detected main activity for {package_name}: {full_activity}')
									return full_activity

						elif i == 1:  # resolve-activity method
							# Output should be the activity name directly
							activity_match = re.search(r'(\w+(?:\.\w+)*)/(\.\w+|\w+(?:\.\w+)*)', output)
							if activity_match:
								package, activity = activity_match.groups()
								if package == package_name:
									if activity.startswith('.'):
										full_activity = package_name + activity
									else:
										full_activity = activity
									logger.info(f'Detected main activity for {package_name}: {full_activity}')
									return full_activity

						elif i == 2:  # dumpsys method with better filtering
							lines = output.split('\n')
							for j, line in enumerate(lines):
								if 'android.intent.action.MAIN' in line:
									# Look for activity info in the following lines
									for k in range(j, min(j + 10, len(lines))):
										activity_line = lines[k].strip()
										# Look for ActivityInfo pattern and ensure it has LAUNCHER category
										if 'ActivityInfo' in activity_line and 'LAUNCHER' in '\n'.join(lines[j : k + 5]):
											activity_match = re.search(
												r'(\w+(?:\.\w+)*)/(\.\w+|\w+(?:\.\w+)*)',
												activity_line,
											)
											if activity_match:
												package, activity = activity_match.groups()
												if package == package_name:
													if activity.startswith('.'):
														full_activity = package_name + activity
													else:
														full_activity = activity
													logger.info(f'Detected main activity for {package_name}: {full_activity}')
													return full_activity

						elif i == 3:  # pm query-activities method
							# Look for activity patterns in package manager output
							activity_matches = re.findall(r'(\w+(?:\.\w+)*)/(\.\w+|\w+(?:\.\w+)*)', output)
							for package, activity in activity_matches:
								if package == package_name:
									if activity.startswith('.'):
										full_activity = package_name + activity
									else:
										full_activity = activity
									logger.info(f'Detected main activity for {package_name}: {full_activity}')
									return full_activity

				except subprocess.TimeoutExpired:
					logger.warning(f'Method {i + 1} timed out')
					continue
				except Exception as e:
					logger.warning(f'Method {i + 1} failed: {str(e)}')
					continue

			# Enhanced fallback: Try to launch the app and see what activity starts
			try:
				logger.info(f'Trying to launch {package_name} to detect main activity...')
				launch_command = f'adb {device_flag} shell am start -n {package_name}/ 2>&1'
				result = subprocess.run(
					launch_command,
					shell=True,
					capture_output=True,
					text=True,
					timeout=10,
				)

				# Check what activity was actually started
				check_command = (
					f"adb {device_flag} shell dumpsys activity activities | grep 'mResumedActivity' | grep '{package_name}'"
				)
				result = subprocess.run(check_command, shell=True, capture_output=True, text=True, timeout=5)

				if result.returncode == 0 and result.stdout.strip():
					activity_match = re.search(r'(\w+(?:\.\w+)*)/(\.\w+|\w+(?:\.\w+)*)', result.stdout)
					if activity_match:
						package, activity = activity_match.groups()
						if package == package_name:
							if activity.startswith('.'):
								full_activity = package_name + activity
							else:
								full_activity = activity
							logger.info(f'Detected activity by launch test: {full_activity}')
							return full_activity
			except Exception as e:
				logger.warning(f'Launch test method failed: {str(e)}')

			# Final fallback: Try common activity naming patterns
			common_activities = [
				f'{package_name}.MainActivity',
				f'{package_name}.main.MainActivity',
				f'{package_name}.ui.MainActivity',
				f'{package_name}.activities.MainActivity',
				f'{package_name}.StartActivity',
				f'{package_name}.LaunchActivity',
				f'{package_name}.SplashActivity',
				f'{package_name}.HomeActivity',
			]

			logger.warning(f'Could not auto-detect activity for {package_name}, trying common patterns...')
			for activity in common_activities:
				logger.info(f'Trying fallback activity: {activity}')
				return activity  # Return the first common pattern to try

		except Exception as e:
			logger.error(f'Unexpected error detecting app activity: {str(e)}')

		logger.error(f'Could not detect main activity for package: {package_name}')
		return ''

	def scroll_by_amount(self, amount: int, direction: str = 'down') -> bool:
		"""
		Scroll the page by a specific pixel amount in the given direction

		Args:
		    amount: Number of pixels to scroll
		    direction: Direction to scroll ("up" or "down")

		Returns:
		    bool: True if scroll was successful
		"""
		try:
			logger.info(f'Scrolling {direction} by {amount} pixels')

			if direction not in ['up', 'down']:
				logger.error(f"Invalid scroll direction: {direction}. Must be 'up' or 'down'.")
				return False

			# Get screen dimensions
			size = self.driver.get_window_size()
			center_x = size['width'] // 2
			center_y = size['height'] // 2

			# Calculate start and end coordinates based on direction
			# To scroll "down" (show content below), swipe up (finger moves up)
			# To scroll "up" (show content above), swipe down (finger moves down)
			if direction == 'down':
				start_x = center_x
				start_y = center_y + (amount // 2)  # Start from lower position
				end_x = center_x
				end_y = center_y - (amount // 2)    # End at higher position (swipe up)
			else:  # direction == "up"
				start_x = center_x
				start_y = center_y - (amount // 2)  # Start from higher position
				end_x = center_x
				end_y = center_y + (amount // 2)    # End at lower position (swipe down)

			# Ensure coordinates are within screen bounds
			start_y = max(0, min(start_y, size['height']))
			end_y = max(0, min(end_y, size['height']))

			success = self.gesture_service.swipe(start_x, start_y, end_x, end_y, 300)

			if success:
				logger.info(f'Successfully scrolled {direction} by {amount} pixels')
			else:
				logger.error(f'Failed to scroll {direction} by {amount} pixels')

			return success
		except Exception as e:
			logger.error(f'Error scrolling {direction} by {amount} pixels: {str(e)}')
			return False

	def send_keys(self, keys: str) -> bool:
		"""
		Send keyboard keys like Enter, Back, Home, etc. for mobile navigation and text input completion

		Args:
		    keys: String representing the key(s) to send. Supports:
		        - Single keys: "Enter", "Back", "Home", "Delete", "Space", "Tab"
		        - Text strings: "Hello World" (sent as individual characters)
		        - Multiple keys: "Enter,Back,Home" (comma-separated)

		Returns:
		    bool: True if keys were sent successfully

		Supported mobile keys:
		    Android: Enter, Back, Home, Menu, Search, Delete, Space, Tab, 
		             VolumeUp, VolumeDown, Power, Camera, Call, EndCall
		    iOS: Home, VolumeUp, VolumeDown, Lock (Power button), Siri
		"""
		try:
			logger.info(f'Sending keys: {keys}')
			return self.gesture_service.send_keys(keys)
		except Exception as e:
			logger.error(f'Error sending keys "{keys}": {str(e)}')
			return False




