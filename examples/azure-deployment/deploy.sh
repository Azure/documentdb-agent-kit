#!/usr/bin/env bash
# Deploy an Azure DocumentDB cluster from main.bicep with preflight checks.
#
# Usage:
#   Interactive (recommended first time):
#     ./deploy.sh
#
#   Semi-interactive (skip subscription picker):
#     ./deploy.sh <resource-group> <location> [parameters-file]
#
# Example:
#   ./deploy.sh rg-docdb-dev eastus2 main.parameters.dev.json

set -euo pipefail

RG="${1:-}"
LOCATION="${2:-}"
PARAMS_FILE="${3:-}"

die()  { printf '\033[31m[error]\033[0m %s\n' "$*" >&2; exit 1; }
info() { printf '\033[36m[info]\033[0m  %s\n' "$*"; }
ok()   { printf '\033[32m[ok]\033[0m    %s\n' "$*"; }
warn() { printf '\033[33m[warn]\033[0m  %s\n' "$*"; }
ask()  { printf '\033[35m[ask]\033[0m   %s ' "$*"; }

# Prompt the user to pick a numbered item from a newline-separated list (printed to stdout).
# Echoes the chosen line on stdout. Usage: chosen=$(pick "$items" "Pick one:")
pick() {
  local items="$1" prompt="$2"
  local -a arr
  mapfile -t arr <<< "$items"
  local n=${#arr[@]}
  [[ $n -gt 0 ]] || die "Nothing to pick from."
  printf '\n' >&2
  local i=0
  for item in "${arr[@]}"; do
    i=$((i+1))
    printf '  %2d) %s\n' "$i" "$item" >&2
  done
  printf '\n' >&2
  while true; do
    ask "$prompt [1-$n]:" >&2
    read -r choice
    if [[ "$choice" =~ ^[0-9]+$ ]] && (( choice >= 1 && choice <= n )); then
      printf '%s' "${arr[$((choice-1))]}"
      return
    fi
    warn "Invalid choice."
  done
}

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

# ---------------------------------------------------------------------------
# Step 1 — pick subscription
# ---------------------------------------------------------------------------
SUBS=$(az account list --query "[?state=='Enabled'].{display: join(' | ', [name, id])}" -o tsv)
[[ -n "$SUBS" ]] || die "No enabled subscriptions found for this account."
SUB_COUNT=$(printf '%s\n' "$SUBS" | wc -l | tr -d ' ')

if [[ "$SUB_COUNT" -eq 1 ]]; then
  SUB_CHOICE="$SUBS"
  SUB_ID="${SUB_CHOICE##* | }"
  SUB_NAME="${SUB_CHOICE% | *}"
  info "Only one subscription available: $SUB_NAME"
else
  info "Available subscriptions:"
  SUB_CHOICE=$(pick "$SUBS" "Pick a subscription")
  SUB_ID="${SUB_CHOICE##* | }"
  SUB_NAME="${SUB_CHOICE% | *}"
fi
az account set --subscription "$SUB_ID"
ok "Using subscription: $SUB_NAME ($SUB_ID)"

# Provider registration (subscription-scoped, so must come after we pick the sub)
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

# ---------------------------------------------------------------------------
# Step 2 — pick (or create) resource group
# ---------------------------------------------------------------------------
if [[ -z "$RG" ]]; then
  EXISTING_RGS=$(az group list --query "[].{display: join(' | ', [name, location])}" -o tsv 2>/dev/null || true)
  MENU=""
  if [[ -n "$EXISTING_RGS" ]]; then
    MENU="$EXISTING_RGS"$'\n'"<create new resource group>"
  else
    MENU="<create new resource group>"
  fi
  info "Resource groups in '$SUB_NAME':"
  RG_CHOICE=$(pick "$MENU" "Pick a resource group")
  if [[ "$RG_CHOICE" == "<create new resource group>" ]]; then
    ask "New resource group name:"
    read -r RG
    [[ -n "$RG" ]] || die "Resource group name required."
  else
    RG="${RG_CHOICE% | *}"
    LOCATION_FROM_RG="${RG_CHOICE##* | }"
    LOCATION="${LOCATION:-$LOCATION_FROM_RG}"
    info "Using existing resource group '$RG' in '$LOCATION_FROM_RG'"
  fi
fi

# ---------------------------------------------------------------------------
# Step 3 — pick location (only needed when the RG doesn't exist yet)
# ---------------------------------------------------------------------------
if ! az group show --name "$RG" >/dev/null 2>&1; then
  if [[ -z "$LOCATION" ]]; then
    info "Regions that support Microsoft.DocumentDB/mongoClusters:"
    LOCS=$(az provider show --namespace Microsoft.DocumentDB \
      --query "resourceTypes[?resourceType=='mongoClusters'].locations[]" -o tsv | sort -u)
    [[ -n "$LOCS" ]] || die "Could not fetch supported regions."
    LOCATION=$(pick "$LOCS" "Pick a region")
  fi
  info "Creating resource group '$RG' in '$LOCATION'..."
  az group create --name "$RG" --location "$LOCATION" >/dev/null
  ok "Created resource group: $RG"
else
  if [[ -z "$LOCATION" ]]; then
    LOCATION=$(az group show --name "$RG" --query location -o tsv)
  fi
  ok "Resource group exists: $RG (location: $LOCATION)"
fi

# ---------------------------------------------------------------------------
# Step 4 — summarise intended deployment and confirm
# ---------------------------------------------------------------------------
if [[ -n "$PARAMS_FILE" ]]; then
  [[ -f "$PARAMS_FILE" ]] || die "Parameters file not found: $PARAMS_FILE"
  info "Parameters file: $PARAMS_FILE"
else
  warn "No parameters file provided — main.bicep defaults will apply:"
  warn "    computeTier   = M30           (production-class; not free tier)"
  warn "    storageSizeGb = 128 GiB"
  warn "    haTargetMode  = ZoneRedundantPreferred (requires M30+)"
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
# Step 5 — deploy
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
