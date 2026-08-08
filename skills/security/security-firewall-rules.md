# security-firewall-rules

**Category:** Security · **Priority:** MEDIUM

## Why it matters

When public network access is enabled on an Azure DocumentDB cluster, **firewall rules are the only thing standing between the database and the internet.** They allow inbound traffic from explicit IPv4 sources expressed as either **CIDR ranges** or **Start-IP / End-IP** pairs (the portal uses the latter; both are equivalent — a `/32` is a single IP, and the same address in Start and End fields does the same thing). Firewall rules are independent of (and complementary to) Private Endpoint — Private Endpoint is the strong-isolation control (see [security-private-endpoint](security-private-endpoint.md)); firewall rules are for cases where you must keep public access on but want to scope it to known sources.

**Default state: locked down.** A newly created cluster with no firewall rules and no private endpoint has **public access effectively disabled** — nothing can reach the data plane until you either add a firewall rule or create a private endpoint. This is a default-deny posture; opening the cluster is a deliberate action, not the absence of one.

Operational gotchas to bake into runbooks:

1. **Firewall changes propagate in up to ~15 minutes** — during that window the firewall can behave inconsistently. Don't troubleshoot "connection refused" for the first 15 minutes after a change.
2. **"Allow public access from Azure resources and services" is a separate toggle** from IP rules. It grants access to Azure services (like Azure Functions or Stream Analytics) without listing their IPs — but ⚠️ **it admits connections from *any* Azure service in *any* customer subscription**, not just yours. Identity (Entra ID + database role) is the only remaining gate.
3. **The `0.0.0.0 - 255.255.255.255` shortcut** is essentially "no firewall." Don't use it for production.
4. **The portal's "current client IP" detection can be wrong** — corporate proxies, VPNs, or IPv6 transition can make the portal-detected IP differ from your actual egress. Verify with a "what is my IP" service before saving.

## Incorrect

Opening the firewall to the world during an incident and forgetting to close it:

```text
Cluster:   production-db
Firewall:  0.0.0.0 - 255.255.255.255   ← effectively no firewall
Public access: enabled
```

Whitelisting a developer's home IP on a production cluster:

```text
Cluster:   production-db
Firewall:  73.123.45.67/32              ← residential DHCP IP — rotates without warning
```

Treating a firewall change as immediate and rolling forward before propagation completes:

```bash
# t+0  Add a CI/CD egress range
az documentdb mongo-cluster firewall-rule create ...

# t+30s  Trigger the deploy — may fail for up to ~15 minutes
ci-pipeline run
```

## Correct

### 1. Add your current client IP for short-lived admin work

Easiest path is the Azure portal:

1. Open the cluster → **Networking**.
2. Select **+ Add current client IP address**.
3. **Verify** the detected IP matches your real egress (corporate proxies and VPN concentrators can shift it).
4. **Save**.

Remove the rule when you're done — don't leave temporary IPs in place.

### 2. Allow Azure services without enumerating IPs

For workloads like Azure Functions or Stream Analytics where listing the source IPs isn't practical:

1. Cluster → **Networking**.
2. Toggle **Allow public access from Azure resources and services** (a.k.a. **Allow Azure services and resources to access this cluster**) on.
3. **Save**.

> ⚠️ This toggle admits traffic from **any Azure service in any customer subscription** — not just yours. The network gate becomes coarse; **identity** (Entra ID + database role) is the only remaining gate that distinguishes your workload from someone else's. Pair this toggle with managed-identity auth and tight database roles (see [security-entra-rbac](security-entra-rbac.md), [security-database-roles](security-database-roles.md)). For sensitive workloads, prefer Private Endpoint instead.

### 3. Allow specific CIDR ranges

For corporate egress NAT, VPN concentrators, partner ranges, or a pinned CI/CD egress IP set:

1. Cluster → **Networking** → **Firewall and virtual networks**.
2. Add entries in CIDR form, e.g. `203.0.113.0/24`, `198.51.100.42/32`.
3. **Save** and wait ~15 minutes before considering the change applied.

Prefer `/32` for single hosts and the narrowest CIDR your environment supports for ranges.

### 4. Plan around the propagation window

- **Never** stack a firewall change in front of a critical deployment without ~15 minutes of slack.
- After a change, smoke-test connectivity from a representative source IP before declaring it done.
- During the window, expect intermittent failures, not a clean cutover.

### 5. Avoid `0.0.0.0 - 255.255.255.255`

The portal exposes a shortcut to allow all IPs *via Azure infrastructure*. The cluster help text labels it as a wide allowance and warns it limits the effectiveness of the firewall policy. The only legitimate use is short-lived debugging in non-production — and even then prefer a tighter rule.

### 6. Prefer Private Endpoint where you can

If the workload runs in Azure and doesn't need public access, the right answer is to disable public network access entirely and use Private Endpoint instead. Firewall rules are best thought of as a stopgap for hybrid or partner-access scenarios. See [security-private-endpoint](security-private-endpoint.md).

### 7. Disable public access entirely

To fully close the public path on an existing cluster:

1. Cluster → **Networking**.
2. **Remove every firewall rule** in the Public access section.
3. **Clear** the **Allow Azure services and resources to access this cluster** checkbox.
4. **Save**.

With no rules and the Azure-services toggle off, the public path is effectively closed — the cluster reverts to the default locked-down posture and only Private Endpoint (if configured) provides reachability. Confirm by attempting a connection from a previously-allowed public source after the ~15-minute propagation window — it should fail.

## Operational checklist

| When | Do |
|---|---|
| Adding a rule | Use the narrowest CIDR possible; document why |
| After saving | Wait ~15 minutes before troubleshooting connectivity |
| Quarterly | Audit firewall rules; remove residential / ad-hoc IPs |
| Production hardening | Disable public access; rely on Private Endpoint instead |

## References

- [Configure firewall — Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/how-to-configure-firewall)
- [Enable and manage public access — Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/how-to-public-access)
- Related: [security-private-endpoint](security-private-endpoint.md), [security-entra-rbac](security-entra-rbac.md), [security-database-roles](security-database-roles.md)
