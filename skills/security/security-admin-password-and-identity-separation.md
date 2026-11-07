# security-admin-password-and-identity-separation

**Category:** Security · **Priority:** MEDIUM

## Why it matters

Two related habits move an Azure DocumentDB cluster from "default-secure" to "production-hardened":

1. The cluster's built-in administrative account uses a **password**. That password is the fallback path that bypasses Entra ID, so its strength and rotation hygiene matter — even when most workloads use managed identities.
2. The Azure identity that **manages** the cluster (creates, scales, deletes, lists connection strings) and the identity that **uses** the cluster's data (reads, writes, queries) should be **different principals**. Sharing one identity across both planes is a classic privilege-escalation path — a data-plane bug that yields code execution now also yields cluster-management rights.

This rule captures both habits because the Learn security overview groups them as identity-management best practices.

## Admin password policy

Azure DocumentDB enforces a minimum password policy on administrative accounts: **at least 8 characters, with all four of upper-case, lower-case, digits, and non-alphanumeric characters.** Treat the floor as the floor, not the target — generate longer passwords from a password manager and store them in Key Vault.

## Identity separation: control plane vs data plane

Recall the two-level access model (see `SKILL.md`):

- **Control plane** — Azure RBAC on `Microsoft.DocumentDB/mongoClusters/*` (resize, firewall, list connection strings, register users).
- **Data plane** — Entra ID + MongoDB database roles (read/write documents).

Use **distinct Azure identities** for these two layers wherever practical. The principle is the same as separating "deploy" identities from "runtime" identities elsewhere in Azure: a single compromised identity should not be able to both modify infrastructure and access data.

## Incorrect

Weak admin password:

```bicep
// Fails policy if too short, but even meeting the minimum (`Pa55!ab`) is too weak.
administrator: {
  userName: 'clusteradmin'
  password: 'Pa55word!'           // ← 9 chars, dictionary-derived, easily guessed
}
```

Hard-coding admin credentials in a connection string for runtime use:

```javascript
// Anti-pattern — the admin account is now exposed to every host that runs this code.
const uri = `mongodb+srv://clusteradmin:${PROD_ADMIN_PASSWORD}@<cluster>.global.mongocluster.cosmos.azure.com/?tls=true`;
```

Using the **same** managed identity for IaC (control plane) and for the application (data plane):

```bicep
// Anti-pattern — the app's managed identity has both:
//   1. Contributor on the cluster (control plane)
//   2. mongoClusters/users registration as readWrite (data plane)
// A code-execution bug in the app can now resize, delete, or exfiltrate keys.
resource appIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: 'app-identity'
}

resource controlPlaneRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  // …
  properties: {
    roleDefinitionId: contributorRoleId
    principalId: appIdentity.properties.principalId    // same identity
  }
}

resource dataPlaneUser 'Microsoft.DocumentDB/mongoClusters/users@2025-09-01' = {
  // …
  properties: {
    identityProvider: { /* … */ }
    roles: [ { db: 'orders', role: 'readWrite' } ]    // same identity
  }
}
```

## Correct

### Generate strong admin passwords from Key Vault

Sample workflow:

```bash
# Generate a 32-char password and store in Key Vault.
NEW_PWD=$(openssl rand -base64 24 | tr -d '/+=' | head -c 32)
az keyvault secret set \
  --vault-name "<kv>" \
  --name "docdb-admin-password" \
  --value "$NEW_PWD"
```

Reference it from Bicep instead of inlining a literal:

```bicep
@secure()
param adminPassword string         // sourced from Key Vault at deploy time

resource cluster 'Microsoft.DocumentDB/mongoClusters@2025-09-01' = {
  name: clusterName
  location: location
  properties: {
    administrator: {
      userName: 'clusteradmin'
      password: adminPassword
    }
    // …
  }
}
```

```bash
az deployment group create \
  --resource-group "<rg>" \
  --template-file cluster.bicep \
  --parameters adminPassword="$(az keyvault secret show --vault-name <kv> --name docdb-admin-password --query value -o tsv)"
```

Rotate the admin password on a schedule (e.g. quarterly) and after any incident. Use managed identities for everyday workload access so admin-password rotation is not on the critical path.

### Use two separate identities

Pattern: one identity for IaC / SRE, a different identity for each workload that consumes data.

```bicep
// Control-plane identity — used by your deploy pipeline.
resource sreIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: 'sre-deploy-identity'
}

resource controlPlaneRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, sreIdentity.id, 'control-plane')
  scope: resourceGroup()
  properties: {
    roleDefinitionId: docdbRbacOwnerRoleId         // see security-azure-rbac-actions
    principalId: sreIdentity.properties.principalId
  }
}

// Data-plane identity — used by the application at runtime.
resource appIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: 'orders-api-identity'
}

resource dataPlaneUser 'Microsoft.DocumentDB/mongoClusters/users@2025-09-01' = {
  name: '${clusterName}/users/${appIdentity.properties.principalId}'
  properties: {
    identityProvider: {
      type: 'Microsoft.EntraID'
      properties: { principalType: 'ManagedIdentity' }
    }
    roles: [
      { db: 'orders', role: 'readWrite' }
    ]
  }
}
```

The SRE identity can resize / configure / register users but has **no** database role and cannot read data. The app identity can read and write `orders` but has **no** Azure RBAC role and cannot scale, list connection strings, or delete the cluster. A compromise of either is bounded.

### Why this matters in practice

- A leaked CI/CD identity that holds Contributor on the cluster but no database role can still cause damage (delete the cluster, change firewall, list connection strings, register a malicious user) — but it cannot directly exfiltrate data, buying the responder time.
- A leaked app identity that holds `readWrite` on one database cannot resize, delete, or reconfigure the cluster — the blast radius is the database it owns.

## References

- [Secure your cluster — Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/security)
- [Create secondary users](https://learn.microsoft.com/azure/documentdb/secondary-users)
- Related: [security-entra-rbac](security-entra-rbac.md), [security-azure-rbac-actions](security-azure-rbac-actions.md), [security-database-roles](security-database-roles.md)
