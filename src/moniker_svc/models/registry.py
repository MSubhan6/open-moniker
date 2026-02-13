"""
Thread-safe model registry with bidirectional indexes.

Provides centralized storage and access to business model configurations,
with efficient lookups both from model → monikers and moniker → models.
"""

import fnmatch
import re
import threading
from typing import Iterator


from .types import Model


class ModelRegistry:
    """
    Thread-safe registry for business model configurations.

    Features:
    - Hierarchical model storage with parent-child relationships
    - Bidirectional index: model path ↔ moniker patterns
    - Pattern matching for finding models by moniker path
    """

    def __init__(self):
        self._models: dict[str, Model] = {}
        self._children: dict[str, set[str]] = {}  # parent → children paths
        self._moniker_to_models: dict[str, set[str]] = {}  # pattern → model paths
        self._lock = threading.RLock()

    def register(self, model: Model) -> None:
        """
        Register a model in the registry.

        Args:
            model: The model to register

        Raises:
            ValueError: If a model with the same path already exists
        """
        with self._lock:
            if model.path in self._models:
                raise ValueError(f"Model '{model.path}' already registered")
            self._register_internal(model)

    def register_or_update(self, model: Model) -> None:
        """
        Register a model, or update if it already exists.

        Args:
            model: The model to register or update
        """
        with self._lock:
            # Remove old indexes if updating
            if model.path in self._models:
                self._remove_indexes(model.path)
            self._register_internal(model)

    def _register_internal(self, model: Model) -> None:
        """Internal registration (assumes lock is held)."""
        self._models[model.path] = model

        # Build parent-child index
        parent = model.parent_path
        if parent is not None:
            if parent not in self._children:
                self._children[parent] = set()
            self._children[parent].add(model.path)

        # Build moniker → models index
        for link in model.appears_in:
            pattern = link.moniker_pattern
            if pattern not in self._moniker_to_models:
                self._moniker_to_models[pattern] = set()
            self._moniker_to_models[pattern].add(model.path)

    def _remove_indexes(self, path: str) -> None:
        """Remove a model from indexes (assumes lock is held)."""
        model = self._models.get(path)
        if not model:
            return

        # Remove from parent's children
        parent = model.parent_path
        if parent and parent in self._children:
            self._children[parent].discard(path)

        # Remove from moniker index
        for link in model.appears_in:
            pattern = link.moniker_pattern
            if pattern in self._moniker_to_models:
                self._moniker_to_models[pattern].discard(path)
                if not self._moniker_to_models[pattern]:
                    del self._moniker_to_models[pattern]

    def get(self, path: str) -> Model | None:
        """
        Get a model by path.

        Args:
            path: The model path

        Returns:
            The model if found, None otherwise
        """
        with self._lock:
            return self._models.get(path)

    def get_or_raise(self, path: str) -> Model:
        """
        Get a model by path, raising if not found.

        Args:
            path: The model path

        Returns:
            The model

        Raises:
            KeyError: If model not found
        """
        with self._lock:
            if path not in self._models:
                raise KeyError(f"Model '{path}' not found")
            return self._models[path]

    def exists(self, path: str) -> bool:
        """
        Check if a model exists.

        Args:
            path: The model path

        Returns:
            True if the model exists
        """
        with self._lock:
            return path in self._models

    def delete(self, path: str) -> bool:
        """
        Delete a model from the registry.

        Args:
            path: The model path

        Returns:
            True if the model was deleted, False if it didn't exist
        """
        with self._lock:
            if path not in self._models:
                return False
            self._remove_indexes(path)
            del self._models[path]
            return True

    def clear(self) -> None:
        """Clear all models from the registry."""
        with self._lock:
            self._models.clear()
            self._children.clear()
            self._moniker_to_models.clear()

    def count(self) -> int:
        """Get the number of registered models."""
        with self._lock:
            return len(self._models)

    # =========================================================================
    # Hierarchy navigation
    # =========================================================================

    def children_paths(self, parent: str) -> list[str]:
        """
        Get paths of direct children of a parent model.

        Args:
            parent: Parent model path (empty string for root)

        Returns:
            Sorted list of child paths
        """
        with self._lock:
            if parent == "":
                # Root level - return all models with no parent
                return sorted([
                    p for p, m in self._models.items()
                    if m.parent_path is None
                ])
            return sorted(self._children.get(parent, set()))

    def children(self, parent: str) -> list[Model]:
        """
        Get direct children of a parent model.

        Args:
            parent: Parent model path

        Returns:
            List of child models
        """
        with self._lock:
            paths = self.children_paths(parent)
            return [self._models[p] for p in paths if p in self._models]

    def all_models(self) -> list[Model]:
        """
        Get all registered models.

        Returns:
            List of all models, sorted by path
        """
        with self._lock:
            return sorted(self._models.values(), key=lambda m: m.path)

    def all_paths(self) -> list[str]:
        """
        Get all registered model paths.

        Returns:
            Sorted list of model paths
        """
        with self._lock:
            return sorted(self._models.keys())

    # =========================================================================
    # Moniker ↔ Model lookups
    # =========================================================================

    def models_for_moniker(self, moniker_path: str) -> list[Model]:
        """
        Find all models that appear in a given moniker path.

        Uses pattern matching on the appears_in patterns.

        Args:
            moniker_path: A moniker path like "risk/cvar/portfolio-123/USD"

        Returns:
            List of models that match
        """
        with self._lock:
            matching_models = set()

            for pattern, model_paths in self._moniker_to_models.items():
                if self._pattern_matches(pattern, moniker_path):
                    matching_models.update(model_paths)

            return sorted(
                [self._models[p] for p in matching_models if p in self._models],
                key=lambda m: m.path
            )

    def monikers_for_model(self, model_path: str) -> list[str]:
        """
        Get all moniker patterns where a model appears.

        Args:
            model_path: The model path

        Returns:
            List of moniker patterns
        """
        with self._lock:
            model = self._models.get(model_path)
            if not model:
                return []
            return [link.moniker_pattern for link in model.appears_in]

    def _pattern_matches(self, pattern: str, path: str) -> bool:
        """
        Check if a moniker path matches a pattern.

        Supports:
        - * matches single segment
        - ** matches any number of segments
        - Exact matches

        Args:
            pattern: Pattern like "risk.cvar/*/*" or "portfolios/*/risk/**"
            path: Actual moniker path

        Returns:
            True if pattern matches path
        """
        # Convert pattern to regex
        # First, escape regex special chars except * and /
        regex_pattern = re.escape(pattern)

        # Convert ** (escaped as \*\*) to match any segments
        regex_pattern = regex_pattern.replace(r"\*\*", r".*")

        # Convert single * (escaped as \*) to match single segment
        # But not if it's part of ** (already handled)
        regex_pattern = re.sub(r"(?<!\.)(?<!\*)\\\*(?!\*)", r"[^/]*", regex_pattern)

        # Anchor the pattern
        regex_pattern = f"^{regex_pattern}$"

        try:
            return bool(re.match(regex_pattern, path))
        except re.error:
            # Fall back to fnmatch for simpler patterns
            return fnmatch.fnmatch(path, pattern)

    # =========================================================================
    # Tree building
    # =========================================================================

    def build_tree(self) -> dict:
        """
        Build a nested tree structure of all models.

        Returns:
            Nested dict with model info at each level
        """
        with self._lock:
            tree: dict = {}

            for model in sorted(self._models.values(), key=lambda m: m.path):
                parts = model.path.replace(".", "/").split("/")
                current = tree

                for i, part in enumerate(parts):
                    if part not in current:
                        current[part] = {"_children": {}}

                    if i == len(parts) - 1:
                        # Leaf node - add model info
                        current[part]["_model"] = model
                    else:
                        current = current[part]["_children"]

            return tree

    # =========================================================================
    # Dunder methods
    # =========================================================================

    def __len__(self) -> int:
        return self.count()

    def __contains__(self, path: str) -> bool:
        return self.exists(path)

    def __iter__(self) -> Iterator[Model]:
        return iter(self.all_models())

    def __getitem__(self, path: str) -> Model:
        return self.get_or_raise(path)
