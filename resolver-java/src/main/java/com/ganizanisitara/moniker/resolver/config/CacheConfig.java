package com.ganizanisitara.moniker.resolver.config;

import lombok.Data;

/**
 * Cache configuration.
 */
@Data
public class CacheConfig {
    private boolean enabled = true;
    private int maxSize = 10000;
    private int defaultTtlSeconds = 300;
}
