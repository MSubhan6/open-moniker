package com.ganizanisitara.moniker.resolver.moniker;

import java.io.UnsupportedEncodingException;
import java.net.URLDecoder;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Parser for moniker strings.
 *
 * Format: [namespace@]path/segments[@version][/sub.resource][/vN][?query=params]
 *
 * Examples:
 *   - indices.sovereign/developed/EUR/ALL
 *   - commodities.derivatives/crypto/ETH@20260115/v2
 *   - verified@reference.security/ISIN/US0378331005@latest
 *   - user@analytics.risk/views/my-watchlist@20260115/v3
 *   - securities/012345678@20260101/details
 *   - securities/012345678@20260101/details.corporate.actions
 *   - prices.equity/AAPL@3M (3-month lookback)
 *   - risk.cvar/portfolio-123@all (full time series)
 *   - moniker://holdings/20260115/fund_alpha?format=json
 */
public class MonikerParser {

    // Validation patterns
    private static final Pattern SEGMENT_PATTERN = Pattern.compile("^[a-zA-Z0-9][a-zA-Z0-9_.\\-]*$");
    private static final Pattern NAMESPACE_PATTERN = Pattern.compile("^[a-zA-Z][a-zA-Z0-9_\\-]*$");
    private static final Pattern VERSION_PATTERN = Pattern.compile("^[a-zA-Z0-9]+$");

    // Version classification patterns
    private static final Pattern DATE_VERSION_PATTERN = Pattern.compile("^\\d{8}$");
    private static final Pattern LOOKBACK_VERSION_PATTERN = Pattern.compile("^\\d+[YMWD]$", Pattern.CASE_INSENSITIVE);
    private static final Pattern FREQUENCY_VERSION_PATTERN = Pattern.compile("^(daily|weekly|monthly)$", Pattern.CASE_INSENSITIVE);
    private static final Pattern KEYWORD_VERSION_PATTERN = Pattern.compile("^(latest|all)$", Pattern.CASE_INSENSITIVE);

    // Max lengths
    private static final int MAX_SEGMENT_LENGTH = 128;
    private static final int MAX_NAMESPACE_LENGTH = 64;

    /**
     * Classify the semantic type of a version string.
     */
    public static VersionType classifyVersion(String version) {
        if (version == null || version.isEmpty()) {
            return null;
        }
        if (DATE_VERSION_PATTERN.matcher(version).matches()) {
            return VersionType.DATE;
        }
        if (LOOKBACK_VERSION_PATTERN.matcher(version).matches()) {
            return VersionType.LOOKBACK;
        }
        if (FREQUENCY_VERSION_PATTERN.matcher(version).matches()) {
            return VersionType.FREQUENCY;
        }
        if (KEYWORD_VERSION_PATTERN.matcher(version).matches()) {
            String versionLower = version.toLowerCase();
            if (versionLower.equals("latest")) {
                return VersionType.LATEST;
            } else if (versionLower.equals("all")) {
                return VersionType.ALL;
            }
        }
        return VersionType.CUSTOM;
    }

    /**
     * Validate a path segment.
     */
    public static boolean validateSegment(String segment) {
        if (segment == null || segment.isEmpty()) {
            return false;
        }
        if (segment.length() > MAX_SEGMENT_LENGTH) {
            return false;
        }
        return SEGMENT_PATTERN.matcher(segment).matches();
    }

    /**
     * Validate a namespace.
     */
    public static boolean validateNamespace(String namespace) {
        if (namespace == null || namespace.isEmpty()) {
            return false;
        }
        if (namespace.length() > MAX_NAMESPACE_LENGTH) {
            return false;
        }
        return NAMESPACE_PATTERN.matcher(namespace).matches();
    }

    /**
     * Parse a path string into a MonikerPath.
     */
    public static MonikerPath parsePath(String pathStr, boolean validate) throws MonikerParseException {
        if (pathStr == null || pathStr.isEmpty() || pathStr.equals("/")) {
            return MonikerPath.root();
        }

        // Strip leading/trailing slashes
        String clean = pathStr.replaceAll("^/+|/+$", "");
        if (clean.isEmpty()) {
            return MonikerPath.root();
        }

        String[] segments = clean.split("/");

        if (validate) {
            for (String seg : segments) {
                if (!validateSegment(seg)) {
                    throw new MonikerParseException(
                        String.format("Invalid path segment: '%s'. Segments must start with " +
                                     "alphanumeric and contain only alphanumerics, hyphens, underscores, or dots.", seg)
                    );
                }
            }
        }

        return new MonikerPath(Arrays.asList(segments));
    }

    /**
     * Parse a full moniker string.
     */
    public static Moniker parse(String monikerStr, boolean validate) throws MonikerParseException {
        if (monikerStr == null || monikerStr.isEmpty()) {
            throw new MonikerParseException("Empty moniker string");
        }

        monikerStr = monikerStr.trim();

        String body;
        String queryStr = null;

        // Handle scheme
        if (monikerStr.startsWith("moniker://")) {
            // Parse as URL
            try {
                int queryIndex = monikerStr.indexOf('?');
                if (queryIndex != -1) {
                    body = monikerStr.substring(10, queryIndex); // Skip "moniker://"
                    queryStr = monikerStr.substring(queryIndex + 1);
                } else {
                    body = monikerStr.substring(10);
                }
            } catch (Exception e) {
                throw new MonikerParseException("Invalid URL: " + e.getMessage(), e);
            }
        } else if (monikerStr.contains("://")) {
            throw new MonikerParseException(
                "Invalid scheme. Expected 'moniker://' or no scheme, got: " + monikerStr
            );
        } else {
            // No scheme - check for query string
            int queryIndex = monikerStr.indexOf('?');
            if (queryIndex != -1) {
                body = monikerStr.substring(0, queryIndex);
                queryStr = monikerStr.substring(queryIndex + 1);
            } else {
                body = monikerStr;
            }
        }

        // Parse namespace (prefix before first @, but only if @ appears before first /)
        String namespace = null;
        String remaining = body;

        int firstAt = body.indexOf('@');
        int firstSlash = body.indexOf('/');

        if (firstAt != -1 && (firstSlash == -1 || firstAt < firstSlash)) {
            // This @ is a namespace prefix
            namespace = body.substring(0, firstAt);
            remaining = body.substring(firstAt + 1);

            if (validate && !validateNamespace(namespace)) {
                throw new MonikerParseException(
                    String.format("Invalid namespace: '%s'. Namespace must start with a letter " +
                                 "and contain only alphanumerics, hyphens, or underscores.", namespace)
                );
            }
        }

        // Parse revision suffix (/vN or /VN at the end - case-insensitive)
        Integer revision = null;
        String remainingLower = remaining.toLowerCase();
        int lastVIndex = remainingLower.lastIndexOf("/v");
        if (lastVIndex != -1) {
            String before = remaining.substring(0, lastVIndex);
            String after = remaining.substring(lastVIndex + 2); // Skip "/v"

            // Check if it's a valid revision (just digits at the end or before ?)
            Pattern revPattern = Pattern.compile("^(\\d+)(?:$|(?=\\?))");
            Matcher matcher = revPattern.matcher(after);
            if (matcher.find()) {
                revision = Integer.parseInt(matcher.group(1));
                remaining = before;
            }
        }

        // Parse version suffix with optional sub-resource: @version[/sub.resource]
        String version = null;
        String subResource = null;
        int atIdx = remaining.lastIndexOf('@');

        if (atIdx != -1) {
            int firstSlashInRemaining = remaining.indexOf('/');

            // Check if this @ is after the first slash (making it a version, not namespace)
            boolean isVersionAt = false;
            if (namespace != null) {
                // Namespace already extracted, any @ is a version
                isVersionAt = true;
            } else {
                // No namespace yet - @ is version only if after first /
                isVersionAt = (firstSlashInRemaining == -1 || atIdx > firstSlashInRemaining);
            }

            if (isVersionAt) {
                // Everything before @ is the path
                String pathPart = remaining.substring(0, atIdx);
                String afterAt = remaining.substring(atIdx + 1);

                // Check if there's a sub-resource (path after version)
                int slashIdx = afterAt.indexOf('/');
                if (slashIdx != -1) {
                    version = afterAt.substring(0, slashIdx);
                    subResource = afterAt.substring(slashIdx + 1);
                } else {
                    version = afterAt;
                }

                remaining = pathPart;

                if (validate && version != null && !VERSION_PATTERN.matcher(version).matches()) {
                    throw new MonikerParseException(
                        String.format("Invalid version: '%s'. Version must be alphanumeric " +
                                     "(e.g., 'latest', '20260115', '3M').", version)
                    );
                }

                // Validate sub_resource segments if present
                if (validate && subResource != null) {
                    // Sub-resource uses dots for multi-level: details.corporate.actions
                    for (String part : subResource.split("\\.")) {
                        if (!validateSegment(part)) {
                            throw new MonikerParseException(
                                String.format("Invalid sub-resource segment: '%s'. " +
                                             "Sub-resource parts must start with alphanumeric.", part)
                            );
                        }
                    }
                }
            }
        }

        // Parse path
        MonikerPath path = parsePath(remaining, validate);

        // Parse query params
        QueryParams params = new QueryParams();
        if (queryStr != null && !queryStr.isEmpty()) {
            for (String pair : queryStr.split("&")) {
                int eqIdx = pair.indexOf('=');
                if (eqIdx != -1) {
                    try {
                        String key = URLDecoder.decode(pair.substring(0, eqIdx), "UTF-8");
                        String value = URLDecoder.decode(pair.substring(eqIdx + 1), "UTF-8");
                        params.put(key, value);
                    } catch (UnsupportedEncodingException e) {
                        // UTF-8 is always supported
                    }
                } else {
                    try {
                        params.put(URLDecoder.decode(pair, "UTF-8"), "");
                    } catch (UnsupportedEncodingException e) {
                        // UTF-8 is always supported
                    }
                }
            }
        }

        // Classify version type
        VersionType versionType = version != null ? classifyVersion(version) : null;

        return new Moniker(path, namespace, version, versionType, subResource, revision, params);
    }

    /**
     * Parse a moniker with validation enabled.
     */
    public static Moniker parseMoniker(String monikerStr) throws MonikerParseException {
        return parse(monikerStr, true);
    }

    /**
     * Normalize a moniker string to canonical form.
     */
    public static String normalizeMoniker(String monikerStr) throws MonikerParseException {
        Moniker m = parseMoniker(monikerStr);
        return m.toString();
    }

    /**
     * Build a moniker from components.
     */
    public static Moniker buildMoniker(String pathStr, String namespace, String version,
                                      VersionType versionType, String subResource,
                                      Integer revision, QueryParams params) throws MonikerParseException {
        MonikerPath path = parsePath(pathStr, true);

        // Auto-classify version if not explicitly provided
        VersionType effectiveVersionType = versionType;
        if (effectiveVersionType == null && version != null) {
            effectiveVersionType = classifyVersion(version);
        }

        if (params == null) {
            params = new QueryParams();
        }

        return new Moniker(path, namespace, version, effectiveVersionType, subResource, revision, params);
    }
}
