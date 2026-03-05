package com.ganizanisitara.moniker.resolver.telemetry;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Identity of the caller making the request.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class CallerIdentity {
    private String userId;
    private String appId;
    private String team;
    private String ipAddress;
    private String userAgent;
}
