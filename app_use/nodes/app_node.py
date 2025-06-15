# app_use/nodes/app_node.py
import logging
from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, Dict, List, Optional

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Forward-declared type aliases to avoid runtime imports & circular deps.
# ----------------------------------------------------------------------
if TYPE_CHECKING:
	from app_use.nodes.history_tree_processor.view import HashedAppElement


@dataclass
class CoordinateSet:
	"""Represents a set of coordinates (x, y, width, height) for mobile elements"""

	x: float
	y: float
	width: float
	height: float

	def __json__(self) -> dict:
		return {'x': self.x, 'y': self.y, 'width': self.width, 'height': self.height}


@dataclass
class ViewportInfo:
	"""Information about the mobile device viewport"""

	width: int
	height: int

	def __json__(self) -> dict:
		return {'width': self.width, 'height': self.height}


@dataclass(frozen=False)
class AppBaseNode:
	"""Base class shared by all nodes in the element tree."""

	is_visible: bool = True
	parent: Optional['AppElementNode'] = None

	def __json__(self) -> dict:
		raise NotImplementedError('AppBaseNode is an abstract class')


@dataclass(frozen=False)
class AppTextNode(AppBaseNode):
	"""A leaf node that only contains text."""

	text: str = ''
	type: str = 'TEXT_NODE'

	def has_parent_with_highlight_index(self) -> bool:
		"""Check if any parent has a highlight index (i.e., is interactive)"""
		current = self.parent
		while current is not None:
			if current.highlight_index is not None:
				return True
			current = current.parent
		return False

	def is_parent_interactive(self) -> bool:
		"""Check if the immediate parent is interactive"""
		if self.parent is None:
			return False
		return self.parent.is_interactive

	def is_parent_in_viewport(self) -> bool:
		"""Check if the parent is in viewport"""
		if self.parent is None:
			return False
		return self.parent.is_in_viewport

	def __json__(self) -> dict:
		return {
			'text': self.text,
			'type': self.type,
			'is_visible': self.is_visible,
		}


@dataclass(frozen=False)
class AppElementNode(AppBaseNode):
	"""Represents any UI element other than a raw text leaf."""

	# Core identification - using highlight_index as primary selector like browser-use
	tag_name: str = ''  # e.g., Button, TextField, ListView, etc.

	# Element attributes and properties
	attributes: Dict[str, str] = field(default_factory=dict)
	children: List[AppBaseNode] = field(default_factory=list)

	# Interaction and visibility
	is_interactive: bool = False
	is_top_element: bool = False
	is_in_viewport: bool = False

	# Mobile-specific properties
	text: Optional[str] = None
	key: Optional[str] = None  # Flutter key or accessibility identifier

	# Highlighting for automation - primary selector like browser-use
	highlight_index: Optional[int] = None

	# Coordinate information
	viewport_coordinates: Optional[CoordinateSet] = None
	page_coordinates: Optional[CoordinateSet] = None
	viewport_info: Optional[ViewportInfo] = None

	# Shadow DOM equivalent for mobile (e.g., custom components)
	shadow_root: bool = False

	# State tracking for dynamic UIs
	is_new: Optional[bool] = None

	def __json__(self) -> dict:
		return {
			'tag_name': self.tag_name,
			'attributes': self.attributes,
			'is_visible': self.is_visible,
			'is_interactive': self.is_interactive,
			'is_top_element': self.is_top_element,
			'is_in_viewport': self.is_in_viewport,
			'text': self.text,
			'key': self.key,
			'highlight_index': self.highlight_index,
			'viewport_coordinates': self.viewport_coordinates.__json__() if self.viewport_coordinates else None,
			'page_coordinates': self.page_coordinates.__json__() if self.page_coordinates else None,
			'viewport_info': self.viewport_info.__json__() if self.viewport_info else None,
			'shadow_root': self.shadow_root,
			'is_new': self.is_new,
			'children': [child.__json__() for child in self.children],
		}

	def __repr__(self) -> str:
		tag_str = f'<{self.tag_name}'

		# Add key attributes
		if self.key:
			tag_str += f' key="{self.key}"'
		if self.text:
			tag_str += f' text="{self.text[:50]}{"..." if len(self.text) > 50 else ""}"'

		tag_str += '>'

		# Add status indicators
		extras = []
		if self.is_interactive:
			extras.append('interactive')
		if self.is_top_element:
			extras.append('top')
		if self.shadow_root:
			extras.append('shadow-root')
		if self.highlight_index is not None:
			extras.append(f'highlight:{self.highlight_index}')
		if self.is_in_viewport:
			extras.append('in-viewport')
		if self.is_new:
			extras.append('new')

		if extras:
			tag_str += f' [{", ".join(extras)}]'

		return tag_str

	@cached_property
	def hash(self) -> 'HashedAppElement':
		"""Return cached hash for history tree comparisons."""
		from app_use.nodes.history_tree_processor.service import HistoryTreeProcessor

		return HistoryTreeProcessor._hash_app_element(self)

	def add_child(self, child: AppBaseNode) -> None:
		"""Add a child node and set its parent reference."""
		self.children.append(child)
		child.parent = self

	def get_node_path(self) -> str:
		"""Get a human-readable path to this element in the UI tree.

		Returns a string representation of the path from the root to this element,
		similar to an XPath but using tag names and indices to uniquely identify the location.

		Returns:
			str: A path string like "/App/MainView/Button[2]" representing the element's location
		"""
		path_parts = []
		current = self

		# Build the path from current element to root
		while current is not None:
			# Count siblings of the same type to determine index
			if current.parent is not None:
				siblings_of_same_type = [
					child
					for child in current.parent.children
					if isinstance(child, AppElementNode) and child.tag_name == current.tag_name
				]

				# Find the index of this element among siblings of the same type
				element_index = 0
				for i, sibling in enumerate(siblings_of_same_type):
					if sibling is current:
						element_index = i
						break

				# Add index if there are multiple siblings of the same type
				if len(siblings_of_same_type) > 1:
					path_parts.append(f'{current.tag_name}[{element_index}]')
				else:
					path_parts.append(current.tag_name)
			else:
				# Root element
				path_parts.append(current.tag_name)

			current = current.parent

		# Reverse to get path from root to current element
		path_parts.reverse()
		return '/' + '/'.join(path_parts) if path_parts else '/'

	def get_all_text_till_next_interactive_element(self, max_depth: int = -1) -> str:
		"""Get all text content until hitting another interactive element."""
		text_parts = []

		def collect_text(node: AppBaseNode, current_depth: int) -> None:
			if max_depth != -1 and current_depth > max_depth:
				return

			# Skip this branch if we hit a highlighted element (except for the current node)
			if isinstance(node, AppElementNode) and node != self and node.highlight_index is not None:
				return

			if isinstance(node, AppTextNode):
				text_parts.append(node.text)
			elif isinstance(node, AppElementNode):
				# Add element's own text if it has any
				if node.text:
					text_parts.append(node.text)
				# Process children
				for child in node.children:
					collect_text(child, current_depth + 1)

		collect_text(self, 0)
		return '\n'.join(text_parts).strip()

	def interactive_elements_to_string(self, include_attributes: List[str] = None) -> str:
		"""Convert interactive elements to a readable string format."""
		formatted_text = []
		include_attributes = include_attributes or ['class', 'id', 'resource-id', 'content-desc']

		def process_node(node: AppBaseNode, depth: int) -> None:
			next_depth = depth
			depth_str = depth * '\t'

			if isinstance(node, AppElementNode):
				# Add element with highlight_index
				if node.highlight_index is not None:
					next_depth += 1

					text = node.get_all_text_till_next_interactive_element()
					attributes_str = ''

					if include_attributes and node.attributes:
						attributes_to_include = {
							key: str(value) for key, value in node.attributes.items() if key in include_attributes and value
						}

						# Optimization: if tag_name == class attribute, don't include it
						if node.tag_name.lower() == attributes_to_include.get('class', '').lower():
							attributes_to_include.pop('class', None)

						# Optimization: if text content == content-desc, don't include it
						if attributes_to_include.get('content-desc', '').strip() == text.strip() and text.strip():
							attributes_to_include.pop('content-desc', None)

						if attributes_to_include:
							attributes_str = ' '.join(f"{key}='{value}'" for key, value in attributes_to_include.items())

					# Build the line
					highlight_indicator = f'*[{node.highlight_index}]*' if node.is_new else f'[{node.highlight_index}]'

					line = f'{depth_str}{highlight_indicator}<{node.tag_name}'

					if attributes_str:
						line += f' {attributes_str}'

					if text:
						if not attributes_str:
							line += ' '
						line += f'>{text}'
					elif not attributes_str:
						line += ' '

					line += ' />'
					formatted_text.append(line)

				# Process children regardless
				for child in node.children:
					process_node(child, next_depth)

			elif isinstance(node, AppTextNode):
				# Add text only if it doesn't have a highlighted parent
				if (
					not node.has_parent_with_highlight_index()
					and node.parent
					and node.parent.is_visible
					and node.parent.is_top_element
				):
					formatted_text.append(f'{depth_str}{node.text}')

		process_node(self, 0)
		return '\n'.join(formatted_text)


# ----------------------------------------------------------------------
# Backwards-compat:   Keep *AppNode* name alive until callers migrate.
# ----------------------------------------------------------------------
AppNode = AppElementNode  # type: ignore


# ----------------------------------------------------------------------
# Selector map & AppState container
# ----------------------------------------------------------------------

SelectorMap = Dict[int, AppBaseNode]


@dataclass
class AppState:
	"""State wrapper containing the root *element_tree* and a *selector_map*."""

	element_tree: AppElementNode
	selector_map: SelectorMap = field(default_factory=dict)
	screenshot: Optional[str] = None  # Base64 encoded screenshot
	# Viewport scroll information (in pixels)
	pixels_above: int = 0
	pixels_below: int = 0

	# ------------------------------------------------------------------
	# Serialisation helpers
	# ------------------------------------------------------------------
	def to_json(self) -> dict:  # noqa: D401
		return {
			'element_tree': self.element_tree.to_json(),
			'selector_map': {uid: node.to_json() for uid, node in self.selector_map.items()},
			'screenshot': self.screenshot,
			'pixels_above': self.pixels_above,
			'pixels_below': self.pixels_below,
		}


class AppNodeUtils:
	@staticmethod
	def find_node_by_highlight_index(nodes, highlight_index):
		"""Find a node by its highlight index"""
		for node in nodes:
			if hasattr(node, 'highlight_index') and node.highlight_index == highlight_index:
				return node
		return None

	@staticmethod
	def find_node_by_key(nodes, key_name):
		"""Find a node by its Flutter key value"""
		for node in nodes:
			if node.key == key_name:
				return node
		return None

	@staticmethod
	def find_interactive_nodes(nodes):
		"""Find interactive nodes in the tree"""
		return [node for node in nodes if node.is_interactive]

	@staticmethod
	def find_nodes_by_key(nodes, key_name):
		"""Find nodes by their Flutter key value"""
		return [node for node in nodes if node.key and key_name.lower() in node.key.lower()]

	@staticmethod
	def find_nodes_by_type(nodes, type_str):
		"""Find nodes by element type (normalized or original)"""
		return [
			node
			for node in nodes
			if type_str.lower() in node.tag_name.lower()
			or (hasattr(node, 'attributes') and node.attributes.get('_original_type', '').lower().find(type_str.lower()) >= 0)
		]

	@staticmethod
	def find_nodes_by_normalized_type(nodes, normalized_type):
		"""Find nodes by their normalized element type"""
		return [node for node in nodes if node.tag_name.lower() == normalized_type.lower()]

	@staticmethod
	def find_nodes_by_text(nodes, text_str):
		"""Find nodes by their visible text content"""
		return [node for node in nodes if node.text and text_str.lower() in node.text.lower()]

	@staticmethod
	def find_nodes_by_description(nodes, description):
		"""Find nodes by description in their attributes"""
		return [
			node
			for node in nodes
			if 'content-desc' in node.attributes and description.lower() in str(node.attributes['content-desc']).lower()
		]

	@staticmethod
	def categorize_ui_elements(nodes):
		"""Categorize UI elements by their function using normalized types"""
		categorized = {
			'navigation': [],
			'input': [],
			'buttons': [],
			'text': [],
			'images': [],
			'interactive': [],
			'containers': [],
			'other': [],
		}

		for node in nodes:
			# Skip text nodes since they're not UI elements to categorize
			if isinstance(node, AppTextNode):
				continue

			normalized_type = node.tag_name.lower()
			description = str(node.attributes.get('content-desc', '')).lower()
			text_content = str(node.text or '').lower()

			# Categorize based on normalized type first, then description
			if normalized_type in ['navbar', 'navigation'] or any(
				nav in description or nav in text_content
				for nav in ['navigation', 'menu', 'nav', 'home', 'profile', 'back', 'drawer']
			):
				categorized['navigation'].append(node)
			elif normalized_type in ['input', 'search', 'textarea'] or any(
				inp in description or inp in text_content for inp in ['input', 'search', 'form', 'field']
			):
				categorized['input'].append(node)
			elif normalized_type in ['button'] or any(
				btn in description or btn in text_content for btn in ['button', 'tap', 'click', 'press']
			):
				categorized['buttons'].append(node)
			elif normalized_type in ['text']:
				categorized['text'].append(node)
			elif normalized_type in ['image']:
				categorized['images'].append(node)
			elif node.is_interactive:
				categorized['interactive'].append(node)
			elif normalized_type in ['container', 'scroll', 'list', 'grid', 'table']:
				categorized['containers'].append(node)
			else:
				categorized['other'].append(node)

		return categorized

	@staticmethod
	def get_interactive_elements_by_type(nodes):
		"""Get interactive elements grouped by their normalized type"""
		interactive_by_type = {}

		for node in nodes:
			if node.is_interactive:
				normalized_type = node.tag_name
				if normalized_type not in interactive_by_type:
					interactive_by_type[normalized_type] = []
				interactive_by_type[normalized_type].append(node)

		return interactive_by_type

	@staticmethod
	def find_form_elements(nodes):
		"""Find form-related elements (inputs, buttons, selects, etc.)"""
		form_types = {'input', 'button', 'select', 'checkbox', 'radio', 'switch', 'slider'}
		return [node for node in nodes if node.tag_name.lower() in form_types]

	@staticmethod
	def extract_text_content(nodes):
		"""Find all text content in the UI with improved extraction"""
		text_content = {}

		for node in nodes:
			# Use text property if available
			if node.text:
				# Use highlight_index as key if available, otherwise use a generic counter
				node_key = f'highlight_{node.highlight_index}' if node.highlight_index is not None else f'node_{id(node)}'
				text_content[node_key] = {
					'text': node.text,
					'type': node.tag_name,
					'interactive': node.is_interactive,
					'visible': node.is_visible,
				}

			# Extract text from various attribute sources
			attribute_sources = [
				('content-desc', 'desc'),
				('textPreview', 'preview'),
				('data', 'data'),
				('label', 'label'),
				('hint', 'hint'),
				('name', 'name'),
				('value', 'value'),
			]

			for attr_name, prefix in attribute_sources:
				if attr_name in node.attributes and isinstance(node.attributes[attr_name], str):
					attr_value = node.attributes[attr_name]
					if attr_value and len(attr_value.strip()) > 0:
						node_key = (
							f'{prefix}_{node.highlight_index}' if node.highlight_index is not None else f'{prefix}_{id(node)}'
						)
						text_content[node_key] = {
							'text': attr_value,
							'type': node.tag_name,
							'source': attr_name,
							'interactive': node.is_interactive,
							'visible': node.is_visible,
						}

		return text_content
