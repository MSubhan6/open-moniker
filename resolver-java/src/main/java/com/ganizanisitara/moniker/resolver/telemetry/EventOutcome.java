package com.ganizanisitara.moniker.resolver.telemetry;

/**
 * Outcome of a telemetry event.
 */
public enum EventOutcome {
    SUCCESS,
    NOT_FOUND,
    UNAUTHORIZED,
    FORBIDDEN,
    VALIDATION_ERROR,
    ERROR,
    TIMEOUT
}
