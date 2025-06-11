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
			selector_map = self._selector_map.copy()
			self._perf_metrics['build_tree_time'] = time.time() - start_time
			self._perf_metrics['node_count'] = len(all_nodes)
			self._perf_metrics['highlighted_count'] = len(selector_map)
			logger.info(f'Built element tree with {len(all_nodes)} nodes, {len(selector_map)} highlighted')

			# Create AppState with optional highlighted screenshot
			app_state = AppState(element_tree=root_node, selector_map=selector_map)

			# ------------------------------------------------------------------
			# Calculate viewport scroll information (pixels above and below)
			# ------------------------------------------------------------------
			try:
				# Gather page-coordinate bounds of *all* nodes and nodes currently in the viewport
				all_coords = [
					(node.page_coordinates.y, node.page_coordinates.y + node.page_coordinates.height)
					for node in all_nodes
					if getattr(node, "page_coordinates", None)
				]
				visible_coords = [
					(node.page_coordinates.y, node.page_coordinates.y + node.page_coordinates.height)
					for node in all_nodes
					if getattr(node, "page_coordinates", None) and node.is_in_viewport
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
				# Non-fatal – just log in debug mode so the rest of the builder continues.
				logger.debug(f'Failed to compute scroll pixels: {e}')

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

		if platform_type.lower() == 'android':
			node_type = attributes.get('class', 'Unknown')
		elif platform_type.lower() == 'ios':
			node_type = attributes.get('type', 'Unknown')
		else:
			node_type = 'Unknown'

		text = (
			attributes.get('text', None)
			or attributes.get('content-desc', None)
			or attributes.get('name', None)
			or attributes.get('label', None)  # iOS accessibility label
			or attributes.get('value', None)
		)

		# Extract unique identifier (key) for reliable element selection
		# This represents the most reliable way to find the element programmatically
		key = None
		if platform_type.lower() == 'android':
			# Use resource-id as the unique identifier for Android elements
			# This corresponds to AppiumBy.ID in Appium selectors
			key = attributes.get('resource-id', None)
		elif platform_type.lower() == 'ios':
			# For iOS, prioritize accessibility-id over name as the unique identifier
			# This corresponds to AppiumBy.ACCESSIBILITY_ID in Appium selectors
			key = attributes.get('accessibility-id', None) or attributes.get('name', None)

		is_interactive = self._is_element_interactive(attributes, node_type, platform_type)

		# Parse bounds and calculate coordinates
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
					# since there's no scrolling offset like in web browsers
					viewport_coordinates = CoordinateSet(x=x1, y=y1, width=width, height=height)
					page_coordinates = CoordinateSet(x=x1, y=y1, width=width, height=height)

					# Calculate if element is in expanded viewport
					expanded_top = -viewport_expansion
					expanded_bottom = screen_height + viewport_expansion
					expanded_left = -viewport_expansion
					expanded_right = screen_width + viewport_expansion
					is_in_viewport = x2 > expanded_left and x1 < expanded_right and y2 > expanded_top and y1 < expanded_bottom
			except Exception as e:
				logger.debug(f"Error parsing bounds '{bounds}': {e}")
		elif screen_width and screen_height:
			try:
				# iOS format: separate x, y, width, height attributes
				x = attributes.get('x')
				y = attributes.get('y')
				width = attributes.get('width')
				height = attributes.get('height')
				
				if x is not None and y is not None and width is not None and height is not None:
					x1, y1 = int(x), int(y)
					w, h = int(width), int(height)
					x2, y2 = x1 + w, y1 + h
					
					# For iOS, check both size and visible attribute
					is_visible = w > 0 and h > 0 and attributes.get('visible', 'true').lower() == 'true'

					# For mobile apps, viewport coordinates and page coordinates are the same
					viewport_coordinates = CoordinateSet(x=x1, y=y1, width=w, height=h)
					page_coordinates = CoordinateSet(x=x1, y=y1, width=w, height=h)

					# Calculate if element is in expanded viewport
					expanded_top = -viewport_expansion
					expanded_bottom = screen_height + viewport_expansion
					expanded_left = -viewport_expansion
					expanded_right = screen_width + viewport_expansion
					is_in_viewport = x2 > expanded_left and x1 < expanded_right and y2 > expanded_top and y1 < expanded_bottom
			except Exception as e:
				logger.debug(f"Error parsing iOS coordinates: {e}")
		
		# Final fallback: check iOS visible attribute even without coordinates
		if platform_type.lower() == 'ios' and viewport_coordinates is None:
			is_visible = attributes.get('visible', 'true').lower() == 'true'

		highlight_index = None
		if is_interactive and is_visible and is_in_viewport:
			highlight_index = self._highlight_index
			self._selector_map[highlight_index] = None
			self._highlight_index += 1

		props = dict(attributes)
		props['_is_visible'] = is_visible
		props['_is_in_viewport'] = is_in_viewport

		node = AppElementNode(
			tag_name=node_type,
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

		if highlight_index is not None:
			self._selector_map[highlight_index] = node

		return node

	def _is_element_interactive(self, attributes, node_type, platform_type):
		"""
		Determine if an element is likely to be interactive based on its attributes and type

		Args:
		    attributes: Element attributes
		    node_type: Element node type
		    platform_type: The platform type (e.g., "android", "ios")

		Returns:
		    bool: True if the element is likely interactive, False otherwise
		"""
		if platform_type.lower() == 'android':
			interactive_types = [
				'android.widget.Button',
				'android.widget.ImageButton',
				'android.widget.EditText',
				'android.widget.CheckBox',
				'android.widget.RadioButton',
				'android.widget.Switch',
				'android.widget.Spinner',
				'android.widget.SeekBar',
			]

			# Primary check: clickable attribute
			if attributes.get('clickable', 'false').lower() == 'true':
				return True

			# Secondary check: has click listener
			if attributes.get('has-click-listener', 'false').lower() == 'true':
				return True

			# Check for known interactive widget types
			if any(interactive_type in node_type for interactive_type in interactive_types):
				return True

			# Check for ViewGroup containers that are focusable and enabled (common for custom buttons)
			if (
				node_type == 'android.view.ViewGroup'
				and attributes.get('focusable', 'false').lower() == 'true'
				and attributes.get('enabled', 'false').lower() == 'true'
			):
				return True

		elif platform_type.lower() == 'ios':
			interactive_types = [
				'XCUIElementTypeButton',
				'XCUIElementTypeTextField',
				'XCUIElementTypeSecureTextField',
				'XCUIElementTypeSwitch',
				'XCUIElementTypeSlider',
				'XCUIElementTypeCell',
				'XCUIElementTypeLink',
				'XCUIElementTypeSearchField',
				'XCUIElementTypeKey',
			]

			# Check if element is enabled first
			is_enabled = attributes.get('enabled', 'false').lower() == 'true'

			if is_enabled:
				# Known interactive types
				if node_type in interactive_types:
					return True

				# XCUIElementTypeOther can be interactive if it's accessible
				if node_type == 'XCUIElementTypeOther' and attributes.get('accessible', 'false').lower() == 'true':
					return True

		return False

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

					# Add highlight index label - just the number
					label = f'{highlight_index}'

					# Use appropriate font size for the highlight index
					font_scale = 1.0
					font_thickness = 2

					# Get text size for positioning
					(label_width, label_height), baseline = cv2.getTextSize(
						label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thickness
					)

					# Position on the right side with small offset from the right edge (using scaled coordinates)
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
			return ''
