package com.ganizanisitara.moniker.resolver.telemetry.factory;

import com.ganizanisitara.moniker.resolver.config.ApplicationConfig;
import com.ganizanisitara.moniker.resolver.config.TelemetryConfig;
import com.ganizanisitara.moniker.resolver.telemetry.Batcher;
import com.ganizanisitara.moniker.resolver.telemetry.Emitter;
import com.ganizanisitara.moniker.resolver.telemetry.Sink;
import com.ganizanisitara.moniker.resolver.telemetry.TelemetryHelper;
import com.ganizanisitara.moniker.resolver.telemetry.sinks.ConsoleSink;
import com.ganizanisitara.moniker.resolver.telemetry.sinks.PostgresSink;
import com.ganizanisitara.moniker.resolver.telemetry.sinks.SQLiteSink;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.sql.SQLException;
import java.util.Map;

/**
 * Factory for creating telemetry components based on configuration.
 */
@Slf4j
@Configuration
public class TelemetryFactory {

    @Bean
    @ConditionalOnProperty(name = "moniker.telemetry.enabled", havingValue = "true", matchIfMissing = false)
    public Sink telemetrySink(ApplicationConfig appConfig) {
        TelemetryConfig config = appConfig.getTelemetry();
        String sinkType = config.getSinkType();
        Map<String, Object> sinkConfig = config.getSinkConfig();

        log.info("Creating telemetry sink of type: {}", sinkType);

        Sink sink = switch (sinkType.toLowerCase()) {
            case "console" -> new ConsoleSink();
            case "sqlite" -> {
                try {
                    yield new SQLiteSink(sinkConfig);
                } catch (SQLException e) {
                    log.error("Failed to create SQLite sink, falling back to console", e);
                    yield new ConsoleSink();
                }
            }
            case "postgres", "postgresql" -> new PostgresSink(sinkConfig);
            default -> {
                log.warn("Unknown sink type '{}', falling back to console", sinkType);
                yield new ConsoleSink();
            }
        };

        sink.initialize();
        return sink;
    }

    @Bean
    @ConditionalOnProperty(name = "moniker.telemetry.enabled", havingValue = "true", matchIfMissing = false)
    public Batcher telemetryBatcher(Sink sink, ApplicationConfig appConfig) {
        TelemetryConfig config = appConfig.getTelemetry();
        Batcher batcher = new Batcher(
            sink,
            config.getBatchSize(),
            config.getFlushIntervalSeconds()
        );
        return batcher;
    }

    @Bean
    @ConditionalOnProperty(name = "moniker.telemetry.enabled", havingValue = "true", matchIfMissing = false)
    public Emitter telemetryEmitter(Batcher batcher, ApplicationConfig appConfig) {
        TelemetryConfig config = appConfig.getTelemetry();
        Emitter emitter = new Emitter(batcher, config.getMaxQueueSize());
        return emitter;
    }

    /**
     * No-op emitter when telemetry is disabled.
     */
    @Bean
    @ConditionalOnProperty(name = "moniker.telemetry.enabled", havingValue = "false", matchIfMissing = true)
    public Emitter disabledEmitter() {
        log.info("Telemetry is disabled, using no-op emitter");
        return new NoOpEmitter();
    }

    @Bean
    @ConditionalOnProperty(name = "moniker.telemetry.enabled", havingValue = "false", matchIfMissing = true)
    public TelemetryHelper disabledTelemetryHelper(Emitter emitter) {
        return new TelemetryHelper(emitter, "disabled", "local", "local");
    }

    /**
     * No-op emitter that does nothing.
     */
    private static class NoOpEmitter extends Emitter {
        public NoOpEmitter() {
            super(createNoOpBatcher(), 1);
        }

        private static Batcher createNoOpBatcher() {
            return new Batcher(events -> {}, 1, 1.0);
        }

        @Override
        public void emit(com.ganizanisitara.moniker.resolver.telemetry.UsageEvent event) {
            // No-op
        }

        @Override
        public void shutdown() {
            // No-op
        }
    }
}
