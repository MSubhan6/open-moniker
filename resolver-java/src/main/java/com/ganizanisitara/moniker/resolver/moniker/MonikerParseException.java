package com.ganizanisitara.moniker.resolver.moniker;

/**
 * Exception raised when a moniker string cannot be parsed.
 */
public class MonikerParseException extends Exception {
    public MonikerParseException(String message) {
        super(message);
    }

    public MonikerParseException(String message, Throwable cause) {
        super(message, cause);
    }
}
