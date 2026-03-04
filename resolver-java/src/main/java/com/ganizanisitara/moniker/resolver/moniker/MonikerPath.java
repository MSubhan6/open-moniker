package com.ganizanisitara.moniker.resolver.moniker;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/**
 * Represents a hierarchical path to a data asset.
 */
public class MonikerPath {
    private final List<String> segments;

    public MonikerPath(List<String> segments) {
        this.segments = Collections.unmodifiableList(new ArrayList<>(segments));
    }

    public MonikerPath(String... segments) {
        this(Arrays.asList(segments));
    }

    /**
     * Create a root path (empty path).
     */
    public static MonikerPath root() {
        return new MonikerPath(Collections.emptyList());
    }

    /**
     * Parse a path string into a MonikerPath.
     */
    public static MonikerPath fromString(String pathStr) {
        if (pathStr == null || pathStr.isEmpty() || pathStr.equals("/")) {
            return root();
        }
        // Strip leading/trailing slashes
        String clean = pathStr.replaceAll("^/+|/+$", "");
        if (clean.isEmpty()) {
            return root();
        }
        return new MonikerPath(Arrays.asList(clean.split("/")));
    }

    /**
     * Get the segments as an immutable list.
     */
    public List<String> getSegments() {
        return segments;
    }

    /**
     * Get path as a slash-separated string.
     */
    @Override
    public String toString() {
        return String.join("/", segments);
    }

    /**
     * Get the number of segments.
     */
    public int length() {
        return segments.size();
    }

    /**
     * Check if the path is empty (root).
     */
    public boolean isEmpty() {
        return segments.isEmpty();
    }

    /**
     * Get the first segment (the data domain).
     */
    public String domain() {
        return segments.isEmpty() ? null : segments.get(0);
    }

    /**
     * Get the parent path, or null if at root.
     */
    public MonikerPath parent() {
        if (segments.size() <= 1) {
            return null;
        }
        return new MonikerPath(segments.subList(0, segments.size() - 1));
    }

    /**
     * Get the final segment of the path.
     */
    public String leaf() {
        return segments.isEmpty() ? null : segments.get(segments.size() - 1);
    }

    /**
     * Get all ancestor paths from root to parent (not including self).
     */
    public List<MonikerPath> ancestors() {
        List<MonikerPath> result = new ArrayList<>();
        for (int i = 1; i < segments.size(); i++) {
            result.add(new MonikerPath(segments.subList(0, i)));
        }
        return result;
    }

    /**
     * Create a child path by appending a segment.
     */
    public MonikerPath child(String segment) {
        List<String> newSegments = new ArrayList<>(segments);
        newSegments.add(segment);
        return new MonikerPath(newSegments);
    }

    /**
     * Check if this path is an ancestor of another.
     */
    public boolean isAncestorOf(MonikerPath other) {
        if (this.segments.size() >= other.segments.size()) {
            return false;
        }
        for (int i = 0; i < this.segments.size(); i++) {
            if (!this.segments.get(i).equals(other.segments.get(i))) {
                return false;
            }
        }
        return true;
    }

    /**
     * Check if this path is a descendant of another.
     */
    public boolean isDescendantOf(MonikerPath other) {
        return other.isAncestorOf(this);
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        MonikerPath that = (MonikerPath) o;
        return Objects.equals(segments, that.segments);
    }

    @Override
    public int hashCode() {
        return Objects.hash(segments);
    }
}
