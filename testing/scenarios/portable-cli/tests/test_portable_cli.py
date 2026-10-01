from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[4] / "scripts"
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import portable_diagnostic as portable  # noqa: E402


def test_every_diagnostic_has_python_and_powershell_entry_points():
    for name in sorted(portable.SUPPORTED):
        assert (SCRIPTS / f"{name}.sh").is_file()
        assert (SCRIPTS / f"{name}.py").is_file()
        assert (SCRIPTS / f"{name}.ps1").is_file()


@pytest.mark.skipif(os.name == "nt", reason="Windows does not expose Unix mode bits")
def test_all_tracked_shell_files_are_executable():
    result = subprocess.run(
        ["git", "ls-files", "*.sh"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    missing = []
    for relative in result.stdout.splitlines():
        path = REPO / relative
        if path.stat().st_mode & 0o111 == 0:
            missing.append(relative)
    assert not missing, f"shell files missing executable mode: {missing}"


def test_container_option_overrides_environment(monkeypatch):
    monkeypatch.setenv("CONTAINER_NAME", "from-env")
    assert portable.container_name(["--container", "from-cli"]) == "from-cli"
    assert portable.container_name([]) == "from-env"


def test_docker_command_uses_argument_list_and_direct_mode(monkeypatch):
    monkeypatch.setenv("DB_PASSWORD", "secret with spaces")
    command = portable.docker_exec_command(
        "docdb",
        "/tmp/kit/perf-advisor.sh",
        ["--db", "sales data", "--json"],
    )
    assert command[:6] == [
        "docker",
        "exec",
        "-i",
        "-u",
        "documentdb",
        "-e",
    ]
    assert "DOCDB_DIRECT=1" in command
    assert "DB_PASSWORD=secret with spaces" in command
    assert command[-3:] == ["--db", "sales data", "--json"]


def test_help_does_not_require_docker():
    output = io.StringIO()
    assert portable.run_named("perf-advisor", ["--help"], stdout=output) == 0
    assert "without requiring Bash on the host" in output.getvalue()


def test_missing_docker_has_actionable_error(monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", missing)
    with pytest.raises(portable.DiagnosticError, match="Docker CLI was not found"):
        portable.run_named("perf-advisor", ["--db", "sales", "--json"])


def test_powershell_wrappers_forward_all_arguments():
    for name in sorted(portable.SUPPORTED):
        text = (SCRIPTS / f"{name}.ps1").read_text()
        assert f'-Diagnostic "{name}"' in text
        assert "@args" in text
        assert "exit $LASTEXITCODE" in text


def test_crlf_shell_checkout_is_normalized(tmp_path):
    source = tmp_path / "diagnostic.sh"
    source.write_bytes(b"#!/usr/bin/env bash\r\nset -uo pipefail\r\necho ok\r\n")
    output_dir = tmp_path / "normalized"
    output_dir.mkdir()

    normalized = portable.normalized_shell_copy(source, output_dir)

    assert normalized.read_bytes() == (
        b"#!/usr/bin/env bash\nset -uo pipefail\necho ok\n"
    )


def test_ci_and_benchmark_pin_the_same_mongosh_version():
    workflow = (
        REPO / ".github" / "workflows" / "diagnostic-regression.yml"
    ).read_text()
    dockerfile = (
        REPO
        / "benchmarks"
        / "documentdb-sdk-skills"
        / "shared"
        / "base"
        / "Dockerfile"
    ).read_text()

    assert 'MONGOSH_VERSION: "2.3.8"' in workflow
    assert "ARG MONGOSH_VERSION=2.3.8" in dockerfile
    digest = "23edb768189663aaa9732a2340a25b5fc05a314940538809a7840be7f2ce221f"
    assert f'MONGOSH_SHA256: "{digest}"' in workflow
    assert f"ARG MONGOSH_SHA256_AMD64={digest}" in dockerfile
    assert (
        "ARG MONGOSH_SHA256_ARM64="
        "8a30ec1833343985d3d5901bb31cbb9e8e8193200dc08a5bddde343b601b7690"
    ) in dockerfile
    assert "sha256sum -c -" in workflow
    assert "sha256sum -c -" in dockerfile
    assert "INSTALLED_VERSION=" in workflow
    assert 'Expected mongosh $MV' in workflow


def test_ci_and_benchmark_pin_documentdb_image_digest():
    workflow = (
        REPO / ".github" / "workflows" / "diagnostic-regression.yml"
    ).read_text()
    dockerfile = (
        REPO
        / "benchmarks"
        / "documentdb-sdk-skills"
        / "shared"
        / "base"
        / "Dockerfile"
    ).read_text()
    image = (
        "ghcr.io/microsoft/documentdb/documentdb-local"
        "@sha256:0fcf634531c1917ad0855ff9f4354aca0a5c5d8e435f08250568deb37eeb0ad5"
    )

    assert f'DOCUMENTDB_LOCAL_IMAGE: "{image}"' in workflow
    assert f"ARG DOCUMENTDB_BASE_IMAGE={image}" in dockerfile
    assert "FROM ${DOCUMENTDB_BASE_IMAGE}" in dockerfile
    assert "documentdb-local:latest" not in workflow
