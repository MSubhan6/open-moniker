package com.ganizanisitara.moniker.resolver.config;

import lombok.Data;

/**
 * Server configuration.
 */
@Data
public class ServerConfig {
    private String host = "0.0.0.0";
    private int port = 8054;
}
