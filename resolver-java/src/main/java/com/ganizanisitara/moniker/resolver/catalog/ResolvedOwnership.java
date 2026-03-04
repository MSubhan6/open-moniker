package com.ganizanisitara.moniker.resolver.catalog;

import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;

/**
 * Ownership resolved through the hierarchy, with provenance.
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class ResolvedOwnership {
    // Simplified ownership with provenance
    private String accountableOwner;
    private String accountableOwnerSource;

    private String dataSpecialist;
    private String dataSpecialistSource;

    private String supportChannel;
    private String supportChannelSource;

    // Formal governance roles with provenance
    private String adop;
    private String adopSource;
    private String adopName;
    private String adopNameSource;

    private String ads;
    private String adsSource;
    private String adsName;
    private String adsNameSource;

    private String adal;
    private String adalSource;
    private String adalName;
    private String adalNameSource;

    private String ui;
    private String uiSource;

    /**
     * Convert to simple Ownership (without provenance).
     */
    public Ownership toOwnership() {
        Ownership o = new Ownership();
        o.setAccountableOwner(accountableOwner);
        o.setDataSpecialist(dataSpecialist);
        o.setSupportChannel(supportChannel);
        o.setAdop(adop);
        o.setAds(ads);
        o.setAdal(adal);
        o.setAdopName(adopName);
        o.setAdsName(adsName);
        o.setAdalName(adalName);
        o.setUi(ui);
        return o;
    }
}
