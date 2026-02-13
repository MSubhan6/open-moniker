"""Catalog registry - manages the hierarchy of catalog nodes."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Iterator

from ..moniker.types import MonikerPath
from .types import CatalogNode, Ownership, ResolvedOwnership, SourceBinding, NodeStatus, AuditEntry

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..domains.registry import DomainRegistry


@dataclass
class CatalogDiff:
    """Result of diffing old vs new catalog nodes."""
    added_paths: list[str] = field(default_factory=list)
    removed_paths: list[str] = field(default_factory=list)
    binding_changed_paths: list[str] = field(default_factory=list)
    status_changed_paths: list[str] = field(default_factory=list)

    @property
    def has_breaking_changes(self) -> bool:
        return len(self.removed_paths) > 0 or len(self.binding_changed_paths) > 0

    def summary(self) -> str:
        parts = []
        if self.added_paths:
            parts.append(f"{len(self.added_paths)} added")
        if self.removed_paths:
            parts.append(f"{len(self.removed_paths)} removed")
        if self.binding_changed_paths:
            parts.append(f"{len(self.binding_changed_paths)} binding changed")
        if self.status_changed_paths:
            parts.append(f"{len(self.status_changed_paths)} status changed")
        return ", ".join(parts) if parts else "no changes"


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
    _audit_log: list[AuditEntry] = field(default_factory=list)
    _path_index: dict[str, set[str]] = field(default_factory=dict)  # prefix -> paths for O(1) prefix lookups

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

    def resolve_ownership(
        self,
        path: str | MonikerPath,
        domain_registry: "DomainRegistry | None" = None,
    ) -> ResolvedOwnership:
        """
        Resolve effective ownership for a path by walking up the hierarchy.

        Each ownership field inherits independently from the nearest ancestor
        that defines it. This includes both simplified ownership fields and
        formal governance roles (ADOP, ADS, ADAL).

        If a domain_registry is provided, fields not set in the catalog hierarchy
        will fall back to the domain's ownership fields:
        - domain.owner → accountable_owner
        - domain.tech_custodian → data_specialist
        - domain.help_channel → support_channel

        Args:
            path: The moniker path to resolve ownership for
            domain_registry: Optional domain registry for ownership fallback
        """
        path_str = str(path) if isinstance(path, MonikerPath) else path

        with self._lock:
            # Collect all paths from root to this node
            paths = self._ancestor_paths(path_str) + [path_str]

            # Simplified ownership fields
            accountable_owner: str | None = None
            accountable_owner_source: str | None = None
            data_specialist: str | None = None
            data_specialist_source: str | None = None
            support_channel: str | None = None
            support_channel_source: str | None = None

            # Formal governance roles
            adop: str | None = None
            adop_source: str | None = None
            adop_name: str | None = None
            adop_name_source: str | None = None
            ads: str | None = None
            ads_source: str | None = None
            ads_name: str | None = None
            ads_name_source: str | None = None
            adal: str | None = None
            adal_source: str | None = None
            adal_name: str | None = None
            adal_name_source: str | None = None
            ui: str | None = None
            ui_source: str | None = None

            # Walk from root to leaf, each level can override
            for p in paths:
                node = self._nodes.get(p)
                if node and node.ownership:
                    # Simplified ownership
                    if node.ownership.accountable_owner:
                        accountable_owner = node.ownership.accountable_owner
                        accountable_owner_source = p
                    if node.ownership.data_specialist:
                        data_specialist = node.ownership.data_specialist
                        data_specialist_source = p
                    if node.ownership.support_channel:
                        support_channel = node.ownership.support_channel
                        support_channel_source = p
                    # Formal governance roles
                    if node.ownership.adop:
                        adop = node.ownership.adop
                        adop_source = p
                    if node.ownership.ads:
                        ads = node.ownership.ads
                        ads_source = p
                    if node.ownership.adal:
                        adal = node.ownership.adal
                        adal_source = p
                    # Human-readable names for governance roles
                    if node.ownership.adop_name:
                        adop_name = node.ownership.adop_name
                        adop_name_source = p
                    if node.ownership.ads_name:
                        ads_name = node.ownership.ads_name
                        ads_name_source = p
                    if node.ownership.adal_name:
                        adal_name = node.ownership.adal_name
                        adal_name_source = p
                    if node.ownership.ui:
                        ui = node.ownership.ui
                        ui_source = p

            # Fall back to domain ownership for fields not set in catalog
            if domain_registry:
                domain = domain_registry.get_domain_for_path(path_str)
                if domain:
                    domain_source = f"domain:{domain.name}"
                    # Map domain fields to ownership fields
                    if not accountable_owner and domain.owner:
                        accountable_owner = domain.owner
                        accountable_owner_source = domain_source
                    if not data_specialist and domain.tech_custodian:
                        data_specialist = domain.tech_custodian
                        data_specialist_source = domain_source
                    if not support_channel and domain.help_channel:
                        support_channel = domain.help_channel
                        support_channel_source = domain_source

            return ResolvedOwnership(
                accountable_owner=accountable_owner,
                accountable_owner_source=accountable_owner_source,
                data_specialist=data_specialist,
                data_specialist_source=data_specialist_source,
                support_channel=support_channel,
                support_channel_source=support_channel_source,
                adop=adop,
                adop_source=adop_source,
                adop_name=adop_name,
                adop_name_source=adop_name_source,
                ads=ads,
                ads_source=ads_source,
                ads_name=ads_name,
                ads_name_source=ads_name_source,
                adal=adal,
                adal_source=adal_source,
                adal_name=adal_name,
                adal_name_source=adal_name_source,
                ui=ui,
                ui_source=ui_source,
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
                # Skip non-resolvable statuses
                if hasattr(node, 'status') and node.status in (NodeStatus.ARCHIVED, NodeStatus.DRAFT, NodeStatus.PENDING_REVIEW):
                    pass  # Fall through to ancestor check
                else:
                    return (node.source_binding, path_str)

            # Walk up hierarchy
            for ancestor in reversed(self._ancestor_paths(path_str)):
                node = self._nodes.get(ancestor)
                if node and node.source_binding:
                    if hasattr(node, 'status') and node.status in (NodeStatus.ARCHIVED, NodeStatus.DRAFT, NodeStatus.PENDING_REVIEW):
                        continue
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

    def find_by_status(self, status: NodeStatus) -> list[CatalogNode]:
        """Get all nodes with a given lifecycle status."""
        with self._lock:
            return [n for n in self._nodes.values() if n.status == status]

    def find_active(self) -> list[CatalogNode]:
        """Get all active (resolvable) nodes."""
        return self.find_by_status(NodeStatus.ACTIVE)

    def find_deprecated(self) -> list[CatalogNode]:
        """Get all deprecated nodes."""
        return self.find_by_status(NodeStatus.DEPRECATED)

    def update_status(self, path: str, new_status: NodeStatus, actor: str) -> CatalogNode | None:
        """Update the lifecycle status of a node and log it."""
        with self._lock:
            node = self._nodes.get(path)
            if node is None:
                return None

            old_status = node.status
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()

            node.status = new_status
            node.updated_at = now
            if new_status == NodeStatus.APPROVED:
                node.approved_by = actor

            self._audit_log.append(AuditEntry(
                timestamp=now,
                path=path,
                action="status_changed",
                actor=actor,
                old_value=old_status.value,
                new_value=new_status.value,
            ))

            return node

    def add_audit_entry(self, entry: AuditEntry) -> None:
        """Add an audit entry."""
        with self._lock:
            self._audit_log.append(entry)

    def get_audit_log(self, path: str | None = None, limit: int = 100) -> list[AuditEntry]:
        """Get audit log entries, optionally filtered by path."""
        with self._lock:
            if path:
                entries = [e for e in self._audit_log if e.path == path]
            else:
                entries = list(self._audit_log)
            return entries[-limit:]

    def search(self, query: str, status: NodeStatus | None = None, limit: int = 50) -> list[CatalogNode]:
        """Search catalog nodes by path, display_name, description, or tags."""
        query_lower = query.lower()
        with self._lock:
            results = []
            for node in self._nodes.values():
                if status and node.status != status:
                    continue
                if (query_lower in node.path.lower()
                    or query_lower in node.display_name.lower()
                    or query_lower in node.description.lower()
                    or any(query_lower in t.lower() for t in node.tags)):
                    results.append(node)
                    if len(results) >= limit:
                        break
            return results

    def count(self) -> dict[str, int]:
        """Get counts by status."""
        with self._lock:
            counts: dict[str, int] = {}
            for node in self._nodes.values():
                key = node.status.value if hasattr(node.status, 'value') else str(node.status)
                counts[key] = counts.get(key, 0) + 1
            counts["total"] = len(self._nodes)
            return counts

    def paginated_paths(self, cursor: str | None = None, limit: int = 100, status: NodeStatus | None = None) -> tuple[list[str], str | None]:
        """Get paginated list of paths with optional status filter."""
        with self._lock:
            all_paths = sorted(self._nodes.keys())
            if status:
                all_paths = [p for p in all_paths if self._nodes[p].status == status]

            # Apply cursor (cursor is the last path from previous page)
            if cursor:
                start_idx = 0
                for i, p in enumerate(all_paths):
                    if p > cursor:
                        start_idx = i
                        break
                else:
                    return [], None
                all_paths = all_paths[start_idx:]

            page = all_paths[:limit]
            next_cursor = page[-1] if len(page) == limit else None
            return page, next_cursor

    def diff(self, new_nodes: list[CatalogNode]) -> CatalogDiff:
        """Diff current catalog against a proposed new set of nodes."""
        new_map = {n.path: n for n in new_nodes}
        result = CatalogDiff()

        with self._lock:
            old_paths = set(self._nodes.keys())
            new_paths = set(new_map.keys())

            result.added_paths = sorted(new_paths - old_paths)
            result.removed_paths = sorted(old_paths - new_paths)

            # Check common paths for changes
            for path in sorted(old_paths & new_paths):
                old_node = self._nodes[path]
                new_node = new_map[path]

                # Binding changed?
                old_fp = old_node.source_binding.fingerprint if old_node.source_binding else None
                new_fp = new_node.source_binding.fingerprint if new_node.source_binding else None
                if old_fp != new_fp:
                    result.binding_changed_paths.append(path)

                # Status changed?
                if old_node.status != new_node.status:
                    result.status_changed_paths.append(path)

        return result

    def validated_replace(
        self,
        new_nodes: list[CatalogNode],
        block_breaking: bool = False,
        audit_actor: str = "system",
    ) -> tuple[CatalogDiff, bool]:
        """Diff, audit, and optionally replace the catalog.

        Args:
            new_nodes: The proposed new set of catalog nodes.
            block_breaking: If True, refuse to apply if there are breaking changes.
            audit_actor: Actor name for audit log entries.

        Returns:
            (diff, applied) — the diff result and whether the replace was applied.
        """
        catalog_diff = self.diff(new_nodes)
        now = datetime.now(timezone.utc).isoformat()

        # Log audit entries for significant changes
        for path in catalog_diff.removed_paths:
            self.add_audit_entry(AuditEntry(
                timestamp=now,
                path=path,
                action="node_removed",
                actor=audit_actor,
                details="Node removed during catalog reload",
            ))

        for path in catalog_diff.binding_changed_paths:
            self.add_audit_entry(AuditEntry(
                timestamp=now,
                path=path,
                action="binding_changed",
                actor=audit_actor,
                details="Source binding changed during catalog reload",
            ))

        for path in catalog_diff.added_paths:
            self.add_audit_entry(AuditEntry(
                timestamp=now,
                path=path,
                action="node_added",
                actor=audit_actor,
                details="Node added during catalog reload",
            ))

        logger.info(f"Catalog reload diff: {catalog_diff.summary()}")

        if block_breaking and catalog_diff.has_breaking_changes:
            logger.warning("Catalog reload blocked: breaking changes detected")
            return catalog_diff, False

        self.atomic_replace(new_nodes)
        return catalog_diff, True

    def validate_successors(self) -> list[str]:
        """Validate all successor pointers reference existing nodes and detect self-references.

        Returns:
            List of error messages (empty if all valid).
        """
        errors = []
        with self._lock:
            for path, node in self._nodes.items():
                if node.successor:
                    if node.successor == path:
                        errors.append(f"{path}: successor points to itself")
                    elif node.successor not in self._nodes:
                        errors.append(f"{path}: successor '{node.successor}' does not exist")
        return errors

    @staticmethod
    def _parent_path(path: str) -> str | None:
        """Get parent path, or None if at root.

        Handles both '.' and '/' as hierarchy separators.
        Examples:
            'analytics.risk/var' -> 'analytics.risk'
            'analytics.risk' -> 'analytics'
            'analytics' -> '' (root)
        """
        if not path:
            return None
        # Check for '/' first (more specific), then '.'
        if "/" in path:
            return path.rsplit("/", 1)[0]
        if "." in path:
            return path.rsplit(".", 1)[0]
        return ""  # Parent is root

    @staticmethod
    def _ancestor_paths(path: str) -> list[str]:
        """Get all ancestor paths from root to parent.

        Handles both '.' and '/' as hierarchy separators.
        Example: 'analytics.risk/var' -> ['analytics', 'analytics.risk']
        """
        if not path:
            return []

        result = []
        current = path
        while True:
            # Find parent by removing last segment (either after '/' or '.')
            if "/" in current:
                parent = current.rsplit("/", 1)[0]
            elif "." in current:
                parent = current.rsplit(".", 1)[0]
            else:
                break  # No more parents

            if parent:
                result.insert(0, parent)  # Insert at beginning to maintain root->parent order
                current = parent
            else:
                break

        return result
