package com.ganizanisitara.moniker.resolver.telemetry;

import java.util.List;

/**
 * Interface for telemetry sinks (destinations for events).
 */
public interface Sink {
    /**
     * Write a batch of events to the sink.
     *
     * @param events The events to write
     */
    void write(List<UsageEvent> events);

    /**
     * Initialize the sink (create tables, connections, etc.).
     */
    default void initialize() {
        // Default no-op
    }

    /**
     * Close the sink and release resources.
     */
    default void close() {
        // Default no-op
    }
}
