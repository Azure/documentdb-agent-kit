#!/usr/bin/env python3
"""kb_route.py — DocumentDB Agent-Kit knowledge-base router (routing engine).

Maps a natural-language question to the exact agent-kit target that answers it
(ONE HOP). There are two target spaces, both scored the same deterministic way
(keyword/example scoring, stdlib only, no deps):

  * Route A — `tools`  : read-only diagnostic scripts (query -> `bash scripts/*.sh`)
  * Route B — `skills` : text guidance the agent opens (query -> `skills/*/SKILL.md`)

kb.json is the single source of truth. The router reports the best of each space
(`match` for scripts, `skill_match` for skills) and a `recommended` route, so it
works without an LLM and gives the LLM agent a structured, reproducible decision
it can trust and explain.

This file is invoked by kb-route.sh (the CLI wrapper), which passes inputs via
environment variables: KB, DB, JSON, MODE, QUERY. It is a standalone module so it
can be linted, unit-tested, and imported — unlike the previous inline heredoc.

Multi-hop troubleshooting workflows (guarded diagnostic graph) are described by
the kb.json workflow_schema and listed with MODE=workflows; traversal is left to
the agent and populated over time.
"""

import json
import os
import re
import sys

STOP = set(
    "the a an is are my me i do does how why what which of to in on for and or "
    "with can should".split()
)


def tokenize(s):
    return set(re.findall(r"[a-z0-9_]+", s.lower()))


def fill(invocation, db, placeholder):
    """Substitute the <db> placeholder with the actual database name, if given."""
    if db:
        return invocation.replace(placeholder, db)
    return invocation


def score_tool(t, q_tokens, q_lower, onegram=False):
    """Score one tool/skill against the query.

    Two keyword-matching modes:

    * ``onegram=False`` (phrase-aware, used for SKILLS): a multi-word keyword
      scores +3.0 only when the whole phrase is present as a substring; a
      single-word keyword scores +1.5 when present as a query token. Higher
      precision — favored where picking the *right* guidance matters.
    * ``onegram=True`` (1-gram, used for TOOLS/scripts): every keyword is split
      into single-word tokens and each *distinct* query token that hits that set
      scores +1.5. Higher recall (a paraphrase like "scan the collection" still
      matches "collection scan"); harmless over-triggering since the diagnostic
      scripts are read-only.

    Both modes then add the best example-query token overlap (+2.5 * fraction).
    Returns (score, matched_keywords) — for 1-gram, matched_keywords are the
    matched single tokens.
    """
    score = 0.0
    hits = []
    if onegram:
        kw_tokens = set()
        for kw in t.get("keywords", []):
            kw_tokens |= (tokenize(kw) - STOP)
        for tok in sorted(q_tokens & kw_tokens):
            score += 1.5
            hits.append(tok)
    else:
        for kw in t.get("keywords", []):
            kwl = kw.lower()
            if " " in kwl:
                if kwl in q_lower:
                    score += 3.0
                    hits.append(kw)
            else:
                if kwl in q_tokens:
                    score += 1.5
                    hits.append(kw)
    best_ex = 0.0
    for ex in t.get("example_queries", []):
        ex_tokens = tokenize(ex) - STOP
        ov = len(ex_tokens & q_tokens)
        frac = ov / max(1, len(ex_tokens))
        best_ex = max(best_ex, frac)
    score += 2.5 * best_ex
    return score, hits


def rank_tools(kb, query):
    """Rank all tools (Route A scripts) for a query. Tools use **1-gram**
    keyword matching (recall-favoring; harmless over-triggering as scripts are
    read-only). Returns (ranked, q_tokens, q_lower) where ranked is a list of
    (score, tool, matched_tokens) sorted best-first."""
    q_tokens = tokenize(query) - STOP
    q_lower = query.lower()

    # extra signal from routes_one_hop exact-ish matches
    route_boost = {}
    for r in kb.get("routes_one_hop", {}).get("examples", []):
        r_tokens = tokenize(r["query"]) - STOP
        ov = len(r_tokens & q_tokens)
        frac = ov / max(1, len(r_tokens))
        if frac > route_boost.get(r["tool"], 0):
            route_boost[r["tool"]] = frac

    ranked = []
    for t in kb["tools"]:
        s, hits = score_tool(t, q_tokens, q_lower, onegram=True)
        s += 2.0 * route_boost.get(t["id"], 0.0)
        ranked.append((s, t, hits))
    ranked.sort(key=lambda x: -x[0])
    return ranked


def rank_skills(kb, query):
    """Rank all skills (Route B text targets) for a query. Skills keep the
    **phrase-aware** matching (score_tool default) — higher precision, because
    routing to the wrong *guidance* is a real cost (unlike an extra read-only
    script). Returns a list of (score, skill, matched_keywords) sorted
    best-first, or [] if the KB defines no skills."""
    skills = kb.get("skills", [])
    if not skills:
        return []
    q_tokens = tokenize(query) - STOP
    q_lower = query.lower()

    route_boost = {}
    for r in kb.get("routes_one_hop_skills", {}).get("examples", []):
        r_tokens = tokenize(r["query"]) - STOP
        ov = len(r_tokens & q_tokens)
        frac = ov / max(1, len(r_tokens))
        if frac > route_boost.get(r["skill"], 0):
            route_boost[r["skill"]] = frac

    ranked = []
    for sk in skills:
        s, hits = score_tool(sk, q_tokens, q_lower)
        s += 2.0 * route_boost.get(sk["id"], 0.0)
        ranked.append((s, sk, hits))
    ranked.sort(key=lambda x: -x[0])
    return ranked


def run_list(kb, db, placeholder, as_json):
    if as_json:
        print(json.dumps(
            [{"id": t["id"], "title": t["title"],
              "invocation": fill(t["invocation"], db, placeholder),
              "layer": t.get("layer"), "produces": t.get("produces")}
             for t in kb["tools"]], indent=2))
        return 0
    print("Knowledge base tools (one-hop targets):")
    for t in kb["tools"]:
        print(f"\n  [{t['id']}]  {t['title']}   ({t.get('layer','')})")
        print(f"    run: {fill(t['invocation'], db, placeholder)}")
        print(f"    for: {t.get('produces','')}")
        ex = t.get("example_queries", [])
        if ex:
            print(f"    e.g. \"{ex[0]}\"")
    return 0


def run_skills_list(kb, as_json):
    skills = kb.get("skills", [])
    if as_json:
        print(json.dumps(
            [{"id": sk["id"], "name": sk.get("name"), "title": sk["title"],
              "open": sk["path"], "produces": sk.get("produces")}
             for sk in skills], indent=2))
        return 0
    if not skills:
        print("No skills registered for routing yet. See kb.json skills[] to add one.")
        return 0
    print("Knowledge base skills (Route B — one-hop text targets):")
    for sk in skills:
        print(f"\n  [{sk['id']}]  {sk['title']}   ({sk.get('name','')})")
        print(f"    open: {sk['path']}")
        print(f"    for: {sk.get('produces','')}")
        ex = sk.get("example_queries", [])
        if ex:
            print(f"    e.g. \"{ex[0]}\"")
    return 0


def run_workflows(kb, as_json):
    wfs = kb.get("workflows", [])
    if as_json:
        print(json.dumps(wfs, indent=2))
        return 0
    if not wfs:
        print("No multi-hop workflows defined yet. See kb.json workflow_schema to add one.")
        return 0
    print("Multi-hop troubleshooting workflows (guarded diagnostic graph):")
    for w in wfs:
        print(f"\n  [{w['id']}]  {w['title']}   status={w.get('status','')}")
        print(f"    entry: {w['entry']}")
        for sid, step in w.get("steps", {}).items():
            deps = step.get("depends_on", [])
            dep = f"  (after: {', '.join(deps)})" if deps else ""
            print(f"      - {sid}: tool={step['tool']}{dep}")
            for obs, edge in step.get("yields", {}).items():
                nxt = edge.get("next")
                concl = edge.get("or_conclude")
                arrow = f"-> {nxt}" if nxt else f"=> {concl}"
                print(f"          on {obs}: {arrow}")
    return 0


def run_route(kb, db, placeholder, as_json, query):
    if not query:
        print("Provide a natural-language query, or use --list / --skills / --workflows.",
              file=sys.stderr)
        return 2

    ranked = rank_tools(kb, query)
    best_s, best_t, best_hits = ranked[0]
    alternatives = [(s, t) for s, t, _ in ranked[1:] if s > 0][:2]

    ranked_sk = rank_skills(kb, query)
    best_sk_s, best_sk, best_sk_hits = ranked_sk[0] if ranked_sk else (0.0, None, [])
    sk_alternatives = [(s, sk) for s, sk, _ in ranked_sk[1:] if s > 0][:2]

    # Which route (script vs skill) is the stronger answer? Ties favour the
    # script (Route A) since a measured diagnostic beats generic guidance.
    if best_sk_s > best_s and best_sk_s > 0:
        recommended = "skill"
    elif best_s > 0:
        recommended = "script"
    else:
        recommended = None

    if as_json:
        out = {
            "query": query,
            "match": None if best_s <= 0 else {
                "tool": best_t["id"], "title": best_t["title"], "score": round(best_s, 2),
                "matched_keywords": best_hits,
                "command": fill(best_t["invocation"], db, placeholder),
                "needs_db": (not db) and (placeholder in best_t["invocation"]),
            },
            "alternatives": [{"tool": t["id"], "score": round(s, 2)} for s, t in alternatives],
            "confident": best_s >= 2.0,
            "skill_match": None if best_sk_s <= 0 else {
                "skill": best_sk["id"], "name": best_sk.get("name"), "title": best_sk["title"],
                "score": round(best_sk_s, 2), "matched_keywords": best_sk_hits,
                "open": best_sk["path"],
            },
            "skill_alternatives": [{"skill": sk["id"], "score": round(s, 2)} for s, sk in sk_alternatives],
            "skill_confident": best_sk_s >= 2.0,
            "recommended": recommended,
        }
        print(json.dumps(out, indent=2))
        return 0

    if best_s <= 0 and best_sk_s <= 0:
        print(f'No confident route for: "{query}"')
        print("Available scripts (use --list) / skills (use --skills).")
        return 0

    print(f'Query: "{query}"')

    if best_s > 0:
        conf = "high" if best_s >= 4 else ("medium" if best_s >= 2 else "low")
        tag = "  ← recommended" if recommended == "script" else ""
        print(f'→ Route A (script): [{best_t["id"]}]  {best_t["title"]}   (confidence: {conf}, score {best_s:.1f}){tag}')
        if best_hits:
            print(f'  matched: {", ".join(best_hits[:6])}')
        print(f'  run: {fill(best_t["invocation"], db, placeholder)}')
        if (not db) and (placeholder in best_t["invocation"]):
            print(f'  (supply the database: --db <name>  — replaces {placeholder})')
        if alternatives:
            print("  alternatives: " + ", ".join(f"{t['id']} ({s:.1f})" for s, t in alternatives))

    if best_sk_s > 0:
        conf = "high" if best_sk_s >= 4 else ("medium" if best_sk_s >= 2 else "low")
        tag = "  ← recommended" if recommended == "skill" else ""
        print(f'→ Route B (skill):  [{best_sk["id"]}]  {best_sk["title"]}   (confidence: {conf}, score {best_sk_s:.1f}){tag}')
        if best_sk_hits:
            print(f'  matched: {", ".join(best_sk_hits[:6])}')
        print(f'  open: {best_sk["path"]}')
        if sk_alternatives:
            print("  alternatives: " + ", ".join(f"{sk['id']} ({s:.1f})" for s, sk in sk_alternatives))

    return 0


def main():
    kb_path = os.environ["KB"]
    db = os.environ.get("DB") or ""
    as_json = os.environ.get("JSON") == "1"
    mode = os.environ.get("MODE") or "route"
    query = (os.environ.get("QUERY") or "").strip()

    with open(kb_path) as fh:
        kb = json.load(fh)

    placeholder = kb.get("conventions", {}).get("db_placeholder", "<db>")

    if mode == "list":
        return run_list(kb, db, placeholder, as_json)
    if mode == "skills":
        return run_skills_list(kb, as_json)
    if mode == "workflows":
        return run_workflows(kb, as_json)
    return run_route(kb, db, placeholder, as_json, query)


if __name__ == "__main__":
    sys.exit(main())
