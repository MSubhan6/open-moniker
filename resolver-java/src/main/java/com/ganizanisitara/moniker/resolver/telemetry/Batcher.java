package com.ganizanisitara.moniker.resolver.telemetry;

import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/**
 * Batches telemetry events and flushes them periodically or when batch size is reached.
 */
@Slf4j
public class Batcher {
    private final List<UsageEvent> buffer;
    private final Sink sink;
    private final int batchSize;
    private final long flushIntervalMs;
    private final ScheduledExecutorService scheduler;

    public Batcher(Sink sink, int batchSize, double flushIntervalSeconds) {
        this.sink = sink;
        this.batchSize = batchSize;
        this.flushIntervalMs = (long) (flushIntervalSeconds * 1000);
        this.buffer = new ArrayList<>(batchSize);
        this.scheduler = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, "telemetry-batcher");
            t.setDaemon(true);
            return t;
        });
    }

    @PostConstruct
    public void start() {
        // Schedule periodic flush
        scheduler.scheduleAtFixedRate(
            this::flush,
            flushIntervalMs,
            flushIntervalMs,
            TimeUnit.MILLISECONDS
        );
        log.info("Telemetry batcher started (batch size: {}, flush interval: {}ms)",
                 batchSize, flushIntervalMs);
    }

    /**
     * Add an event to the batch.
     * Flushes immediately if batch size is reached.
     */
    public synchronized void add(UsageEvent event) {
        buffer.add(event);

        if (buffer.size() >= batchSize) {
            flush();
        }
    }

    /**
     * Flush current batch to the sink.
     */
    public synchronized void flush() {
        if (buffer.isEmpty()) {
            return;
        }

        List<UsageEvent> toFlush = new ArrayList<>(buffer);
        buffer.clear();

        try {
            sink.write(toFlush);
            log.debug("Flushed {} telemetry events", toFlush.size());
        } catch (Exception e) {
            log.error("Failed to flush {} telemetry events", toFlush.size(), e);
        }
    }

    /**
     * Get current buffer size.
     */
    public synchronized int getBufferSize() {
        return buffer.size();
    }

    @PreDestroy
    public void shutdown() {
        log.info("Shutting down telemetry batcher...");

        scheduler.shutdown();
        try {
            if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
                scheduler.shutdownNow();
            }
        } catch (InterruptedException e) {
            scheduler.shutdownNow();
            Thread.currentThread().interrupt();
        }

        // Final flush
        flush();
        log.info("Telemetry batcher shutdown complete");
    }
}
