package com.ganizanisitara.moniker.resolver.catalog;

import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;

/**
 * Access policy for controlling query patterns.
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class AccessPolicy {
    private List<Integer> requiredSegments = new ArrayList<>();
    private int minFilters = 0;
    private List<String> blockedPatterns = new ArrayList<>();
    private Integer maxRowsWarn;
    private Integer maxRowsBlock;
    private List<Integer> cardinalityMultipliers = new ArrayList<>();
    private int baseRowCount = 100;
    private Integer requireConfirmationAbove;
    private String denialMessage;
    private List<String> allowedRoles = new ArrayList<>();
    private int[] allowedHours; // [start_hour, end_hour] in UTC

    /**
     * Estimate the number of rows that would be returned based on segment values.
     */
    public int estimateRows(List<String> segments) {
        int multiplier = 1;
        for (int i = 0; i < segments.size(); i++) {
            if ("ALL".equalsIgnoreCase(segments.get(i))) {
                if (i < cardinalityMultipliers.size()) {
                    multiplier *= cardinalityMultipliers.get(i);
                } else {
                    multiplier *= 100; // Default multiplier
                }
            }
        }
        int base = baseRowCount > 0 ? baseRowCount : 100;
        return base * multiplier;
    }

    /**
     * Validate if a query pattern is allowed.
     * Returns [is_allowed, error_message, estimated_rows]
     */
    public ValidationResult validate(List<String> segments) {
        String path = String.join("/", segments);
        int estimatedRows = estimateRows(segments);

        // Check blocked patterns
        for (String patternStr : blockedPatterns) {
            Pattern pattern = Pattern.compile(patternStr, Pattern.CASE_INSENSITIVE);
            if (pattern.matcher(path).find()) {
                String msg = denialMessage != null ? denialMessage
                           : String.format("Query pattern '%s' is blocked by access policy", path);
                return new ValidationResult(false, msg, estimatedRows);
            }
        }

        // Check required segments
        for (int idx : requiredSegments) {
            if (idx < segments.size() && "ALL".equalsIgnoreCase(segments.get(idx))) {
                String msg = String.format("Access policy requires segment %d to be specified (cannot use ALL)", idx);
                return new ValidationResult(false, msg, estimatedRows);
            }
        }

        // Check minimum filters
        if (minFilters > 0) {
            long nonAllCount = segments.stream()
                .filter(s -> !"ALL".equalsIgnoreCase(s))
                .count();
            if (nonAllCount < minFilters) {
                String msg = String.format("Access policy requires at least %d specific filters, but only %d provided",
                    minFilters, nonAllCount);
                return new ValidationResult(false, msg, estimatedRows);
            }
        }

        // Check row limits
        if (maxRowsBlock != null && estimatedRows > maxRowsBlock) {
            String msg = denialMessage != null ? denialMessage
                       : String.format("Query would return ~%d rows, exceeding limit of %d. " +
                                      "Add more specific filters to reduce result size.",
                                      estimatedRows, maxRowsBlock);
            return new ValidationResult(false, msg, estimatedRows);
        }

        // Warning for large queries (but allowed)
        String warning = null;
        if (maxRowsWarn != null && estimatedRows > maxRowsWarn) {
            warning = String.format("Large query: estimated %d rows", estimatedRows);
        }

        return new ValidationResult(true, warning, estimatedRows);
    }

    /**
     * Result of access policy validation.
     */
    @Data
    @AllArgsConstructor
    public static class ValidationResult {
        private boolean allowed;
        private String message; // Error message or warning
        private int estimatedRows;
    }
}
