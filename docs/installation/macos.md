# Installation — macOS

**1. Prerequisites**

```bash
# git
xcode-select --install      # if not already installed
# Node.js 20+ (Homebrew)
brew install node@20 && brew link --overwrite --force node@20

# Verify
git --version
node --version    # must be v20.x or higher
```

**2. Get your DocumentDB connection string**

- **Azure DocumentDB:** Azure portal → cluster → *Settings → Connection strings*. Shape:
  `mongodb+srv://<user>:<password>@<cluster>.mongocluster.cosmos.azure.com/?tls=true&authMechanism=SCRAM-SHA-256&retrywrites=false`.
  URL-encode special characters in the password.
- **Local DocumentDB / MongoDB:** `mongodb://localhost:27017`
- **Atlas / self-hosted:** your standard MongoDB URI.

> ⚠️ Keep the connection string in your shell only — don't paste it into any AI agent chat.

**3. Run the installer**

```bash
curl -fsSL https://raw.githubusercontent.com/Azure/documentdb-agent-kit/main/install.sh \
  | bash -s -- --uri "<your-connection-string>" --yes
```

Or with the URI in an env var:

```bash
export DOCUMENTDB_URI="<your-connection-string>"
curl -fsSL https://raw.githubusercontent.com/Azure/documentdb-agent-kit/main/install.sh | bash -s -- --yes
```

**4. Fully quit and reopen each configured client.** Closing the window isn't enough — MCP config is read only at process start.

**5. Verify** — see [Verify it worked](verify.md).
