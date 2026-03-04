package com.ganizanisitara.moniker.resolver.moniker;

import java.util.HashMap;
import java.util.Map;

/**
 * Holds query parameters for a moniker.
 */
public class QueryParams {
    private final Map<String, String> params;

    public QueryParams() {
        this.params = new HashMap<>();
    }

    public QueryParams(Map<String, String> params) {
        this.params = new HashMap<>(params);
    }

    /**
     * Get a parameter value or return a default.
     */
    public String get(String key, String defaultVal) {
        return params.getOrDefault(key, defaultVal);
    }

    /**
     * Get a parameter value or return null.
     */
    public String get(String key) {
        return params.get(key);
    }

    /**
     * Check if a parameter exists.
     */
    public boolean has(String key) {
        return params.containsKey(key);
    }

    /**
     * Check if there are no parameters.
     */
    public boolean isEmpty() {
        return params.isEmpty();
    }

    /**
     * Put a parameter.
     */
    public void put(String key, String value) {
        params.put(key, value);
    }

    /**
     * Get all parameters as a map.
     */
    public Map<String, String> asMap() {
        return new HashMap<>(params);
    }

    /**
     * Get the number of parameters.
     */
    public int size() {
        return params.size();
    }
}
