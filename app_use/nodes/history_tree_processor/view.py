"""View definitions for the *history_tree_processor* package."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app_use.nodes.app_node import CoordinateSet, ViewportInfo

__all__ = [
	'HashedAppElement',
	'AppHistoryElement',
]


# ---------------------------------------------------------------------------
#   Hash container for fast equality comparison of historical vs current nodes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HashedAppElement:
	"""SHA-256 digests of the three aspects that uniquely identify a UI element.

	*   **branch_path_hash** – hash of the parent element *types* from root → self
	*   **attributes_hash** – hash of the element's properties / text / key
	*   **path_hash** – hash of the human-readable path returned by
	    :py:meth:`app_use.nodes.app_node.AppElementNode.get_node_path`
	"""

	branch_path_hash: str
	attributes_hash: str
	path_hash: str


# ---------------------------------------------------------------------------
#   Historical representation of an :class:`AppElementNode`
# ---------------------------------------------------------------------------


@dataclass
class AppHistoryElement:
	"""Serialisable snapshot of an :class:`app_use.nodes.app_node.AppElementNode`.

	The goal is to capture just enough information to reliably locate the same
	element when the UI is rebuilt at a later point in time.
	"""

	node_type: str
	node_path: str
	highlight_index: Optional[int]
	entire_parent_branch_path: List[str]
	properties: Dict[str, Any]
	text: Optional[str] = None
	key: Optional[str] = None

	# Geometry / viewport information – optional and only present when the
	# original element carried this data.
	page_coordinates: Optional[CoordinateSet] = None
	viewport_coordinates: Optional[CoordinateSet] = None
	viewport_info: Optional[ViewportInfo] = None

	# ------------------------------------------------------------------
	# Serialisation helpers
	# ------------------------------------------------------------------
	def to_dict(self) -> dict:  # noqa: D401
		page_coords = self.page_coordinates.__json__() if self.page_coordinates else None
		viewport_coords = self.viewport_coordinates.__json__() if self.viewport_coordinates else None
		viewport_info = self.viewport_info.__json__() if self.viewport_info else None

		return {
			'node_type': self.node_type,
			'node_path': self.node_path,
			'highlight_index': self.highlight_index,
			'entire_parent_branch_path': self.entire_parent_branch_path,
			'properties': self.properties,
			'text': self.text,
			'key': self.key,
			'page_coordinates': page_coords,
			'viewport_coordinates': viewport_coords,
			'viewport_info': viewport_info,
		}
