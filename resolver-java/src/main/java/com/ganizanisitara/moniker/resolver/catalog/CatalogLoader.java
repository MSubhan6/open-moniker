package com.ganizanisitara.moniker.resolver.catalog;

import org.yaml.snakeyaml.Yaml;

import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.*;

/**
 * Loads catalog definitions from YAML files.
 */
public class CatalogLoader {

    /**
     * Load catalog from YAML file.
     */
    @SuppressWarnings("unchecked")
    public static CatalogRegistry loadFromFile(String filePath) throws IOException {
        Path path = Paths.get(filePath);
        if (!Files.exists(path)) {
            throw new IOException("Catalog file not found: " + filePath);
        }

        CatalogRegistry registry = new CatalogRegistry();

        try (InputStream input = new FileInputStream(path.toFile())) {
            Yaml yaml = new Yaml();
            Map<String, Object> data = yaml.load(input);

            if (data == null || data.isEmpty()) {
                throw new IOException("Empty catalog YAML file");
            }

            // Handle both formats: with 'catalog' key and without
            Map<String, Object> catalogData;
            if (data.containsKey("catalog")) {
                catalogData = (Map<String, Object>) data.get("catalog");
            } else {
                // Assume the whole file is the catalog
                catalogData = data;
            }

            // Recursively load nodes
            List<CatalogNode> nodes = new ArrayList<>();
            loadNodes(catalogData, "", nodes);

            // Register all nodes
            registry.registerMany(nodes);

            return registry;
        }
    }

    /**
     * Recursively load nodes from nested map structure.
     */
    @SuppressWarnings("unchecked")
    private static void loadNodes(Map<String, Object> nodeMap, String parentPath, List<CatalogNode> result) {
        if (nodeMap == null) {
            return;
        }

        for (Map.Entry<String, Object> entry : nodeMap.entrySet()) {
            String name = entry.getKey();
            Object value = entry.getValue();

            if (!(value instanceof Map)) {
                continue;
            }

            Map<String, Object> nodeData = (Map<String, Object>) value;

            // Build path
            String path = parentPath.isEmpty() ? name : parentPath + "/" + name;

            // Create node
            CatalogNode node = new CatalogNode();
            node.setPath(path);
            node.setDisplayName((String) nodeData.getOrDefault("display_name", name));
            node.setDescription((String) nodeData.getOrDefault("description", ""));
            node.setClassification((String) nodeData.getOrDefault("classification", ""));

            // Parse status
            String statusStr = (String) nodeData.get("status");
            if (statusStr != null) {
                node.setStatus(NodeStatus.fromString(statusStr));
            } else {
                node.setStatus(NodeStatus.ACTIVE); // default
            }

            // Parse ownership
            if (nodeData.containsKey("ownership")) {
                node.setOwnership(parseOwnership((Map<String, Object>) nodeData.get("ownership")));
            }

            // Parse source binding
            if (nodeData.containsKey("source_binding")) {
                node.setSourceBinding(parseSourceBinding((Map<String, Object>) nodeData.get("source_binding")));
                node.setLeaf(true);
            }

            // Parse access policy
            if (nodeData.containsKey("access_policy")) {
                node.setAccessPolicy(parseAccessPolicy((Map<String, Object>) nodeData.get("access_policy")));
            }

            // Parse tags
            if (nodeData.containsKey("tags")) {
                node.setTags((List<String>) nodeData.get("tags"));
            }

            // Metadata fields
            node.setCreatedAt((String) nodeData.get("created_at"));
            node.setUpdatedAt((String) nodeData.get("updated_at"));
            node.setCreatedBy((String) nodeData.get("created_by"));
            node.setSuccessor((String) nodeData.get("successor"));
            node.setSunsetDeadline((String) nodeData.get("sunset_deadline"));

            result.add(node);

            // Recursively load children
            if (nodeData.containsKey("children")) {
                Map<String, Object> children = (Map<String, Object>) nodeData.get("children");
                loadNodes(children, path, result);
            }
        }
    }

    @SuppressWarnings("unchecked")
    private static Ownership parseOwnership(Map<String, Object> data) {
        Ownership ownership = new Ownership();
        ownership.setAccountableOwner((String) data.get("accountable_owner"));
        ownership.setDataSpecialist((String) data.get("data_specialist"));
        ownership.setSupportChannel((String) data.get("support_channel"));
        ownership.setAdop((String) data.get("adop"));
        ownership.setAds((String) data.get("ads"));
        ownership.setAdal((String) data.get("adal"));
        ownership.setAdopName((String) data.get("adop_name"));
        ownership.setAdsName((String) data.get("ads_name"));
        ownership.setAdalName((String) data.get("adal_name"));
        ownership.setUi((String) data.get("ui"));
        return ownership;
    }

    @SuppressWarnings("unchecked")
    private static SourceBinding parseSourceBinding(Map<String, Object> data) {
        SourceBinding binding = new SourceBinding();

        String typeStr = (String) data.get("type");
        if (typeStr != null) {
            binding.setType(SourceType.fromString(typeStr));
        }

        binding.setConfig((Map<String, Object>) data.getOrDefault("config", new HashMap<>()));
        binding.setSchema((Map<String, Object>) data.get("schema"));
        binding.setAllowedOperations((List<String>) data.get("allowed_operations"));
        binding.setReadOnly((Boolean) data.getOrDefault("read_only", true));

        // Parse cache config if present
        if (data.containsKey("cache")) {
            Map<String, Object> cacheData = (Map<String, Object>) data.get("cache");
            SourceBinding.QueryCacheConfig cache = new SourceBinding.QueryCacheConfig();
            cache.setEnabled((Boolean) cacheData.getOrDefault("enabled", false));
            cache.setTtlSeconds((Integer) cacheData.getOrDefault("ttl_seconds", 300));
            cache.setRefreshIntervalSeconds((Integer) cacheData.getOrDefault("refresh_interval_seconds", 60));
            cache.setRefreshOnStartup((Boolean) cacheData.getOrDefault("refresh_on_startup", false));
            binding.setCache(cache);
        }

        return binding;
    }

    @SuppressWarnings("unchecked")
    private static AccessPolicy parseAccessPolicy(Map<String, Object> data) {
        AccessPolicy policy = new AccessPolicy();

        if (data.containsKey("required_segments")) {
            policy.setRequiredSegments((List<Integer>) data.get("required_segments"));
        }

        policy.setMinFilters((Integer) data.getOrDefault("min_filters", 0));

        if (data.containsKey("blocked_patterns")) {
            policy.setBlockedPatterns((List<String>) data.get("blocked_patterns"));
        }

        policy.setMaxRowsWarn((Integer) data.get("max_rows_warn"));
        policy.setMaxRowsBlock((Integer) data.get("max_rows_block"));

        if (data.containsKey("cardinality_multipliers")) {
            policy.setCardinalityMultipliers((List<Integer>) data.get("cardinality_multipliers"));
        }

        policy.setBaseRowCount((Integer) data.getOrDefault("base_row_count", 100));
        policy.setRequireConfirmationAbove((Integer) data.get("require_confirmation_above"));
        policy.setDenialMessage((String) data.get("denial_message"));

        if (data.containsKey("allowed_roles")) {
            policy.setAllowedRoles((List<String>) data.get("allowed_roles"));
        }

        if (data.containsKey("allowed_hours")) {
            List<Integer> hours = (List<Integer>) data.get("allowed_hours");
            if (hours != null && hours.size() == 2) {
                policy.setAllowedHours(new int[]{hours.get(0), hours.get(1)});
            }
        }

        return policy;
    }
}
