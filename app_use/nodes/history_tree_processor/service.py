"""Utility helpers for converting between *live* :pyclass:`AppElementNode` instances
and their *historical* counterparts, as well as locating / matching the same
nodes in two different UI trees.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from app_use.nodes.app_node import AppElementNode
from app_use.nodes.history_tree_processor.view import (
	AppHistoryElement,
	HashedAppElement,
)

if TYPE_CHECKING:  # pragma: no cover
	from app_use.nodes.app_node import AppBaseNode  # noqa: F401 – typing only


class HistoryTreeProcessor:  # noqa: D101 – public API mirrors web implementation
	# ------------------------------------------------------------------
	# Public helpers
	# ------------------------------------------------------------------
	@staticmethod
	def convert_app_element_to_history_element(
		app_element: AppElementNode,
	) -> AppHistoryElement:  # noqa: D401
		"""Create an :class:`AppHistoryElement` snapshot from *app_element*."""
		parent_branch_path = HistoryTreeProcessor._get_parent_branch_path(app_element)
		node_path = app_element.get_node_path()

		# Ensure we have a plain-serialisable *properties* dict (cast all values
		# to *str* so the hash is stable across executions)
		str_props: Dict[str, str] = {k: str(v) for k, v in app_element.attributes.items()}

		return AppHistoryElement(
			node_type=app_element.tag_name,
			node_path=node_path,
			highlight_index=app_element.highlight_index,
			entire_parent_branch_path=parent_branch_path,
			properties=str_props,
			text=app_element.text,
			key=app_element.key,
			page_coordinates=app_element.page_coordinates,
			viewport_coordinates=app_element.viewport_coordinates,
			viewport_info=app_element.viewport_info,
		)

	# ------------------------------------------------------------------
	#   History ↔ Tree helpers
	# ------------------------------------------------------------------
	@staticmethod
	def find_history_element_in_tree(
		app_history_element: AppHistoryElement,
		tree: AppElementNode,
	) -> Optional[AppElementNode]:
		"""Depth-first search *tree* for the element that matches *app_history_element*."""
		target_hash = HistoryTreeProcessor._hash_app_history_element(app_history_element)

		def _traverse(node: AppElementNode) -> Optional[AppElementNode]:
			if node.highlight_index is not None:
				if HistoryTreeProcessor._hash_app_element(node) == target_hash:
					return node
			for child in node.children:
				if isinstance(child, AppElementNode):
					match = _traverse(child)
					if match is not None:
						return match
			return None

		return _traverse(tree)

	@staticmethod
	def compare_history_element_and_app_element(
		app_history_element: AppHistoryElement,
		app_element: AppElementNode,
	) -> bool:
		"""Return *True* when *app_history_element* describes *app_element*."""
		return HistoryTreeProcessor._hash_app_history_element(app_history_element) == HistoryTreeProcessor._hash_app_element(
			app_element
		)

	# ------------------------------------------------------------------
	#   Hash helpers (private)
	# ------------------------------------------------------------------
	@staticmethod
	def _hash_app_history_element(
		app_history_element: AppHistoryElement,
	) -> HashedAppElement:
		branch_path_hash = HistoryTreeProcessor._parent_branch_path_hash(app_history_element.entire_parent_branch_path)
		attributes_hash = HistoryTreeProcessor._attributes_hash(
			app_history_element.properties,
			app_history_element.text,
			app_history_element.key,
		)
		path_hash = HistoryTreeProcessor._path_hash(app_history_element.node_path)
		return HashedAppElement(branch_path_hash, attributes_hash, path_hash)

	@staticmethod
	def _hash_app_element(app_element: AppElementNode) -> HashedAppElement:
		parent_branch_path = HistoryTreeProcessor._get_parent_branch_path(app_element)
		branch_path_hash = HistoryTreeProcessor._parent_branch_path_hash(parent_branch_path)
		attributes_hash = HistoryTreeProcessor._attributes_hash(
			app_element.attributes,
			app_element.text,
			app_element.key,
		)
		path_hash = HistoryTreeProcessor._path_hash(app_element.get_node_path())
		return HashedAppElement(branch_path_hash, attributes_hash, path_hash)

	# ------------------------------------------------------------------
	#   Low-level hashing primitives
	# ------------------------------------------------------------------
	@staticmethod
	def _get_parent_branch_path(app_element: AppElementNode) -> List[str]:
		parents: List[AppElementNode] = []
		current: AppElementNode = app_element
		while current.parent is not None:
			parents.append(current.parent)
			current = current.parent
		parents.reverse()
		return [p.tag_name for p in parents]

	# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
	@staticmethod
	def _parent_branch_path_hash(parent_branch_path: List[str]) -> str:
		return hashlib.sha256('/'.join(parent_branch_path).encode()).hexdigest()

	@staticmethod
	def _attributes_hash(
		properties: Dict[str, Any],
		text: Optional[str],
		key: Optional[str],
	) -> str:
		# Convert *properties* to a stable string (sorted by key)
		prop_str = ''.join(f'{k}={properties[k]}' for k in sorted(properties))
		full_str = f'{prop_str}|text={text or ""}|key={key or ""}'
		return hashlib.sha256(full_str.encode()).hexdigest()

	@staticmethod
	def _path_hash(node_path: str) -> str:
		return hashlib.sha256(node_path.encode()).hexdigest()

	# Optionally keep a text hash helper (unused for equality at the moment)
	@staticmethod
	def _text_hash(text: str) -> str:  # pragma: no cover
		return hashlib.sha256(text.encode()).hexdigest()
