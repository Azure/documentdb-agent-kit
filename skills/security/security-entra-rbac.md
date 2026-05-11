# security-entra-rbac

**Category:** Security · **Priority:** HIGH

## Why it matters

Long-lived database passwords in app config or Key Vault entries are a persistent attack surface — they leak, get checked into code, and rotate poorly. Azure DocumentDB supports **Microsoft Entra ID** authentication (via OIDC) so apps can authenticate with a **managed identity** and receive short-lived tokens — no secrets to rotate. Entra-authenticated principals also benefit from centralized credential management, MFA, passwordless sign-in, and uniform identity across Azure services.

Authentication on Azure DocumentDB is **non-disruptive to toggle** — you can enable or change auth methods on a running cluster without a restart. Every cluster is created with native authentication enabled and one built-in admin user; the supported configurations are:

- **NativeAuth only** (default at create time — native must always be enabled when the cluster is created)
- **MicrosoftEntraID only** (native can be disabled *after* the cluster is provisioned)
- **NativeAuth + MicrosoftEntraID** (most common; recommended during migration)

Once Entra is enabled, you register Entra principals (users, service principals, system- or user-assigned managed identities, workload identities) on the cluster as Azure resources of type `Microsoft.DocumentDB/mongoClusters/users` and map them to MongoDB database roles. Multiple admin principals of different types can coexist.

## Incorrect

Hard-coded admin credentials in a connection string:

```javascript
const uri = `mongodb+srv://admin:SuperSecret123@prod-ddb.mongocluster.cosmos.azure.com/?tls=true`;
```

Registering an app's service principal with `root` on `admin` "just in case":

```bicep
// Over-privileged — any data-plane bug now executes with cluster-wide admin.
resource user 'Microsoft.DocumentDB/mongoClusters/users@2025-09-01' = {
  name: '${clusterName}/users/${appPrincipalId}'
  properties: {
    identityProvider: {
      type: 'Microsoft.EntraID'
      properties: { principalType: 'ServicePrincipal' }
    }
    roles: [ { db: 'admin', role: 'root' } ]    // ← grants everything
  }
}
```

## Correct

### 1. Enable Entra auth on the cluster

Add `MicrosoftEntraID` to `authConfig.allowedModes` (keep `NativeAuth` during migration; remove it later if policy allows):

```bicep
resource cluster 'Microsoft.DocumentDB/mongoClusters@2025-09-01' = {
  name: clusterName
  location: location
  properties: {
    authConfig: {
      allowedModes: [
        'MicrosoftEntraID'
        'NativeAuth'
      ]
    }
  }
}
```

Or via Azure CLI:

```bash
az resource patch \
  --resource-group "<rg>" \
  --name "<cluster-name>" \
  --resource-type "Microsoft.DocumentDB/mongoClusters" \
  --properties '{"authConfig":{"allowedModes":["MicrosoftEntraID","NativeAuth"]}}' \
  --latest-include-preview
```

### 2. Register the principal on the cluster with a least-privilege database role

```bicep
@allowed([ 'User', 'ServicePrincipal', 'ManagedIdentity' ])
param principalType string = 'ManagedIdentity'
param principalId string                   // object ID of the Entra principal
param dbName string = 'sales'

resource user 'Microsoft.DocumentDB/mongoClusters/users@2025-09-01' = {
  name: '${clusterName}/users/${principalId}'
  properties: {
    identityProvider: {
      type: 'Microsoft.EntraID'
      properties: { principalType: principalType }
    }
    roles: [
      { db: dbName, role: 'readWrite' }    // scoped to one database
    ]
  }
}
```

For role-shape details (`readWriteAnyDatabase` + `clusterAdmin` must be granted together; `readAnyDatabase` for read-only) see [security-database-roles](security-database-roles.md).

### 3. Connect using `MONGODB-OIDC`

Use the global SRV host so the connection automatically follows promotion in multi-cluster setups:

```
mongodb+srv://<client-id>@<cluster-name>.global.mongocluster.cosmos.azure.com/?tls=true&authMechanism=MONGODB-OIDC&retrywrites=false&maxIdleTimeMS=120000
```

Required driver settings:

| Option | Value |
|---|---|
| `scheme` | `mongodb+srv` |
| `host` | `<cluster>.global.mongocluster.cosmos.azure.com` (or `<cluster>.mongocluster.cosmos.azure.com`) |
| `tls` | `true` |
| `authMechanism` | `MONGODB-OIDC` |
| `retrywrites` | `false` |
| `maxIdleTimeMS` | `120000` |

#### Python — `DefaultAzureCredential` + OIDC callback

```python
class AzureIdentityTokenCallback(OIDCCallback):
    def __init__(self, credential):
        self.credential = credential

    def fetch(self, context: OIDCCallbackContext) -> OIDCCallbackResult:
        token = self.credential.get_token(
            "https://ossrdbms-aad.database.windows.net/.default").token
        return OIDCCallbackResult(access_token=token)

credential = DefaultAzureCredential()
authProperties = {"OIDC_CALLBACK": AzureIdentityTokenCallback(credential)}

client = MongoClient(
  f"mongodb+srv://{clusterName}.global.mongocluster.cosmos.azure.com/",
  connectTimeoutMS=120000,
  tls=True,
  retryWrites=True,
  authMechanism="MONGODB-OIDC",
  authMechanismProperties=authProperties,
)
```

#### TypeScript / Node

```typescript
const callback = async (params: OIDCCallbackParams, credential: TokenCredential): Promise<OIDCResponse> => {
  const tokenResponse = await credential.getToken(['https://ossrdbms-aad.database.windows.net/.default']);
  return {
    accessToken: tokenResponse?.token || '',
    expiresInSeconds: (tokenResponse?.expiresOnTimestamp || 0) - Math.floor(Date.now() / 1000),
  };
};

const credential = new DefaultAzureCredential();
const client = new MongoClient(
  `mongodb+srv://${clusterName}.global.mongocluster.cosmos.azure.com/`,
  {
    connectTimeoutMS: 120000,
    tls: true,
    retryWrites: true,
    authMechanism: 'MONGODB-OIDC',
    authMechanismProperties: {
      OIDC_CALLBACK: (params) => callback(params, credential),
      ALLOWED_HOSTS: ['*.azure.com'],
    },
  },
);
```

#### C# / .NET

```csharp
DefaultAzureCredential credential = new();
AzureIdentityTokenHandler tokenHandler = new(credential, tenantId);

MongoUrl url = MongoUrl.Create($"mongodb+srv://{clusterName}.global.mongocluster.cosmos.azure.com/");
MongoClientSettings settings = MongoClientSettings.FromUrl(url);
settings.UseTls = true;
settings.RetryWrites = false;
settings.MaxConnectionIdleTime = TimeSpan.FromMinutes(2);
settings.Credential = MongoCredential.CreateOidcCredential(tokenHandler);
settings.Freeze();

MongoClient client = new(settings);
```

The OIDC callback acquires a token for the scope `https://ossrdbms-aad.database.windows.net/.default` (same OAuth resource used by Azure Database for PostgreSQL / MySQL — this is by design and required).

## Authentication on replica clusters

Authentication methods are managed **independently** on the primary and replica clusters. Users and managed identities are managed on the primary and synchronized to the replica; auth-mode toggles are not. **Gotcha:** if native auth is disabled on the primary at the moment the replica is created, you cannot enable native auth on the replica without first promoting it. See `high-availability/ha-cross-region-replica.md`.

## References

- [Connect using role-based access control and Microsoft Entra ID](https://learn.microsoft.com/azure/documentdb/how-to-connect-role-based-access-control)
- [Create secondary users](https://learn.microsoft.com/azure/documentdb/secondary-users)
- Related: [security-azure-rbac-actions](security-azure-rbac-actions.md), [security-database-roles](security-database-roles.md), [security-token-lifetime-revocation](security-token-lifetime-revocation.md)
