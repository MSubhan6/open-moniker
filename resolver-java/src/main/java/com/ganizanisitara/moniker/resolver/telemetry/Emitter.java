package com.ganizanisitara.moniker.resolver.telemetry;

import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import jakarta.annotation.PreDestroy;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Non-blocking telemetry emitter using a background thread and queue.
 */
@Slf4j
public class Emitter {
    private final BlockingQueue<UsageEvent> queue;
    private final ExecutorService executor;
    private final Batcher batcher;
    private final AtomicLong dropCounter = new AtomicLong(0);
    private volatile boolean shutdown = false;

    public Emitter(Batcher batcher, int maxQueueSize) {
        this.batcher = batcher;
        this.queue = new ArrayBlockingQueue<>(maxQueueSize);
        this.executor = Executors.newSingleThreadExecutor(r -> {
            Thread t = new Thread(r, "telemetry-emitter");
            t.setDaemon(true);
            return t;
        });

        // Start background processing loop
        executor.submit(this::processLoop);
        log.info("Telemetry emitter started with max queue size: {}", maxQueueSize);
    }

    /**
     * Emit a telemetry event (non-blocking).
     * If the queue is full, the event is dropped and a counter is incremented.
     */
    public void emit(UsageEvent event) {
        if (shutdown) {
            return;
        }

        if (!queue.offer(event)) {
            long drops = dropCounter.incrementAndGet();
            if (drops % 100 == 0) {
                log.warn("Telemetry queue full, dropped {} events so far", drops);
            }
        }
    }

    /**
     * Background loop that processes events from the queue.
     */
    private void processLoop() {
        log.info("Telemetry processing loop started");

        while (!shutdown) {
            try {
                UsageEvent event = queue.poll(100, TimeUnit.MILLISECONDS);
                if (event != null) {
                    batcher.add(event);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                log.info("Telemetry processing loop interrupted");
                break;
            } catch (Exception e) {
                log.error("Error processing telemetry event", e);
            }
        }

        log.info("Telemetry processing loop stopped");
    }

    /**
     * Get current queue size.
     */
    public int getQueueSize() {
        return queue.size();
    }

    /**
     * Get number of dropped events.
     */
    public long getDroppedCount() {
        return dropCounter.get();
    }

    /**
     * Graceful shutdown.
     */
    @PreDestroy
    public void shutdown() {
        log.info("Shutting down telemetry emitter...");
        shutdown = true;

        executor.shutdown();
        try {
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        } catch (InterruptedException e) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }

        // Flush remaining events
        batcher.flush();

        long dropped = dropCounter.get();
        if (dropped > 0) {
            log.warn("Telemetry emitter shutdown complete. Dropped {} events total", dropped);
        } else {
            log.info("Telemetry emitter shutdown complete");
        }
    }
}
