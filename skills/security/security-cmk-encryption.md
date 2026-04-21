# security-cmk-encryption

**Category:** Security · **Priority:** MEDIUM

## Why it matters

Azure DocumentDB encrypts data at rest by default with Microsoft-managed keys. For regulated workloads (finance, healthcare, government), compliance often requires **customer-managed keys (CMK)** backed by Azure Key Vault so that your organization controls the key lifecycle and can revoke access.

Decisions to make up front:
- CMK must be enabled on cluster creation (migration paths are limited).
- The cluster's managed identity needs `Key Vault Crypto Service Encryption User` on the key.
- Key rotation and expiration policies must be defined and monitored — a revoked/expired key can make the cluster unreachable.

## Incorrect

Enabling CMK in production without a documented key-rotation and recovery plan — a missing or expired key will render the database unavailable.

## Correct

1. Create (or reuse) a Key Vault in the same region with **Soft Delete** and **Purge Protection** enabled.
2. Create a key intended for DocumentDB encryption.
3. Grant the DocumentDB cluster's managed identity the Crypto Service Encryption User role on the key.
4. Configure CMK at cluster creation, referencing the Key Vault URI.
5. Define rotation cadence and alerting on key expiration / deletion.
6. Test the revocation/restore runbook in a non-production environment before go-live.

```bicep
// sketch — confirm current property names/versions in the docs
resource ddb 'Microsoft.DocumentDB/...@...' = {
  identity: { type: 'SystemAssigned' }
  properties: {
    encryption: {
      type: 'CustomerManaged'
      keyVaultKeyUri: kv.keyUri
    }
  }
}
```

## References

- [Data encryption at rest](https://learn.microsoft.com/azure/documentdb/database-encryption-at-rest)
- [Configure customer-managed key encryption](https://learn.microsoft.com/azure/documentdb/how-to-data-encryption)
- [Troubleshoot CMK encryption](https://learn.microsoft.com/azure/documentdb/how-to-database-encryption-troubleshoot)
