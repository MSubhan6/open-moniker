package com.ganizanisitara.moniker.resolver.catalog;

import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.locks.StampedLock;
import java.util.stream.Collectors;

/**
 * Thread-safe registry of catalog nodes.
 * Uses StampedLock with optimistic reads for high-performance concurrent access.
 */
public class CatalogRegistry {
    private final Map<String, CatalogNode> nodes = new ConcurrentHashMap<>();
    private final Map<String, Set<String>> children = new ConcurrentHashMap<>();
    private final StampedLock lock = new StampedLock();

    /**
     * Register a single catalog node.
     */
    public void register(CatalogNode node) {
        long stamp = lock.writeLock();
        try {
            nodes.put(node.getPath(), node);

            // Update parent's children set
            String parentPath = getParentPath(node.getPath());
            if (parentPath != null) {
                children.computeIfAbsent(parentPath, k -> ConcurrentHashMap.newKeySet())
                        .add(node.getPath());
            }
        } finally {
            lock.unlockWrite(stamp);
        }
    }

    /**
     * Register multiple nodes atomically.
     */
    public void registerMany(List<CatalogNode> nodesList) {
        long stamp = lock.writeLock();
        try {
            for (CatalogNode node : nodesList) {
                nodes.put(node.getPath(), node);

                String parentPath = getParentPath(node.getPath());
                if (parentPath != null) {
                    children.computeIfAbsent(parentPath, k -> ConcurrentHashMap.newKeySet())
                            .add(node.getPath());
                }
            }
        } finally {
            lock.unlockWrite(stamp);
        }
    }

    /**
     * Get a node by path (optimistic read for performance).
     */
    public CatalogNode get(String path) {
        long stamp = lock.tryOptimisticRead();
        CatalogNode node = nodes.get(path);
        if (lock.validate(stamp)) {
            return node; // Fast path: no concurrent writes
        }

        // Fallback to read lock
        stamp = lock.readLock();
        try {
            return nodes.get(path);
        } finally {
            lock.unlockRead(stamp);
        }
    }

    /**
     * Get a node or create a virtual node if it doesn't exist.
     */
    public CatalogNode getOrVirtual(String path) {
        CatalogNode node = get(path);
        if (node != null) {
            return node;
        }

        // Create virtual node (not added to registry)
        CatalogNode virtual = new CatalogNode();
        virtual.setPath(path);
        virtual.setLeaf(false);
        virtual.setStatus(NodeStatus.DRAFT);
        return virtual;
    }

    /**
     * Check if a path exists.
     */
    public boolean exists(String path) {
        long stamp = lock.tryOptimisticRead();
        boolean exists = nodes.containsKey(path);
        if (lock.validate(stamp)) {
            return exists;
        }

        stamp = lock.readLock();
        try {
            return nodes.containsKey(path);
        } finally {
            lock.unlockRead(stamp);
        }
    }

    /**
     * Get direct children of a path.
     */
    public List<CatalogNode> children(String path) {
        long stamp = lock.readLock();
        try {
            Set<String> childPaths = children.get(path);
            if (childPaths == null) {
                return Collections.emptyList();
            }

            List<CatalogNode> result = new ArrayList<>();
            for (String p : childPaths) {
                CatalogNode node = nodes.get(p);
                if (node != null) {
                    result.add(node);
                }
            }
            return result;
        } finally {
            lock.unlockRead(stamp);
        }
    }

    /**
     * Get paths of direct children.
     */
    public List<String> childrenPaths(String path) {
        long stamp = lock.readLock();
        try {
            Set<String> childPaths = children.get(path);
            if (childPaths == null) {
                return Collections.emptyList();
            }
            return new ArrayList<>(childPaths);
        } finally {
            lock.unlockRead(stamp);
        }
    }

    /**
     * Resolve effective ownership for a path by walking up the hierarchy.
     * Each ownership field inherits independently from the nearest ancestor that defines it.
     */
    public ResolvedOwnership resolveOwnership(String path) {
        long stamp = lock.readLock();
        try {
            // Collect all paths from root to this node
            List<String> paths = new ArrayList<>(getAncestorPaths(path));
            paths.add(path);

            ResolvedOwnership result = new ResolvedOwnership();

            // Walk from root to leaf, each level can override
            for (String p : paths) {
                CatalogNode node = nodes.get(p);
                if (node == null || node.getOwnership() == null) {
                    continue;
                }

                Ownership ownership = node.getOwnership();

                // Simplified ownership
                if (ownership.getAccountableOwner() != null) {
                    result.setAccountableOwner(ownership.getAccountableOwner());
                    result.setAccountableOwnerSource(p);
                }
                if (ownership.getDataSpecialist() != null) {
                    result.setDataSpecialist(ownership.getDataSpecialist());
                    result.setDataSpecialistSource(p);
                }
                if (ownership.getSupportChannel() != null) {
                    result.setSupportChannel(ownership.getSupportChannel());
                    result.setSupportChannelSource(p);
                }

                // Governance roles
                if (ownership.getAdop() != null) {
                    result.setAdop(ownership.getAdop());
                    result.setAdopSource(p);
                }
                if (ownership.getAds() != null) {
                    result.setAds(ownership.getAds());
                    result.setAdsSource(p);
                }
                if (ownership.getAdal() != null) {
                    result.setAdal(ownership.getAdal());
                    result.setAdalSource(p);
                }

                // Governance role names
                if (ownership.getAdopName() != null) {
                    result.setAdopName(ownership.getAdopName());
                    result.setAdopNameSource(p);
                }
                if (ownership.getAdsName() != null) {
                    result.setAdsName(ownership.getAdsName());
                    result.setAdsNameSource(p);
                }
                if (ownership.getAdalName() != null) {
                    result.setAdalName(ownership.getAdalName());
                    result.setAdalNameSource(p);
                }

                // UI link
                if (ownership.getUi() != null) {
                    result.setUi(ownership.getUi());
                    result.setUiSource(p);
                }
            }

            return result;
        } finally {
            lock.unlockRead(stamp);
        }
    }

    /**
     * Find source binding by walking up the hierarchy.
     * Skips archived and draft nodes.
     */
    public CatalogNode findSourceBinding(String path) {
        long stamp = lock.readLock();
        try {
            // Check current node first
            CatalogNode node = nodes.get(path);
            if (node != null && node.hasSourceBinding() && node.isResolvable()) {
                return node;
            }

            // Walk up to ancestors
            for (String ancestorPath : getAncestorPaths(path)) {
                CatalogNode ancestor = nodes.get(ancestorPath);
                if (ancestor != null && ancestor.hasSourceBinding() && ancestor.isResolvable()) {
                    return ancestor;
                }
            }

            return null;
        } finally {
            lock.unlockRead(stamp);
        }
    }

    /**
     * Get all nodes in the catalog.
     */
    public List<CatalogNode> getAllNodes() {
        long stamp = lock.readLock();
        try {
            return new ArrayList<>(nodes.values());
        } finally {
            lock.unlockRead(stamp);
        }
    }

    /**
     * Get total number of nodes.
     */
    public int size() {
        return nodes.size();
    }

    /**
     * Clear all nodes.
     */
    public void clear() {
        long stamp = lock.writeLock();
        try {
            nodes.clear();
            children.clear();
        } finally {
            lock.unlockWrite(stamp);
        }
    }

    // Helper methods

    private String getParentPath(String path) {
        if (path == null || path.isEmpty() || !path.contains("/")) {
            return null;
        }
        int lastSlash = path.lastIndexOf('/');
        return path.substring(0, lastSlash);
    }

    private List<String> getAncestorPaths(String path) {
        List<String> ancestors = new ArrayList<>();
        String current = path;
        while (true) {
            String parent = getParentPath(current);
            if (parent == null || parent.isEmpty()) {
                break;
            }
            ancestors.add(0, parent); // Add at beginning to get root-to-leaf order
            current = parent;
        }
        return ancestors;
    }
}
