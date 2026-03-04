package com.ganizanisitara.moniker.resolver.config;

import lombok.Data;

/**
 * Catalog configuration.
 */
@Data
public class CatalogConfig {
    private String definitionFile = "../catalog.yaml";
    private int reloadIntervalSeconds = 60;
}
