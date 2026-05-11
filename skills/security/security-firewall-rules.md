# security-firewall-rules

**Category:** Security · **Priority:** MEDIUM

## Why it matters

When public network access is enabled on an Azure DocumentDB cluster, **firewall rules are the only thing standing between the database and the internet.** They allow inbound traffic from explicit IPv4 ranges in CIDR form. Firewall rules are independent of (and complementary to) Private Endpoint — Private Endpoint is the strong-isolation control (see [security-private-endpoint](security-private-endpoint.md)); firewall rules are for cases where you must keep public access on but want to scope it to known sources.

Three operational gotchas make this rule worth its own page:

1. **Firewall changes propagate in up to ~15 minutes** — during that window the firewall can behave inconsistently. Bake this into your runbooks; don't troubleshoot "connection refused" for the first 15 minutes after a change.
2. **"Allow public access from Azure resources and services" is a separate toggle** from IP rules. It grants access to Azure services (like Azure Functions or Stream Analytics) without listing their IPs — useful, but coarse.
3. **The `0.0.0.0 - 255.255.255.255` shortcut "allow all from Azure"** lets every Azure tenant in every subscription reach your cluster. It is essentially "no firewall." Don't use it for production.

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
3. **Save**.

Remove the rule when you're done — don't leave temporary IPs in place.

### 2. Allow Azure services without enumerating IPs

For workloads like Azure Functions or Stream Analytics where listing the source IPs isn't practical:

1. Cluster → **Networking**.
2. Toggle **Allow public access from Azure resources and services** on.
3. **Save**.

This is broader than a specific IP rule but narrower than `0.0.0.0/0` — only traffic that originates from Azure infrastructure is permitted. Combine it with strong **identity** (Entra ID + managed identity; see [security-entra-rbac](security-entra-rbac.md)) so a misuse of this toggle still can't reach data without a registered principal.

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

## Operational checklist

| When | Do |
|---|---|
| Adding a rule | Use the narrowest CIDR possible; document why |
| After saving | Wait ~15 minutes before troubleshooting connectivity |
| Quarterly | Audit firewall rules; remove residential / ad-hoc IPs |
| Production hardening | Disable public access; rely on Private Endpoint instead |

## References

- [Configure firewall — Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/how-to-configure-firewall)
- Related: [security-private-endpoint](security-private-endpoint.md), [security-entra-rbac](security-entra-rbac.md)
