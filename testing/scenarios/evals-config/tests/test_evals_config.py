"""Static validation of the Cross-Model Skill Evaluations eval + experiment configs.

WHY THIS EXISTS
---------------
`vally experiment run --dry-run` validates the matrix structure but does NOT
check that the skill paths point at anything real. That gap produced a live bug
while this scenario's sibling files were being written: the experiment
referenced `../skills/query-performance-tuning`, which exists on a different
branch. The dry run passed.

That is the worst possible failure mode for an A/B test. A treatment arm whose
skills silently fail to load is just a second control arm — and it would have
produced a confident, published, completely wrong conclusion of "the kit makes
no difference".

These tests are cheap, need no container, no credentials and no network, and
they run on every PR.
"""

from pathlib import Path

import pytest
import yaml

import kit

pytestmark = pytest.mark.evalsconfig

EVALS_DIR = kit.REPO_DIR / "evals"
EVAL_SPEC = EVALS_DIR / "documentdb-skills" / "eval.yaml"
EXPERIMENT = EVALS_DIR / "documentdb-skills.experiment.yaml"


def _load(path: Path) -> dict:
    assert path.exists(), f"missing config: {path}"
    return yaml.safe_load(path.read_text())


@pytest.fixture(scope="module")
def spec():
    return _load(EVAL_SPEC)


@pytest.fixture(scope="module")
def experiment():
    return _load(EXPERIMENT)


# ---------------------------------------------------------------------------
# skill paths must resolve
# ---------------------------------------------------------------------------
def _skill_dir_is_valid(p: Path) -> bool:
    return p.is_dir() and (p / "SKILL.md").is_file()


def test_eval_skill_paths_exist(spec):
    """Paths in an eval spec resolve relative to the eval file's directory."""
    base = EVAL_SPEC.parent
    skills = spec["environment"]["skills"]
    assert skills, "eval spec declares no skills — the treatment arm is empty"
    missing = [s for s in skills if not _skill_dir_is_valid((base / s).resolve())]
    assert not missing, (
        f"eval.yaml references skills that do not exist or have no SKILL.md: "
        f"{missing}"
    )


def _kit_skills(experiment) -> list[str]:
    for entry in experiment["matrix"]["skills"]["values"]:
        if isinstance(entry, dict) and "kit" in entry:
            return entry["kit"]
    pytest.fail("experiment matrix has no 'kit' (treatment) arm")


def test_experiment_skill_paths_exist(experiment):
    """Paths inside variant overrides resolve relative to the EXPERIMENT file's
    directory — a different base than the eval spec uses. Getting this wrong is
    easy and silent, which is exactly why it is asserted."""
    base = EXPERIMENT.parent
    missing = [
        s for s in _kit_skills(experiment)
        if not _skill_dir_is_valid((base / s).resolve())
    ]
    assert not missing, (
        f"experiment treatment arm references skills that do not exist: {missing}\n"
        "A treatment arm whose skills fail to load is a second control arm."
    )


def test_treatment_and_eval_skill_sets_agree(spec, experiment):
    """The two files must describe the same kit.

    If they drift, `vally eval` and `vally experiment run` measure different
    things while reporting under the same name.
    """
    eval_names = {Path(s).name for s in spec["environment"]["skills"]}
    exp_names = {Path(s).name for s in _kit_skills(experiment)}
    assert eval_names <= exp_names, (
        f"eval.yaml declares skills the experiment's treatment arm omits: "
        f"{sorted(eval_names - exp_names)}"
    )


# ---------------------------------------------------------------------------
# the experiment must be a valid controlled comparison
# ---------------------------------------------------------------------------
def test_control_arm_is_empty(experiment):
    """The control must have NO skills. A 'control' that loads part of the kit
    measures nothing."""
    values = experiment["matrix"]["skills"]["values"]
    control = next(
        (v["control"] for v in values if isinstance(v, dict) and "control" in v),
        None,
    )
    assert control is not None, "experiment matrix has no 'control' arm"
    assert control == [], f"control arm is not empty: {control}"


def test_baseline_is_a_control_cell(experiment):
    """Deltas are measured against the baseline, so the baseline must be an
    unskilled arm — otherwise every reported delta is against a treated run."""
    assert experiment["baseline"]["skills"] == "control", (
        "baseline must sit in the control arm"
    )


def test_models_are_declared_and_distinct(experiment):
    models = experiment["matrix"]["model"]["values"]
    assert len(models) >= 2, "a cross-model comparison needs at least 2 models"
    assert len(set(models)) == len(models), f"duplicate models: {models}"
    assert experiment["baseline"]["model"] in models


def test_runs_per_cell_is_enough_for_a_spread(experiment):
    """Agent output is non-deterministic. N=1 is an anecdote, not a measurement.

    The token harness flags cells with n<3; the experiment should not be
    configured to produce them in the first place.
    """
    runs = experiment.get("overrides", {}).get("runs")
    assert runs is not None, "experiment does not pin `runs`"
    assert runs >= 3, f"runs={runs} is too few to report a mean and spread"


def test_matrix_expands_to_every_model_arm_cell(experiment):
    models = experiment["matrix"]["model"]["values"]
    arms = experiment["matrix"]["skills"]["values"]
    assert len(models) * len(arms) == 6, (
        "expected a 3-model x 2-arm matrix; update this test deliberately if "
        "the design changes"
    )


# ---------------------------------------------------------------------------
# the eval spec must remain an honest measurement
# ---------------------------------------------------------------------------
def test_prompts_never_mention_the_skills(spec):
    """The organic-discovery protocol: the agent is never told to use the kit.

    Hinting turns 'does an installed kit get applied?' into the much easier and
    much less interesting 'can the model follow an instruction?'.
    """
    banned = ("use the skill", "using the skill", "documentdb-query-optimizer",
              "documentdb-indexing", "documentdb-connection", "agent kit",
              "skills/")
    offenders = []
    for stim in spec["stimuli"]:
        prompt = stim.get("prompt", "").lower()
        for phrase in banned:
            if phrase in prompt:
                offenders.append((stim["name"], phrase))
    assert not offenders, (
        f"stimulus prompts hint at the skills, which invalidates the "
        f"organic-discovery protocol: {offenders}"
    )


def test_anti_trigger_stimuli_exist(spec):
    """Half of routing quality is NOT firing on unrelated questions. An eval
    with only positive triggers rewards a kit that triggers on everything."""
    kinds = [s.get("tags", {}).get("kind") for s in spec["stimuli"]]
    assert "anti-trigger" in kinds, "no anti-trigger stimuli — over-triggering "
    assert "trigger" in kinds, "no positive-trigger stimuli"


def test_every_stimulus_has_a_grader(spec):
    for stim in spec["stimuli"]:
        assert stim.get("graders"), f"stimulus {stim['name']!r} has no grader"


def test_graders_are_objective(spec):
    """Phase 1 stimuli should be graded reproducibly.

    Not a prohibition on LLM judges — they are a normal grader and
    Cross-Model Skill Evaluations are expected to use one for qualitative
    dimensions. But the Phase 1 stimuli are
    all skill-TRIGGERING checks, which have a definite right answer, so a
    reproducible grader is the correct fit and a judge here would add cost and
    variance for nothing.

    The allowlist is a speed bump, not a wall: adding a judge should be a
    deliberate, reviewed change that records which stimulus needs it and why.
    """
    reproducible = {"skill-invocation", "run-command", "file-exists", "regex"}
    others = []
    for stim in spec["stimuli"]:
        for g in stim["graders"]:
            if g["type"] not in reproducible:
                others.append((stim["name"], g["type"]))
    assert not others, (
        f"graders outside the reproducible set are in use: {others}. If a "
        f"judge is genuinely the right fit for that stimulus, add its type to "
        f"the allowlist in this test and note why."
    )


# ---------------------------------------------------------------------------
# quality eval — the LLM-judge panel
#
# A judge is easy to do badly, and a badly-built one produces confident numbers
# that are wrong. These pin the anti-bias properties that make the score worth
# reporting at all. They are cheap, need no model, and run on every PR.
# ---------------------------------------------------------------------------
QUALITY_SPEC = EVALS_DIR / "documentdb-quality" / "quality-eval.yaml"
QUALITY_EXPERIMENT = EVALS_DIR / "quality.experiment.yaml"


@pytest.fixture(scope="module")
def quality():
    return _load(QUALITY_SPEC)


def _panels(spec):
    out = []
    for stim in spec["stimuli"]:
        for g in stim["graders"]:
            if g["type"] == "panel":
                out.append((stim["name"], g["config"]))
    return out


def test_quality_eval_uses_a_multi_vendor_panel(quality):
    """Self-preference bias is real: models rate their own output higher.

    A single-model judge on a cross-model comparison would systematically
    favour one arm. Requiring judges from 3 distinct vendors makes that
    impossible for any one of them to swing alone.
    """
    for name, cfg in _panels(quality):
        models = [m["model"] if isinstance(m, dict) else m for m in cfg["models"]]
        assert len(models) >= 3, f"{name}: panel has only {models}"
        vendors = {m.split("-")[0] for m in models}
        assert len(vendors) >= 3, (
            f"{name}: judges come from too few vendors ({sorted(vendors)}). "
            f"A model must never be the sole judge of output it could have "
            f"produced itself."
        )


def test_quality_panel_aggregates_by_median(quality):
    """A mean lets one miscalibrated judge drag the verdict; a median does not."""
    for name, cfg in _panels(quality):
        assert cfg.get("aggregation") == "median", (
            f"{name}: aggregation is {cfg.get('aggregation')!r}, expected "
            f"'median' — one outlier judge must not decide the result."
        )


def test_correctness_criteria_are_gates(quality):
    """A fluent, confident, WRONG answer must fail.

    technical_correctness and documentdb_specificity are marked `required`, so
    they gate the verdict: prose quality can never outvote accuracy.
    """
    must_gate = {"technical_correctness", "documentdb_specificity"}
    for name, cfg in _panels(quality):
        criteria = {c["name"]: c for c in cfg["criteria"]}
        missing = must_gate - set(criteria)
        assert not missing, f"{name}: missing criteria {sorted(missing)}"
        for key in must_gate:
            assert criteria[key].get("required") is True, (
                f"{name}: {key} is not a required gate, so an answer could "
                f"pass on style while being wrong."
            )


def test_correctness_outweighs_style(quality):
    """Weight, not just gating: correctness must carry more than any single
    presentational dimension."""
    for name, cfg in _panels(quality):
        criteria = {c["name"]: c.get("weight", 1) for c in cfg["criteria"]}
        correctness = criteria["technical_correctness"]
        for other, weight in criteria.items():
            if other in ("technical_correctness", "documentdb_specificity"):
                continue
            assert correctness > weight, (
                f"{name}: technical_correctness (weight {correctness}) does not "
                f"outweigh {other} (weight {weight})."
            )


def test_judges_are_blinded(quality):
    """If a judge knows which arm produced an answer, it will find reasons.

    The prompt must instruct the judge not to infer provenance, and must not
    itself leak the experiment's vocabulary.
    """
    for name, cfg in _panels(quality):
        prompt = cfg.get("prompt", "")
        assert prompt, f"{name}: panel has no judge prompt"
        assert "BLINDING" in prompt.upper(), (
            f"{name}: judge prompt carries no blinding instruction"
        )
        leaked = [w for w in ("treatment arm", "control arm", "skills installed",
                              "with the kit", "agent kit")
                  if w in prompt.lower()]
        assert not leaked, (
            f"{name}: judge prompt leaks experiment vocabulary {leaked}; the "
            f"judge must not know which condition it is grading."
        )


def test_every_quality_stimulus_has_an_anchored_rubric(quality):
    """"Rate this 1-5" is not a rubric. Each stimulus states what a good answer
    contains, so two runs are scored against the same yardstick."""
    for stim in quality["stimuli"]:
        rubric = stim.get("rubric")
        assert rubric and len(rubric) >= 3, (
            f"{stim['name']}: needs an anchored rubric of at least 3 criteria, "
            f"got {rubric!r}"
        )


def test_quality_prompts_do_not_name_the_solution(quality):
    """Same organic-discovery rule as the triggering eval: if the prompt says
    "use a compound index", the judge grades instruction-following instead of
    guidance quality, and both arms score alike."""
    banned = ("compound index", "createindex", "create_index", "esr",
              "singleton", "ttl index", "multikey", "skill")
    offenders = []
    for stim in quality["stimuli"]:
        prompt = stim["prompt"].lower()
        offenders += [(stim["name"], b) for b in banned if b in prompt]
    assert not offenders, (
        f"quality prompts name the solution {offenders}; the answer must come "
        f"from the responder, not the question."
    )


def test_quality_runs_are_repeated(quality):
    """Both agent output and judge scoring vary. n=1 is an anecdote."""
    runs = quality.get("defaults", {}).get("runs")
    assert runs and runs >= 3, f"runs={runs}; need >= 3 for a usable median"


def test_quality_experiment_has_a_control_arm():
    """The decisive one for this eval.

    Frontier models already answer MongoDB questions well, so a treatment-only
    quality score proves nothing. Only the delta against an unskilled agent
    supports the claim "the kit makes the guidance better".
    """
    exp = _load(QUALITY_EXPERIMENT)
    values = exp["matrix"]["skills"]["values"]
    control = next((v["control"] for v in values
                    if isinstance(v, dict) and "control" in v), None)
    assert control == [], f"control arm must be empty, got {control!r}"
    assert exp["baseline"]["skills"] == "control"


def test_quality_experiment_skill_paths_exist():
    """Same silent-failure trap as the triggering experiment: a treatment arm
    whose skills do not load is just a second control arm."""
    exp = _load(QUALITY_EXPERIMENT)
    kit = next((v["kit"] for v in exp["matrix"]["skills"]["values"]
                if isinstance(v, dict) and "kit" in v), [])
    base = QUALITY_EXPERIMENT.parent
    missing = [s for s in kit if not _skill_dir_is_valid((base / s).resolve())]
    assert not missing, f"quality experiment references missing skills: {missing}"
