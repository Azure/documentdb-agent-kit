---
name: documentdb-security
description: Security best practices for Azure DocumentDB — TLS enforcement, Private Endpoint / firewall configuration, two-level access control (Azure RBAC on the `mongoCluster` resource + Microsoft Entra ID OIDC authentication with MongoDB database roles for data-plane access), token-lifetime / revocation handling, and customer-managed keys (CMK) for encryption at rest. Use when reviewing production security posture, configuring networking, setting up authentication / authorization, granting per-app least-privilege access, revoking compromised tokens, or preparing for compliance audits.
license: MIT
---

# Security — Azure DocumentDB

Core controls: TLS on the wire, network isolation with Private Endpoint, **two-level access control** (Azure RBAC for the cluster resource + Entra ID + MongoDB database roles for data), and CMK for data-at-rest encryption on regulated workloads.

## Two-level access model

Azure DocumentDB separates **who can manage the cluster as an Azure resource** from **who can read/write data inside it**:

| Layer | What it controls | Granted via |
|---|---|---|
| **Azure RBAC** (control-plane) | Read cluster metadata, list connection strings, manage firewall rules, manage private endpoints, register/remove Entra users | Role assignments on `Microsoft.DocumentDB/mongoClusters/*` actions |
| **Database roles** (data-plane) | Read/write documents, run queries, create collections | MongoDB roles (`readWriteAnyDatabase`, `clusterAdmin`, `readAnyDatabase`, `root`) mapped to a registered Entra principal or native user |

A principal needs both layers for end-to-end access, and they are managed independently.

## Rules

- [security-tls-required](security-tls-required.md) — Always connect with TLS; never disable certificate validation in production.
- [security-private-endpoint](security-private-endpoint.md) — Use Private Endpoint / firewall rules; disable public network access where possible.
- [security-firewall-rules](security-firewall-rules.md) — IP firewall rules in CIDR form; "Allow Azure services" toggle; ~15-minute propagation delay; avoid the `0.0.0.0-255.255.255.255` shortcut.
- [security-entra-rbac](security-entra-rbac.md) — Enable Microsoft Entra ID authentication, register principals as `mongoClusters/users`, connect with `MONGODB-OIDC`; prefer managed identities over passwords.
- [security-azure-rbac-actions](security-azure-rbac-actions.md) — Azure resource-level RBAC: actions exposed by `Microsoft.DocumentDB/mongoClusters/*`, custom-role pattern, control-plane least-privilege.
- [security-database-roles](security-database-roles.md) — MongoDB database roles for data-plane access: `readWriteAnyDatabase` + `clusterAdmin` must be granted together for read-write; `readAnyDatabase` for read-only; secondary-user management via mongo shell.
- [security-token-lifetime-revocation](security-token-lifetime-revocation.md) — Entra access tokens are valid up to ~90 minutes from issuance even after the principal is disabled; revoke data-plane access immediately by deleting the `mongoClusters/users/<principal-id>` resource.
- [security-cmk-encryption](security-cmk-encryption.md) — Use customer-managed keys (CMK) for data-at-rest encryption on regulated workloads.

