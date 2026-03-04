package com.ganizanisitara.moniker.resolver.catalog;

import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Represents a node in the catalog hierarchy.
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class CatalogNode {
    private String path;
    private String displayName;
    private String description;

    // Domain mapping (for top-level nodes)
    private String domain;

    // Ownership (inherits from ancestors if not set)
    private Ownership ownership;

    // Source binding (only leaf nodes typically have this)
    private SourceBinding sourceBinding;

    // Data governance (optional fields - not creating full classes for brevity)
    private Map<String, Object> dataQuality;
    private Map<String, Object> sla;
    private Map<String, Object> freshness;

    // Machine-readable schema for AI agent discoverability
    private Map<String, Object> dataSchema;

    // Access policy for query guardrails
    private AccessPolicy accessPolicy;

    // Documentation links
    private Map<String, Object> documentation;

    // Data classification
    private String classification = "";

    // Tags for searchability
    private List<String> tags = new ArrayList<>();

    // Additional metadata
    private Map<String, Object> metadata = new HashMap<>();

    // Governance lifecycle
    private NodeStatus status = NodeStatus.DRAFT;
    private String createdAt;
    private String updatedAt;
    private String createdBy;
    private String approvedBy;
    private String deprecationMessage;

    // Successor-based migration
    private String successor;
    private String sunsetDeadline;
    private String migrationGuideUrl;

    // Is this a leaf node (actual data) or category (contains children)?
    private boolean isLeaf = false;

    /**
     * Check if the node is resolvable (active or deprecated, not draft/archived).
     */
    public boolean isResolvable() {
        return status == NodeStatus.ACTIVE || status == NodeStatus.DEPRECATED;
    }

    /**
     * Check if the node is deprecated.
     */
    public boolean isDeprecated() {
        return status == NodeStatus.DEPRECATED;
    }

    /**
     * Check if the node has a source binding.
     */
    public boolean hasSourceBinding() {
        return sourceBinding != null;
    }

    /**
     * Check if the node has a successor.
     */
    public boolean hasSuccessor() {
        return successor != null && !successor.isEmpty();
    }

    /**
     * Get the parent path (null if root).
     */
    public String getParentPath() {
        if (path == null || path.isEmpty() || !path.contains("/")) {
            return null;
        }
        int lastSlash = path.lastIndexOf('/');
        return path.substring(0, lastSlash);
    }

    /**
     * Get the node name (last segment of path).
     */
    public String getNodeName() {
        if (path == null || path.isEmpty()) {
            return "";
        }
        int lastSlash = path.lastIndexOf('/');
        return lastSlash >= 0 ? path.substring(lastSlash + 1) : path;
    }
}
