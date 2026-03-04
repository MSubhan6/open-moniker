package com.ganizanisitara.moniker.resolver.config;

import lombok.Data;

/**
 * Config UI configuration.
 */
@Data
public class ConfigUIConfig {
    private boolean enabled = false;
    private String yamlOutputPath = "";
    private boolean showFilePaths = true;
}
