package com.ganizanisitara.moniker.resolver.catalog;

/**
 * Lifecycle status for catalog nodes.
 */
public enum NodeStatus {
    DRAFT("draft"),                   // Being defined, not visible to clients
    PENDING_REVIEW("pending_review"), // Submitted for governance review
    APPROVED("approved"),             // Governance approved, ready to activate
    ACTIVE("active"),                 // Live and resolvable
    DEPRECATED("deprecated"),         // Still works but clients warned
    ARCHIVED("archived");             // No longer resolvable

    private final String value;

    NodeStatus(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }

    @Override
    public String toString() {
        return value;
    }

    public static NodeStatus fromString(String value) {
        for (NodeStatus status : NodeStatus.values()) {
            if (status.value.equalsIgnoreCase(value)) {
                return status;
            }
        }
        return DRAFT; // default
    }
}
