# security-entra-rbac

**Category:** Security · **Priority:** MEDIUM

## Why it matters

Long-lived database passwords in app config or Key Vault entries are a persistent attack surface: they leak, get checked into code, and rotate poorly. Azure DocumentDB supports **Microsoft Entra ID (Azure AD) authentication with role-based access control (RBAC)**, so apps can authenticate with a managed identity and receive short-lived tokens — no secrets to rotate.

For shared-secret scenarios, create **secondary users** with least-privilege roles instead of using the admin account from applications.

## Incorrect

```javascript
// Hard-coded admin creds in config
const uri = `mongodb+srv://admin:SuperSecret123@prod-ddb.mongocluster.documentdb.azure.com/?tls=true`;
```

## Correct

Use a managed identity via Entra + RBAC:

```javascript
// Node example — use the driver's Entra auth mechanism
// (verify current driver support/spec in the official docs)
const client = new MongoClient(uri, {
  authMechanism: "MONGODB-OIDC", // or the current documented mechanism
  // credentialProvider: Azure Managed Identity
  tls: true
});
```

Or, if you must use SCRAM auth, create a dedicated least-privilege user:

```javascript
// As admin, create a per-app user with only what it needs
db.adminCommand({
  createUser: "orders-api",
  pwd: passwordFromKeyVault,
  roles: [
    { role: "readWrite", db: "orders" }
  ]
});
```

Rotate secondary-user passwords on a schedule; prefer Entra when available.

## References

- [Use Microsoft Entra ID and role-based access control](https://learn.microsoft.com/azure/documentdb/how-to-connect-role-based-access-control)
- [Create secondary users](https://learn.microsoft.com/azure/documentdb/secondary-users)
