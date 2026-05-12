---
name: documentdb-security
description: Security best practices for Azure DocumentDB — TLS enforcement, Private Endpoint / firewall configuration, two-level access control (Azure RBAC on the `mongoCluster` resource + Microsoft Entra ID OIDC authentication with MongoDB database roles for data-plane access), token-lifetime / revocation handling, and customer-managed keys (CMK) for encryption at rest. Use when reviewing production security posture, configuring networking, setting up authentication / authorization, granting per-app least-privilege access, revoking compromised tokens, or preparing for compliance audits.
license: MIT
---

# Security — Azure DocumentDB

Core controls: TLS on the wire, network isolation with Private Endpoint, **two-level access control** (Azure RBAC for the cluster resource + Entra ID + MongoDB database roles for data), and CMK for data-at-rest encryption on regulated workloads.

## Defense-in-depth checklist

A production cluster should have all eight layers in place:

| Layer | Default | Production recommendation | Rule |
|---|---|---|---|
| **Network** | Public access + firewall rules | Private Endpoint; public access disabled; firewall ≠ `0.0.0.0/0` | [`security-private-endpoint`](security-private-endpoint.md), [`security-firewall-rules`](security-firewall-rules.md) |
| **Transport** | TLS up to 1.3 (always on) | TLS verified at client; `tlsAllowInvalidCertificates` never set | [`security-tls-required`](security-tls-required.md) |
| **Identity** | One built-in native admin | Entra ID enabled; managed identities per workload; admin password strong + rotated | [`security-entra-rbac`](security-entra-rbac.md), [`security-admin-password-and-identity-separation`](security-admin-password-and-identity-separation.md) |
| **Control-plane authorization** | Subscription-level Azure RBAC | Custom role scoped to `Microsoft.DocumentDB/mongoClusters/*` at resource-group scope | [`security-azure-rbac-actions`](security-azure-rbac-actions.md) |
| **Data-plane authorization** | One admin user | Per-database least-privilege roles; admin identity ≠ runtime identity | [`security-database-roles`](security-database-roles.md), [`security-admin-password-and-identity-separation`](security-admin-password-and-identity-separation.md) |
| **Encryption at rest** | Service-managed AES-256 | CMK for regulated workloads (Premium SSD v1 only — see `storage/`) | [`security-cmk-encryption`](security-cmk-encryption.md) |
| **Backups** | Automated, 35-day retention | Restore drills; understand 7-day post-deletion window | [`high-availability/ha-backup-retention`](../high-availability/ha-backup-retention.md) |
| **Incident response** | Audit + activity logs available | Token revocation playbook ready; monitoring alerts wired up | [`security-token-lifetime-revocation`](security-token-lifetime-revocation.md), [`monitoring/`](../monitoring/) |

## Two-level access model

Azure DocumentDB separates **who can manage the cluster as an Azure resource** from **who can read/write data inside it**:

| Layer | What it controls | Granted via |
|---|---|---|
| **Azure RBAC** (control-plane) | Read cluster metadata, list connection strings, manage firewall rules, manage private endpoints, register/remove Entra users | Role assignments on `Microsoft.DocumentDB/mongoClusters/*` actions |
| **Database roles** (data-plane) | Read/write documents, run queries, create collections | MongoDB roles (`readWriteAnyDatabase`, `clusterAdmin`, `readAnyDatabase`, `root`) mapped to a registered Entra principal or native user |

A principal needs both layers for end-to-end access, and they are managed independently. **Use different principals for the two layers** wherever practical — see [`security-admin-password-and-identity-separation`](security-admin-password-and-identity-separation.md).

## Rules

- [security-tls-required](security-tls-required.md) — Always connect with TLS; never disable certificate validation in production.
- [security-private-endpoint](security-private-endpoint.md) — Use Private Endpoint / firewall rules; disable public network access where possible.
- [security-firewall-rules](security-firewall-rules.md) — IP firewall rules in CIDR form; "Allow Azure services" toggle; ~15-minute propagation delay; avoid the `0.0.0.0-255.255.255.255` shortcut.
- [security-entra-rbac](security-entra-rbac.md) — Enable Microsoft Entra ID authentication, register principals as `mongoClusters/users`, connect with `MONGODB-OIDC`; prefer managed identities over passwords.
- [security-azure-rbac-actions](security-azure-rbac-actions.md) — Azure resource-level RBAC: actions exposed by `Microsoft.DocumentDB/mongoClusters/*`, custom-role pattern, control-plane least-privilege.
- [security-database-roles](security-database-roles.md) — MongoDB database roles for data-plane access: `readWriteAnyDatabase` + `clusterAdmin` must be granted together for read-write; `readAnyDatabase` for read-only; secondary-user management via mongo shell.
- [security-admin-password-and-identity-separation](security-admin-password-and-identity-separation.md) — Strong admin password policy (≥8 chars + complexity); use distinct Azure identities for control-plane vs data-plane to bound blast radius.
- [security-token-lifetime-revocation](security-token-lifetime-revocation.md) — Entra access tokens are valid up to ~90 minutes from issuance even after the principal is disabled; revoke data-plane access immediately by deleting the `mongoClusters/users/<principal-id>` resource.
- [security-cmk-encryption](security-cmk-encryption.md) — Use customer-managed keys (CMK) for data-at-rest encryption on regulated workloads.
- [security-cmk-troubleshooting](security-cmk-troubleshooting.md) — CMK operational runbook: causes of `Inaccessible` cluster state, ~60-minute revalidation window, managed-identity / key / vault recovery procedures, and provisioning-failure triage.

