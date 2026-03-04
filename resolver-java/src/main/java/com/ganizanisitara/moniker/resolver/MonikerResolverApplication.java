package com.ganizanisitara.moniker.resolver;

import com.ganizanisitara.moniker.resolver.catalog.CatalogLoader;
import com.ganizanisitara.moniker.resolver.catalog.CatalogRegistry;
import com.ganizanisitara.moniker.resolver.config.ApplicationConfig;
import com.ganizanisitara.moniker.resolver.config.ConfigLoader;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

import java.io.IOException;

/**
 * Main application entry point for Java Moniker Resolver.
 */
@SpringBootApplication
public class MonikerResolverApplication {

    public static void main(String[] args) {
        SpringApplication.run(MonikerResolverApplication.class, args);
    }

    /**
     * Load application configuration from YAML.
     */
    @Bean
    public ApplicationConfig applicationConfig(
            @Value("${moniker.config-file:../config.yaml}") String configFile) throws IOException {
        return ConfigLoader.load(configFile);
    }

    /**
     * Load catalog registry from YAML.
     */
    @Bean
    public CatalogRegistry catalogRegistry(ApplicationConfig config) throws IOException {
        String catalogFile = config.getCatalog().getDefinitionFile();
        if (catalogFile == null || catalogFile.isEmpty()) {
            catalogFile = "catalog.yaml";  // Default to current directory
        }

        // Try to find the file in common locations
        java.io.File file = new java.io.File(catalogFile);
        if (!file.exists()) {
            // Try parent directory
            file = new java.io.File("../" + catalogFile);
            if (file.exists()) {
                catalogFile = "../" + catalogFile;
            } else {
                // Try sample catalog
                file = new java.io.File("sample_catalog.yaml");
                if (file.exists()) {
                    catalogFile = "sample_catalog.yaml";
                }
            }
        }

        System.out.println("Loading catalog from: " + catalogFile);
        CatalogRegistry registry = CatalogLoader.loadFromFile(catalogFile);
        System.out.println("Loaded " + registry.size() + " catalog nodes");

        return registry;
    }
}
