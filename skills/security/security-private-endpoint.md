# security-private-endpoint

**Category:** Security · **Priority:** HIGH

## Why it matters

A **Private Endpoint** attaches an Azure DocumentDB cluster to your virtual network with a **private IP**, so client traffic never traverses the public internet. Combined with disabling public network access and tight NSG rules, this is the strongest network-isolation posture for the cluster — far stronger than IP firewall rules (see [security-firewall-rules](security-firewall-rules.md)).

Two things to know up front so you don't fight the platform:

- **Private Link does not prevent your cluster's FQDN from being resolved by public DNS.** The defense is at the application/connection level — clients can only reach the cluster's private IP, and only from networks that can route to that IP. The public DNS name is harmless without network reachability.
- **Private DNS integration must be enabled for the connection to resolve correctly.** The cluster's MongoDB `mongodb+srv` discovery uses SRV records, and those SRV records must resolve to private IPs from inside the VNet.

Private Link works from:

- The same virtual network as the private endpoint.
- **Peered virtual networks**.
- **On-premises networks** connected via VPN or ExpressRoute (private peering).

## DNS, group ID, and subresource cheat sheet

| Field | Value |
|---|---|
| Resource type | `Microsoft.DocumentDB/mongoClusters` |
| Group ID / target subresource | `MongoCluster` |
| Private DNS zone name | `privatelink.mongocluster.cosmos.azure.com` |
| SRV record for discovery | `_mongodb._tcp.<cluster>.mongocluster.cosmos.azure.com` |
| Public host (unchanged) | `<cluster>.mongocluster.cosmos.azure.com` / `<cluster>.global.mongocluster.cosmos.azure.com` |
| MongoDB driver port | 27017 |

Inside the VNet, the public host resolves (via the private DNS zone) to a private IP. Outside the VNet, it resolves to the public IP — but cannot be reached unless public access is also enabled.

## Incorrect

Leaving public access on and the firewall wide-open as a "fallback" after creating a private endpoint:

```text
Cluster:           production-db
Public access:     Enabled
Firewall:          0.0.0.0 - 255.255.255.255
Private endpoint:  Created (but bypassed by the open firewall)
```

Creating a private endpoint **without** linking the private DNS zone to your VNet — clients will still resolve the cluster to its public IP and fail:

```bash
az network private-endpoint create ...           # OK
az network private-dns zone create ...           # OK
# Missing: az network private-dns link vnet create ...
# Missing: az network private-endpoint dns-zone-group create ...
# Result: app fails with DNS / connection errors inside the VNet.
```

Forgetting to disable subnet network policies — the private endpoint create fails:

```bash
# Required on the target subnet before creating the private endpoint:
az network vnet subnet update \
  --vnet-name $VNetName \
  --name $SubnetName \
  --resource-group $ResourceGroupName \
  --disable-private-endpoint-network-policies true
```

## Correct

### Full Azure CLI flow

```bash
ResourceGroupName="myResourceGroup"
ClusterName="myMongoCluster"
SubscriptionId="<sub-id>"
SubResourceType="MongoCluster"                       # group ID
VNetName="myVnet"
SubnetName="mySubnet"
PrivateEndpointName="myPrivateEndpoint"
PrivateConnectionName="myConnection"

# 1. VNet + subnet (or use existing).
az network vnet create \
  --name $VNetName \
  --resource-group $ResourceGroupName \
  --subnet-name $SubnetName

# 2. Disable PE network policies on the subnet.
az network vnet subnet update \
  --name $SubnetName \
  --resource-group $ResourceGroupName \
  --vnet-name $VNetName \
  --disable-private-endpoint-network-policies true

# 3. Create the private endpoint.
az network private-endpoint create \
  --name $PrivateEndpointName \
  --resource-group $ResourceGroupName \
  --vnet-name $VNetName \
  --subnet $SubnetName \
  --private-connection-resource-id "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroupName/providers/Microsoft.DocumentDB/mongoClusters/$ClusterName" \
  --group-ids $SubResourceType \
  --connection-name $PrivateConnectionName

# 4. Private DNS zone (exact name matters).
zoneName="privatelink.mongocluster.cosmos.azure.com"
az network private-dns zone create \
  --resource-group $ResourceGroupName \
  --name $zoneName

# 5. Link the DNS zone to the VNet.
az network private-dns link vnet create \
  --resource-group $ResourceGroupName \
  --zone-name $zoneName \
  --name "${VNetName}-link" \
  --virtual-network $VNetName \
  --registration-enabled false

# 6. Bind the zone to the private endpoint so A records auto-populate.
az network private-endpoint dns-zone-group create \
  --resource-group $ResourceGroupName \
  --endpoint-name $PrivateEndpointName \
  --name "default" \
  --private-dns-zone $zoneName \
  --zone-name mongocluster
```

### Lock the data plane down to private only

Once apps have verified connectivity through the private endpoint, disable public access and reset firewall rules:

```bash
az resource update \
  --ids "/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroupName/providers/Microsoft.DocumentDB/mongoClusters/$ClusterName" \
  --set properties.publicNetworkAccess="Disabled"
```

Bicep sketch:

```bicep
resource cluster 'Microsoft.DocumentDB/mongoClusters@2025-09-01' = {
  name: clusterName
  properties: {
    publicNetworkAccess: 'Disabled'
  }
}
```

### Replica clusters: connection-string detail

On a **replica cluster**, only **self** connection strings are exposed — there is no global read-write string on the replica. Apps that need to reach a replica via Private Link must use the replica's self connection string. (See `high-availability/ha-cross-region-replica.md` for replica networking — settings do **not** inherit from the primary, so the replica needs its own private endpoint and DNS link.)

## Verify and troubleshoot

### Verify the endpoint

```bash
az network private-endpoint show \
  --resource-group $ResourceGroupName \
  --name $PrivateEndpointName \
  --query '{Name:name, PrivateIpAddress:customDnsConfigs[0].ipAddresses[0], FQDN:customDnsConfigs[0].fqdn, ProvisioningState:provisioningState}' \
  --output table
```

Expect `ProvisioningState = Succeeded` and a private IP in your subnet range.

Also confirm in the portal that the connection state is **Approved** under the cluster's Networking → Private endpoint connections.

### Test SRV-based discovery from inside the VNet

Driver discovery uses an SRV record — DNS for the public hostname alone isn't enough.

**Windows / PowerShell:**

```powershell
Resolve-DnsName -Name _mongodb._tcp.<cluster>.mongocluster.cosmos.azure.com -Type SRV
Resolve-DnsName -Name <node-host>.mongocluster.cosmos.azure.com
# A-record answer should be a 10.x.x.x / private RFC1918 address.

# Alternative:
nslookup -type=SRV _mongodb._tcp.<cluster>.mongocluster.cosmos.azure.com
nslookup <node-host>.mongocluster.cosmos.azure.com
```

**Linux / macOS:**

```bash
dig _mongodb._tcp.<cluster>.mongocluster.cosmos.azure.com SRV
dig <node-host>.mongocluster.cosmos.azure.com
# A-record answer should be a private IP in the subnet range.

# Alternative:
nslookup -type=SRV _mongodb._tcp.<cluster>.mongocluster.cosmos.azure.com
nslookup <node-host>.mongocluster.cosmos.azure.com
```

### Common failure modes

**DNS resolves to a public IP / fails inside the VNet**

- Verify the private DNS zone is **linked to the VNet** (`az network private-dns link vnet list`).
- Verify the **DNS zone group** is bound to the private endpoint.
- Confirm the VNet's DNS settings are Azure-provided DNS (`168.63.129.16`) or a custom resolver that forwards to Azure DNS.
- Test from a resource actually inside the VNet (or a peered VNet) — not from the developer's laptop.

**Connection times out**

- Check **NSG rules** on the subnet — outbound to port **27017** must be allowed.
- Check that the private endpoint's NIC has the expected private IP.
- Verify the connection string uses `mongodb+srv` scheme.
- Confirm cluster-side firewall rules aren't blocking the source (only relevant if public access is still enabled).

**Private DNS zone exists but no records appear**

- The zone name must be **exactly** `privatelink.mongocluster.cosmos.azure.com`.
- The DNS zone group on the endpoint must be created (`az network private-endpoint dns-zone-group create …`) — that's the binding that populates A records.

## References

- [Use Azure Private Link with Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/how-to-private-link)
- [What is Azure Private Link?](https://learn.microsoft.com/azure/private-link/private-endpoint-overview)
- Related: [security-firewall-rules](security-firewall-rules.md), [security-entra-rbac](security-entra-rbac.md), [high-availability/ha-cross-region-replica](../high-availability/ha-cross-region-replica.md)
