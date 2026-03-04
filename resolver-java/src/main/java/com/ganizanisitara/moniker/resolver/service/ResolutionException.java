package com.ganizanisitara.moniker.resolver.service;

/**
 * Exception during moniker resolution.
 */
public class ResolutionException extends Exception {
    private final int statusCode;

    public ResolutionException(String message, int statusCode) {
        super(message);
        this.statusCode = statusCode;
    }

    public ResolutionException(String message, int statusCode, Throwable cause) {
        super(message, cause);
        this.statusCode = statusCode;
    }

    public int getStatusCode() {
        return statusCode;
    }
}
