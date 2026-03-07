package com.ganizanisitara.moniker.resolver.config;

import lombok.Data;
import java.util.HashMap;
import java.util.Map;

/**
 * Configuration for data assurance tiers.
 *
 * Defines configurable labels for data quality tiers (1, 2, 3).
 * Different installations can use their own terminology.
 */
@Data
public class AssuranceTiersConfig {
    private boolean enabled = true;
    private int defaultTier = 1;
    private Map<Integer, String> labels;

    public AssuranceTiersConfig() {
        // Default labels: bronze, silver, gold
        labels = new HashMap<>();
        labels.put(1, "bronze");
        labels.put(2, "silver");
        labels.put(3, "gold");
    }

    /**
     * Get the label for a tier.
     * @param tier The tier number (1, 2, or 3)
     * @return The label string, or null if not found
     */
    public String getLabel(int tier) {
        return labels.get(tier);
    }
}
