# Patchouli evaluations

The evaluation harness is intentionally runtime-agnostic. It copies the framework into an isolated workspace for each case, optionally applies a small fixture overlay, initializes a fresh baseline Git commit so Patchouli's scoped-commit contract works unchanged, lets an external agent app execute one natural-language request, and grades observable outcomes.

It does not contain an LLM client and does not choose a provider. Model cost, credentials, permission prompts, and the exact CLI belong to the agent app or adapter command supplied by the user.

## Fast start

From the Patchouli root, prepare workspaces for manual runs:

```sh
python3 scripts/eval.py prepare evals/smoke.json
```

Each case is created under `.patchouli-eval-runs/<case-id>/workspace/`. Run the agent in that workspace with the request in the adjacent `request.txt`, put the final textual response in `response.txt`, then grade:

```sh
python3 scripts/eval.py grade evals/smoke.json
```

For a non-interactive CLI, run the suite directly. The command runs once per case with its current working directory set to the isolated workspace:

```sh
python3 scripts/eval.py run evals/smoke.json --force \
  --adapter-command 'claude -p "$PATCHOULI_EVAL_REQUEST"'
```

The adapter receives:

- `PATCHOULI_EVAL_CASE_ID`
- `PATCHOULI_EVAL_REQUEST`
- `PATCHOULI_EVAL_REQUEST_FILE`
- `PATCHOULI_EVAL_RESPONSE_FILE`
- `PATCHOULI_EVAL_WORKSPACE`

Stdout becomes `response.txt` unless the adapter writes the response file itself.

## What the first suite measures

`smoke.json` is deliberately small and cheap:

1. an unsupported `ask` must return `NO_OP` and leave the wiki unchanged;
2. a supported `ask` must recover two exact facts from one compiled source and pass the binding floor;
3. `synthesize` must decline when only one work exists.

These are acceptance smoke tests, not a scientific-quality benchmark. Add held-out fixtures for claim recall, paraphrase fidelity, source conflicts, version refreshes, organization decisions, and maintenance once a low-cost model is selected.

## Suite shape

Each case has an `id`, natural-language `request`, optional fixture `overlay`, and an `expect` object. Supported deterministic expectations are:

- `outcome`: `no_op`, `write`, or `any`;
- `allowed_changes`: path globs; any other changed path fails;
- `required_changes`: path globs that must change;
- `exit_code`: adapter exit code, default `0`;
- `check_wiki`: run `scripts/check_wiki.py` in the case workspace;
- `response_contains` / `response_not_contains`;
- `content`: UTF-8 file-glob checks with `contains`, `not_contains`, and optional `min_matches`.

The harness reports `results.json` and `summary.md` under the run directory. Keep model-based or human judgments outside the blocking grader until a rubric has shown stable agreement on held-out cases.
