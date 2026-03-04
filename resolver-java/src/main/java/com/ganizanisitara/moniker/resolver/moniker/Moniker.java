package com.ganizanisitara.moniker.resolver.moniker;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Represents a complete moniker reference.
 */
public class Moniker {
    private final MonikerPath path;
    private final String namespace;
    private final String version;
    private final VersionType versionType;
    private final String subResource;
    private final Integer revision;
    private final QueryParams params;

    public Moniker(MonikerPath path, String namespace, String version, VersionType versionType,
                   String subResource, Integer revision, QueryParams params) {
        this.path = path;
        this.namespace = namespace;
        this.version = version;
        this.versionType = versionType;
        this.subResource = subResource;
        this.revision = revision;
        this.params = params != null ? params : new QueryParams();
    }

    /**
     * Get the canonical moniker string.
     */
    @Override
    public String toString() {
        StringBuilder sb = new StringBuilder();

        // Namespace prefix
        if (namespace != null) {
            sb.append(namespace).append("@");
        }

        // Path
        sb.append(path.toString());

        // Version suffix
        if (version != null) {
            sb.append("@").append(version);
        }

        // Sub-resource (after version, before revision)
        if (subResource != null) {
            sb.append("/").append(subResource);
        }

        // Revision suffix
        if (revision != null) {
            sb.append("/v").append(revision);
        }

        String base = sb.toString();

        // Query params
        if (!params.isEmpty()) {
            List<String> paramParts = new ArrayList<>();
            for (Map.Entry<String, String> entry : params.asMap().entrySet()) {
                paramParts.add(entry.getKey() + "=" + entry.getValue());
            }
            return "moniker://" + base + "?" + String.join("&", paramParts);
        }

        return "moniker://" + base;
    }

    /**
     * Get the data domain (first path segment).
     */
    public String domain() {
        return path.domain();
    }

    /**
     * Get the path as a string (without namespace, version, or params).
     */
    public String canonicalPath() {
        return path.toString();
    }

    /**
     * Get full path including version, sub-resource, and revision but not namespace.
     */
    public String fullPath() {
        StringBuilder sb = new StringBuilder(path.toString());
        if (version != null) {
            sb.append("@").append(version);
        }
        if (subResource != null) {
            sb.append("/").append(subResource);
        }
        if (revision != null) {
            sb.append("/v").append(revision);
        }
        return sb.toString();
    }

    /**
     * Check if the moniker has a version specifier.
     */
    public boolean isVersioned() {
        return version != null;
    }

    /**
     * Check if the moniker explicitly requests latest version.
     */
    public boolean isLatest() {
        return version != null && version.equalsIgnoreCase("latest");
    }

    /**
     * Check if the moniker requests the full time series.
     */
    public boolean isAll() {
        return versionType == VersionType.ALL;
    }

    /**
     * Extract date from version if it's a date format (YYYYMMDD).
     */
    public String versionDate() {
        if (versionType == VersionType.DATE) {
            return version;
        }
        // Fallback for backwards compatibility
        if (version != null && version.length() == 8 && version.matches("\\d{8}")) {
            return version;
        }
        return null;
    }

    /**
     * Extract lookback components if version is a lookback period.
     * Returns an array [value, unit] where unit is Y/M/W/D, or null if not a lookback.
     */
    public String[] versionLookback() {
        if (versionType == VersionType.LOOKBACK && version != null) {
            Pattern pattern = Pattern.compile("^(\\d+)([YMWD])$", Pattern.CASE_INSENSITIVE);
            Matcher matcher = pattern.matcher(version.toUpperCase());
            if (matcher.matches()) {
                return new String[]{matcher.group(1), matcher.group(2)};
            }
        }
        return null;
    }

    /**
     * Extract frequency if version is a frequency specifier.
     * Returns frequency string (daily, weekly, monthly) or null.
     */
    public String versionFrequency() {
        if (versionType == VersionType.FREQUENCY && version != null) {
            return version.toLowerCase();
        }
        return null;
    }

    /**
     * Create a copy with a different version.
     */
    public Moniker withVersion(String version, VersionType versionType) {
        return new Moniker(path, namespace, version, versionType, subResource, revision, params);
    }

    /**
     * Create a copy with a different namespace.
     */
    public Moniker withNamespace(String namespace) {
        return new Moniker(path, namespace, version, versionType, subResource, revision, params);
    }

    /**
     * Create a copy with a different sub-resource.
     */
    public Moniker withSubResource(String subResource) {
        return new Moniker(path, namespace, version, versionType, subResource, revision, params);
    }

    // Getters
    public MonikerPath getPath() {
        return path;
    }

    public String getNamespace() {
        return namespace;
    }

    public String getVersion() {
        return version;
    }

    public VersionType getVersionType() {
        return versionType;
    }

    public String getSubResource() {
        return subResource;
    }

    public Integer getRevision() {
        return revision;
    }

    public QueryParams getParams() {
        return params;
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        Moniker moniker = (Moniker) o;
        return Objects.equals(path, moniker.path) &&
                Objects.equals(namespace, moniker.namespace) &&
                Objects.equals(version, moniker.version) &&
                versionType == moniker.versionType &&
                Objects.equals(subResource, moniker.subResource) &&
                Objects.equals(revision, moniker.revision);
    }

    @Override
    public int hashCode() {
        return Objects.hash(path, namespace, version, versionType, subResource, revision);
    }
}
