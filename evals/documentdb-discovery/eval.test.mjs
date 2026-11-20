import assert from "node:assert/strict";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { loadEvalSpec, PanelGrader } from "@microsoft/vally";

const spec = await loadEvalSpec(fileURLToPath(new URL("eval.yaml", import.meta.url)));
const stimulus = spec.stimuli[0];
const config = stimulus.graders[0].config;
const names = ["selected_oss_documentdb", "selected_azure_documentdb"];
const trajectory = {
  id: "discovery-grading-fixture",
  output: "Synthetic API evidence",
  events: [],
  diff: "diff --git a/README.md b/README.md\n+Synthetic API evidence\n",
  metrics: {
    tokenUsage: { inputTokens: 0, outputTokens: 0, totalTokens: 0 },
    toolCallCount: 0,
    toolCallBreakdown: {},
    skillActivationCount: 0,
    skillActivationBreakdown: {},
    turnCount: 0,
    wallTimeMs: 0,
    errorCount: 0,
  },
};

// Synthetic judge responses verify native aggregation, not model classification.
for (const { name, votes, expected, failedJudge } of [
  { name: "OSS alone passes", votes: [[1, 0], [1, 0], [1, 0]], expected: [1, 0] },
  { name: "Azure alone passes", votes: [[0, 1], [0, 1], [0, 1]], expected: [0, 1] },
  { name: "neither target fails", votes: [[0, 0], [0, 0], [0, 0]], expected: [0, 0] },
  { name: "OSS median survives dissent", votes: [[1, 0], [1, 0], [0, 1]], expected: [1, 0] },
  { name: "Azure median survives dissent", votes: [[0, 1], [0, 1], [1, 0]], expected: [0, 1] },
  {
    name: "judge errors are preserved, not successful discovery",
    votes: [[1, 0], [1, 0], [1, 0]],
    expected: [1, 0],
    failedJudge: 2,
  },
]) {
  test(name, async () => {
    const grader = new PanelGrader({
      async judge({ model }) {
        const index = config.models.findIndex((entry) => entry.model === model);
        assert.notEqual(index, -1);
        if (index === failedJudge) throw new Error("Synthetic judge failure");
        return {
          args: {
            overall_score: Math.max(...votes[index]),
            overall_reasoning: "Synthetic fixture",
            rubric_scores: names.map((criterion, i) => ({
              criterion, score: votes[index][i], reasoning: "Synthetic fixture",
            })),
          },
        };
      },
    });
    const result = await grader.grade({ config, stimulus, trajectory });
    assert.deepEqual(
      Object.fromEntries(result.metadata.criteria.map((criterion) => [
        criterion.name, criterion.score,
      ])),
      Object.fromEntries(names.map((name, i) => [name, expected[i]])),
    );
    assert.equal(result.score, (expected[0] + expected[1]) / 2);
    const shouldPass = expected.includes(1) && failedJudge === undefined;
    assert.equal(result.passed, shouldPass);
    assert.equal(result.passed && result.score >= spec.scoring.threshold, shouldPass);
    assert.equal(result.metadata.failed_judges?.length ?? 0, failedJudge === undefined ? 0 : 1);
  });
}
