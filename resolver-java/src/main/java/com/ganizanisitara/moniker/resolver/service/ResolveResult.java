package com.ganizanisitara.moniker.resolver.service;

import com.ganizanisitara.moniker.resolver.catalog.CatalogNode;
import com.ganizanisitara.moniker.resolver.catalog.ResolvedOwnership;
import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Result of resolving a moniker.
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class ResolveResult {
    private String moniker;
    private String path;
    private String version;
    private String namespace;
    private String sourceType;
    private Map<String, Object> sourceConfig;
    private Map<String, Object> schema;
    private String query;
    private ResolvedOwnership ownership;
    private Map<String, Object> accessPolicy;
    private List<String> warnings;
    private Map<String, Object> metadata;
    private String deprecationMessage;
    private String successor;
    private boolean deprecated;
    private int estimatedRows;

    public ResolveResult(String moniker, String path) {
        this.moniker = moniker;
        this.path = path;
        this.warnings = new ArrayList<>();
        this.metadata = new HashMap<>();
        this.sourceConfig = new HashMap<>();
    }
}
