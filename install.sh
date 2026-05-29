#!/usr/bin/env bash
# documentdb-agent-kit installer (macOS / Linux)
# Installs DocumentDB skills + the microsoft/documentdb-mcp server into every
# detected MCP client.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Azure/documentdb-agent-kit/main/install.sh | bash
#   curl -fsSL .../install.sh | bash -s -- --uri "mongodb://localhost:27017" --yes
#   ./install.sh --dry-run
#   ./install.sh --uninstall
#
# Flags:
#   --uri <conn>        DocumentDB / MongoDB connection string (else prompts or uses $DOCUMENTDB_URI)
#   --yes               Non-interactive; never prompt
#   --dry-run           Print planned changes; write nothing
#   --uninstall         Remove the kit's MCP entries and skill symlinks; remove ~/.documentdb-agent-kit
#   --clients <list>    Comma-separated subset of: claude-code,claude-desktop,cursor,copilot-cli,gemini-cli
#   --skills-only       Install skills only; skip MCP server
#   --mcp-only          Install MCP server only; skip skills
#   --mcp-ref <ref>     Git ref of microsoft/documentdb-mcp to build (default: main)
#   --kit-ref <ref>     Git ref of Azure/documentdb-agent-kit to install (default: main)
#   --profile <name>    Name to use in CONNECTION_PROFILES (default: default)
#   -h, --help          Show this help

set -euo pipefail

# ---------- Constants ----------
readonly KIT_REPO="https://github.com/Azure/documentdb-agent-kit.git"
readonly MCP_REPO="https://github.com/microsoft/documentdb-mcp.git"
readonly INSTALL_ROOT="${HOME}/.documentdb-agent-kit"
readonly KIT_DIR="${INSTALL_ROOT}/agent-kit"
readonly MCP_DIR="${INSTALL_ROOT}/mcp-server"
readonly MCP_ENTRY="DocumentDB"
readonly SUPPORTED_CLIENTS=(claude-code claude-desktop cursor copilot-cli gemini-cli)
readonly MIN_NODE_MAJOR=20

# ---------- Defaults ----------
URI=""
YES=0
DRY_RUN=0
UNINSTALL=0
CLIENTS=""
SKILLS_ONLY=0
MCP_ONLY=0
MCP_REF="main"
KIT_REF="main"
PROFILE_NAME="default"

# ---------- Colors (only when TTY) ----------
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C_RED=$'\033[0;31m'; C_GRN=$'\033[0;32m'; C_YEL=$'\033[0;33m'
  C_BLU=$'\033[0;34m'; C_BLD=$'\033[1m'; C_DIM=$'\033[2m'; C_RST=$'\033[0m'
else
  C_RED=""; C_GRN=""; C_YEL=""; C_BLU=""; C_BLD=""; C_DIM=""; C_RST=""
fi

log()    { printf '%s\n' "$*"; }
info()   { printf '%s%s%s %s\n' "$C_BLU" "→" "$C_RST" "$*"; }
ok()     { printf '%s%s%s %s\n' "$C_GRN" "✓" "$C_RST" "$*"; }
warn()   { printf '%s%s%s %s\n' "$C_YEL" "!" "$C_RST" "$*" >&2; }
err()    { printf '%s%s%s %s\n' "$C_RED" "✗" "$C_RST" "$*" >&2; }
heading(){ printf '\n%s%s%s\n' "$C_BLD" "$*" "$C_RST"; }
dry()    { [ "$DRY_RUN" -eq 1 ] && printf '%s[dry-run]%s %s\n' "$C_DIM" "$C_RST" "$*"; }

# ---------- Arg parsing ----------
usage() {
  sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//' | head -30
}

while [ $# -gt 0 ]; do
  case "$1" in
    --uri)           URI="$2"; shift 2 ;;
    --yes|-y)        YES=1; shift ;;
    --dry-run)       DRY_RUN=1; shift ;;
    --uninstall)     UNINSTALL=1; shift ;;
    --clients)       CLIENTS="$2"; shift 2 ;;
    --skills-only)   SKILLS_ONLY=1; shift ;;
    --mcp-only)      MCP_ONLY=1; shift ;;
    --mcp-ref)       MCP_REF="$2"; shift 2 ;;
    --kit-ref)       KIT_REF="$2"; shift 2 ;;
    --profile)       PROFILE_NAME="$2"; shift 2 ;;
    -h|--help)       usage; exit 0 ;;
    *)               err "unknown flag: $1"; usage; exit 2 ;;
  esac
done

# ---------- OS detection ----------
OS="unknown"
case "$(uname -s)" in
  Darwin) OS="macos" ;;
  Linux)  OS="linux" ;;
  *)      err "unsupported OS: $(uname -s) (use install.ps1 on Windows)"; exit 1 ;;
esac

# ---------- Client config paths ----------
client_mcp_config_path() {
  case "$1" in
    claude-code)     printf '%s\n' "${HOME}/.claude.json" ;;
    claude-desktop)
      if [ "$OS" = "macos" ]; then
        printf '%s\n' "${HOME}/Library/Application Support/Claude/claude_desktop_config.json"
      else
        printf '%s\n' "${HOME}/.config/Claude/claude_desktop_config.json"
      fi
      ;;
    cursor)          printf '%s\n' "${HOME}/.cursor/mcp.json" ;;
    copilot-cli)     printf '%s\n' "${HOME}/.copilot/mcp-config.json" ;;
    gemini-cli)      printf '%s\n' "${HOME}/.gemini/settings.json" ;;
    *)               return 1 ;;
  esac
}

client_skills_dir() {
  case "$1" in
    claude-code)     printf '%s\n' "${HOME}/.claude/skills" ;;
    claude-desktop)
      if [ "$OS" = "macos" ]; then
        printf '%s\n' "${HOME}/Library/Application Support/Claude/skills"
      else
        printf '%s\n' "${HOME}/.config/Claude/skills"
      fi
      ;;
    *)               return 1 ;;
  esac
}

client_label() {
  case "$1" in
    claude-code)     printf 'Claude Code\n' ;;
    claude-desktop)  printf 'Claude Desktop\n' ;;
    cursor)          printf 'Cursor\n' ;;
    copilot-cli)     printf 'GitHub Copilot CLI\n' ;;
    gemini-cli)      printf 'Gemini CLI\n' ;;
  esac
}

# Some clients are "MCP-only" globally (skills are discovered from cwd files).
is_mcp_only_client() {
  case "$1" in
    cursor|copilot-cli|gemini-cli) return 0 ;;
    *) return 1 ;;
  esac
}

# ---------- Detection ----------
detect_clients() {
  local found=()
  for c in "${SUPPORTED_CLIENTS[@]}"; do
    local cfg; cfg="$(client_mcp_config_path "$c")"
    local parent_dir; parent_dir="$(dirname "$cfg")"
    if [ -f "$cfg" ] || [ -d "$parent_dir" ]; then
      found+=("$c")
    fi
  done
  printf '%s\n' "${found[@]:-}"
}

filter_clients_by_user() {
  if [ -z "$CLIENTS" ]; then
    cat
    return
  fi
  local allow=",${CLIENTS},"
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    case "$allow" in
      *",$line,"*) printf '%s\n' "$line" ;;
    esac
  done
}

# ---------- Prereq checks ----------
check_prereqs() {
  local missing=0
  if ! command -v git >/dev/null 2>&1; then
    err "git is required"
    missing=1
  fi
  if [ "$MCP_ONLY" -eq 1 ] || [ "$SKILLS_ONLY" -eq 0 ]; then
    if ! command -v node >/dev/null 2>&1; then
      err "node is required (Node.js ${MIN_NODE_MAJOR}+ for the MCP server)"
      missing=1
    else
      local nv; nv="$(node --version | sed 's/^v//' | cut -d. -f1)"
      if [ "$nv" -lt "$MIN_NODE_MAJOR" ]; then
        err "Node.js ${MIN_NODE_MAJOR}+ required, found v${nv}"
        missing=1
      fi
    fi
    if ! command -v npm >/dev/null 2>&1; then
      err "npm is required (ships with Node.js)"
      missing=1
    fi
  fi
  [ "$missing" -eq 0 ] || exit 1
}

# ---------- JSON I/O ----------
# Detect a JSON tool. Prefer python3 (universally available on macOS/Linux dev
# machines) — it gives us full programmatic merging. Fall back to jq if no
# python3, fall back to bare cat for read-only.
JSON_TOOL=""
if command -v python3 >/dev/null 2>&1; then
  JSON_TOOL="python3"
elif command -v python >/dev/null 2>&1; then
  JSON_TOOL="python"
elif command -v jq >/dev/null 2>&1; then
  JSON_TOOL="jq"
fi

# Merge the DocumentDB MCP entry into a client config file.
# Args: <config-path> <top-level-key> <server-cmd> <server-args-json> <env-json>
# Creates the file if missing. Backs up if existing.
merge_mcp_entry() {
  local cfg="$1" top_key="$2" cmd="$3" args_json="$4" env_json="$5"
  local parent; parent="$(dirname "$cfg")"

  if [ "$DRY_RUN" -eq 1 ]; then
    dry "would merge ${MCP_ENTRY} entry into ${cfg} under ${top_key}"
    return
  fi

  mkdir -p "$parent"

  if [ -f "$cfg" ]; then
    local backup="${cfg}.bak.$(date +%Y%m%d%H%M%S)"
    cp "$cfg" "$backup"
    info "backed up existing config → ${backup}"
  fi

  case "$JSON_TOOL" in
    python3|python)
      "$JSON_TOOL" - "$cfg" "$top_key" "$cmd" "$args_json" "$env_json" <<'PYEOF'
import json, os, sys, tempfile
cfg_path, top_key, cmd, args_json, env_json = sys.argv[1:6]
try:
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
        if not isinstance(cfg, dict):
            cfg = {}
except (FileNotFoundError, json.JSONDecodeError):
    cfg = {}

# Support dotted top-level keys like "mcp.servers"
parts = top_key.split(".")
node = cfg
for i, p in enumerate(parts):
    is_last = (i == len(parts) - 1)
    if is_last:
        if not isinstance(node.get(p), dict):
            node[p] = {}
        node[p]["DocumentDB"] = {
            "command": cmd,
            "args": json.loads(args_json),
            "env": json.loads(env_json),
        }
    else:
        if not isinstance(node.get(p), dict):
            node[p] = {}
        node = node[p]

dir_ = os.path.dirname(cfg_path) or "."
fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".docdb-mcp-", suffix=".json")
try:
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    os.replace(tmp, cfg_path)
except Exception:
    try: os.unlink(tmp)
    except FileNotFoundError: pass
    raise
PYEOF
      ;;
    jq)
      # jq path. Note: jq supports `.["mcp.servers"]` for keys-with-dots but
      # our `top_key` may be "mcp.servers" treated as nested. Handle both.
      local tmp; tmp="$(mktemp "${cfg}.XXXXXX")"
      local existing="{}"
      [ -f "$cfg" ] && existing="$(cat "$cfg")"
      local entry; entry=$(printf '{"command":"%s","args":%s,"env":%s}' "$cmd" "$args_json" "$env_json")
      # Build the merge expression based on whether top_key has dots
      local expr
      if [[ "$top_key" == *.* ]]; then
        expr=".[\"${top_key}\"][\"${MCP_ENTRY}\"] = ${entry}"
      else
        expr=".[\"${top_key}\"][\"${MCP_ENTRY}\"] = ${entry}"
      fi
      printf '%s' "$existing" | jq "$expr" > "$tmp"
      mv "$tmp" "$cfg"
      ;;
    *)
      err "Neither python3 nor jq found; cannot safely merge JSON. Install one and re-run."
      exit 1
      ;;
  esac
}

# Remove the DocumentDB MCP entry from a client config.
remove_mcp_entry() {
  local cfg="$1" top_key="$2"
  [ -f "$cfg" ] || return 0
  if [ "$DRY_RUN" -eq 1 ]; then
    dry "would remove ${MCP_ENTRY} entry from ${cfg}"
    return
  fi
  local backup="${cfg}.bak.$(date +%Y%m%d%H%M%S)"
  cp "$cfg" "$backup"

  case "$JSON_TOOL" in
    python3|python)
      "$JSON_TOOL" - "$cfg" "$top_key" <<'PYEOF'
import json, os, sys, tempfile
cfg_path, top_key = sys.argv[1], sys.argv[2]
try:
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    sys.exit(0)

parts = top_key.split(".")
node = cfg
for i, p in enumerate(parts):
    if not isinstance(node.get(p), dict):
        sys.exit(0)
    if i == len(parts) - 1:
        node[p].pop("DocumentDB", None)
    else:
        node = node[p]

dir_ = os.path.dirname(cfg_path) or "."
fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".docdb-mcp-", suffix=".json")
with os.fdopen(fd, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
os.replace(tmp, cfg_path)
PYEOF
      ;;
    jq)
      local tmp; tmp="$(mktemp "${cfg}.XXXXXX")"
      jq "del(.[\"${top_key}\"][\"${MCP_ENTRY}\"])" "$cfg" > "$tmp"
      mv "$tmp" "$cfg"
      ;;
  esac
}

# ---------- Repos ----------
clone_or_update_repo() {
  local repo="$1" dest="$2" ref="$3"
  if [ -d "$dest/.git" ]; then
    info "updating $(basename "$dest") (ref: ${ref})"
    if [ "$DRY_RUN" -eq 1 ]; then dry "git fetch + checkout ${ref} in ${dest}"; return; fi
    (cd "$dest" && git fetch --quiet --tags --depth=1 origin "${ref}" 2>/dev/null \
                && git checkout --quiet "${ref}" 2>/dev/null \
                && git reset --quiet --hard "FETCH_HEAD" 2>/dev/null) \
      || (cd "$dest" && git fetch --quiet --tags && git checkout --quiet "${ref}" && git reset --quiet --hard "origin/${ref}" 2>/dev/null || true)
  else
    info "cloning ${repo} → ${dest} (ref: ${ref})"
    if [ "$DRY_RUN" -eq 1 ]; then dry "git clone --branch ${ref} ${repo} ${dest}"; return; fi
    git clone --quiet --depth=1 --branch "${ref}" "${repo}" "${dest}" 2>/dev/null \
      || git clone --quiet "${repo}" "${dest}"
    (cd "$dest" && git checkout --quiet "${ref}" 2>/dev/null || true)
  fi
}

build_mcp_server() {
  if [ "$DRY_RUN" -eq 1 ]; then
    dry "(cd ${MCP_DIR} && npm install && npm run build)"
    return
  fi
  info "installing MCP server dependencies (this may take a minute)"
  (cd "$MCP_DIR" && npm install --silent --no-audit --no-fund --no-progress) \
    || { err "npm install failed in ${MCP_DIR}"; exit 1; }
  info "building MCP server"
  (cd "$MCP_DIR" && npm run build --silent) \
    || { err "npm run build failed in ${MCP_DIR}"; exit 1; }
  if [ ! -f "${MCP_DIR}/dist/main.js" ]; then
    err "expected ${MCP_DIR}/dist/main.js after build, not found"
    exit 1
  fi
  ok "MCP server built at ${MCP_DIR}/dist/main.js"
}

# ---------- Skills ----------
install_skills_for_client() {
  local client="$1"
  local dest; dest="$(client_skills_dir "$client")" || return 0
  if [ "$DRY_RUN" -eq 1 ]; then
    dry "would symlink each skills/<name>/ into ${dest}/"
    return
  fi
  mkdir -p "$dest"
  local count=0 skipped=0
  for skill_dir in "${KIT_DIR}"/skills/*/; do
    [ -d "$skill_dir" ] || continue
    local name; name="$(basename "$skill_dir")"
    local link="${dest}/${name}"
    if [ -L "$link" ]; then
      # Replace existing symlink (idempotent update)
      rm -f "$link"
    elif [ -e "$link" ]; then
      warn "skipping ${name} (target ${link} exists and is not a symlink)"
      skipped=$((skipped+1))
      continue
    fi
    ln -s "$skill_dir" "$link"
    count=$((count+1))
  done
  ok "$(client_label "$client"): linked ${count} skills into ${dest}${skipped:+ (${skipped} skipped)}"
}

uninstall_skills_for_client() {
  local client="$1"
  local dest; dest="$(client_skills_dir "$client")" || return 0
  [ -d "$dest" ] || return 0
  if [ "$DRY_RUN" -eq 1 ]; then
    dry "would remove kit's skill symlinks from ${dest}/"
    return
  fi
  local count=0
  for skill_dir in "${KIT_DIR}"/skills/*/; do
    [ -d "$skill_dir" ] || continue
    local name; name="$(basename "$skill_dir")"
    local link="${dest}/${name}"
    if [ -L "$link" ]; then
      local target; target="$(readlink "$link" 2>/dev/null || true)"
      case "$target" in
        "${KIT_DIR}"/*|"${KIT_DIR}")
          rm -f "$link"
          count=$((count+1))
          ;;
      esac
    fi
  done
  ok "$(client_label "$client"): removed ${count} skill symlinks from ${dest}"
}

# ---------- MCP entry ----------
build_env_json() {
  local conn="$1" profile="$2"
  # CONNECTION_PROFILES must be a JSON string, so we serialise twice.
  if [ -n "$JSON_TOOL" ] && [ "$JSON_TOOL" != "jq" ]; then
    "$JSON_TOOL" - "$conn" "$profile" <<'PYEOF'
import json, sys
conn, profile = sys.argv[1], sys.argv[2]
profiles = {profile: {"authMode": "connectionString", "uri": conn}}
# AUTH_REQUIRED gates ONLY the Entra-JWT bearer-token check on the MCP
# server's HTTP/SSE transport (i.e., calls FROM the MCP client TO this
# server). It is fully independent of MongoDB cluster auth: SCRAM
# username/password from the URI and Entra-to-cluster tokens (when a
# profile uses authMode=entra) flow through CONNECTION_PROFILES and stay
# active regardless of this setting.
#
# The server defaults AUTH_REQUIRED=true and its startup validator fails
# unless ENTRA_TENANT_ID / ENTRA_AUDIENCE are set. For local stdio we set
# AUTH_REQUIRED=false (which short-circuits the Entra validator entirely)
# and TRUST_LOCAL_STDIO=true (the upstream-recommended way to declare the
# stdio process boundary trusted; previously named
# ALLOW_UNAUTHENTICATED_STDIO before microsoft/documentdb-mcp#83).
#
# This is SAFE ONLY because TRANSPORT=stdio means the MCP server is a
# subprocess on the user's trusted local machine — no network listener
# is opened. If you ever switch TRANSPORT to streamable-http or sse, set
# AUTH_REQUIRED=true and provide the Entra tenant/audience, or the /mcp
# endpoint will be exposed unauthenticated.
env = {
    "TRANSPORT": "stdio",
    "AUTH_REQUIRED": "false",
    "TRUST_LOCAL_STDIO": "true",
    "CONNECTION_PROFILES": json.dumps(profiles),
}
print(json.dumps(env))
PYEOF
  else
    jq -n --arg conn "$conn" --arg profile "$profile" '
      {
        TRANSPORT: "stdio",
        AUTH_REQUIRED: "false",
        TRUST_LOCAL_STDIO: "true",
        CONNECTION_PROFILES: ({($profile): {authMode: "connectionString", uri: $conn}} | tostring)
      }'
  fi
}

install_mcp_for_client() {
  local client="$1" conn="$2"
  local cfg; cfg="$(client_mcp_config_path "$client")"
  local top_key="mcpServers"
  # (VS Code would use mcp.servers, but VS Code isn't in our auto-detect list)
  local cmd="node"
  local args_json='["'"${MCP_DIR}/dist/main.js"'"]'
  local env_json; env_json="$(build_env_json "$conn" "$PROFILE_NAME")"
  merge_mcp_entry "$cfg" "$top_key" "$cmd" "$args_json" "$env_json"
  ok "$(client_label "$client"): wrote ${MCP_ENTRY} MCP entry → ${cfg}"
}

uninstall_mcp_for_client() {
  local client="$1"
  local cfg; cfg="$(client_mcp_config_path "$client")"
  [ -f "$cfg" ] || return 0
  local top_key="mcpServers"
  remove_mcp_entry "$cfg" "$top_key"
  ok "$(client_label "$client"): removed ${MCP_ENTRY} MCP entry from ${cfg}"
}

# ---------- Connection string ----------
prompt_for_uri() {
  if [ -n "$URI" ]; then return; fi
  if [ -n "${DOCUMENTDB_URI:-}" ]; then
    URI="$DOCUMENTDB_URI"
    info "using \$DOCUMENTDB_URI from environment"
    return
  fi
  if [ "$YES" -eq 1 ]; then
    err "no connection string provided (use --uri, or set \$DOCUMENTDB_URI)"
    exit 2
  fi
  if [ ! -t 0 ]; then
    # Likely curl|bash with no TTY. Tell user how to provide it.
    err "no connection string provided and no TTY for prompt"
    err "re-run with: --uri \"mongodb://...\"  OR  set \$DOCUMENTDB_URI before running"
    err "for local dev: --uri mongodb://localhost:27017"
    exit 2
  fi
  heading "DocumentDB connection string"
  log "Examples:"
  log "  • Local:  mongodb://localhost:27017"
  log "  • Azure:  mongodb+srv://<user>:<pw>@<cluster>.mongocluster.cosmos.azure.com/?tls=true&authMechanism=SCRAM-SHA-256"
  log ""
  printf 'Connection string: '
  IFS= read -r URI || URI=""
  if [ -z "$URI" ]; then
    err "connection string is required"
    exit 2
  fi
}

# ---------- Run ----------
main() {
  heading "documentdb-agent-kit installer"
  log "Install root: ${INSTALL_ROOT}"
  [ "$DRY_RUN" -eq 1 ] && warn "DRY RUN — no files will be modified"

  if [ "$UNINSTALL" -eq 1 ]; then
    run_uninstall
    return
  fi

  check_prereqs

  # Resolve client list
  local clients_str
  clients_str="$(detect_clients | filter_clients_by_user)"
  if [ -z "$clients_str" ]; then
    warn "no supported MCP clients detected"
    warn "supported: ${SUPPORTED_CLIENTS[*]}"
    warn "(install one and re-run, or use --clients to force a specific config path)"
    exit 1
  fi
  heading "Detected clients"
  while IFS= read -r c; do log "  • $(client_label "$c")"; done <<< "$clients_str"

  # Clone the kit (for skills + AGENTS.md)
  if [ "$MCP_ONLY" -eq 0 ]; then
    heading "Installing agent kit"
    clone_or_update_repo "$KIT_REPO" "$KIT_DIR" "$KIT_REF"
    ok "kit at ${KIT_DIR}"
  fi

  # Clone & build the MCP server
  if [ "$SKILLS_ONLY" -eq 0 ]; then
    heading "Installing DocumentDB MCP server"
    clone_or_update_repo "$MCP_REPO" "$MCP_DIR" "$MCP_REF"
    build_mcp_server
  fi

  # Connection string for MCP entry
  if [ "$SKILLS_ONLY" -eq 0 ]; then
    prompt_for_uri
  fi

  heading "Wiring clients"
  while IFS= read -r c; do
    [ -z "$c" ] && continue
    if [ "$SKILLS_ONLY" -eq 0 ]; then
      install_mcp_for_client "$c" "$URI"
    fi
    if [ "$MCP_ONLY" -eq 0 ] && ! is_mcp_only_client "$c"; then
      install_skills_for_client "$c"
    fi
  done <<< "$clients_str"

  # Final report with per-client notes
  heading "Done"
  log "Kit installed at: ${KIT_DIR}"
  [ "$SKILLS_ONLY" -eq 0 ] && log "MCP server at:    ${MCP_DIR}/dist/main.js"
  log ""
  log "Next steps:"
  log "  1. Fully quit and reopen each configured client."
  log "  2. Verify by asking the agent to list DocumentDB tools."
  log "     (Try: \"list_databases with connection_profile: ${PROFILE_NAME}\")"
  if [ "$MCP_ONLY" -eq 0 ]; then
    local mcp_only_seen=0
    while IFS= read -r c; do
      [ -z "$c" ] && continue
      if is_mcp_only_client "$c"; then
        if [ "$mcp_only_seen" -eq 0 ]; then
          log ""
          log "  Note for Cursor / Copilot CLI / Gemini CLI:"
          log "  These clients discover skills from project-local files (AGENTS.md /"
          log "  GEMINI.md). To use the kit's skills in a project, copy or symlink:"
          log "    cp ${KIT_DIR}/AGENTS.md <your-project>/"
          log "    (Gemini: ln -s AGENTS.md GEMINI.md  inside the project)"
          mcp_only_seen=1
        fi
      fi
    done <<< "$clients_str"
  fi
  log ""
  # When invoked via `curl ... | bash -s -- ...`, $0 is "bash" / "-bash" /
  # "/usr/bin/bash" — not a script path — so suggesting "$0 --uninstall" prints
  # the misleading "bash --uninstall". Detect that and emit the curl one-liner
  # instead. When run as a local script, show the script-path form.
  case "$0" in
    bash|-bash|*/bash|sh|-sh|*/sh)
      log "Uninstall: curl -fsSL https://raw.githubusercontent.com/Azure/documentdb-agent-kit/main/install.sh | bash -s -- --uninstall --yes"
      ;;
    *)
      if [ -f "$0" ]; then
        log "Uninstall: $0 --uninstall"
      else
        log "Uninstall: curl -fsSL https://raw.githubusercontent.com/Azure/documentdb-agent-kit/main/install.sh | bash -s -- --uninstall --yes"
      fi
      ;;
  esac
}

run_uninstall() {
  heading "Uninstalling documentdb-agent-kit"

  local clients_str
  clients_str="$(detect_clients | filter_clients_by_user)"
  if [ -z "$clients_str" ]; then
    warn "no clients detected to clean up"
  else
    while IFS= read -r c; do
      [ -z "$c" ] && continue
      uninstall_mcp_for_client "$c" || true
      is_mcp_only_client "$c" || uninstall_skills_for_client "$c" || true
    done <<< "$clients_str"
  fi

  if [ -d "$INSTALL_ROOT" ]; then
    if [ "$DRY_RUN" -eq 1 ]; then
      dry "would remove ${INSTALL_ROOT}"
    else
      rm -rf "$INSTALL_ROOT"
      ok "removed ${INSTALL_ROOT}"
    fi
  fi
  ok "uninstall complete"
}

main "$@"
