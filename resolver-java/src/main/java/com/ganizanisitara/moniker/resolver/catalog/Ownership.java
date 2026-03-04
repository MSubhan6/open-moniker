package com.ganizanisitara.moniker.resolver.catalog;

import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;

/**
 * Ownership information for catalog nodes.
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class Ownership {
    // Simplified ownership fields
    private String accountableOwner;
    private String dataSpecialist;
    private String supportChannel;

    // Formal data governance roles (BCBS 239 / DAMA style)
    private String adop;      // Accountable Data Owner/Principal
    private String ads;       // Accountable Data Steward
    private String adal;      // Accountable Data Access Lead
    private String adopName;  // Human-readable names
    private String adsName;
    private String adalName;

    // UI link
    private String ui;

    /**
     * Merge with parent ownership, using parent values for any fields not set.
     */
    public Ownership mergeWithParent(Ownership parent) {
        if (parent == null) {
            return this;
        }

        Ownership merged = new Ownership();
        merged.accountableOwner = firstNonNull(this.accountableOwner, parent.accountableOwner);
        merged.dataSpecialist = firstNonNull(this.dataSpecialist, parent.dataSpecialist);
        merged.supportChannel = firstNonNull(this.supportChannel, parent.supportChannel);
        merged.adop = firstNonNull(this.adop, parent.adop);
        merged.ads = firstNonNull(this.ads, parent.ads);
        merged.adal = firstNonNull(this.adal, parent.adal);
        merged.adopName = firstNonNull(this.adopName, parent.adopName);
        merged.adsName = firstNonNull(this.adsName, parent.adsName);
        merged.adalName = firstNonNull(this.adalName, parent.adalName);
        merged.ui = firstNonNull(this.ui, parent.ui);
        return merged;
    }

    /**
     * Check if all ownership fields are defined.
     */
    public boolean isComplete() {
        return accountableOwner != null && dataSpecialist != null && supportChannel != null;
    }

    /**
     * Check if any formal governance roles are defined.
     */
    public boolean hasGovernanceRoles() {
        return adop != null || ads != null || adal != null;
    }

    /**
     * Check if no ownership fields are defined.
     */
    public boolean isEmpty() {
        return accountableOwner == null && dataSpecialist == null && supportChannel == null &&
               adop == null && ads == null && adal == null;
    }

    private static String firstNonNull(String... values) {
        for (String value : values) {
            if (value != null) {
                return value;
            }
        }
        return null;
    }
}
