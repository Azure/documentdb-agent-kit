#!/usr/bin/env python3
"""Cross-platform launcher for the Bash-based DocumentDB diagnostics.

Windows hosts do not need Bash, awk, sed, or grep. The launcher copies the
selected diagnostic and its shared runtime into the Linux DocumentDB container,
then executes the existing diagnostic logic there. Docker Desktop and Python
3.10+ are the only host requirements.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import TextIO

SCRIPT_DIR = Path(__file__).resolve().parent
SUPPORTED = {
    "data-integrity-check",
    "db-config-advisor",
    "document-bloat-advisor",
    "index-redundancy-finder",
    "perf-advisor",
    "toast-split-advisor",
}


class DiagnosticError(RuntimeError):
    """A portable diagnostic could not be launched or completed."""


def option_value(args: list[str], name: str, default: str) -> str:
    try:
        index = args.index(name)
    except ValueError:
        return default
    if index + 1 >= len(args):
        raise DiagnosticError(f"{name} requires a value")
    return args[index + 1]


def container_name(args: list[str]) -> str:
    return option_value(
        args,
        "--container",
        os.environ.get("CONTAINER_NAME")
        or os.environ.get("CONTAINER")
        or "documentdb-local",
    )


def docker_environment() -> dict[str, str]:
    names = (
        "DB_PASSWORD",
        "DB_USER",
        "PORT",
        "PG_PORT",
        "PG_USER",
        "PG_DB",
        "DEBUG",
    )
    return {name: os.environ[name] for name in names if name in os.environ}


def docker_exec_command(
    container: str,
    remote_script: str,
    args: list[str],
    extra_env: dict[str, str] | None = None,
) -> list[str]:
    environment = {"DOCDB_DIRECT": "1", **docker_environment(), **(extra_env or {})}
    command = ["docker", "exec", "-i", "-u", "documentdb"]
    for name, value in environment.items():
        command.extend(["-e", f"{name}={value}"])
    command.extend([container, "/bin/bash", remote_script, *args])
    return command


def _run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command, text=True, encoding="utf-8", errors="replace", **kwargs
        )
    except FileNotFoundError as error:
        raise DiagnosticError(
            "Docker CLI was not found. Install Docker Desktop and ensure "
            "'docker' is available on PATH."
        ) from error


def _copy(container: str, source: Path, destination: str) -> None:
    result = _run(
        ["docker", "cp", str(source), f"{container}:{destination}"],
        capture_output=True,
    )
    if result.returncode != 0:
        raise DiagnosticError(result.stderr.strip() or f"docker cp failed: {source}")


def normalized_shell_copy(source: Path, directory: Path) -> Path:
    """Create an LF-only copy so Git-for-Windows CRLF checkout is harmless."""
    target = directory / source.name
    content = source.read_text(encoding="utf-8").replace("\r\n", "\n").replace(
        "\r", "\n"
    )
    target.write_text(content, encoding="utf-8", newline="\n")
    return target


def _render_index_findings(
    payload: str, args: list[str], container: str, output: TextIO
) -> None:
    from index_redundancy_render import render

    findings = json.loads(payload)
    by_database: dict[str, list[dict]] = defaultdict(list)
    for finding in findings:
        by_database[finding.get("db", "")].append(finding)

    target = option_value(args, "--db", "ALL") if "--all-dbs" not in args else "ALL"
    print("╔" + "═" * 66 + "╗", file=output)
    print("║  DocumentDB Index Redundancy Finder".ljust(67) + "║", file=output)
    print(f"║  Database: {target}".ljust(67) + "║", file=output)
    print(f"║  Container: {container}".ljust(67) + "║", file=output)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    print(f"║  Timestamp: {timestamp}".ljust(67) + "║", file=output)
    print("╚" + "═" * 66 + "╝", file=output)
    print(file=output)

    databases = sorted(by_database) or ([target] if target != "ALL" else [])
    for database in databases:
        print("┌" + "─" * 62 + "┐", file=output)
        print(f"│  Database: {database}".ljust(63) + "│", file=output)
        print("└" + "─" * 62 + "┘", file=output)
        print(file=output)
        render(by_database.get(database, []), output)

    print(file=output)
    print("═" * 67, file=output)
    print("  Legend:", file=output)
    print("    🔴 HIGH   — Safe to drop (validated by index spec / catalog)", file=output)
    print("    🟡 MEDIUM — Likely safe (zero usage validated at both layers)", file=output)
    print("    🔵 LOW    — Review query patterns before dropping", file=output)
    print("═" * 67, file=output)


def _render_toast_report(payload: str, args: list[str], output: TextIO) -> None:
    from toast_split_advisor_render import render

    render(
        data=payload,
        json_mode="--json" in args,
        db_name=option_value(args, "--db", ""),
        field_min=int(option_value(args, "--field-min-bytes", "1024")),
        inline_threshold=2000,
        toast_ratio=float(option_value(args, "--toast-ratio", "0.5")),
        min_kb=option_value(args, "--min-total-kb", "256"),
        output=output,
    )


def run_named(
    name: str,
    args: list[str],
    *,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    if name not in SUPPORTED:
        raise DiagnosticError(f"unsupported diagnostic: {name}")

    if any(arg in ("-h", "--help") for arg in args):
        print(
            f"Usage: python {name}.py [the same options as {name}.sh]\n"
            "Runs the diagnostic through Docker without requiring Bash on the host.",
            file=stdout,
        )
        return 0

    container = container_name(args)
    remote_dir = f"/tmp/documentdb-agent-kit-{uuid.uuid4().hex}"
    remote_script = f"{remote_dir}/{name}.sh"
    script = SCRIPT_DIR / f"{name}.sh"
    runtime = SCRIPT_DIR / "diagnostic-runtime.sh"

    create = _run(
        ["docker", "exec", "-u", "root", container, "mkdir", "-p", remote_dir],
        capture_output=True,
    )
    if create.returncode != 0:
        raise DiagnosticError(
            create.stderr.strip()
            or f"cannot prepare portable diagnostic in container '{container}'"
        )

    try:
        with tempfile.TemporaryDirectory(prefix="documentdb-agent-kit-") as temp:
            temp_dir = Path(temp)
            _copy(
                container,
                normalized_shell_copy(runtime, temp_dir),
                f"{remote_dir}/diagnostic-runtime.sh",
            )
            _copy(
                container,
                normalized_shell_copy(script, temp_dir),
                remote_script,
            )

            inner_args = list(args)
            extra_env: dict[str, str] = {}
            render = None
            if name == "index-redundancy-finder" and "--json" not in inner_args:
                inner_args.append("--json")
                render = lambda payload, stream: _render_index_findings(
                    payload, args, container, stream
                )
            elif name == "toast-split-advisor":
                extra_env["DOCDB_PORTABLE_RAW"] = "1"
                render = lambda payload, stream: _render_toast_report(
                    payload, args, stream
                )

            result = _run(
                docker_exec_command(
                    container, remote_script, inner_args, extra_env
                ),
                capture_output=True,
            )
        if result.stderr:
            stderr.write(result.stderr)
        if result.returncode != 0:
            if result.stdout:
                stdout.write(result.stdout)
            return result.returncode

        if render is None:
            stdout.write(result.stdout)
        else:
            render(result.stdout, stdout)
        return 0
    finally:
        _run(
            ["docker", "exec", "-u", "root", container, "rm", "-rf", remote_dir],
            capture_output=True,
        )


def main(name: str | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    selected = name
    args = sys.argv[1:]
    if selected is None:
        if not args:
            print(
                "Usage: python portable_diagnostic.py <diagnostic-name> [options]",
                file=sys.stderr,
            )
            return 2
        selected, args = args[0], args[1:]
    try:
        return run_named(selected, args)
    except (DiagnosticError, json.JSONDecodeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
