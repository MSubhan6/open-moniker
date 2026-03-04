package com.ganizanisitara.moniker.resolver.moniker;

/**
 * Represents the semantic type of a version specifier in a moniker.
 */
public enum VersionType {
    DATE("date"),           // @20260101 (YYYYMMDD format)
    LATEST("latest"),       // @latest
    LOOKBACK("lookback"),   // @3M, @12Y, @1W, @5D (lookback period)
    FREQUENCY("frequency"), // @daily, @weekly, @monthly
    ALL("all"),             // @all (full time series)
    CUSTOM("custom");       // Source-specific version identifier

    private final String value;

    VersionType(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }

    @Override
    public String toString() {
        return value;
    }
}
