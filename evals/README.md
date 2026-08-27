# Patchouli evaluations

The evaluation harness is runtime-agnostic: it does not contain an LLM client,
choose a provider, or count model calls. It prepares one Patchouli workspace per
natural-language contract request and grades observable outcomes such as
`NO_OP`, changed paths, exact content, and the binding floor.

## Two execution modes

### Manual/open-book preparation

```sh
python3 scripts/eval.py prepare evals/smoke.json
```

Each case appears under `.patchouli-eval-runs/<case-id>/workspace/`. Run an agent
there with the adjacent `request.txt`, put its final response in `response.txt`,
then grade:

```sh
python3 scripts/eval.py grade evals/smoke.json
```

The workspace copy omits `.env`, `personal.md`, `evals/`, `tests/`, the suite
file, and the fixture's original location. That is useful hygiene, but it is not
an OS access boundary: a manually launched process can still walk to parent or
repository paths unless the agent app itself confines filesystem access. Treat
manual mode as open-book acceptance testing.

### Held-out non-interactive runs on Linux

`run` defaults to Bubblewrap isolation:

```sh
python3 scripts/eval.py run /private/evals/suite.json --force \
  --isolation bwrap \
  --sandbox-home ~/.patchouli-eval-home \
  --adapter-command 'your-agent-cli "$PATCHOULI_EVAL_REQUEST"'
```

The Bubblewrap policy starts from an empty mount namespace. It exposes:

- the case workspace read-write at `/workspace`;
- the request read-only and response read-write under `/patchouli-eval`;
- `/usr` and `/etc` read-only, plus minimal `/proc`, `/dev`, and `/tmp`;
- an optional dedicated sandbox home;
- only additional paths explicitly named by `--sandbox-read` or
  `--sandbox-write`.

The repository, source suite, fixture origin, sibling cases, and run-control
files are not mounted. A new PID namespace hides host processes. The harness
rejects extra mounts that overlap the repository, suite, or output tree.

Install `bubblewrap` (`bwrap`) first. Keep the sandbox home outside both the
repository and output, and put only the adapter state it needs there. The policy
retains network access because hosted model CLIs need it. Therefore a suite
committed to a public repository is public/open-book regardless of local
filesystem isolation; credible held-out suites and fixtures must remain private
and unpublished.

Use `--isolation none` only for explicit acceptance smoke or when the selected
agent runtime independently enforces an equivalent workspace-only boundary:

```sh
python3 scripts/eval.py run evals/smoke.json --force --isolation none \
  --adapter-command 'claude -p "$PATCHOULI_EVAL_REQUEST"'
```

The included `smoke.json` is deliberately public acceptance material, not a
scientific held-out benchmark.

## Private suites and fixtures

Fixture overlay paths are resolved relative to the suite JSON, not the Patchouli
repository. A private suite can therefore live outside the framework clone:

```text
/private/evals/
  suite.json
  fixtures/
    case-a/
      wiki/...
      extracted/...
```

```json
{
  "cases": [
    {
      "id": "case-a",
      "overlay": "fixtures/case-a",
      "request": "...",
      "expect": {"outcome": "write"}
    }
  ]
}
```

An overlay must remain beneath its suite directory. The overlay copier applies
the same finite-tree rules as the framework copier: repository/fixture-confined
file symlinks are materialized; directory symlinks, broken symlinks, and symlinks
escaping their source tree are rejected.

## Adapter protocol

The command runs once per case. It receives:

- `PATCHOULI_EVAL_CASE_ID`
- `PATCHOULI_EVAL_REQUEST`
- `PATCHOULI_EVAL_REQUEST_FILE`
- `PATCHOULI_EVAL_RESPONSE_FILE`
- `PATCHOULI_EVAL_WORKSPACE`

Stdout becomes `response.txt` unless the adapter writes the response file. In
Bubblewrap mode the three path variables name sandbox paths, not host control
paths.

The default timeout is 900 seconds per case. Set `--timeout-seconds` for a run,
`timeout_seconds` at the suite root, or `timeout_seconds` on one case; case-level
wins. Adapter commands start in their own process session. On timeout Patchouli
terminates the process group; Bubblewrap additionally uses `--die-with-parent`
and a PID namespace so descendants cannot continue mutating a case after grade.

## Output replacement

`--force` removes only an empty directory or a directory carrying Patchouli's
dedicated evaluation-run marker. It refuses the repository root, any ancestor of
the repository, and unrelated non-empty directories.

A prepared run stores a frozen suite for deterministic later grading. That file
contains expectations and is intentionally outside the Bubblewrap adapter view;
in manual mode it remains readable and is another reason that mode is open-book.

## What the first suite measures

`smoke.json` checks three cheap acceptance properties:

1. an unsupported `ask` returns `NO_OP` and leaves the wiki unchanged;
2. a supported `ask` recovers two exact facts from one compiled source and
   passes the binding floor;
3. `synthesize` declines when only one work exists.

Add private held-out fixtures for claim recall, paraphrase fidelity, source
conflicts, version refreshes, organization decisions, and maintenance after a
low-cost model is selected.

## Suite expectations

Each case has an `id`, `request`, optional `overlay`, and an `expect` object.
Deterministic expectations are:

- `outcome`: `no_op`, `write`, or `any`;
- `allowed_changes`: path globs; any other changed path fails;
- `required_changes`: globs that must change;
- `exit_code`: adapter exit code, default `0`;
- `check_wiki`: run `scripts/check_wiki.py` in the case workspace;
- `response_contains` / `response_not_contains`;
- `content`: UTF-8 file-glob checks with `contains`, `not_contains`, and optional
  `min_matches`.

The harness writes `results.json` and `summary.md`. Keep model-based or human
judgments outside the blocking grader until a rubric has demonstrated stable
agreement on held-out cases.
