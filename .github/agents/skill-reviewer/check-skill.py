#!/usr/bin/env python3
"""
check-skill.py — deterministic SKILL.md reviewer for documentdb-agent-kit

Runs the mechanical checks the agent shouldn't waste tokens re-deriving:
  - Token cost at each progressive-disclosure level (Level 1/2/3)
  - The five canonical antipatterns (frontmatter on refs, monolithic spine,
    hardcoded paths, missing Gotchas on operational skills, no evals)
  - Reference-link integrity

Usage:
  python3 check-skill.py skills/<name>/         # review one skill
  python3 check-skill.py skills/                # review every skill
  python3 check-skill.py skills/<name> --human  # human-readable summary

Output (default):
  JSON to stdout. Agents should parse `findings[]` and `cost.*` fields.
  Exit code: 0 on PASS, 1 on any FAIL finding, 2 on script error.

Token counting:
  Uses `tiktoken` (cl100k_base) if installed for accurate counts.
  Falls back to len(text) / 4 — coarse but consistent across files,
  which is what matters for ratio-based budgeting.

References:
  Lax Meiyappan, "What you're actually writing when you write a SKILL.md,"
  INTERNALS.md #2, Apr 2026 — and the Anthropic Agent Skills runtime docs
  it draws from.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# ---- Token counting -------------------------------------------------------

try:
    import tiktoken  # type: ignore
    _ENC = tiktoken.get_encoding("cl100k_base")
    _TOKENIZER = "tiktoken/cl100k_base"

    def count_tokens(text: str) -> int:
        return len(_ENC.encode(text, disallowed_special=()))
except Exception:
    _TOKENIZER = "fallback/chars-div-4"

    def count_tokens(text: str) -> int:
        return max(1, len(text) // 4) if text else 0


# Context window assumption used for the "% of context" framing.
# Matches Claude Sonnet 4.5/4.6 and GPT-5 standard windows; configurable via flag.
DEFAULT_CONTEXT_WINDOW = 200_000

# Token thresholds (calibrated to the article's 20%-vs-7% measurement and
# Anthropic's recommended 500-line SKILL.md ceiling, ≈ 5k tokens).
LEVEL1_WARN_TOKENS = 300       # frontmatter description balloon
LEVEL1_FAIL_TOKENS = 1024      # Anthropic's hard description ceiling
LEVEL2_PASS_TOKENS = 5_000     # ~500 lines, the recommended ceiling
LEVEL2_WARN_TOKENS = 10_000    # 2× the ceiling — antipattern #2 territory
LEVEL3_REF_WARN_TOKENS = 8_000 # per-reference; if loaded it dominates context

# Heuristics
HARDCODED_PATH_RE = re.compile(
    r"(?<![\w./])"
    r"("
    r"/Users/[A-Za-z0-9._-]+"
    r"|/home/[A-Za-z0-9._-]+"
    r"|[A-Z]:\\Users\\[A-Za-z0-9._-]+"
    r")"
)
GOTCHA_HEADING_RE = re.compile(
    r"(?im)^\s{0,3}#{1,6}\s+(gotchas?|pitfalls?|common\s+mistakes|"
    r"watch\s+out|known\s+issues?|caveats?|warnings?)\b"
)
OPERATIONAL_HINTS = (
    "deployment", "deploy", "provision", "setup", "install", "connection",
    "driver", "runtime", "mcp-setup", "local-deployment", "azure-deployment",
)
LINK_RE = re.compile(r"(?<!\!)\[[^\]]+\]\(([^)#?\s]+)(?:#[^)]*)?\)")
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


# ---- Data model -----------------------------------------------------------

@dataclass
class Finding:
    severity: str         # "blocker" | "improvement" | "info"
    antipattern: Optional[int]  # 1..5 or None
    file: str             # repo-relative path
    line: Optional[int]
    message: str
    fix: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class FileCost:
    path: str
    bytes: int
    lines: int
    tokens: int
    has_frontmatter: bool
    frontmatter_tokens: int


@dataclass
class SkillReport:
    skill: str
    path: str
    cost: dict = field(default_factory=dict)
    files: list[FileCost] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    grade: dict = field(default_factory=dict)

    def add(self, f: Finding) -> None:
        self.findings.append(f)


# ---- Per-file analysis ----------------------------------------------------

def split_frontmatter(text: str) -> tuple[Optional[str], str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None, text
    return m.group(1), text[m.end():]


def measure_file(path: Path, repo_root: Path) -> FileCost:
    text = path.read_text(encoding="utf-8", errors="replace")
    fm, body = split_frontmatter(text)
    rel = str(path.relative_to(repo_root))
    return FileCost(
        path=rel,
        bytes=len(text.encode("utf-8")),
        lines=text.count("\n") + (1 if text and not text.endswith("\n") else 0),
        tokens=count_tokens(text),
        has_frontmatter=fm is not None,
        frontmatter_tokens=count_tokens(fm) if fm else 0,
    )


def find_hardcoded_paths(text: str, rel_path: str) -> list[tuple[int, str]]:
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        # Skip lines that are explicit examples for the user
        if re.search(r"\b(e\.g\.|example|your\s+username|<[A-Z_-]+>)", line, re.I):
            continue
        for m in HARDCODED_PATH_RE.finditer(line):
            hits.append((i, m.group(0)))
    return hits


def looks_operational(skill_dir: Path) -> bool:
    name = skill_dir.name.lower()
    if any(h in name for h in OPERATIONAL_HINTS):
        return True
    # Also operational if the skill body talks about running shell commands extensively
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        body = skill_md.read_text(encoding="utf-8", errors="replace").lower()
        if body.count("```bash") + body.count("```sh") + body.count("```pwsh") >= 3:
            return True
    return False


# ---- Skill-level review ---------------------------------------------------

def review_skill(skill_dir: Path, repo_root: Path, ctx_window: int) -> SkillReport:
    rep = SkillReport(skill=skill_dir.name, path=str(skill_dir.relative_to(repo_root)))
    skill_md = skill_dir / "SKILL.md"

    if not skill_md.exists():
        rep.add(Finding(
            severity="blocker", antipattern=None,
            file=str(skill_dir.relative_to(repo_root)) + "/", line=None,
            message="missing SKILL.md",
            fix="create SKILL.md with `name` and `description` frontmatter",
        ))
        return rep

    md_files = sorted(p for p in skill_dir.rglob("*.md") if p.is_file())
    costs = [measure_file(p, repo_root) for p in md_files]
    rep.files = costs

    # Identify the spine vs references
    spine = next((c for c in costs if Path(c.path).name == "SKILL.md"), None)
    refs = [c for c in costs if c is not spine]

    # ---- Antipattern #1: frontmatter on reference files -------------------
    for c in refs:
        if c.has_frontmatter:
            rep.add(Finding(
                severity="blocker", antipattern=1,
                file=c.path, line=1,
                message="reference file has YAML frontmatter — promotes it to skill-level visibility (always-loaded)",
                fix="delete the `---` frontmatter block; references are chapters, not skills",
            ))

    # ---- Antipattern #2: monolithic SKILL.md ------------------------------
    if spine is not None:
        if spine.tokens > LEVEL2_WARN_TOKENS:
            rep.add(Finding(
                severity="blocker", antipattern=2,
                file=spine.path, line=None,
                message=f"SKILL.md is {spine.tokens:,} tokens ({spine.lines} lines) — over the 500-line / ~10k-token guardrail",
                fix="split into a ≤200-line spine that points to topic references in the same folder",
            ))
        elif spine.tokens > LEVEL2_PASS_TOKENS:
            rep.add(Finding(
                severity="improvement", antipattern=2,
                file=spine.path, line=None,
                message=f"SKILL.md is {spine.tokens:,} tokens ({spine.lines} lines) — approaching Anthropic's 500-line ceiling",
                fix="identify sections that load on different tasks and move them to references/",
            ))

    # ---- Antipattern #3: hardcoded paths ----------------------------------
    for p in md_files:
        text = p.read_text(encoding="utf-8", errors="replace")
        for line_no, hit in find_hardcoded_paths(text, str(p.relative_to(repo_root))):
            rep.add(Finding(
                severity="improvement", antipattern=3,
                file=str(p.relative_to(repo_root)), line=line_no,
                message=f"hardcoded user path `{hit}` — breaks for any other reader",
                fix="replace with a placeholder (e.g. `<your-home>`) or instruct the agent to discover the path",
            ))

    # ---- Antipattern #4: missing Gotchas on operational skills ------------
    if looks_operational(skill_dir):
        any_gotchas = any(
            GOTCHA_HEADING_RE.search(p.read_text(encoding="utf-8", errors="replace"))
            for p in md_files
        )
        if not any_gotchas:
            rep.add(Finding(
                severity="improvement", antipattern=4,
                file=spine.path if spine else rep.path, line=None,
                message="operational skill has no Gotchas / Pitfalls / Common-mistakes section",
                fix="add a `## Gotchas` section to SKILL.md or a reference, listing 1–3 things the agent's defaults get wrong here",
            ))

    # ---- Antipattern #5: no evals ----------------------------------------
    eval_signals = ["evals", "tests", "golden-set", "eval.md", "eval.json", "eval.yaml"]
    has_evals = any((skill_dir / s).exists() for s in eval_signals)
    if not has_evals:
        rep.add(Finding(
            severity="info", antipattern=5,
            file=rep.path, line=None,
            message="no evals/golden-set found alongside the skill",
            fix="add a small Golden Set (3–4 prompts) if this skill encodes voice, formatting, or compliance behavior; safe to skip for pure technical reference skills",
        ))

    # ---- Description quality (Level 1) -----------------------------------
    if spine is not None:
        spine_text = (skill_dir / "SKILL.md").read_text(encoding="utf-8", errors="replace")
        fm, _ = split_frontmatter(spine_text)
        desc_match = re.search(r"(?ms)^description\s*:\s*(.+?)(?=^\w[\w-]*\s*:|\Z)", fm or "")
        desc = (desc_match.group(1).strip() if desc_match else "")
        desc_tokens = count_tokens(desc)
        if not desc:
            rep.add(Finding(
                severity="blocker", antipattern=None,
                file=spine.path, line=None,
                message="frontmatter has no `description` — the agent has nothing to route on",
                fix="add a description listing 2–3 concrete situations that should trigger this skill",
            ))
        else:
            if desc_tokens > LEVEL1_FAIL_TOKENS:
                rep.add(Finding(
                    severity="blocker", antipattern=None,
                    file=spine.path, line=None,
                    message=f"description is {desc_tokens} tokens — exceeds Anthropic's 1024-char ceiling",
                    fix="trim to 200–500 chars; move detail into the body",
                ))
            elif desc_tokens > LEVEL1_WARN_TOKENS:
                rep.add(Finding(
                    severity="improvement", antipattern=None,
                    file=spine.path, line=None,
                    message=f"description is {desc_tokens} tokens — likely contains content that belongs in the body",
                    fix="keep the description to triggers and differentiation; move how-to content into SKILL.md",
                ))
            if "use when" not in desc.lower() and "use this" not in desc.lower():
                rep.add(Finding(
                    severity="improvement", antipattern=None,
                    file=spine.path, line=None,
                    message="description does not name the situations that should trigger the skill",
                    fix='add "Use when …" with 2–3 concrete trigger situations',
                ))

    # ---- Reference-link integrity ----------------------------------------
    if spine is not None:
        spine_text = (skill_dir / "SKILL.md").read_text(encoding="utf-8", errors="replace")
        linked = set()
        for m in LINK_RE.finditer(spine_text):
            target = m.group(1)
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            linked.add(target)
            target_path = (skill_dir / target).resolve()
            if not target_path.exists():
                # cross-skill references are OK — only flag if not resolvable from anywhere reasonable
                also = (repo_root / target).resolve() if target.startswith(("..", "skills/")) else None
                if not (also and also.exists()):
                    rep.add(Finding(
                        severity="blocker", antipattern=None,
                        file=spine.path, line=None,
                        message=f"broken reference link: {target}",
                        fix="fix the path or remove the link",
                    ))
        # Orphaned references — files in the folder that nothing links to
        for c in refs:
            name = Path(c.path).name
            if not any(name in t or t.endswith(name) for t in linked):
                rep.add(Finding(
                    severity="info", antipattern=None,
                    file=c.path, line=None,
                    message="reference file is not linked from SKILL.md",
                    fix="link it from the spine, or delete it if obsolete",
                ))

    # ---- Cost summary -----------------------------------------------------
    level1 = spine.frontmatter_tokens if spine else 0
    level2 = (spine.tokens - spine.frontmatter_tokens) if spine else 0
    level3_total = sum(c.tokens for c in refs)
    on_invocation = level1 + level2
    full_load = on_invocation + level3_total

    rep.cost = {
        "tokenizer": _TOKENIZER,
        "context_window": ctx_window,
        "level1_always_loaded_tokens": level1,
        "level2_on_invocation_tokens": level2,
        "level3_references_tokens_total": level3_total,
        "level3_references_per_file": [
            {"path": c.path, "tokens": c.tokens, "lines": c.lines} for c in refs
        ],
        "on_invocation_total_tokens": on_invocation,
        "full_load_total_tokens": full_load,
        "pct_of_context_always": pct(level1, ctx_window),
        "pct_of_context_on_invocation": pct(on_invocation, ctx_window),
        "pct_of_context_full_load": pct(full_load, ctx_window),
    }

    # ---- Grading ----------------------------------------------------------
    rep.grade = {
        "architecture_cost": grade_architecture(spine, refs),
        "antipatterns_violated": sorted({f.antipattern for f in rep.findings if f.antipattern}),
        "blockers": sum(1 for f in rep.findings if f.severity == "blocker"),
        "improvements": sum(1 for f in rep.findings if f.severity == "improvement"),
    }

    # Per-reference token-cost warnings (Level 3)
    for c in refs:
        if c.tokens > LEVEL3_REF_WARN_TOKENS:
            rep.add(Finding(
                severity="improvement", antipattern=2,
                file=c.path, line=None,
                message=f"reference is {c.tokens:,} tokens — would dominate context if loaded",
                fix="split into smaller topic-scoped references the spine can pick from",
            ))

    return rep


def pct(numer: int, denom: int) -> float:
    return round(100 * numer / denom, 3) if denom else 0.0


def grade_architecture(spine: Optional[FileCost], refs: list[FileCost]) -> str:
    if spine is None:
        return "FAIL"
    t = spine.tokens
    if t > LEVEL2_WARN_TOKENS:
        return "FAIL"
    if t > LEVEL2_PASS_TOKENS:
        return "WARN"
    return "PASS"


# ---- CLI ------------------------------------------------------------------

def find_repo_root(start: Path) -> Path:
    p = start.resolve()
    for cand in [p, *p.parents]:
        if (cand / ".git").exists() or (cand / "AGENTS.md").exists():
            return cand
    return start.resolve()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("target", help="path to a skill folder OR to skills/ for kit-wide review")
    ap.add_argument("--human", action="store_true", help="emit a human-readable summary instead of JSON")
    ap.add_argument("--context-window", type=int, default=DEFAULT_CONTEXT_WINDOW,
                    help=f"context window in tokens for %% calculations (default {DEFAULT_CONTEXT_WINDOW:,})")
    args = ap.parse_args(argv)

    target = Path(args.target).resolve()
    if not target.exists():
        print(f"error: {target} does not exist", file=sys.stderr)
        return 2

    repo_root = find_repo_root(target)
    skill_dirs: list[Path]
    if (target / "SKILL.md").exists():
        skill_dirs = [target]
    else:
        skill_dirs = sorted(p for p in target.iterdir() if p.is_dir() and (p / "SKILL.md").exists())
        if not skill_dirs:
            print(f"error: no SKILL.md found under {target}", file=sys.stderr)
            return 2

    reports = [review_skill(d, repo_root, args.context_window) for d in skill_dirs]

    if args.human:
        emit_human(reports, args.context_window)
    else:
        emit_json(reports, args.context_window)

    any_blockers = any(r.grade.get("blockers", 0) for r in reports)
    return 1 if any_blockers else 0


def emit_json(reports: list[SkillReport], ctx: int) -> None:
    payload = {
        "tokenizer": _TOKENIZER,
        "context_window": ctx,
        "summary": {
            "skills": len(reports),
            "total_always_loaded_tokens": sum(r.cost.get("level1_always_loaded_tokens", 0) for r in reports),
            "pct_of_context_always_loaded_kit_wide": pct(
                sum(r.cost.get("level1_always_loaded_tokens", 0) for r in reports), ctx
            ),
            "blockers": sum(r.grade.get("blockers", 0) for r in reports),
            "improvements": sum(r.grade.get("improvements", 0) for r in reports),
        },
        "skills": [
            {
                "skill": r.skill,
                "path": r.path,
                "cost": r.cost,
                "grade": r.grade,
                "findings": [f.as_dict() for f in r.findings],
            }
            for r in reports
        ],
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")


def emit_human(reports: list[SkillReport], ctx: int) -> None:
    print(f"# Skill review · tokenizer={_TOKENIZER} · context window={ctx:,}")
    total_always = sum(r.cost.get("level1_always_loaded_tokens", 0) for r in reports)
    print(f"\n## Kit-wide always-loaded cost: {total_always:,} tokens "
          f"({pct(total_always, ctx)}% of {ctx:,})")
    print(f"   ({len(reports)} skills × frontmatter loaded every turn)\n")

    for r in reports:
        c = r.cost
        bar_pct = c.get("pct_of_context_on_invocation", 0)
        print(f"### {r.skill}  →  {r.grade.get('architecture_cost','?')}")
        print(f"   L1 always:        {c.get('level1_always_loaded_tokens',0):>6,} tok  "
              f"({c.get('pct_of_context_always',0)}%)")
        print(f"   L2 on-invocation: {c.get('level2_on_invocation_tokens',0):>6,} tok  "
              f"({c.get('pct_of_context_on_invocation',0)}%)")
        print(f"   L3 refs total:    {c.get('level3_references_tokens_total',0):>6,} tok  "
              f"({len(c.get('level3_references_per_file',[]))} files)")
        print(f"   Full load:        {c.get('full_load_total_tokens',0):>6,} tok  "
              f"({c.get('pct_of_context_full_load',0)}%)")
        if r.findings:
            for f in r.findings:
                icon = {"blocker": "🔴", "improvement": "🟡", "info": "🔵"}.get(f.severity, "·")
                ap = f" [AP#{f.antipattern}]" if f.antipattern else ""
                where = f" {f.file}" + (f":{f.line}" if f.line else "")
                print(f"   {icon}{ap}{where}  {f.message}")
        else:
            print("   ✅ no findings")
        print()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
