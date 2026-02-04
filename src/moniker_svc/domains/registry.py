"""
Thread-safe domain registry.

Provides centralized storage and access to domain configurations.
"""

import threading
from typing import Dict, List, Optional

from .types import Domain


class DomainRegistry:
    """
    Thread-safe registry for domain configurations.

    Provides methods to register, retrieve, and manage domains.
    """

    def __init__(self):
        self._domains: Dict[str, Domain] = {}
        self._lock = threading.RLock()

    def register(self, domain: Domain) -> None:
        """
        Register a domain in the registry.

        Args:
            domain: The domain to register

        Raises:
            ValueError: If a domain with the same name already exists
        """
        with self._lock:
            if domain.name in self._domains:
                raise ValueError(f"Domain '{domain.name}' already registered")
            self._domains[domain.name] = domain

    def register_or_update(self, domain: Domain) -> None:
        """
        Register a domain, or update if it already exists.

        Args:
            domain: The domain to register or update
        """
        with self._lock:
            self._domains[domain.name] = domain

    def get(self, name: str) -> Optional[Domain]:
        """
        Get a domain by name.

        Args:
            name: The domain name

        Returns:
            The domain if found, None otherwise
        """
        with self._lock:
            return self._domains.get(name)

    def get_or_raise(self, name: str) -> Domain:
        """
        Get a domain by name, raising if not found.

        Args:
            name: The domain name

        Returns:
            The domain

        Raises:
            KeyError: If domain not found
        """
        with self._lock:
            if name not in self._domains:
                raise KeyError(f"Domain '{name}' not found")
            return self._domains[name]

    def exists(self, name: str) -> bool:
        """
        Check if a domain exists.

        Args:
            name: The domain name

        Returns:
            True if the domain exists
        """
        with self._lock:
            return name in self._domains

    def all_domains(self) -> List[Domain]:
        """
        Get all registered domains.

        Returns:
            List of all domains, sorted by name
        """
        with self._lock:
            return sorted(self._domains.values(), key=lambda d: d.name)

    def domain_names(self) -> List[str]:
        """
        Get all registered domain names.

        Returns:
            Sorted list of domain names
        """
        with self._lock:
            return sorted(self._domains.keys())

    def delete(self, name: str) -> bool:
        """
        Delete a domain from the registry.

        Args:
            name: The domain name

        Returns:
            True if the domain was deleted, False if it didn't exist
        """
        with self._lock:
            if name in self._domains:
                del self._domains[name]
                return True
            return False

    def clear(self) -> None:
        """Clear all domains from the registry."""
        with self._lock:
            self._domains.clear()

    def count(self) -> int:
        """Get the number of registered domains."""
        with self._lock:
            return len(self._domains)

    def get_domain_for_path(self, moniker_path: str) -> Optional[Domain]:
        """
        Get the domain for a moniker path.

        Extracts the first segment of the path and looks up the domain.

        Args:
            moniker_path: A moniker path like "indices/equity/sp500"

        Returns:
            The domain if found, None otherwise
        """
        if not moniker_path:
            return None

        # Extract first segment
        parts = moniker_path.strip("/").split("/")
        if not parts:
            return None

        domain_name = parts[0]
        return self.get(domain_name)

    def __len__(self) -> int:
        return self.count()

    def __contains__(self, name: str) -> bool:
        return self.exists(name)

    def __iter__(self):
        return iter(self.all_domains())
