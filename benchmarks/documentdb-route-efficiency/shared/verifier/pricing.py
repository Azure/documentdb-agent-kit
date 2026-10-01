#!/usr/bin/env python3
"""Convert token usage to USD, so models can be compared on cost.

WHY TOKENS ARE NOT COMPARABLE ACROSS MODELS
-------------------------------------------
One token of Gemini 3.1 Pro is not one token of GPT-5.6 Sol. Measured against
the published rates below, output tokens differ by **2.5x** ($12 vs $30 per
MTok) and input by **2.5x** ($2 vs $5). A cross-model table in raw tokens would
rank the models by their tokenisers and their verbosity, not by what they cost.

RELATIONSHIP TO COPILOT AI CREDITS (validated, and it surprised me)
-------------------------------------------------------------------
`total_nano_aiu` turns out to BE token-based per-model pricing at
1 credit = $0.01. Pricing this machine's own history with the published rates
below and dividing by (credits x $0.01) gives a median ratio of:

    gemini-3.1-pro-preview  1.000      claude-opus-5    0.995
    claude-opus-4.8         0.985      gpt-5.6-sol      0.968

i.e. the two agree within ~3%.

An earlier reading of this data concluded the opposite — that credits were a
premium-request metric only weakly related to tokens (correlations 0.15-0.46).
That was a measurement error worth recording: it correlated RAW token counts
with cost, but cached tokens are billed ~10x cheaper, so total tokens and cost
are not proportional by construction. Once fresh and cached input are priced
separately, the relationship is essentially exact.

So why keep this module rather than just report credits?

  * it is an INDEPENDENT check on Copilot's billing — two methods agreeing
    within 3% is far stronger evidence than either alone, and a future
    divergence is a signal worth catching
  * it itemises fresh input vs cache reads vs output, which is what explains
    WHERE a route's cost goes; a single credit figure cannot
  * it prices against each provider's published rates, so a number can be
    quoted to someone who does not use Copilot billing
  * it still works when credits are absent or zero

CACHE PRICING IS THE REASON THE FRESH/CACHED SPLIT MATTERS
-----------------------------------------------------------
All three providers discount cache reads by ~90% ($0.50/MTok against $2-$5).
Billing every input token at the full rate would overstate a skill payload's
cost by roughly 10x, because it is sent once and then read from cache.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Published rates, USD per 1M tokens. Retrieved 2026-08-17 from each provider's
# own documentation — not from a third-party aggregator.
#
# Re-check before publishing: these change, and a stale table silently produces
# wrong dollar figures with no other symptom.
# ---------------------------------------------------------------------------
PRICING_RETRIEVED = "2026-08-17"

PRICING = {
    "claude-opus-5": {
        "input": 5.00, "cached_input": 0.50, "output": 25.00,
        "cache_write_5m": 6.25,
        "source": "https://platform.claude.com/docs/en/about-claude/pricing",
    },
    "claude-opus-4.8": {
        "input": 5.00, "cached_input": 0.50, "output": 25.00,
        "cache_write_5m": 6.25,
        "source": "https://platform.claude.com/docs/en/about-claude/pricing",
    },
    "gpt-5.6-sol": {
        "input": 5.00, "cached_input": 0.50, "output": 30.00,
        "cache_write_5m": 6.25,
        # Prompts over 272K input tokens bill at 2x input and 1.5x output for
        # the WHOLE request, not just the overflow.
        "long_context_threshold": 272_000,
        "long_context_input_mult": 2.0,
        "long_context_output_mult": 1.5,
        "source": "https://developers.openai.com/api/docs/models/gpt-5.6-sol",
    },
    "gemini-3.1-pro-preview": {
        "input": 2.00, "cached_input": 0.50, "output": 12.00,
        "cache_write_5m": 2.00,
        # Over 200K context the whole request moves to the higher tier.
        "long_context_threshold": 200_000,
        "long_context_input_mult": 2.0,     # $2 -> $4
        "long_context_output_mult": 1.5,    # $12 -> $18
        "source": "https://ai.google.dev/gemini-api/docs/pricing",
    },
}

# `output_tokens` is treated as the billable output and `reasoning_tokens` is
# NOT added on top. In this machine's history reasoning <= output in 99.6% of
# rows (16 of 4,269 exceptions), which is what you would expect if reasoning is
# already counted inside output. Adding them would double-bill thinking tokens.
# Flip with --add-reasoning if a provider is shown to report them separately.
ADD_REASONING_BY_DEFAULT = False


class UnknownModel(KeyError):
    """Raised rather than guessing a price.

    A default rate would produce a plausible dollar figure for a model we have
    no pricing for, and nothing downstream could tell it was invented.
    """


def cost_usd(usage: dict, model: str, add_reasoning: bool = ADD_REASONING_BY_DEFAULT) -> dict:
    """Itemised USD cost for one run.

    `usage` needs: fresh_input_tokens (or input_tokens + cache_read_tokens),
    output_tokens, and optionally reasoning_tokens.
    """
    if model not in PRICING:
        raise UnknownModel(
            f"no published pricing for {model!r}. Add it to PRICING with a "
            f"source URL rather than falling back to a default rate."
        )
    p = PRICING[model]

    cache_read = int(usage.get("cache_read_tokens", 0) or 0)
    if "fresh_input_tokens" in usage:
        fresh = int(usage["fresh_input_tokens"])
    else:
        fresh = max(int(usage.get("input_tokens", 0) or 0) - cache_read, 0)

    output = int(usage.get("output_tokens", 0) or 0)
    if add_reasoning:
        output += int(usage.get("reasoning_tokens", 0) or 0)

    in_rate, out_rate = p["input"], p["output"]
    total_input = fresh + cache_read
    long_context = False
    threshold = p.get("long_context_threshold")
    if threshold and total_input > threshold:
        long_context = True
        in_rate *= p.get("long_context_input_mult", 1.0)
        out_rate *= p.get("long_context_output_mult", 1.0)

    fresh_cost = fresh / 1e6 * in_rate
    cache_cost = cache_read / 1e6 * p["cached_input"]
    out_cost = output / 1e6 * out_rate

    return {
        "model": model,
        "usd_total": round(fresh_cost + cache_cost + out_cost, 6),
        "usd_fresh_input": round(fresh_cost, 6),
        "usd_cached_input": round(cache_cost, 6),
        "usd_output": round(out_cost, 6),
        "billed_fresh_input_tokens": fresh,
        "billed_cache_read_tokens": cache_read,
        "billed_output_tokens": output,
        "long_context_tier": long_context,
        "rates_usd_per_mtok": {
            "input": in_rate, "cached_input": p["cached_input"], "output": out_rate,
        },
        "pricing_retrieved": PRICING_RETRIEVED,
        "pricing_source": p["source"],
    }


def price_runs(runs: list[dict], add_reasoning: bool = ADD_REASONING_BY_DEFAULT) -> list[dict]:
    out = []
    for r in runs:
        priced = dict(r)
        try:
            priced["cost"] = cost_usd(r, r.get("model", ""), add_reasoning)
        except UnknownModel as exc:
            priced["cost"] = None
            priced["cost_error"] = str(exc)
        out.append(priced)
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("runs", type=Path, nargs="?",
                   help="JSON array of runs from attribute.py (default: show the rate table)")
    p.add_argument("--add-reasoning", action="store_true",
                   help="bill reasoning_tokens on top of output_tokens")
    p.add_argument("--out", type=Path)
    args = p.parse_args(argv)

    if not args.runs:
        print(f"Published rates (USD per 1M tokens), retrieved {PRICING_RETRIEVED}\n")
        print(f"{'model':26} {'input':>8} {'cached':>8} {'output':>8}")
        for name, v in PRICING.items():
            print(f"{name:26} {v['input']:>8.2f} {v['cached_input']:>8.2f} {v['output']:>8.2f}")
        print("\nSources:")
        for name, v in PRICING.items():
            print(f"  {name:26} {v['source']}")
        return 0

    runs = json.loads(args.runs.read_text())
    priced = price_runs(runs, args.add_reasoning)
    text = json.dumps(priced, indent=2, sort_keys=True)
    if args.out:
        args.out.write_text(text + "\n")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
