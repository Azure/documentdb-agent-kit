# security-token-lifetime-revocation

**Category:** Security · **Priority:** HIGH

## Why it matters

When you authenticate to Azure DocumentDB with Microsoft Entra ID, the MongoDB driver presents an **OIDC access token** issued by Entra. That token has a finite lifetime — typically **up to ~90 minutes from issuance** — and remains valid for that full window even if:

- The Entra principal is **disabled** or **deleted** in the tenant.
- The associated **refresh token is revoked**.
- The cluster user resource (`mongoClusters/users/<principal-id>`) is **deleted**.

In other words, **the access-token lifetime is the maximum attack window if a token is compromised.** A malicious actor with a valid token can keep using it until expiry. This is a fundamental property of token-based auth — not specific to DocumentDB — but the response pattern is specific.

## Incorrect

Assuming that removing a principal from Entra immediately ends all sessions:

```bash
# This stops *new* tokens from being issued — it does NOT invalidate tokens
# already in flight, which can stay valid for up to ~90 minutes.
az ad user delete --id "<compromised-user>"
```

Treating "user deleted in Entra" as the only step in incident response:

```bash
# Missing the second half — the cluster user resource is still present,
# and any currently-valid token will still authenticate.
az ad sp delete --id "<compromised-app>"
```

## Correct

### Immediate revocation: a two-step pattern

To shrink the attack window as far as possible, do **both** of these as fast as possible:

1. **Revoke the principal's sign-in / refresh tokens in Entra** so no new access tokens can be issued — follow the [Microsoft Entra revoke-access guidance](https://learn.microsoft.com/entra/identity/users/users-revoke-access).
2. **Delete the cluster user resource** so the principal is no longer authorized as a DocumentDB user even if a still-valid access token is presented:

   ```bash
   az resource delete \
     --resource-group "<rg>" \
     --name "<cluster-name>/users/<principal-id>" \
     --resource-type "Microsoft.DocumentDB/mongoClusters/users" \
     --latest-include-preview
   ```

   Or via Bicep — deploy a template that omits the user resource (or use `existing` + `Microsoft.Authorization/locks` patterns for change control).

3. **Drop any non-admin entries from the mongo shell** (those aren't represented as Azure resources):

   ```javascript
   db.runCommand({ dropUser: "<entra-object-id>" });
   ```

After step 2, the user record is gone from the cluster metadata, so the principal is no longer a recognized DocumentDB user — even a still-valid Entra access token will fail authorization on subsequent operations.

### Treat connection-string actions as secret-grade

`Microsoft.DocumentDB/mongoClusters/listConnectionStrings/action` returns the administrator credentials for the native-auth admin user. Grant this action only to identities that absolutely need it, and audit its use. See [security-azure-rbac-actions](security-azure-rbac-actions.md).

### Prefer managed identities over service-principal secrets

Managed identities don't have client secrets that can leak. Use **system-assigned managed identity** when only one workload needs the identity; use **user-assigned managed identity** when several workloads share it.

### Limit token attack window where you can

- Use **Conditional Access policies** in Entra to require MFA / compliant device / corporate network on token issuance, raising the bar for an attacker even before revocation.
- Rotate workload identities periodically as defense-in-depth, even though they don't have static secrets.

## Operational checklist for a compromised principal

| Step | Where | Effect |
|---|---|---|
| 1. Revoke refresh tokens / disable account | Entra ID | No new access tokens issued |
| 2. Delete `mongoClusters/users/<principal-id>` resource | Azure RBAC | DocumentDB stops recognizing principal as a user |
| 3. `dropUser` non-admin entries via mongo shell | Database | Removes any shell-managed user records |
| 4. Rotate the cluster's native admin password if also exposed | Cluster | Closes the SCRAM/native fallback |
| 5. Audit `usersInfo` and Azure activity logs | Both | Confirm no residual access |

## References

- [Connect using role-based access control and Microsoft Entra ID — Access Token Validity](https://learn.microsoft.com/azure/documentdb/how-to-connect-role-based-access-control)
- [Revoke user access in Microsoft Entra ID](https://learn.microsoft.com/entra/identity/users/users-revoke-access)
- Related: [security-entra-rbac](security-entra-rbac.md), [security-database-roles](security-database-roles.md), [security-azure-rbac-actions](security-azure-rbac-actions.md)
