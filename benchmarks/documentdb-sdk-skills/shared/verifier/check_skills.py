r"""Skills-compliance checks — hygiene rules that must hold in any submission.

These are the non-negotiables from the kit's `documentdb-security` skill. Unlike
check_source.py, credential checks run against the RAW source (comments
included): a password committed in a comment is still a leaked password.
"""
from __future__ import annotations

import re

import pytest

# The base image generates a password at container start and exports it. Any
# literal that looks like a credential in source is therefore a real finding.
_CREDENTIAL_PATTERNS = [
    # mongodb://user:password@host — a password embedded in a URI LITERAL.
    #
    # The password class excludes { } $ % + on purpose: those characters mean
    # the value is being INTERPOLATED, e.g.
    #     f"mongodb://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/"
    # which is the CORRECT pattern (credentials from the environment), not a
    # leak. Without this exclusion the check fails every well-written
    # submission — it did exactly that to the reference implementation.
    (r"mongodb(?:\+srv)?://[^\s\"']*:[^\s\"'@/{}$%+]{3,}@",
     "a connection URI with an embedded password"),
    # password = "literal"  (not os.environ / getenv / a format placeholder)
    (r"(?i)\b(?:password|passwd|pwd)\s*=\s*[\"'][^\"'{}$<>%+]{4,}[\"']",
     "a hardcoded password literal"),
]

_ENV_READ = re.compile(
    r"os\.environ|os\.getenv|getenv\(|dotenv|Environment\.GetEnvironmentVariable|"
    r"process\.env|System\.getenv"
)


class TestNoHardcodedCredentials:
    def test_no_credential_literals_in_source(self, source_text_raw):
        """Deliberately scans RAW source.

        A credential in a comment is still a credential. This is the one place
        where comment-stripping would weaken rather than strengthen the check.
        """
        findings = []
        for pattern, label in _CREDENTIAL_PATTERNS:
            for match in re.finditer(pattern, source_text_raw):
                snippet = match.group(0)
                # Redact before reporting: the failure message ends up in logs.
                findings.append(f"{label}: {snippet[:24]}…")
        assert not findings, (
            "Hardcoded credentials found in the source:\n  "
            + "\n  ".join(findings[:5])
            + "\nRead the password from the environment "
              "(DOCUMENTDB_PASSWORD) instead — the container generates a fresh "
              "one per run, so a literal cannot even be correct."
        )


class TestConfigurationComesFromTheEnvironment:
    def test_connection_settings_are_read_from_env(self, source_text):
        assert _ENV_READ.search(source_text), (
            "No environment-variable reads found. The host, port, credentials "
            "and database name are supplied via the environment "
            "(DOCUMENTDB_HOST / _PORT / _USER / _PASSWORD / _DATABASE); an app "
            "that does not read them cannot be deployed anywhere else."
        )

    def test_database_name_is_not_hardcoded_over_the_env(self, source_text):
        """A default is fine; ignoring the env var is not."""
        if not re.search(r"DOCUMENTDB_DATABASE", source_text):
            pytest.fail(
                "The database name is never read from DOCUMENTDB_DATABASE. "
                "Hardcoding it means the same build cannot target another "
                "database."
            )


class TestNoForbiddenAntiPatterns:
    def test_no_insecure_auth_bypass(self, sdk, source_text):
        """`authMechanism` must not be downgraded to none/PLAIN.

        Azure DocumentDB uses SCRAM-SHA-256 or Entra. Disabling auth to make a
        local run work is the kind of shortcut that survives into production.
        """
        if sdk != "python":
            pytest.skip(f"does not apply to {sdk}")
        bad = re.search(r"authMechanism\s*=\s*[\"'](?:PLAIN|NONE|none)[\"']", source_text)
        assert not bad, (
            "authMechanism is set to an insecure value. Azure DocumentDB uses "
            "SCRAM-SHA-256 (or Microsoft Entra)."
        )
