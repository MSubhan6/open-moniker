package com.ganizanisitara.moniker.resolver.telemetry;

/**
 * Type of operation being performed.
 */
public enum Operation {
    READ,           // /resolve, /fetch
    LIST,           // /list
    DESCRIBE,       // /describe
    LINEAGE,        // /lineage
    TREE,           // /tree
    CATALOG_READ,   // /catalog
    METADATA_READ,  // /metadata
    HEALTH_CHECK,   // /health
    OTHER
}
