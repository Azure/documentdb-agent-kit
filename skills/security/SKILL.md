---
name: documentdb-security
description: Security best practices for Azure DocumentDB — TLS enforcement, Private Endpoint / firewall configuration, Microsoft Entra ID + RBAC for authentication, and customer-managed keys (CMK) for encryption at rest. Use when reviewing production security posture, configuring networking, setting up authentication / authorization, or preparing for compliance audits.
license: MIT
---

# Security — Azure DocumentDB

Core controls: TLS on the wire, network isolation with Private Endpoint, Microsoft Entra ID for identity, and CMK for data-at-rest encryption on regulated workloads.

## Rules

- [security-tls-required](security-tls-required.md) — Always connect with TLS; never disable certificate validation in production.
- [security-private-endpoint](security-private-endpoint.md) — Use Private Endpoint / firewall rules; disable public network access where possible.
- [security-entra-rbac](security-entra-rbac.md) — Prefer Microsoft Entra ID + RBAC over long-lived passwords; create per-app secondary users with least privilege.
- [security-cmk-encryption](security-cmk-encryption.md) — Use customer-managed keys (CMK) for data-at-rest encryption on regulated workloads.
