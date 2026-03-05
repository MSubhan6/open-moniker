package com.ganizanisitara.moniker.resolver.telemetry.sinks;

import com.ganizanisitara.moniker.resolver.telemetry.Sink;
import com.ganizanisitara.moniker.resolver.telemetry.UsageEvent;
import lombok.extern.slf4j.Slf4j;

import java.util.List;

/**
 * Console sink - writes events to stdout (for development).
 */
@Slf4j
public class ConsoleSink implements Sink {

    @Override
    public void write(List<UsageEvent> events) {
        for (UsageEvent event : events) {
            System.out.printf("[TELEMETRY] %s | %s | %s | %s | %dms | %s%n",
                event.getTimestamp(),
                event.getResolverName(),
                event.getOperation(),
                event.getMoniker(),
                event.getLatencyMs(),
                event.getOutcome()
            );
        }
    }

    @Override
    public void initialize() {
        log.info("Console sink initialized");
    }
}
