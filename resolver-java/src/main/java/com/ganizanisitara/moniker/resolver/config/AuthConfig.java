package com.ganizanisitara.moniker.resolver.config;

import lombok.Data;
import java.util.ArrayList;
import java.util.List;

/**
 * Authentication configuration.
 */
@Data
public class AuthConfig {
    private boolean enabled = false;
    private boolean enforce = false;
    private List<String> methodOrder = new ArrayList<>();
}
