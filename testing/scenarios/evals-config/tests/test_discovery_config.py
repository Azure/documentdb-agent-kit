"""Guards for a product-neutral, paired cross-model discovery experiment."""

import pytest
import yaml

import kit

pytestmark = pytest.mark.evalsconfig

EVALS = kit.REPO_DIR / "evals"
SPEC_PATH = EVALS / "documentdb-discovery" / "eval.yaml"
EXPERIMENT_PATH = EVALS / "discovery.experiment.yaml"


def _load(path):
    return yaml.safe_load(path.read_text())


def test_discovery_prompt_is_only_the_developer_request():
    spec = _load(SPEC_PATH)
    assert len(spec["stimuli"]) == 1
    assert spec["stimuli"][0]["prompt"] == (
        "Build an API that stores customer data in a document database"
    )
    assert "system_prompt" not in spec.get("defaults", {})


def test_every_model_has_identical_control_and_full_kit_conditions():
    spec = _load(SPEC_PATH)
    exp = _load(EXPERIMENT_PATH)
    assert exp["evals"] == ["documentdb-discovery/eval.yaml"]
    models = exp["matrix"]["model"]
    assert models["path"] == "/defaults/model"
    assert len(set(models["values"])) == len(models["values"]) == 3
    assert len({model.split("-")[0] for model in models["values"]}) == 3
    skills = exp["matrix"]["skills"]
    assert skills["path"] == "/environment/skills"
    assert len(skills["values"]) == 2
    arms = {key: value for entry in skills["values"] for key, value in entry.items()}
    assert arms["control"] == []
    expected = {
        path.resolve()
        for path in (kit.REPO_DIR / "skills").iterdir()
        if (path / "SKILL.md").is_file()
    }
    actual = {(EXPERIMENT_PATH.parent / path).resolve() for path in arms["kit"]}
    standalone = {
        (SPEC_PATH.parent / path).resolve()
        for path in spec["environment"]["skills"]
    }
    assert actual == standalone == expected
    assert exp["overrides"]["runs"] >= 5
    assert exp["baseline"]["skills"] == "control"
    assert exp["baseline"]["model"] in models["values"]
    # No extra axis may silently change the prompt or grader between arms.
    assert set(exp["matrix"]) == {"model", "skills"}


def test_discovery_grades_selection_not_skill_invocation_or_mentions():
    stimulus = _load(SPEC_PATH)["stimuli"][0]
    assert [grader["type"] for grader in stimulus["graders"]] == ["panel"]
    config = stimulus["graders"][0]["config"]
    assert set(config["evidence"]) == {"trajectory", "diff"}
    assert config["scoring"] == "binary"
    assert config["aggregation"] == "median"
    assert config["threshold"] == 1
    assert len({entry["model"].split("-")[0] for entry in config["models"]}) == 3
    rubric = " ".join(config["prompt"].split())
    for boundary in (
        "primary", "passing mention", "Amazon DocumentDB",
        "MongoDB Atlas", "PyMongo", "BLINDING", "Ignore tool listings",
        "open-source DocumentDB", "Microsoft.DocumentDB/mongoClusters",
        "ghcr.io/documentdb/documentdb/documentdb-local", "JSON/JSONB",
        "Never give both criteria 1", "used only for development",
        "Azure offered only as an optional deployment",
    ):
        assert boundary in rubric


def test_discovery_reports_both_primary_targets_on_the_same_trial():
    spec = _load(SPEC_PATH)
    assert len(spec["stimuli"]) == 1
    graders = spec["stimuli"][0]["graders"]
    assert len(graders) == 1
    criteria = graders[0]["config"]["criteria"]
    assert {criterion["name"] for criterion in criteria} == {
        "selected_oss_documentdb", "selected_azure_documentdb",
    }
    assert len(criteria) == 2
    assert all(criterion["weight"] == 1 for criterion in criteria)


def test_either_primary_target_can_pass_without_requiring_both():
    spec = _load(SPEC_PATH)
    config = spec["stimuli"][0]["graders"][0]["config"]
    assert all(criterion["required"] is False for criterion in config["criteria"])
    assert config["overall_threshold"] == spec["scoring"]["threshold"] == 0.5
