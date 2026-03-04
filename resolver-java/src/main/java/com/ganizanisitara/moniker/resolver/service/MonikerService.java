package com.ganizanisitara.moniker.resolver.service;

import com.ganizanisitara.moniker.resolver.catalog.*;
import com.ganizanisitara.moniker.resolver.moniker.Moniker;
import com.ganizanisitara.moniker.resolver.moniker.MonikerParser;
import com.ganizanisitara.moniker.resolver.moniker.MonikerParseException;
import org.springframework.stereotype.Service;

import java.util.*;

/**
 * Core moniker resolution service.
 */
@Service
public class MonikerService {
    private static final int MAX_SUCCESSOR_DEPTH = 5;

    private final CatalogRegistry catalog;

    public MonikerService(CatalogRegistry catalog) {
        this.catalog = catalog;
    }

    /**
     * Resolve a moniker string to a source binding.
     */
    public ResolveResult resolve(String monikerStr) throws ResolutionException {
        // Parse moniker
        Moniker moniker;
        try {
            moniker = MonikerParser.parseMoniker(monikerStr);
        } catch (MonikerParseException e) {
            throw new ResolutionException("Invalid moniker: " + e.getMessage(), 400);
        }

        // Find the catalog node with source binding
        String path = moniker.getPath().toString();
        CatalogNode node = catalog.findSourceBinding(path);

        if (node == null) {
            throw new ResolutionException("No source binding found for path: " + path, 404);
        }

        // Follow successor chain if node is deprecated
        int successorDepth = 0;
        while (node.hasSuccessor() && successorDepth < MAX_SUCCESSOR_DEPTH) {
            String successorPath = node.getSuccessor();
            CatalogNode successorNode = catalog.findSourceBinding(successorPath);

            if (successorNode == null) {
                break; // Broken successor chain
            }

            node = successorNode;
            path = successorNode.getPath();
            successorDepth++;
        }

        if (successorDepth >= MAX_SUCCESSOR_DEPTH) {
            throw new ResolutionException("Successor chain too deep (max 5)", 500);
        }

        // Validate access policy
        AccessPolicy policy = node.getAccessPolicy();
        List<String> warnings = new ArrayList<>();
        int estimatedRows = 0;

        if (policy != null) {
            List<String> segments = moniker.getPath().getSegments();
            AccessPolicy.ValidationResult validation = policy.validate(segments);
            estimatedRows = validation.getEstimatedRows();

            if (!validation.isAllowed()) {
                throw new ResolutionException(validation.getMessage(), 403);
            }

            if (validation.getMessage() != null) {
                warnings.add(validation.getMessage());
            }
        }

        // Resolve ownership
        ResolvedOwnership ownership = catalog.resolveOwnership(path);

        // Build result
        ResolveResult result = new ResolveResult(monikerStr, path);
        result.setVersion(moniker.getVersion());
        result.setNamespace(moniker.getNamespace());

        SourceBinding binding = node.getSourceBinding();
        if (binding != null) {
            result.setSourceType(binding.getType().toString());
            result.setSourceConfig(binding.getConfig());
            result.setSchema(binding.getSchema());

            // Build query from template (simplified - just return config for now)
            String queryTemplate = (String) binding.getConfig().get("query_template");
            if (queryTemplate != null) {
                result.setQuery(substituteQueryTemplate(queryTemplate, moniker, path));
            }
        }

        result.setOwnership(ownership);
        result.setWarnings(warnings);
        result.setEstimatedRows(estimatedRows);

        if (node.isDeprecated()) {
            result.setDeprecated(true);
            result.setDeprecationMessage(node.getDeprecationMessage());
            result.setSuccessor(node.getSuccessor());
        }

        return result;
    }

    /**
     * Describe a catalog node.
     */
    public DescribeResult describe(String path) throws ResolutionException {
        CatalogNode node = catalog.get(path);
        if (node == null) {
            throw new ResolutionException("Node not found: " + path, 404);
        }

        DescribeResult result = new DescribeResult(path);
        result.setDisplayName(node.getDisplayName());
        result.setDescription(node.getDescription());
        result.setStatus(node.getStatus());
        result.setClassification(node.getClassification());
        result.setTags(node.getTags());
        result.setLeaf(node.isLeaf());
        result.setHasSourceBinding(node.hasSourceBinding());
        result.setCreatedAt(node.getCreatedAt());
        result.setUpdatedAt(node.getUpdatedAt());
        result.setSuccessor(node.getSuccessor());

        // Add ownership
        if (node.getOwnership() != null) {
            Map<String, Object> ownershipMap = new HashMap<>();
            Ownership o = node.getOwnership();
            if (o.getAccountableOwner() != null) ownershipMap.put("accountable_owner", o.getAccountableOwner());
            if (o.getDataSpecialist() != null) ownershipMap.put("data_specialist", o.getDataSpecialist());
            if (o.getSupportChannel() != null) ownershipMap.put("support_channel", o.getSupportChannel());
            result.setOwnership(ownershipMap);
        }

        return result;
    }

    /**
     * List children of a path.
     */
    public List<String> listChildren(String path) {
        return catalog.childrenPaths(path);
    }

    /**
     * Get lineage (ancestor chain) for a path.
     */
    public List<Map<String, Object>> getLineage(String path) {
        List<Map<String, Object>> lineage = new ArrayList<>();

        String current = path;
        while (current != null && !current.isEmpty()) {
            CatalogNode node = catalog.get(current);

            Map<String, Object> item = new HashMap<>();
            item.put("path", current);

            if (node != null) {
                item.put("display_name", node.getDisplayName());
                item.put("description", node.getDescription());
                item.put("status", node.getStatus().toString());
            }

            lineage.add(0, item); // Add at beginning for root-to-leaf order

            // Move to parent
            int lastSlash = current.lastIndexOf('/');
            if (lastSlash > 0) {
                current = current.substring(0, lastSlash);
            } else {
                break;
            }
        }

        return lineage;
    }

    /**
     * Get catalog statistics.
     */
    public Map<String, Object> getStats() {
        List<CatalogNode> allNodes = catalog.getAllNodes();

        Map<String, Integer> byStatus = new HashMap<>();
        Map<String, Integer> bySourceType = new HashMap<>();
        int totalNodes = allNodes.size();
        int leafNodes = 0;

        for (CatalogNode node : allNodes) {
            // Count by status
            String status = node.getStatus().toString();
            byStatus.put(status, byStatus.getOrDefault(status, 0) + 1);

            // Count leaf nodes
            if (node.isLeaf()) {
                leafNodes++;
            }

            // Count by source type
            if (node.getSourceBinding() != null) {
                String sourceType = node.getSourceBinding().getType().toString();
                bySourceType.put(sourceType, bySourceType.getOrDefault(sourceType, 0) + 1);
            }
        }

        Map<String, Object> stats = new HashMap<>();
        stats.put("total_nodes", totalNodes);
        stats.put("leaf_nodes", leafNodes);
        stats.put("category_nodes", totalNodes - leafNodes);
        stats.put("by_status", byStatus);
        stats.put("by_source_type", bySourceType);

        return stats;
    }

    // Helper methods

    private String substituteQueryTemplate(String template, Moniker moniker, String path) {
        // Simple template substitution (enhance as needed)
        String result = template;

        // Substitute path segments
        List<String> segments = moniker.getPath().getSegments();
        for (int i = 0; i < segments.size(); i++) {
            result = result.replace("{" + i + "}", segments.get(i));
            result = result.replace("{seg" + i + "}", segments.get(i));
        }

        // Substitute version
        if (moniker.getVersion() != null) {
            result = result.replace("{version}", moniker.getVersion());
        }

        // Substitute query params
        for (Map.Entry<String, String> entry : moniker.getParams().asMap().entrySet()) {
            result = result.replace("{" + entry.getKey() + "}", entry.getValue());
        }

        return result;
    }
}
