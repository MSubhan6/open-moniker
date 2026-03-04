package com.ganizanisitara.moniker.resolver.catalog;

/**
 * Supported data source types.
 */
public enum SourceType {
    SNOWFLAKE("snowflake"),
    ORACLE("oracle"),
    MSSQL("mssql"),               // Microsoft SQL Server
    REST("rest"),
    STATIC("static"),
    EXCEL("excel"),
    BLOOMBERG("bloomberg"),
    REFINITIV("refinitiv"),
    OPENSEARCH("opensearch"),     // OpenSearch/Elasticsearch
    COMPOSITE("composite"),       // Combines multiple sources
    DERIVED("derived");           // Computed from other monikers

    private final String value;

    SourceType(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }

    @Override
    public String toString() {
        return value;
    }

    public static SourceType fromString(String value) {
        for (SourceType type : SourceType.values()) {
            if (type.value.equalsIgnoreCase(value)) {
                return type;
            }
        }
        throw new IllegalArgumentException("Unknown source type: " + value);
    }
}
