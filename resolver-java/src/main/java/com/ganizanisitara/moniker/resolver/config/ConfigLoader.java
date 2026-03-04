package com.ganizanisitara.moniker.resolver.config;

import org.yaml.snakeyaml.Yaml;
import org.yaml.snakeyaml.LoaderOptions;
import org.yaml.snakeyaml.constructor.Constructor;
import org.yaml.snakeyaml.introspector.PropertyUtils;

import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

/**
 * Loads configuration from YAML files.
 */
public class ConfigLoader {

    /**
     * Load configuration from a YAML file.
     * If configPath is null or empty, defaults to ../config.yaml
     */
    public static ApplicationConfig load(String configPath) throws IOException {
        // Default to config.yaml in current directory
        if (configPath == null || configPath.isEmpty()) {
            configPath = "config.yaml";
        }

        Path path = Paths.get(configPath);
        if (!Files.exists(path)) {
            // Try ../config.yaml
            path = Paths.get("../config.yaml");
            if (Files.exists(path)) {
                configPath = "../config.yaml";
            } else {
                // Try sample_config.yaml
                path = Paths.get("sample_config.yaml");
                if (Files.exists(path)) {
                    configPath = "sample_config.yaml";
                } else {
                    throw new IOException("Config file not found. Tried: config.yaml, ../config.yaml, sample_config.yaml");
                }
            }
        }

        try (InputStream input = new FileInputStream(path.toFile())) {
            LoaderOptions loaderOptions = new LoaderOptions();
            Constructor constructor = new Constructor(ApplicationConfig.class, loaderOptions);

            // Configure property utils to handle snake_case YAML keys
            PropertyUtils propertyUtils = new PropertyUtils();
            propertyUtils.setSkipMissingProperties(true);
            constructor.setPropertyUtils(propertyUtils);

            Yaml yaml = new Yaml(constructor);
            ApplicationConfig config = yaml.load(input);

            if (config == null) {
                throw new IOException("Empty or invalid config file: " + configPath);
            }

            return config;
        }
    }

    /**
     * Load configuration from default path.
     */
    public static ApplicationConfig loadDefault() throws IOException {
        return load(null);
    }
}
