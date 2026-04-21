# security-private-endpoint

**Category:** Security · **Priority:** MEDIUM

## Why it matters

By default a DocumentDB cluster can accept traffic from approved public IPs via its firewall. For regulated or production workloads, exposing the data plane to the public internet is unnecessary risk. A **Private Endpoint** attaches the cluster to your VNet with a private IP, and public network access can be **disabled** entirely so that only traffic from your VNet (and peered networks) can reach it.

## Incorrect

```text
Cluster: production-db
Firewall: 0.0.0.0 – 255.255.255.255 (allow all, "temporarily")
Public access: enabled
```

## Correct

1. Create a Private Endpoint for the cluster in the app subnet.
2. Configure Private DNS so the DocumentDB FQDN resolves to the private IP inside the VNet.
3. In the cluster's networking blade, **disable public network access** once the app has verified connectivity.
4. Restrict any remaining firewall rules to specific management/CI IPs only.

```bicep
// sketch — verify current property names
resource pe 'Microsoft.Network/privateEndpoints@...' = { /* ... */ }
resource ddb 'Microsoft.DocumentDB/...@...' = {
  properties: {
    publicNetworkAccess: 'Disabled'
    // firewallRules: []  (empty or minimal)
  }
}
```

## References

- [Configure firewall rules](https://learn.microsoft.com/azure/documentdb/how-to-configure-firewall)
- [Security guide](https://learn.microsoft.com/azure/documentdb/security)
