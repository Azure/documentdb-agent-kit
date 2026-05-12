# security-azure-rbac-actions

**Category:** Security · **Priority:** MEDIUM

## Why it matters

Azure DocumentDB exposes its cluster as an Azure resource of type `Microsoft.DocumentDB/mongoClusters`. **Azure role-based access control** governs *resource-level* operations — reading cluster metadata, listing connection strings, managing firewall rules, managing private endpoints, and registering/removing users. This is independent of the database-level roles that control data-plane access (see [security-database-roles](security-database-roles.md)).

Following the two-level access model:

- **Use built-in Azure roles** (Reader, Contributor, Owner) for broad personas.
- **Use a custom role** scoped to the `Microsoft.DocumentDB/mongoClusters/*` actions when a persona needs cluster-management rights without subscription-wide access.
- **Never** rely on Azure role assignments alone to grant data access — data-plane authorization is governed by Entra principal registration + MongoDB database roles.

## Actions available on `Microsoft.DocumentDB/mongoClusters`

| Action | Description |
|---|---|
| `Microsoft.DocumentDB/mongoClusters/read` | Read a cluster resource or list clusters |
| `Microsoft.DocumentDB/mongoClusters/write` | Create / update cluster properties or tags |
| `Microsoft.DocumentDB/mongoClusters/delete` | Delete a cluster |
| `Microsoft.DocumentDB/mongoClusters/listConnectionStrings/action` | List connection strings (read access to credentials!) |
| `Microsoft.DocumentDB/mongoClusters/PrivateEndpointConnectionsApproval/action` | Approve a private endpoint connection |
| `Microsoft.DocumentDB/mongoClusters/firewallRules/{read,write,delete}` | Manage firewall rules |
| `Microsoft.DocumentDB/mongoClusters/privateEndpointConnections/{read,write,delete}` | Manage private endpoint connections |
| `Microsoft.DocumentDB/mongoClusters/privateEndpointConnectionProxies/{read,write,delete,validate/action}` | Manage private endpoint connection proxies |
| `Microsoft.DocumentDB/mongoClusters/privateLinkResources/read` | Read private link resources |
| `Microsoft.DocumentDB/mongoClusters/users/{read,write,delete}` | Register / remove Entra principals on the cluster |

> ⚠️ `listConnectionStrings/action` returns the **administrator connection string** including the password (for native-auth clusters). Treat it as a secret-grade action and grant it sparingly.

## Incorrect

Giving an application's service principal the subscription-scoped Contributor role just to "let it read its own connection string":

```bash
# Massively over-broad — grants write on everything in the subscription.
az role assignment create \
  --assignee "<sp-object-id>" \
  --role "Contributor" \
  --scope "/subscriptions/<sub-id>"
```

Using subscription-scoped custom roles when resource-group or resource scope would do:

```bicep
assignableScopes: [ subscription().id ]    // too broad for an app role
```

## Correct

### Pattern 1 — built-in roles for the common cases

| Persona | Built-in Azure role | Scope |
|---|---|---|
| Read-only operator (dashboards, audits) | **Reader** | Cluster resource |
| Cluster operator (resize, firewall) | **Contributor** | Cluster resource |
| Full owner (delete, role assignments) | **Owner** | Resource group |

### Pattern 2 — custom role for cluster-management only

For an SRE or automation principal that needs to manage clusters but not other Azure resources, define a custom role at resource-group scope:

```bicep
metadata description = 'RBAC definition for Azure DocumentDB cluster management.'

@description('Name of the role definition.')
param roleDefinitionName string = 'Azure DocumentDB RBAC Owner'

@description('Description of the role definition.')
param roleDefinitionDescription string = 'Can perform all Azure role-based access control actions for Azure DocumentDB clusters.'

resource definition 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: guid(subscription().id, resourceGroup().id, roleDefinitionName)
  scope: resourceGroup()
  properties: {
    roleName: roleDefinitionName
    description: roleDefinitionDescription
    type: 'CustomRole'
    permissions: [
      {
        actions: [
          'Microsoft.DocumentDb/mongoClusters/*'
        ]
      }
    ]
    assignableScopes: [
      resourceGroup().id
    ]
  }
}

output definitionId string = definition.id
```

Assign it to a principal:

```bicep
resource assignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(subscription().id, resourceGroup().id, roleDefinitionId, identityId)
  scope: resourceGroup()
  properties: {
    roleDefinitionId: roleDefinitionId
    principalId: identityId
  }
}
```

Terraform equivalent:

```terraform
resource "azurerm_role_definition" "control_plane" {
  name        = "Azure DocumentDB RBAC Owner"
  scope       = data.azurerm_resource_group.existing.id
  description = "Can perform all Azure role-based access control actions for Azure DocumentDB clusters."

  permissions {
    actions = [ "Microsoft.DocumentDB/mongoClusters/*" ]
  }

  assignable_scopes = [ data.azurerm_resource_group.existing.id ]
}

resource "azurerm_role_assignment" "control_plane" {
  scope              = data.azurerm_resource_group.existing.id
  role_definition_id = azurerm_role_definition.control_plane.role_definition_resource_id
  principal_id       = var.identity_id
}
```

### Pattern 3 — narrow custom role for an automation principal

If a CI/CD identity should only register users on existing clusters (not create or delete clusters), restrict the actions:

```bicep
permissions: [
  {
    actions: [
      'Microsoft.DocumentDB/mongoClusters/read'
      'Microsoft.DocumentDB/mongoClusters/users/read'
      'Microsoft.DocumentDB/mongoClusters/users/write'
      'Microsoft.DocumentDB/mongoClusters/users/delete'
    ]
  }
]
```

## References

- [Azure RBAC custom roles](https://learn.microsoft.com/azure/role-based-access-control/custom-roles)
- [Connect using role-based access control and Microsoft Entra ID](https://learn.microsoft.com/azure/documentdb/how-to-connect-role-based-access-control)
