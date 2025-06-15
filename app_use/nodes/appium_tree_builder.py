import base64
import logging
import re
import time
import xml.etree.ElementTree as ET
from io import BytesIO

import cv2
import numpy as np
from PIL import Image

from app_use.nodes.app_node import (
	AppElementNode,
	AppState,
	CoordinateSet,
	ViewportInfo,
)

logger = logging.getLogger('AppiumApp')


# Platform-specific class mappings for better element type normalization
ANDROID_CLASS_MAPPING = {
	'android.widget.TextView': 'text',
	'android.widget.Button': 'button',
	'android.widget.ImageButton': 'button',
	'android.widget.ImageView': 'image',
	'android.widget.EditText': 'input',
	'android.widget.CheckBox': 'checkbox',
	'android.widget.CheckedTextView': 'checkbox',
	'android.widget.ToggleButton': 'button',
	'android.widget.RadioButton': 'radio',
	'android.widget.Spinner': 'select',
	'android.widget.Switch': 'switch',
	'android.widget.SeekBar': 'slider',
	'android.widget.VideoView': 'video',
	'android.widget.SearchView': 'search',
	'android.widget.ListView': 'list',
	'android.widget.GridView': 'grid',
	'android.widget.ScrollView': 'scroll',
	'android.view.ViewGroup': 'container',
}

IOS_CLASS_MAPPING = {
	'XCUIElementTypeStaticText': 'text',
	'XCUIElementTypeButton': 'button',
	'XCUIElementTypeImage': 'image',
	'XCUIElementTypeTextField': 'input',
	'XCUIElementTypeSecureTextField': 'input',
	'XCUIElementTypeSwitch': 'switch',
	'XCUIElementTypeSlider': 'slider',
	'XCUIElementTypeCell': 'cell',
	'XCUIElementTypeTable': 'table',
	'XCUIElementTypeNavigationBar': 'navbar',
	'XCUIElementTypeApplication': 'app',
	'XCUIElementTypeWindow': 'window',
	'XCUIElementTypePicker': 'picker',
	'XCUIElementTypePickerWheel': 'picker',
	'XCUIElementTypePageIndicator': 'indicator',
	'XCUIElementTypeKey': 'key',
	'XCUIElementTypeKeyboard': 'keyboard',
	'XCUIElementTypeLink': 'link',
	'XCUIElementTypeSearchField': 'search',
	'XCUIElementTypeTextView': 'textarea',
	'XCUIElementTypeWebView': 'webview',
	'XCUIElementTypeOther': 'other',
}

# Interactive element types by platform
ANDROID_INTERACTIVE_TYPES = {
	'android.widget.Button',
	'android.widget.ImageButton',
	'android.widget.EditText',
	'android.widget.CheckBox',
	'android.widget.RadioButton',
	'android.widget.Switch',
	'android.widget.Spinner',
	'android.widget.SeekBar',
	'android.widget.ToggleButton',
	'android.widget.SearchView',
}

IOS_INTERACTIVE_TYPES = {
	'XCUIElementTypeButton',
	'XCUIElementTypeTextField',
	'XCUIElementTypeSecureTextField',
	'XCUIElementTypeSwitch',
	'XCUIElementTypeSlider',
	'XCUIElementTypeCell',
	'XCUIElementTypeLink',
	'XCUIElementTypeSearchField',
	'XCUIElementTypeKey',
}


class AppiumElementTreeBuilder:
	"""
	Builds element trees from Appium page source XML, with highlight indices and visibility tracking
	"""

	def __init__(self, driver):
		"""
		Initialize the element tree builder with an Appium driver

		Args:
		    driver: Appium WebDriver instance
		"""
		self.driver = driver
		self._highlight_index = 0
		self._selector_map = {}
		self._perf_metrics = {
			'build_tree_time': 0,
			'node_count': 0,
			'highlighted_count': 0,
		}

	def build_element_tree(
		self,
		platform_type: str,
		viewport_expansion: int = 0,
		debug_mode: bool = False,
		include_highlights: bool = True,
	):
		"""
		Build an element tree from the current app state, with highlight indices and selector map

		Args:
		    platform_type: The platform type (e.g., "android", "ios")
		    viewport_expansion: Viewport expansion in pixels
		    debug_mode: Enable debug mode
		    include_highlights: Whether to include highlighted screenshot with bounding boxes (default: True)
		"""
		self._highlight_index = 0
		self._selector_map = {}
		self._perf_metrics = {
			'build_tree_time': 0,
			'node_count': 0,
			'highlighted_count': 0,
		}
		start_time = time.time()
		try:
			page_source = self.driver.page_source
			root = ET.fromstring(page_source)

			# Get screen dimensions for viewport calculations
			try:
				size = self.driver.get_window_size()
				screen_width = size['width']
				screen_height = size['height']
				viewport_info = ViewportInfo(width=screen_width, height=screen_height)
			except Exception:
				screen_width = screen_height = 0
				viewport_info = ViewportInfo(width=0, height=0)

			root_node = self._parse_element(
				root,
				None,
				platform_type,
				screen_width,
				screen_height,
				viewport_expansion,
				debug_mode,
				viewport_info,
			)

			all_nodes = self._collect_all_nodes(root_node)

			# Sort nodes by position (top-to-bottom, left-to-right) for consistent ordering
			interactive_nodes = [node for node in all_nodes if node.highlight_index is not None]
			self._sort_nodes_by_position(interactive_nodes)

			# Reassign highlight indices after sorting
			self._reassign_highlight_indices(interactive_nodes)

			selector_map = self._selector_map.copy()
			self._perf_metrics['build_tree_time'] = time.time() - start_time
			self._perf_metrics['node_count'] = len(all_nodes)
			self._perf_metrics['highlighted_count'] = len(selector_map)
			logger.info(f'Built element tree with {len(all_nodes)} nodes, {len(selector_map)} highlighted')

			# Create AppState with optional highlighted screenshot
			app_state = AppState(element_tree=root_node, selector_map=selector_map)

			# Calculate viewport scroll information (pixels above and below)
			self._calculate_scroll_info(app_state, all_nodes)

			# Add screenshot to the node state
			try:
				screenshot = self._take_screenshot_with_highlights(app_state, include_highlights)
				app_state.screenshot = screenshot
			except Exception as e:
				logger.error(f'Failed to capture screenshot: {e}')

			return app_state

		except Exception as e:
			logger.error(f'Error building element tree: {str(e)}')
			empty_node = AppElementNode(
				tag_name='Error',
				is_interactive=False,
				attributes={},
				is_visible=False,
			)
			return AppState(element_tree=empty_node, selector_map={})

	def _parse_element(
		self,
		element,
		parent,
		platform_type,
		screen_width,
		screen_height,
		viewport_expansion,
		debug_mode,
		viewport_info,
	):
		"""
		Parse an XML element into an AppElementNode

		Args:
		    element: XML element to parse
		    parent: Parent AppElementNode
		    platform_type: The platform type (e.g., "android", "ios")
		    screen_width: Screen width
		    screen_height: Screen height
		    viewport_expansion: Viewport expansion
		    debug_mode: Debug mode
		    viewport_info: ViewportInfo object with screen dimensions

		Returns:
		    AppElementNode: The parsed element node
		"""
		attributes = element.attrib
		platform_lower = platform_type.lower()

		# Get original class/type and map to normalized type
		original_type = self._get_element_type(attributes, platform_lower)
		normalized_type = self._normalize_element_type(original_type, platform_lower)

		# Extract text content
		text = self._extract_text_content(attributes, platform_lower)

		# Extract unique identifier (key) for reliable element selection
		key = self._extract_element_key(attributes, platform_lower)

		# Determine if element is interactive
		is_interactive = self._is_element_interactive(attributes, original_type, platform_lower)

		# Parse coordinates and visibility
		viewport_coordinates, page_coordinates, is_visible, is_in_viewport = self._parse_coordinates(
			attributes, screen_width, screen_height, viewport_expansion, platform_lower
		)

		# Handle highlighting for interactive elements
		highlight_index = None
		if is_interactive and is_visible and is_in_viewport:
			highlight_index = self._highlight_index
			self._selector_map[highlight_index] = None
			self._highlight_index += 1

		# Build node properties
		props = dict(attributes)
		props['_is_visible'] = is_visible
		props['_is_in_viewport'] = is_in_viewport
		props['_original_type'] = original_type
		props['_normalized_type'] = normalized_type

		node = AppElementNode(
			tag_name=normalized_type,
			is_interactive=is_interactive,
			attributes=props,
			parent=parent,
			text=text,
			key=key,
			viewport_coordinates=viewport_coordinates,
			page_coordinates=page_coordinates,
			viewport_info=viewport_info,
			is_in_viewport=is_in_viewport,
			is_visible=is_visible,
			highlight_index=highlight_index,
		)

		# Parse children
		for child_element in element:
			child_node = self._parse_element(
				child_element,
				node,
				platform_type,
				screen_width,
				screen_height,
				viewport_expansion,
				debug_mode,
				viewport_info,
			)
			if child_node:
				node.add_child(child_node)

		# Update selector map
		if highlight_index is not None:
			self._selector_map[highlight_index] = node

		return node

	def _get_element_type(self, attributes, platform_type):
		"""Get the element type based on platform"""
		if platform_type == 'android':
			return attributes.get('class', 'Unknown')
		elif platform_type == 'ios':
			return attributes.get('type', 'Unknown')
		else:
			return 'Unknown'

	def _normalize_element_type(self, original_type, platform_type):
		"""Normalize element type using class mappings"""
		if platform_type == 'android':
			return ANDROID_CLASS_MAPPING.get(original_type, original_type)
		elif platform_type == 'ios':
			return IOS_CLASS_MAPPING.get(original_type, original_type)
		else:
			return original_type

	def _extract_text_content(self, attributes, platform_type):
		"""Extract text content from element attributes"""
		if platform_type == 'android':
			return attributes.get('text', None) or attributes.get('content-desc', None)
		elif platform_type == 'ios':
			return attributes.get('name', None) or attributes.get('label', None) or attributes.get('value', None)
		else:
			return None

	def _extract_element_key(self, attributes, platform_type):
		"""Extract unique identifier (key) for reliable element selection"""
		if platform_type == 'android':
			return attributes.get('resource-id', None)
		elif platform_type == 'ios':
			return attributes.get('accessibility-id', None) or attributes.get('name', None)
		else:
			return None

	def _is_element_interactive(self, attributes, element_type, platform_type):
		"""
		Determine if an element is interactive using simplified logic

		Args:
		    attributes: Element attributes
		    element_type: Original element type
		    platform_type: The platform type (e.g., "android", "ios")

		Returns:
		    bool: True if the element is likely interactive, False otherwise
		"""
		if platform_type == 'android':
			# Primary check: clickable attribute
			if attributes.get('clickable', 'false').lower() == 'true':
				return True

			# Secondary check: known interactive types
			if element_type in ANDROID_INTERACTIVE_TYPES:
				return True

			# Special case: ViewGroup with focus and enabled
			if (
				element_type == 'android.view.ViewGroup'
				and attributes.get('focusable', 'false').lower() == 'true'
				and attributes.get('enabled', 'false').lower() == 'true'
			):
				return True

		elif platform_type == 'ios':
			# Check if element is enabled first
			if attributes.get('enabled', 'false').lower() != 'true':
				return False

			# Known interactive types
			if element_type in IOS_INTERACTIVE_TYPES:
				return True

			# XCUIElementTypeOther can be interactive if accessible
			if element_type == 'XCUIElementTypeOther' and attributes.get('accessible', 'false').lower() == 'true':
				return True

		return False

	def _parse_coordinates(self, attributes, screen_width, screen_height, viewport_expansion, platform_type):
		"""Parse element coordinates and determine visibility"""
		bounds = attributes.get('bounds', None)
		viewport_coordinates = None
		page_coordinates = None
		is_visible = True
		is_in_viewport = True

		if bounds and screen_width and screen_height:
			try:
				# Android/iOS bounds: [x1,y1][x2,y2]
				m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
				if m:
					x1, y1, x2, y2 = map(int, m.groups())
					width = x2 - x1
					height = y2 - y1
					is_visible = width > 0 and height > 0

					# For mobile apps, viewport coordinates and page coordinates are the same
					viewport_coordinates = CoordinateSet(x=x1, y=y1, width=width, height=height)
					page_coordinates = CoordinateSet(x=x1, y=y1, width=width, height=height)

					# Calculate if element is in expanded viewport
					is_in_viewport = self._is_in_viewport(x1, y1, x2, y2, screen_width, screen_height, viewport_expansion)
			except Exception as e:
				logger.debug(f"Error parsing bounds '{bounds}': {e}")

		elif screen_width and screen_height:
			try:
				# iOS format: separate x, y, width, height attributes
				x = attributes.get('x')
				y = attributes.get('y')
				width = attributes.get('width')
				height = attributes.get('height')

				if all(coord is not None for coord in [x, y, width, height]):
					x1, y1 = int(x), int(y)
					w, h = int(width), int(height)
					x2, y2 = x1 + w, y1 + h

					# Check visibility
					is_visible = w > 0 and h > 0 and attributes.get('visible', 'true').lower() == 'true'

					viewport_coordinates = CoordinateSet(x=x1, y=y1, width=w, height=h)
					page_coordinates = CoordinateSet(x=x1, y=y1, width=w, height=h)

					is_in_viewport = self._is_in_viewport(x1, y1, x2, y2, screen_width, screen_height, viewport_expansion)
			except Exception as e:
				logger.debug(f'Error parsing iOS coordinates: {e}')

		# Final fallback: check iOS visible attribute
		if platform_type == 'ios' and viewport_coordinates is None:
			is_visible = attributes.get('visible', 'true').lower() == 'true'

		return viewport_coordinates, page_coordinates, is_visible, is_in_viewport

	def _is_in_viewport(self, x1, y1, x2, y2, screen_width, screen_height, viewport_expansion):
		"""Check if element is in expanded viewport"""
		expanded_top = -viewport_expansion
		expanded_bottom = screen_height + viewport_expansion
		expanded_left = -viewport_expansion
		expanded_right = screen_width + viewport_expansion
		return x2 > expanded_left and x1 < expanded_right and y2 > expanded_top and y1 < expanded_bottom

	def _sort_nodes_by_position(self, nodes):
		"""Sort nodes by position (top-to-bottom, left-to-right)"""

		def sort_key(node):
			if node.viewport_coordinates:
				return (node.viewport_coordinates.y, node.viewport_coordinates.x)
			return (0, 0)

		nodes.sort(key=sort_key)

	def _reassign_highlight_indices(self, sorted_nodes):
		"""Reassign highlight indices after sorting"""
		self._selector_map.clear()
		for i, node in enumerate(sorted_nodes):
			node.highlight_index = i
			self._selector_map[i] = node

	def _calculate_scroll_info(self, app_state, all_nodes):
		"""Calculate viewport scroll information"""
		try:
			# Gather page-coordinate bounds of all nodes and visible nodes
			all_coords = [
				(node.page_coordinates.y, node.page_coordinates.y + node.page_coordinates.height)
				for node in all_nodes
				if getattr(node, 'page_coordinates', None)
			]
			visible_coords = [
				(node.page_coordinates.y, node.page_coordinates.y + node.page_coordinates.height)
				for node in all_nodes
				if getattr(node, 'page_coordinates', None) and node.is_in_viewport
			]

			if all_coords and visible_coords:
				total_top = min(y1 for y1, _ in all_coords)
				total_bottom = max(y2 for _, y2 in all_coords)
				visible_top = min(y1 for y1, _ in visible_coords)
				visible_bottom = max(y2 for _, y2 in visible_coords)

				# Pixels scrolled above the current viewport
				app_state.pixels_above = max(0, int(visible_top - total_top))
				# Pixels remaining to scroll below the current viewport
				app_state.pixels_below = max(0, int(total_bottom - visible_bottom))
		except Exception as e:
			logger.debug(f'Failed to compute scroll pixels: {e}')

	def _collect_all_nodes(self, root_node):
		"""
		Collect all nodes in the element tree

		Args:
		    root_node: Root node of the element tree

		Returns:
		    list: List of all nodes in the element tree
		"""
		all_nodes = []

		def traverse(node):
			all_nodes.append(node)
			for child in node.children:
				traverse(child)

		traverse(root_node)
		return all_nodes

	def _take_screenshot_with_highlights(self, app_state: AppState, include_highlights: bool = True) -> str:
		"""
		Take a screenshot and optionally add bounding box highlights

		Args:
		    app_state: AppState containing the element tree and selector map
		    include_highlights: Whether to include bounding box highlights (default: True)

		Returns:
		    str: Base64 encoded screenshot
		"""
		try:
			# Take base screenshot
			screenshot = self.driver.get_screenshot_as_base64()

			if not include_highlights:
				return screenshot

			# Add bounding box highlights
			highlighted_screenshot = self._draw_bounding_boxes_on_screenshot(screenshot, app_state)
			return highlighted_screenshot if highlighted_screenshot else screenshot

		except Exception as e:
			logger.error(f'Error taking screenshot: {str(e)}')
			return ''

	def _draw_bounding_boxes_on_screenshot(self, screenshot_base64: str, app_state: AppState) -> str:
		"""
		Draw bounding boxes over the screenshot using app nodes

		Args:
		    screenshot_base64: Base64 encoded screenshot
		    app_state: AppState containing the element tree and selector map

		Returns:
		    str: Base64 encoded screenshot with bounding boxes, or empty string on error
		"""
		try:
			if not screenshot_base64:
				logger.error('No screenshot data provided')
				return ''

			# Decode base64 screenshot
			screenshot_data = base64.b64decode(screenshot_base64)
			screenshot_image = Image.open(BytesIO(screenshot_data))

			# Convert PIL Image to OpenCV format (RGB to BGR)
			screenshot_cv = cv2.cvtColor(np.array(screenshot_image), cv2.COLOR_RGB2BGR)

			# Get actual screenshot dimensions
			screenshot_height, screenshot_width = screenshot_cv.shape[:2]

			# Get reported screen dimensions from driver
			try:
				driver_size = self.driver.get_window_size()
				driver_width = driver_size['width']
				driver_height = driver_size['height']
			except Exception:
				logger.warning('Could not get driver window size, using screenshot dimensions')
				driver_width = screenshot_width
				driver_height = screenshot_height

			# Calculate scaling factors to handle device pixel ratio differences
			scale_x = screenshot_width / driver_width if driver_width > 0 else 1.0
			scale_y = screenshot_height / driver_height if driver_height > 0 else 1.0

			logger.debug(f'Screenshot dimensions: {screenshot_width}x{screenshot_height}')
			logger.debug(f'Driver window size: {driver_width}x{driver_height}')
			logger.debug(f'Scaling factors: x={scale_x:.2f}, y={scale_y:.2f}')

			# Define color for highlighted elements (red)
			highlight_color = (0, 0, 255)  # Red for highlighted/selector map elements

			drawn_count = 0

			# Draw bounding boxes for nodes in selector_map (highlighted interactive elements)
			logger.debug(f'Drawing {len(app_state.selector_map)} highlighted interactive elements...')
			for highlight_index, node in app_state.selector_map.items():
				if node and node.viewport_coordinates:
					# Apply scaling to coordinates
					x = int(node.viewport_coordinates.x * scale_x)
					y = int(node.viewport_coordinates.y * scale_y)
					width = int(node.viewport_coordinates.width * scale_x)
					height = int(node.viewport_coordinates.height * scale_y)

					# Ensure coordinates are within screenshot bounds
					x = max(0, min(x, screenshot_width - 1))
					y = max(0, min(y, screenshot_height - 1))
					x2 = max(x + 1, min(x + width, screenshot_width))
					y2 = max(y + 1, min(y + height, screenshot_height))

					# Draw rectangle
					cv2.rectangle(
						screenshot_cv,
						(x, y),
						(x2, y2),
						highlight_color,
						2,
					)

					# Add highlight index label
					label = f'{highlight_index}'
					font_scale = 1.0
					font_thickness = 2

					# Get text size for positioning
					(label_width, label_height), baseline = cv2.getTextSize(
						label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thickness
					)

					# Position label
					label_x = max(0, min(x2 - label_width - 5, screenshot_width - label_width))
					label_y = max(label_height, min(y + label_height + 5, screenshot_height))

					# Draw background rectangle for better visibility
					cv2.rectangle(
						screenshot_cv,
						(label_x - 2, label_y - label_height - 2),
						(label_x + label_width + 2, label_y + 2),
						highlight_color,
						-1,
					)

					# Draw the number in white
					cv2.putText(
						screenshot_cv,
						label,
						(label_x, label_y),
						cv2.FONT_HERSHEY_SIMPLEX,
						font_scale,
						(255, 255, 255),
						font_thickness,
					)

					drawn_count += 1

			logger.debug(f'Successfully drew {drawn_count} bounding boxes on screenshot')

			# Convert back to RGB for encoding
			screenshot_rgb = cv2.cvtColor(screenshot_cv, cv2.COLOR_BGR2RGB)
			final_image = Image.fromarray(screenshot_rgb)

			# Convert back to base64
			buffered = BytesIO()
			final_image.save(buffered, format='PNG')
			highlighted_screenshot_base64 = base64.b64encode(buffered.getvalue()).decode()

			return highlighted_screenshot_base64

		except Exception as e:
			logger.error(f'Error drawing bounding boxes on screenshot: {str(e)}')
			return ''
