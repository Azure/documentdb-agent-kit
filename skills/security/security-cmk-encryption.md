# security-cmk-encryption

**Category:** Security · **Priority:** MEDIUM

## Why it matters

**Every Azure DocumentDB cluster encrypts data at rest, always.** That includes user databases, system databases, temporary files, logs, and backups. The question isn't *whether* data is encrypted — it's **who controls the key**.

Azure DocumentDB offers two encryption modes:

| Mode | Key owner | When to choose it |
|------|-----------|--------------------|
| **Service-managed keys (SMK)** — default | Microsoft | You want zero key-management overhead and have no regulatory requirement to hold the key yourself. |
| **Customer-managed keys (CMK)** | You, via your Azure Key Vault | Regulated workload (finance, healthcare, government), separation-of-duties policy, or you need to be able to **revoke** the key to make a database inaccessible on demand. |

Under the hood, both modes rely on [server-side encryption of Azure Storage](https://learn.microsoft.com/azure/storage/common/storage-service-encryption). In CMK mode, **Azure Storage wraps the root Data Encryption Key (DEK) with your key in Key Vault** — your key encrypts a key, not the data directly. Data stays encrypted at all times; switching the wrapping key has no effect on the ciphertext.

### The non-negotiables

1. **CMK vs. SMK is a cluster-creation-time decision and cannot be changed for the lifetime of the cluster.** Pick correctly the first time. If you might ever need CMK, create the cluster as CMK from day one — even if the initial key is owned by you with minimal restrictions.
2. **With CMK, you own the responsibility for every component required to keep the cluster decryptable**: the Key Vault, the user-assigned managed identity, the key itself, the network configuration of the vault, and auditing. A misconfiguration on any of these can make the cluster unreachable.
3. **Revocation is a feature, not a bug.** Removing the identity's access to the key, disabling the key, or deleting the key will make the cluster inaccessible. Build that into your runbooks intentionally; don't trip over it accidentally.
4. **Performance is not affected** by either mode. CMK is not slower than SMK at runtime — Storage wraps/unwraps the DEK on key-rotation events, not on every read/write.

## Incorrect

```text
☐ Cluster created with SMK because "we'll switch to CMK later when audit asks for it."
  → Not possible. The mode is fixed at creation time.

☐ Key Vault used for CMK has soft-delete and purge-protection disabled.
  → An accidental delete of the key or the vault permanently destroys the cluster's
    ability to decrypt. There is no recovery.

☐ Key Vault and DocumentDB cluster live in different Microsoft Entra tenants.
  → Unsupported. The cluster's managed identity cannot read the key across tenants.

☐ Cluster uses a system-assigned managed identity for CMK.
  → CMK requires a user-assigned managed identity. System-assigned cannot be used.

☐ Key Vault firewall is set to "Allow public access from all networks" in production.
  → Works, but defeats the purpose of CMK. Use "Disable public access" + "Allow
    trusted Microsoft services to bypass this firewall" instead.

☐ Symmetric key, or RSA-1024, or EC key used for wrapping.
  → Only asymmetric RSA / RSA-HSM keys at 2048, 3072, or 4096 bits are supported.

☐ Key has an activation date in the future, or an expiry in the past, or is Disabled.
  → The wrap operation will fail; cluster operations on encrypted data stop.

☐ No Azure resource lock on the Key Vault; no logging; no alerting.
  → A misclick in the portal or a runaway script can delete the vault. No telemetry
    means you find out by way of cluster outage.

☐ No backup of the key kept outside the vault.
  → If Key Vault generates the key for you, take a key backup *before* first use.
    The backup can only be restored to Key Vault, but it survives vault loss.
```

## Correct

### 1. Decide at architecture time

Before opening the portal:

- **Compliance review**: does the workload require customer-controlled keys? If unsure, default to SMK — switching from SMK to CMK later requires recreating the cluster and migrating data.
- **Key ownership**: who in the org owns the Key Vault? Typically not the same team as the DocumentDB cluster — CMK is the right tool when you want **separation of duties** between database administrators and security/key custodians.

### 2. Stand up the Key Vault correctly

Pre-flight checklist for the vault that will hold the CMK:

| Setting | Required value | Why |
|---------|---------------|-----|
| Tenant | Same Microsoft Entra tenant as the DocumentDB cluster | Cross-tenant managed-identity access is not supported |
| Soft-delete | **Enabled** (90-day retention recommended) | Lets you recover an accidentally deleted key or vault |
| Purge protection | **Enabled** | Enforces mandatory retention even against malicious deletes |
| Days to retain deleted vaults | **90** (set at vault creation — cannot be changed later) | Maximum safety window |
| Permission model | **RBAC** (preferred) or access policies (legacy) | RBAC is the modern model — use it for new vaults |
| Public network access | **Disabled** + **Allow trusted Microsoft services to bypass this firewall** | Closes the public surface while letting DocumentDB reach the key |
| Resource lock | `CanNotDelete` | Belt-and-suspenders against accidental deletion |
| Logging | Diagnostic settings → Log Analytics / SIEM | You need an audit trail of every key access |
| Alerting | Alerts on key delete, key disable, role-assignment removal | Detect revocation events fast |
| Availability / redundancy | Review and configure per [Key Vault DR guidance](https://learn.microsoft.com/azure/key-vault/general/disaster-recovery-guidance) | Vault unavailability ≈ cluster outage |

After enabling the firewall lockdown above, the portal may surface the warning **"You enabled the network access control. Only allowed networks have access to this key vault."** when you try to administer the vault from your laptop. **This is expected** and does not block DocumentDB from fetching the key during cluster operations — the cluster reaches the vault via the "trusted Microsoft services" exception.

### 3. Generate or import the encryption key

Requirements that the cluster *will not* relax:

- Algorithm: **RSA** or **RSA-HSM** (asymmetric only — no symmetric, no EC).
- Size: **2048**, **3072**, or **4096** bits. **Recommendation: 4096** for better security.
- State: **Enabled**.
- Activation date: past or unset.
- Expiry: future or unset.
- If importing an existing key: supported file formats are `.pfx`, `.byok`, or `.backup`.

If Key Vault generates the key, immediately take a [key backup](https://learn.microsoft.com/azure/key-vault/general/backup) before any encryption operation runs against it. The backup can only be restored to Key Vault, but it protects against the catastrophic case of a vault being lost entirely. Store a copy of the key (or the backup) in a separate secure location, or use a key-escrow service — your call, but document the location.

### 4. Create the user-assigned managed identity and grant it on the key

CMK on DocumentDB **requires a user-assigned managed identity**. Create one in the same subscription/region as the cluster.

Grant the identity access to the key:

**Preferred (RBAC permission model on the vault):**

- Role: **Key Vault Crypto Service Encryption User**
- Scope: the specific key (preferred) or the vault.

```azurecli
az role assignment create \
  --assignee-object-id <managed-identity-principal-id> \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Crypto Service Encryption User" \
  --scope <key-vault-resource-id>
```

**Legacy (access-policy permission model on the vault):**

Grant the managed identity these key permissions:

| Permission | Used for |
|------------|----------|
| `get` | Read the public part and properties of the key |
| `list` | Iterate and discover keys in the vault |
| `wrapKey` | Encrypt the DEK with the customer key |
| `unwrapKey` | Decrypt the DEK with the customer key |

`wrapKey` and `unwrapKey` are the operational permissions DocumentDB uses; `get` and `list` are used during initial setup.

### 5. Create the cluster with CMK

CMK must be specified at cluster creation. The cluster references:

- The user-assigned managed identity (by resource ID).
- The Key Vault key URI (either versioned or version-less — see next section).

After creation, verify in the portal that the cluster reports CMK as active and that the key URI matches what you provisioned.

### 6. Take advantage of version-less keys + autorotation

Azure DocumentDB CMK supports **automatic key-version updates**, a.k.a. **version-less keys**. When the underlying key rolls to a new version, DocumentDB picks it up automatically and re-wraps the DEK — no cluster action required.

Combine this with **Key Vault [autorotation](https://learn.microsoft.com/azure/key-vault/keys/how-to-configure-key-rotation)** to fully automate key rotation:

1. Reference the key in the cluster by its version-less URI (no `/<version>` suffix).
2. Configure a rotation policy on the key in Key Vault (e.g., rotate every 90 days, expire after 1 year).
3. DocumentDB will follow the active version automatically.

This is the recommended setup for production: rotation is automatic, the cluster never goes through a stale-key window, and you get key freshness without operational toil.

### 7. Plan revocation and recovery

Document and rehearse:

- **Revoke** — disable the key in Key Vault, or remove the role assignment from the managed identity. This intentionally renders the cluster inaccessible to the data plane. Use for compromise response.
- **Restore** — re-enable the key (or reassign the role). Access resumes within the propagation window. Cluster does not need to be restarted.
- **Vault DR** — if the Key Vault is lost, restore from the key backup you took in step 3 into a new vault (same tenant, same key material). Update the cluster to reference the new vault if necessary.

Test all three runbooks in a non-production environment before relying on them.

## Decision: should I use CMK?

| Signal | Choice |
|--------|--------|
| Regulatory mandate (PCI-DSS, HIPAA BAA addendum, FedRAMP High, etc.) requires customer-controlled keys | **CMK** |
| Internal policy mandates separation of duties between DBAs and key custodians | **CMK** |
| You need to be able to **immediately revoke access** to the database by disabling a key | **CMK** |
| You want to centrally manage all encryption keys in Key Vault alongside other workloads | **CMK** |
| No regulatory or policy driver, no key-revocation requirement | **SMK** (default) |
| You're unsure but suspect CMK might be needed within the cluster's lifetime | **CMK from day one** — the choice is fixed at creation |

## References

- [Encryption at rest in Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/database-encryption-at-rest)
- [Server-side encryption of Azure Storage](https://learn.microsoft.com/azure/virtual-machines/disk-encryption)
- [Azure Key Vault basic concepts](https://learn.microsoft.com/azure/key-vault/general/basic-concepts)
- [Key Vault RBAC guide](https://learn.microsoft.com/azure/key-vault/general/rbac-guide)
- [Key Vault soft-delete](https://learn.microsoft.com/azure/key-vault/general/soft-delete-overview)
- [Key Vault best practices — purge protection](https://learn.microsoft.com/azure/key-vault/general/best-practices#turn-on-data-protection-for-your-vault)
- [Key Vault key autorotation](https://learn.microsoft.com/azure/key-vault/keys/how-to-configure-key-rotation)
- [Key Vault disaster recovery](https://learn.microsoft.com/azure/key-vault/general/disaster-recovery-guidance)
- [User-assigned managed identities](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview#managed-identity-types)
- Related: [security-entra-rbac](security-entra-rbac.md), [security-private-endpoint](security-private-endpoint.md)
