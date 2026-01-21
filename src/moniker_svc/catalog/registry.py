"""Catalog registry - manages the hierarchy of catalog nodes."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Iterator

from ..moniker.types import MonikerPath
from .types import CatalogNode, Ownership, ResolvedOwnership, SourceBinding


@dataclass
class CatalogRegistry:
    """
    Thread-safe registry of catalog nodes.

    Supports:
    - Hierarchical lookup
    - Ownership inheritance resolution
    - Atomic refresh (for hot reload)
    - Children enumeration
    """
    _nodes: dict[str, CatalogNode] = field(default_factory=dict)
    _children: dict[str, set[str]] = field(default_factory=dict)  # parent -> children paths
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def register(self, node: CatalogNode) -> None:
        """Register a catalog node."""
        with self._lock:
            self._nodes[node.path] = node
            # Update parent's children set
            parent_path = self._parent_path(node.path)
            if parent_path is not None:
                if parent_path not in self._children:
                    self._children[parent_path] = set()
                self._children[parent_path].add(node.path)

    def register_many(self, nodes: list[CatalogNode]) -> None:
        """Register multiple nodes atomically."""
        with self._lock:
            for node in nodes:
                self.register(node)

    def get(self, path: str | MonikerPath) -> CatalogNode | None:
        """Get a node by path."""
        path_str = str(path) if isinstance(path, MonikerPath) else path
        with self._lock:
            return self._nodes.get(path_str)

    def get_or_virtual(self, path: str | MonikerPath) -> CatalogNode:
        """
        Get a node, or create a virtual node if it doesn't exist.

        Virtual nodes exist in the hierarchy but weren't explicitly registered.
        They inherit ownership from ancestors.
        """
        path_str = str(path) if isinstance(path, MonikerPath) else path
        with self._lock:
            node = self._nodes.get(path_str)
            if node:
                return node
            # Create virtual node
            return CatalogNode(path=path_str, is_leaf=False)

    def exists(self, path: str | MonikerPath) -> bool:
        """Check if a path exists in the catalog."""
        path_str = str(path) if isinstance(path, MonikerPath) else path
        with self._lock:
            return path_str in self._nodes

    def children(self, path: str | MonikerPath) -> list[CatalogNode]:
        """Get direct children of a path."""
        path_str = str(path) if isinstance(path, MonikerPath) else path
        with self._lock:
            child_paths = self._children.get(path_str, set())
            return [self._nodes[p] for p in child_paths if p in self._nodes]

    def children_paths(self, path: str | MonikerPath) -> list[str]:
        """Get paths of direct children."""
        path_str = str(path) if isinstance(path, MonikerPath) else path
        with self._lock:
            return list(self._children.get(path_str, set()))

    def resolve_ownership(self, path: str | MonikerPath) -> ResolvedOwnership:
        """
        Resolve effective ownership for a path by walking up the hierarchy.

        Each ownership field inherits independently from the nearest ancestor
        that defines it.
        """
        path_str = str(path) if isinstance(path, MonikerPath) else path

        with self._lock:
            # Collect all paths from root to this node
            paths = self._ancestor_paths(path_str) + [path_str]

            accountable_owner: str | None = None
            accountable_owner_source: str | None = None
            data_specialist: str | None = None
            data_specialist_source: str | None = None
            support_channel: str | None = None
            support_channel_source: str | None = None

            # Walk from root to leaf, each level can override
            for p in paths:
                node = self._nodes.get(p)
                if node and node.ownership:
                    if node.ownership.accountable_owner:
                        accountable_owner = node.ownership.accountable_owner
                        accountable_owner_source = p
                    if node.ownership.data_specialist:
                        data_specialist = node.ownership.data_specialist
                        data_specialist_source = p
                    if node.ownership.support_channel:
                        support_channel = node.ownership.support_channel
                        support_channel_source = p

            return ResolvedOwnership(
                accountable_owner=accountable_owner,
                accountable_owner_source=accountable_owner_source,
                data_specialist=data_specialist,
                data_specialist_source=data_specialist_source,
                support_channel=support_channel,
                support_channel_source=support_channel_source,
            )

    def find_source_binding(self, path: str | MonikerPath) -> tuple[SourceBinding, str] | None:
        """
        Find the source binding for a path.

        Returns the binding and the path where it was defined.
        If the exact path doesn't have a binding, walks up to find
        a parent with a binding that can handle children.
        """
        path_str = str(path) if isinstance(path, MonikerPath) else path

        with self._lock:
            # First check exact match
            node = self._nodes.get(path_str)
            if node and node.source_binding:
                return (node.source_binding, path_str)

            # Walk up hierarchy
            for ancestor in reversed(self._ancestor_paths(path_str)):
                node = self._nodes.get(ancestor)
                if node and node.source_binding:
                    # Check if this binding can handle sub-paths
                    # (most source types can - they just append the sub-path)
                    return (node.source_binding, ancestor)

            return None

    def all_paths(self) -> list[str]:
        """Get all registered paths."""
        with self._lock:
            return list(self._nodes.keys())

    def all_nodes(self) -> list[CatalogNode]:
        """Get all registered nodes."""
        with self._lock:
            return list(self._nodes.values())

    def clear(self) -> None:
        """Clear all nodes."""
        with self._lock:
            self._nodes.clear()
            self._children.clear()

    def atomic_replace(self, new_nodes: list[CatalogNode]) -> None:
        """
        Atomically replace all nodes with a new set.

        This is for hot reload - build the new catalog, then swap.
        """
        new_nodes_dict: dict[str, CatalogNode] = {}
        new_children: dict[str, set[str]] = {}

        for node in new_nodes:
            new_nodes_dict[node.path] = node
            parent_path = self._parent_path(node.path)
            if parent_path is not None:
                if parent_path not in new_children:
                    new_children[parent_path] = set()
                new_children[parent_path].add(node.path)

        with self._lock:
            self._nodes = new_nodes_dict
            self._children = new_children

    def iter_subtree(self, path: str | MonikerPath) -> Iterator[CatalogNode]:
        """Iterate all nodes under a path (including the path itself)."""
        path_str = str(path) if isinstance(path, MonikerPath) else path
        prefix = path_str + "/" if path_str else ""

        with self._lock:
            for p, node in self._nodes.items():
                if p == path_str or p.startswith(prefix):
                    yield node

    @staticmethod
    def _parent_path(path: str) -> str | None:
        """Get parent path, or None if at root."""
        if "/" not in path:
            return ""  # Parent is root
        parts = path.rsplit("/", 1)
        return parts[0] if parts[0] else None

    @staticmethod
    def _ancestor_paths(path: str) -> list[str]:
        """Get all ancestor paths from root to parent."""
        if not path:
            return []
        parts = path.split("/")
        result = []
        for i in range(1, len(parts)):
            result.append("/".join(parts[:i]))
        return result
