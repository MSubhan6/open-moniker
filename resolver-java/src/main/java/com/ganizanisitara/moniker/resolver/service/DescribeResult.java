package com.ganizanisitara.moniker.resolver.service;

import com.ganizanisitara.moniker.resolver.catalog.NodeStatus;
import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Result of describing a catalog node.
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class DescribeResult {
    private String path;
    private String displayName;
    private String description;
    private NodeStatus status;
    private String classification;
    private List<String> tags;
    private boolean isLeaf;
    private boolean hasSourceBinding;
    private Map<String, Object> ownership;
    private Map<String, Object> metadata;
    private String createdAt;
    private String updatedAt;
    private String successor;

    public DescribeResult(String path) {
        this.path = path;
        this.tags = new ArrayList<>();
        this.ownership = new HashMap<>();
        this.metadata = new HashMap<>();
    }
}
