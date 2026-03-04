package com.ganizanisitara.moniker.resolver.moniker;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

/**
 * Unit tests for MonikerParser.
 */
class MonikerParserTest {

    @Test
    void testParseSimplePath() throws MonikerParseException {
        Moniker m = MonikerParser.parseMoniker("prices.equity/AAPL");

        assertEquals("prices.equity/AAPL", m.getPath().toString());
        assertNull(m.getVersion());
        assertNull(m.getNamespace());
    }

    @Test
    void testParseWithVersion() throws MonikerParseException {
        Moniker m = MonikerParser.parseMoniker("prices.equity/AAPL@latest");

        assertEquals("prices.equity/AAPL", m.getPath().toString());
        assertEquals("latest", m.getVersion());
        assertEquals(VersionType.LATEST, m.getVersionType());
    }

    @Test
    void testParseWithNamespace() throws MonikerParseException {
        Moniker m = MonikerParser.parseMoniker("verified@reference.security/ISIN/US0378331005@latest");

        assertEquals("reference.security/ISIN/US0378331005", m.getPath().toString());
        assertEquals("latest", m.getVersion());
        assertEquals("verified", m.getNamespace());
    }

    @Test
    void testParseDateVersion() throws MonikerParseException {
        Moniker m = MonikerParser.parseMoniker("prices.equity/AAPL@20260115");

        assertEquals("20260115", m.getVersion());
        assertEquals(VersionType.DATE, m.getVersionType());
    }

    @Test
    void testParseLookbackVersion() throws MonikerParseException {
        Moniker m = MonikerParser.parseMoniker("prices.equity/AAPL@3M");

        assertEquals("3M", m.getVersion());
        assertEquals(VersionType.LOOKBACK, m.getVersionType());

        String[] lookback = m.versionLookback();
        assertNotNull(lookback);
        assertEquals("3", lookback[0]);
        assertEquals("M", lookback[1]);
    }

    @Test
    void testParseWithRevision() throws MonikerParseException {
        Moniker m = MonikerParser.parseMoniker("commodities.derivatives/crypto/ETH@20260115/v2");

        assertEquals("commodities.derivatives/crypto/ETH", m.getPath().toString());
        assertEquals("20260115", m.getVersion());
        assertEquals(2, m.getRevision());
    }

    @Test
    void testParseWithSubResource() throws MonikerParseException {
        Moniker m = MonikerParser.parseMoniker("securities/012345678@20260101/details.corporate.actions");

        assertEquals("securities/012345678", m.getPath().toString());
        assertEquals("20260101", m.getVersion());
        assertEquals("details.corporate.actions", m.getSubResource());
    }

    @Test
    void testParseWithScheme() throws MonikerParseException {
        Moniker m = MonikerParser.parseMoniker("moniker://holdings/20260115/fund_alpha");

        assertEquals("holdings/20260115/fund_alpha", m.getPath().toString());
    }

    @Test
    void testParseWithQueryParams() throws MonikerParseException {
        Moniker m = MonikerParser.parseMoniker("holdings/20260115/fund_alpha?format=json");

        assertEquals("holdings/20260115/fund_alpha", m.getPath().toString());
        assertTrue(m.getParams().has("format"));
        assertEquals("json", m.getParams().get("format"));
    }

    @Test
    void testClassifyVersionTypes() {
        assertEquals(VersionType.DATE, MonikerParser.classifyVersion("20260115"));
        assertEquals(VersionType.LATEST, MonikerParser.classifyVersion("latest"));
        assertEquals(VersionType.LOOKBACK, MonikerParser.classifyVersion("3M"));
        assertEquals(VersionType.LOOKBACK, MonikerParser.classifyVersion("12Y"));
        assertEquals(VersionType.FREQUENCY, MonikerParser.classifyVersion("daily"));
        assertEquals(VersionType.ALL, MonikerParser.classifyVersion("all"));
        assertEquals(VersionType.CUSTOM, MonikerParser.classifyVersion("custom123"));
    }

    @Test
    void testValidateSegment() {
        assertTrue(MonikerParser.validateSegment("valid_segment"));
        assertTrue(MonikerParser.validateSegment("segment123"));
        assertTrue(MonikerParser.validateSegment("seg.ment"));
        assertTrue(MonikerParser.validateSegment("seg-ment"));

        assertFalse(MonikerParser.validateSegment("")); // Empty
        assertFalse(MonikerParser.validateSegment("_invalid")); // Starts with underscore
        assertFalse(MonikerParser.validateSegment("-invalid")); // Starts with hyphen
    }

    @Test
    void testValidateNamespace() {
        assertTrue(MonikerParser.validateNamespace("valid"));
        assertTrue(MonikerParser.validateNamespace("valid_namespace"));
        assertTrue(MonikerParser.validateNamespace("valid-namespace"));

        assertFalse(MonikerParser.validateNamespace("")); // Empty
        assertFalse(MonikerParser.validateNamespace("123invalid")); // Starts with digit
        assertFalse(MonikerParser.validateNamespace("_invalid")); // Starts with underscore
        assertFalse(MonikerParser.validateNamespace("invalid.namespace")); // Contains dot
    }

    @Test
    void testInvalidMoniker() {
        assertThrows(MonikerParseException.class, () -> {
            MonikerParser.parseMoniker("");
        });

        assertThrows(MonikerParseException.class, () -> {
            MonikerParser.parseMoniker("invalid://scheme");
        });
    }
}
