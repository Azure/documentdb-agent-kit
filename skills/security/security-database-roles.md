# security-database-roles

**Category:** Security · **Priority:** HIGH

## Why it matters

Once an Entra principal (or a native user) is registered on an Azure DocumentDB cluster, **MongoDB database roles** decide what it can actually do with data. Azure DocumentDB exposes the standard MongoDB role names but applies them with a few cluster-specific rules that are easy to get wrong:

- **Full read-write at cluster scope requires *two* roles together**: `readWriteAnyDatabase` *and* `clusterAdmin`. You cannot grant either of them alone for full read-write — they must both be present.
- `readAnyDatabase` is the read-only equivalent at cluster scope.
- For per-database least privilege, use `readWrite` or `read` scoped to a specific `db`.
- Administrative privileges = `{ db: 'admin', role: 'root' }`. Reserve this for genuine cluster administrators.
- **Non-admin (secondary) users — including Entra ones — cannot create, delete, or update other users.** Only admin principals can. Native non-admin users can change their own password but nothing else.

| Provider | Role(s) | CreateUser | DeleteUser | UpdateUser | ListUser |
|---|---|---|---|---|---|
| Microsoft Entra ID | `readWriteAnyDatabase` + `clusterAdmin` | ❌ | ❌ | ❌ | ✔️ |
| Microsoft Entra ID | `readAnyDatabase` | ❌ | ❌ | ❌ | ✔️ |
| Native DocumentDB | `readWriteAnyDatabase` + `clusterAdmin` | ❌ | ❌ | Own password only | ✔️ |
| Native DocumentDB | `readAnyDatabase` | ❌ | ❌ | Own password only | ✔️ |

## Incorrect

Granting `readWriteAnyDatabase` alone and expecting full write access:

```bicep
roles: [
  { db: 'admin', role: 'readWriteAnyDatabase' }   // ← incomplete, must also include clusterAdmin
]
```

Granting `root` for an app that only needs to write to one database:

```bicep
// Anti-pattern — single-DB workloads should never be assigned root.
roles: [
  { db: 'admin', role: 'root' }
]
```

Trying to drop a user from a non-admin session:

```javascript
// Will fail — only admin principals can manage users.
db.runCommand({ dropUser: "<some-other-user>" });
```

## Correct

### Per-database least privilege (preferred for apps)

```bicep
resource appUser 'Microsoft.DocumentDB/mongoClusters/users@2025-09-01' = {
  name: '${clusterName}/users/${appPrincipalId}'
  properties: {
    identityProvider: {
      type: 'Microsoft.EntraID'
      properties: { principalType: 'ManagedIdentity' }
    }
    roles: [
      { db: 'orders', role: 'readWrite' }    // only the database the app actually needs
    ]
  }
}
```

### Cluster-wide read-write (operational roles, migration tools)

Both roles must be present:

```bicep
roles: [
  { db: 'admin', role: 'readWriteAnyDatabase' }
  { db: 'admin', role: 'clusterAdmin' }       // required alongside readWriteAnyDatabase
]
```

### Read-only (reporting, BI, audit)

```bicep
roles: [
  { db: 'admin', role: 'readAnyDatabase' }
]
```

### Administrative (rarely used for non-humans)

```bicep
roles: [
  { db: 'admin', role: 'root' }
]
```

## Manage secondary (non-admin) users via the mongo shell

Sign in as an admin principal first, then run management commands. The `customData.IdentityProvider` field marks the principal type for Entra users; native users omit it.

Add a non-admin Entra user with cluster-wide read-write:

```javascript
db.runCommand({
  createUser: "<entra-object-id>",
  roles: [
    { role: "clusterAdmin",         db: "admin" },
    { role: "readWriteAnyDatabase", db: "admin" }
  ],
  customData: {
    IdentityProvider: {
      type: "MicrosoftEntraID",
      properties: { principalType: "user" }   // or "servicePrincipal" / "ManagedIdentity"
    }
  }
});
```

Add a non-admin Entra user with cluster-wide read-only:

```javascript
db.runCommand({
  createUser: "<entra-object-id>",
  roles: [
    { role: "readAnyDatabase", db: "admin" }
  ],
  customData: {
    IdentityProvider: {
      type: "MicrosoftEntraID",
      properties: { principalType: "user" }
    }
  }
});
```

Remove a non-admin user:

```javascript
db.runCommand({ dropUser: "<entra-object-id>" });
```

List all users on the cluster (Entra + native, admin + non-admin):

```javascript
db.runCommand({ usersInfo: 1 });
```

> Admin Entra principals are also registered as Azure resources under `Microsoft.DocumentDB/mongoClusters/users` and replicated to the database. Non-admin Entra principals managed via the mongo shell are **not** registered as Azure resources and won't appear in the Azure portal user list — they only show up in `usersInfo`.

## References

- [Connect using role-based access control and Microsoft Entra ID](https://learn.microsoft.com/azure/documentdb/how-to-connect-role-based-access-control)
- [Create secondary users](https://learn.microsoft.com/azure/documentdb/secondary-users)
- MongoDB docs: [Built-in roles](https://www.mongodb.com/docs/manual/reference/built-in-roles/)
