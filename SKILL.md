---
name: pr-review
description: 'Review a GitHub pull request end to end: fetch its metadata and diff, produce a severity-ranked code review in chat, and optionally post the findings back as line-anchored review comments a developer can resolve. Use this whenever someone mentions reviewing a PR, gives a PR number or PR link, asks what is wrong with a change, asks for a second pair of eyes on a branch, or asks to leave review comments on GitHub — for any repository and any programming language.'
user-invocable: true
---

# PR Review

Reviews a pull request from the repository configured in `config.json` and delivers the review in chat. Nothing is written to GitHub unless the user explicitly asks for it.

The skill is language-agnostic — the same folder works for a Go service, a React app or a Terraform module. `config.json` only names the host and the repository; everything else has a sensible default, and a team that wants to tune the defaults can add optional keys described at the end of this file.

## Layout

```
pr-review/
├── SKILL.md            this file
├── config.json         host, repo, exclusions, severity scale, team rules
└── scripts/
    └── pr-review.sh    fetch and post
```

## One-time setup

Fill in the two values in `config.json`:

```json
{
  "github": {
    "host": "sgithub.world.socgen",
    "repo": "OWNER/REPO"
  }
}
```

`repo` is the `OWNER/REPO` path, not a URL — for `https://sgithub.world.socgen/DKL/data-catalog-api` that is `DKL/data-catalog-api`. The script refuses to run while the placeholder is still there. A team on public GitHub changes `host` to `github.com`.

Then confirm the CLI is authenticated with `gh auth status --hostname <host>`, and make sure `jq` is on the PATH.

A repository can keep its own config anywhere and point at it with `--config <file>` or the `PR_REVIEW_CONFIG` environment variable. Command-line flags beat the config, and the config beats the built-in defaults.

## Step 1 — Identify the pull request

Pass whatever the user gave you. `--pr` accepts a bare number, a `#`-prefixed number, or a full pull request URL — a URL carries its own host and repository, so it overrides the config for that run and needs no `--repo`. A repository web link, an HTTPS clone URL or an SSH remote all work as `--repo` too. If no pull request is identifiable, ask for one.

## Step 2 — Fetch

```bash
bash scripts/pr-review.sh fetch --pr <NUMBER>

# or, without touching the config at all:
bash scripts/pr-review.sh fetch --pr https://sgithub.world.socgen/DKL/data-catalog-api/pull/482
```

This prints a single JSON document on stdout: title, author, branches, head SHA, changed files with per-file add/delete counts, labels, CI status, existing reviews, and the unified diff with generated and vendored files already stripped out. If the config defines any optional review settings they arrive under `reviewConfig`; if it does not, that object is empty and the defaults in this file apply.

Read `diff.truncated` before reviewing. If it is `true`, the diff was cut at `diff.maxLines` and the tail of the change is missing — say so in the review rather than implying full coverage, and offer to re-run with `--max-diff-lines 3000`. Note which files appear in `excludedFiles`: they were deliberately skipped, and findings about them are out of scope.

## Step 3 — Review the diff

Read the change as a whole first. The most valuable review comment is usually about the design of the change, not a line of it: is this the simplest thing that solves the problem the author actually has, does it fit the system it is landing in, and will the next person understand it without archaeology. Then go line by line.

Look for these things, in roughly this order of value. **Correctness** — off-by-one errors, inverted conditions, wrong operator precedence, comparisons that will not behave as intended for empty, zero, null or unicode input, and boundaries at the ends of collections and ranges. **Failure paths** — errors that are caught and discarded, failures that leave state half-written, retries without a ceiling, and paths where a partial write is never rolled back or compensated. **Resources and lifecycle** — anything opened, locked, allocated or subscribed that is not released on every path out of the function, including the error path. **Concurrency** — shared mutable state reached from more than one thread, task or request; check-then-act sequences that are not atomic; ordering assumptions that the runtime does not guarantee. **Trust boundaries** — data crossing in from a user, another service or a file needs validation and encoding at the point it is used, whether that is a query, a shell invocation, a template, a path or a deserializer; authorization checks belong on the server side of the boundary and need to cover the new endpoint too. **Secrets and exposure** — credentials in source or config, tokens or personal data in logs and error messages, and stack traces returned to callers. **Contract compatibility** — a renamed field, a narrowed type, a new required parameter or a changed default breaks every consumer that was not updated in this change; persisted schemas and event payloads need a migration path. **Tests** — new behaviour should arrive with tests that would fail without the change, and they should cover the failure case, not only the happy path. **Observability** — new failure modes need a way to be seen in production. **Performance** — work inside a loop that could be done once, queries issued per item instead of in a batch, unbounded collections built from user-controlled input. **Clarity** — names that mislead, dead code, duplicated logic that will drift, magic values, and comments that explain what the code does instead of why it exists.

Four rules always apply regardless of language. A credential, token, private key or connection string written as a literal in source or a checked-in env file is a BLOCKER. Renaming, removing or retyping a field on a published interface, event payload or persisted schema without a migration or version bump is a CRITICAL. Commented-out code introduced by the change is a MAJOR — version control already holds the history. A new TODO or FIXME with no tracked issue behind it is a MINOR.

If the fetch output carries `reviewConfig.teamRules`, apply each rule whose `appliesTo` globs match the file in hand, at the severity that rule declares, in addition to everything above.

Scope discipline matters more than volume. Raise findings only on lines the diff actually changed; do not review unchanged code, the PR description, commit messages, or CI configuration unless the change touches them. Do not restate what an automated formatter or linter already enforces. Cap the review at 25 findings, or at `reviewConfig.maxFindings` when the config sets it, and drop the weakest ones first — a review of forty nits reads as noise and gets ignored. If something is a matter of taste, either say so explicitly or leave it out.

## Step 4 — Deliver the review in chat

Write the review directly in the response. Do not create files or reports.

Open with a header line naming the PR, its author, branches, file count and line counts, plus the state of existing reviews and CI. Follow it with a compact list of changed files and their add/delete counts, marking excluded ones. Then the findings, each in this shape:

> **[SEVERITY] Short title**
> `path/to/file` — line `N`
> What is wrong, why it matters, and the concrete fix.

Order findings by severity, then by file. The scale is 🔴 BLOCKER for security holes, data loss and leaked secrets; 🟠 CRITICAL for logic errors, unhandled failures, leaks, races and broken contracts; 🟡 MAJOR for untested behaviour, duplication and structural problems; 🔵 MINOR for naming, dead code and style, which never blocks a merge on its own. If the config defines `reviewConfig.severityScale`, use its labels instead.

Close with a short paragraph: overall quality, the single biggest concern, and a recommendation of approve, request changes, or discuss. If the diff was truncated or files were excluded, say what was not looked at.

## Step 5 — Offer next actions

After the review, offer to post it as a flat comment on the conversation tab, or as an inline review whose comments are anchored to file and line and can be marked resolved. Also offer to re-run with a larger diff limit if the diff was truncated. Post nothing without an explicit yes.

## Step 6 — Post an inline review

A posted review lands in two places at once. Each entry in the comments array becomes a line-anchored comment on the **Files changed** tab, carrying a *Resolve conversation* button just like a human reviewer's. The `--body` summary becomes the review's header comment on the **Conversation** tab, so the thread shows one review event rather than a scatter of unrelated notes.

Build a JSON array where each finding becomes one object:

```json
[
  {
    "path": "src/limiter.ts",
    "line": 42,
    "side": "RIGHT",
    "body": "🟠 **CRITICAL** — the token bucket is refilled without holding the lock, so two concurrent requests can both pass the capacity check.\n\n**Fix:** move the refill inside the critical section, or use an atomic compare-and-swap on the counter."
  }
]
```

`path` must match the diff exactly. `line` is the line number in the **new** version of the file, not an offset into the diff. Derive it from the hunk header: `@@ -12,7 +15,9 @@` means the first line after the header is line 15 of the new file; count added and context lines forward from there and skip removed lines. Getting this wrong is the usual cause of a rejected post. Use `side: "RIGHT"` for added or context lines and `"LEFT"` only when commenting on a removed line. For a range, add `start_line` and `start_side`.

Only lines that appear in the diff can be commented on. GitHub's batch review endpoint does not accept file-level or PR-level comments, so any finding without a line — a missing file, an architectural concern, a gap across several files — goes into the review summary body instead. The script rejects `subject_type` entries rather than letting the API fail.

Preview first, always, and show the user the payload:

```bash
bash scripts/pr-review.sh post \
  --pr <NUMBER> \
  --comments <path/to/comments.json> \
  --body "<review summary>" \
  --dry-run
```

Then, only after an explicit confirmation, drop `--dry-run` and add `--event`:

```bash
bash scripts/pr-review.sh post \
  --pr <NUMBER> \
  --comments <path/to/comments.json> \
  --body-file <path/to/summary.md> \
  --event COMMENT
```

`--event` is `COMMENT`, `APPROVE` or `REQUEST_CHANGES`, defaulting to `COMMENT` unless the config sets `review.defaultEvent`. Never use `APPROVE` on your own initiative — approving is the user's call, not the reviewer bot's. Post findings of MAJOR and above, or at `reviewConfig.minSeverityToPost` when the config sets it, and fold anything below into the summary body. `--commit-id` defaults to the PR's current head; override it only to review a specific historical commit. On success the script prints the review URL.

## Failures

The script exits `1` on usage errors, `2` when `gh` or `jq` is missing, `3` on authentication problems, `4` when the PR or repository cannot be found, `5` when input is invalid, and `6` on unexpected API errors. Each failure prints a tag first, so match on that:

| Tag | What to do |
|---|---|
| `GH_NOT_FOUND`, `JQ_NOT_FOUND` | Install the missing tool. |
| `GH_AUTH_FAILED`, `GH_AUTH_ERROR` | `gh auth login --hostname <host>`, or the account lacks access to the repo. |
| `REPO_NOT_CONFIGURED`, `INVALID_REPO` | Set `github.repo` in `config.json` or pass `--repo OWNER/REPO`. |
| `PR_NOT_FOUND` | Wrong number, wrong repo, or wrong host. |
| `INVALID_COMMENT_ENTRY` | The listed entries are malformed; fix them and re-run the dry run. |
| `INVALID_PATH` | A comment names a file the PR does not touch. |
| `INVALID_LINE` | The line is not in the diff for that commit. Recompute from the hunk headers on a fresh fetch. |

## Optional configuration

None of this is needed to use the skill. Add a key only when the default is wrong for the repository.

Under `fetch`, `maxDiffLines` changes the truncation budget (default 800, `0` for unlimited), `includeDiff` set to `false` fetches metadata only, and `excludePaths` replaces the built-in exclusion list. That list already covers lockfiles, minified bundles, source maps, snapshots, images, `dist/`, `build/`, `vendor/`, `node_modules/`, `*/generated/` and common protobuf output. Patterns are shell globs matched against both the full path and the bare filename, so `*.pyc` and `infra/*` both behave as expected; an empty array turns exclusion off entirely.

Under `review`, `defaultEvent` sets what `post` submits when `--event` is absent, `maxFindings` caps how many findings a review may carry, `minSeverityToPost` is the floor for a finding to become an inline comment, `severityScale` renames or relabels the four levels, and `teamRules` adds conventions specific to the repository — this is where language-specific or house rules belong, since the skill itself stays language-agnostic.

```json
{
  "github": {
    "host": "sgithub.world.socgen",
    "repo": "DKL/data-catalog-api"
  },
  "fetch": {
    "maxDiffLines": 2000,
    "excludePaths": ["*.lock", "*/generated/*", "docs/*"]
  },
  "review": {
    "maxFindings": 15,
    "minSeverityToPost": "CRITICAL",
    "teamRules": [
      {
        "id": "no-field-injection",
        "appliesTo": ["*.java"],
        "severity": "MAJOR",
        "rule": "Inject dependencies through the constructor so the class stays testable without a container."
      },
      {
        "id": "no-raw-sql-interpolation",
        "appliesTo": ["*.py", "*.go"],
        "severity": "BLOCKER",
        "rule": "Build queries with bound parameters, never string interpolation."
      }
    ]
  }
}
```

## Safety

`fetch` only reads. `post` writes to GitHub and needs explicit user confirmation every time, after a dry run whose payload the user has seen. Never echo tokens, never post an approval the user did not ask for, and never edit source files from this skill.
