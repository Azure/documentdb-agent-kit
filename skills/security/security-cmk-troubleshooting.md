# security-cmk-troubleshooting

**Category:** Security · **Priority:** MEDIUM

## Why it matters

With CMK, the cluster's ability to decrypt data depends on a chain of resources you own: a **user-assigned managed identity** → a **role assignment / access policy** on a **Key Vault** → a specific **key** in that vault, reachable over the network. **Break any link and the cluster transitions to the `Inaccessible` state and refuses all connections.** This is by design — it's the security feature you opted into when you chose CMK over service-managed keys. But it means CMK clusters need a sharp operational playbook that SMK clusters do not.

Two timing facts to memorize:

- After a key becomes disabled / deleted / expired / unreachable, the cluster transitions to **`Inaccessible`** within **~60 minutes** (not instantly — there's a revalidation cadence).
- After the underlying problem is fixed, the cluster takes **up to ~60 minutes** to revalidate the key and return to **`Ready`**. **You cannot force this.** No restart, no manual revalidation knob — you wait.

So the worst case is an outage window of ~2 hours from misconfiguration to full recovery, even if you detect and fix in seconds. Plan SLAs accordingly, and make sure operators **don't keep "fixing" things mid-revalidation** under the assumption that the first fix didn't work — they'll thrash the configuration during the recovery window.

The companion architecture/setup rule is [security-cmk-encryption](security-cmk-encryption.md); this rule covers what to do when it goes wrong.

## Common causes of `Inaccessible` state

The cluster goes `Inaccessible` when the managed identity can no longer perform key operations against the configured key. Every cause reduces to one of these:

| Cause | What changed | Resolution |
|-------|--------------|------------|
| **Key expired** | The key in Key Vault hit its configured expiry date/time | **Extend the expiry date on the existing key** and wait for revalidation. ⚠️ Don't rotate to a new key version or create a new key while the cluster is `Inaccessible` — wait for it to return to `Ready`, *then* rotate. |
| **Key disabled** | Someone toggled the key's state to Disabled | Re-enable the key in Key Vault. Wait for revalidation. |
| **Key deleted** | Someone deleted the key (soft-delete catches this) | Recover the key from soft-delete in Key Vault. Wait for revalidation. (This is why soft-delete + purge-protection are non-negotiable — see [security-cmk-encryption](security-cmk-encryption.md).) |
| **Key Vault deleted** | The vault itself was deleted | [Recover the Key Vault](https://learn.microsoft.com/azure/key-vault/general/key-vault-recovery) from soft-delete. Wait for revalidation. |
| **Managed identity deleted** | The user-assigned identity referenced by the cluster was removed from Entra ID | See "Recovering from managed identity deletion" below — this one has a subtlety. |
| **RBAC role removed** | The `Key Vault Crypto Service Encryption User` assignment was deleted from the identity (or from the vault scope) | **Re-grant the role** to the same identity. Wait for revalidation. **Or**, grant the role to a *different* managed identity and update the cluster to use that identity. |
| **Access policy revoked** (legacy permission model) | One of `list`, `get`, `wrapKey`, `unwrapKey` was removed from the identity's access policy | Re-grant the missing permissions, **or** grant them to a different identity and update the cluster. |
| **Vault firewall too restrictive** | Vault networking was tightened in a way that blocks DocumentDB | Either set vault to **Disable public access** + **Allow trusted Microsoft services to bypass this firewall**, or allow public access from all networks. The trusted-services bypass is the right answer for production. |

## Incorrect

```text
☐ Reacting to "Inaccessible" by recreating the cluster.
  → Pointless and destructive. Fix the key/identity/vault problem and wait the
    revalidation window. The data is still encrypted and intact.

☐ Rotating the key (creating a new version) while the cluster is Inaccessible.
  → The cluster's pointer is still bound to the old (expired/disabled) version's
    metadata until revalidation succeeds. Fix the existing key first, get the
    cluster back to Ready, *then* rotate.

☐ Tightening Key Vault networking without selecting "Allow trusted Microsoft
  services to bypass this firewall."
  → The cluster will lose access at the next revalidation. The vault doesn't
    fail loudly when you save the change - failure happens an hour later when
    the cluster goes Inaccessible.

☐ "Recovering" a deleted managed identity by creating a new identity with the
  same name.
  → Entra ID identities are identified by object ID, not name. A new identity
    with the same name is NOT the same principal. Either soft-restore the
    original identity, OR create a new one and update the cluster to reference
    the new identity's resource ID.

☐ Repeatedly editing the cluster configuration during the ~60-minute recovery
  window because "it's not working yet."
  → Revalidation runs on its own cadence. Edit-thrashing extends the outage.
    Make the fix, log it, walk away for an hour, then verify.

☐ No alerting on Key Vault key-disable / role-removal / vault-delete events.
  → You'll find out about CMK problems via a cluster outage, ~60 minutes after
    the fact. Configure Key Vault diagnostic logs + alerts (see
    security-cmk-encryption).
```

## Correct

### Triage: cluster is reported as `Inaccessible`

1. **Don't restart, recreate, or rotate keys yet.** Investigate first.
2. Check the cluster's CMK configuration in the portal: note the **Key Vault URI**, **key name / version (if versioned)**, and the **user-assigned managed identity** resource ID. You'll need all three.
3. In Key Vault, verify the key:
   - Does it still exist? (Check soft-deleted items if not.)
   - Is it **Enabled**?
   - Activation date in the past, expiry in the future (or unset)?
4. Verify the managed identity exists in Entra ID and has the expected role assignment / access policy on the vault.
5. Verify Key Vault networking allows the cluster to reach it (public-from-all-networks **or** disabled-public + trusted-services bypass).
6. Once you find and fix the broken link, **wait up to ~60 minutes** for the periodic revalidation to flip the cluster back to `Ready`. Don't keep poking.

### Recovering from managed identity deletion (the subtle one)

If the user-assigned managed identity was deleted from Entra ID:

1. **Try to recover the original identity** from soft-delete in Entra ID first ([Entra recovery guidance](https://learn.microsoft.com/azure/active-directory/fundamentals/recover-from-deletions)). If recovery succeeds, the original object ID is restored — no cluster reconfiguration needed.
2. **If recovery is not possible**, create a **new** user-assigned managed identity. Then:
   - Grant it the `Key Vault Crypto Service Encryption User` role (RBAC) or the `get` / `list` / `wrapKey` / `unwrapKey` access policy (legacy) on the same key.
   - **Update the cluster's `identity` properties to reference the new identity's resource ID.** This step is mandatory — the cluster does not auto-discover the new identity.
3. Wait ~60 minutes for revalidation.

> ⚠️ **Creating a new identity with the same name as the deleted one does NOT recover the original principal.** Entra ID identities are keyed by object ID (a GUID), not name. The new identity is a different principal — the cluster will not authenticate as it without an explicit reconfiguration.

### Recovering from key or Key Vault deletion

1. In Key Vault, navigate to **Managed deleted vaults** (subscription level) or **Manage deleted keys** (vault level).
2. Recover the deleted resource. Soft-delete retention is 90 days by default; after purge, recovery is impossible — your fallback is the key backup you took at vault provisioning time (see [security-cmk-encryption](security-cmk-encryption.md), step 3).
3. Verify the recovered key is **Enabled** and the cluster's managed identity still has the required role / access policy.
4. Wait ~60 minutes for revalidation.

### Recovering from over-restrictive Key Vault firewall

Symptoms: the vault and the key are fine, the identity and role are fine, but the cluster still goes `Inaccessible` after a recent Key Vault networking change.

Fix:

- Open the Key Vault → **Networking** → set **Allow access from** to either:
  - **All networks** (works, but loses the public-surface lockdown), or
  - **Disable public access** + tick **Allow trusted Microsoft services to bypass this firewall** ✅ (recommended).
- Save. Wait for the firewall change to propagate (a few minutes) and then for cluster revalidation (~60 minutes).

The "trusted Microsoft services" bypass is what lets DocumentDB reach the vault without you needing to enumerate cluster egress IPs. It's the production-correct setting.

### When CMK provisioning fails at cluster creation

If you see the error:

> *"Couldn't get access to the key. It might be missing, the provided user identity doesn't have GET permissions on it, or the key vault hasn't enabled access to the public internet."*

then one of the CMK requirements isn't met. **The failed cluster entity stays around with `clusterStatus: Failed`** — you must clean it up. Procedure:

1. Walk through the CMK requirements checklist in [security-cmk-encryption](security-cmk-encryption.md):
   - Key Vault and DocumentDB in the **same Microsoft Entra tenant**.
   - Key Vault firewall allows the cluster to reach the key (public-from-all-networks, or disabled-public + trusted-services bypass).
   - Key is **RSA / RSA-HSM**, **Enabled**, 2048 / 3072 / 4096 bits, valid activation and expiry.
   - User-assigned managed identity exists.
   - Identity has `Key Vault Crypto Service Encryption User` role (RBAC) **or** `get` / `list` / `wrapKey` / `unwrapKey` (legacy access policies) on the key.
2. **Delete the failed cluster** (you can find `clusterStatus = Failed` on the **Overview** blade).
3. Re-provision the cluster, referencing the verified identity and key URI.

The error message is intentionally vague because the failure mode is on the caller side — DocumentDB cannot tell you which of the requirements is missing, only that the wrap operation failed. Walk the full checklist; don't guess.

## Reference: monitoring to set up *before* you need this rule

Bake these alerts into the Key Vault that holds the CMK so you find out *before* the cluster goes `Inaccessible`:

| Signal | Source | Why |
|--------|--------|-----|
| Key delete / disable event | Key Vault diagnostic logs (`AuditEvent`) | Catches the most common cause of CMK outage |
| Role assignment removed from the cluster's identity on the vault | Azure Activity Log (Authorization category) | Catches RBAC-revocation outage |
| Key Vault firewall configuration change | Azure Activity Log (resource-write on the vault) | Catches networking-tightening mistakes before revalidation |
| User-assigned managed identity deleted | Azure Activity Log on the identity resource | Catches the highest-impact, hardest-to-recover failure mode |
| Key approaching expiry (e.g., 30 days out) | Key Vault key-expiry events / custom alerting | Lets you extend or rotate before automatic outage |

## References

- [Troubleshoot CMK encryption — Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/how-to-database-encryption-troubleshoot)
- [Encryption at rest in Azure DocumentDB](https://learn.microsoft.com/azure/documentdb/database-encryption-at-rest)
- [Recover a deleted Key Vault](https://learn.microsoft.com/azure/key-vault/general/key-vault-recovery)
- [Recover from Entra ID deletions](https://learn.microsoft.com/azure/active-directory/fundamentals/recover-from-deletions)
- [Manage user-assigned managed identities](https://learn.microsoft.com/azure/active-directory/managed-identities-azure-resources/how-manage-user-assigned-managed-identities)
- [Key Vault trusted services](https://learn.microsoft.com/azure/key-vault/general/overview-vnet-service-endpoints#trusted-services)
- [Key Vault RBAC roles](https://learn.microsoft.com/azure/key-vault/general/rbac-guide#azure-built-in-roles-for-key-vault-data-plane-operations)
- Related: [security-cmk-encryption](security-cmk-encryption.md), [security-private-endpoint](security-private-endpoint.md)
