#!/usr/bin/env bash
# Deploy an Azure DocumentDB cluster from main.bicep with preflight checks.
#
# Usage:
#   ./deploy.sh <resource-group> <location> [parameters-file]
#
# Example:
#   ./deploy.sh rg-docdb-dev eastus2 main.parameters.sample.json

set -euo pipefail

RG="${1:-}"
LOCATION="${2:-}"
PARAMS_FILE="${3:-}"

die()  { printf '\033[31m[error]\033[0m %s\n' "$*" >&2; exit 1; }
info() { printf '\033[36m[info]\033[0m  %s\n' "$*"; }
ok()   { printf '\033[32m[ok]\033[0m    %s\n' "$*"; }
warn() { printf '\033[33m[warn]\033[0m  %s\n' "$*"; }

[[ -n "$RG" && -n "$LOCATION" ]] || die "usage: $0 <resource-group> <location> [parameters-file]"

# ---------------------------------------------------------------------------
# Step 0 — preflight checks
# ---------------------------------------------------------------------------
info "Preflight checks..."

command -v az >/dev/null 2>&1 || die "Azure CLI ('az') not found. Install: https://learn.microsoft.com/cli/azure/install-azure-cli"
ok "Azure CLI found: $(az version --query '"azure-cli"' -o tsv)"

if ! az account show >/dev/null 2>&1; then
  warn "Not signed in to Azure. Launching 'az login'..."
  az login >/dev/null
fi
SUB_NAME=$(az account show --query name -o tsv)
SUB_ID=$(az account show --query id -o tsv)
ok "Signed in to subscription: $SUB_NAME ($SUB_ID)"

REG_STATE=$(az provider show --namespace Microsoft.DocumentDB --query registrationState -o tsv 2>/dev/null || echo "NotRegistered")
if [[ "$REG_STATE" != "Registered" ]]; then
  warn "Microsoft.DocumentDB provider is '$REG_STATE' — registering..."
  az provider register --namespace Microsoft.DocumentDB >/dev/null
  for _ in {1..60}; do
    REG_STATE=$(az provider show --namespace Microsoft.DocumentDB --query registrationState -o tsv)
    [[ "$REG_STATE" == "Registered" ]] && break
    sleep 5
  done
  [[ "$REG_STATE" == "Registered" ]] || die "Provider registration timed out (state: $REG_STATE)"
fi
ok "Microsoft.DocumentDB provider: Registered"

if ! az group show --name "$RG" >/dev/null 2>&1; then
  info "Resource group '$RG' does not exist — creating in $LOCATION..."
  az group create --name "$RG" --location "$LOCATION" >/dev/null
  ok "Created resource group: $RG"
else
  ok "Resource group exists: $RG"
fi

# ---------------------------------------------------------------------------
# Step 1 — summarise intended deployment and confirm
# ---------------------------------------------------------------------------
if [[ -n "$PARAMS_FILE" ]]; then
  [[ -f "$PARAMS_FILE" ]] || die "Parameters file not found: $PARAMS_FILE"
  info "Parameters file: $PARAMS_FILE"
else
  warn "No parameters file provided — main.bicep defaults will apply:"
  warn "    computeTier   = M30           (production-class; not free tier)"
  warn "    storageSizeGb = 128 GiB"
  warn "    haTargetMode  = ZoneRedundant (requires M30+)"
  warn "    shardCount    = 1"
  warn "For dev/test, re-run with: $0 $RG $LOCATION main.parameters.dev.json"
fi

if [[ -t 0 && "${SKIP_CONFIRM:-0}" != "1" ]]; then
  read -r -p "Proceed with deployment to '$RG' in '$LOCATION'? [y/N] " REPLY
  case "$REPLY" in
    y|Y|yes|YES) ;;
    *) die "Aborted by user." ;;
  esac
fi

# ---------------------------------------------------------------------------
# Step 2 — deploy
# ---------------------------------------------------------------------------
DEPLOY_ARGS=(--resource-group "$RG" --template-file "$(dirname "$0")/main.bicep")
if [[ -n "$PARAMS_FILE" ]]; then
  DEPLOY_ARGS+=(--parameters "@$PARAMS_FILE")
else
  info "You'll be prompted for adminUsername and adminPassword."
fi

info "Deploying cluster (this typically takes 8–12 minutes)..."
az deployment group create "${DEPLOY_ARGS[@]}" \
  --query "properties.outputs" \
  --output json

ok "Deployment complete. Retrieve the connection string from: Azure portal -> cluster -> Connection strings"
