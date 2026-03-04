package com.ganizanisitara.moniker.resolver.catalog;

import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Binding to an actual data source.
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class SourceBinding {
    private SourceType type;
    private Map<String, Object> config = new HashMap<>();
    private List<String> allowedOperations;
    private Map<String, Object> schema;
    private boolean readOnly = true;
    private QueryCacheConfig cache;

    /**
     * Generate SHA-256 fingerprint of the binding contract.
     */
    public String fingerprint() {
        try {
            Map<String, Object> data = new HashMap<>();
            data.put("source_type", type.toString());
            data.put("config", config);
            data.put("allowed_operations", allowedOperations);
            data.put("schema", schema);
            data.put("read_only", readOnly);

            ObjectMapper mapper = new ObjectMapper();
            String json = mapper.writeValueAsString(data);

            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(json.getBytes(StandardCharsets.UTF_8));

            // Return first 16 hex chars (8 bytes)
            StringBuilder hexString = new StringBuilder();
            for (int i = 0; i < 8 && i < hash.length; i++) {
                String hex = Integer.toHexString(0xff & hash[i]);
                if (hex.length() == 1) hexString.append('0');
                hexString.append(hex);
            }
            return hexString.toString();
        } catch (Exception e) {
            return "error";
        }
    }

    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    public static class QueryCacheConfig {
        private boolean enabled = false;
        private int ttlSeconds = 300;
        private int refreshIntervalSeconds = 60;
        private boolean refreshOnStartup = false;
    }
}
