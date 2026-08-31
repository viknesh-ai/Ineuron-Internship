# Understanding Code Scanner (Tributary)

Written to be read once, start to finish. Where I'm stating something I read in the
code, I say so plainly. Where I'm guessing, I say I'm guessing. Where I couldn't tell,
I say that too and put it on the questions list at the end.

---

## What problem this solves

A bank has to be able to explain, for each of its critical data fields, where the
value came from and what happened to it along the way. Regulators ask. Auditors ask.
Today someone answers by opening the codebase and reading it for two days, and their
answer is only as good as their patience.

Your team wanted a machine to answer it instead.

The important detail — and you only told me this partway through — is that the scan
runs **once per CDE**, per Critical Data Element. So the tool isn't pointed at an
application and asked "find me all the lineage." It's handed one governed field name
from an approved list and asked "trace this one, in this application, and show me the
code that proves every claim."

That single fact explains a lot of the design, and I'll come back to it.

---

## What's actually in the repository

Fourteen markdown files and one shell script. That's it.

No parser. No AST library. No graph database. No orchestrator process. No Java, no
C#, no Python.

The markdown files are *instructions for Claude*. Four of them are skills — the
top-level workflows you invoke. Ten are agent definitions — specialised roles that get
spawned as sub-agents. The shell script is a 676-line validator that checks whether
files came out looking right between stages.

So when someone says "the tool," they mean a carefully written set of prompts
executed by Claude Code. This surprised me, and it's the first thing to have straight
in your head. If a Code Scanner engineer asks you what the system is and you say
"a static analysis tool," you'll be wrong in a way that's hard to recover from. It is
a prompting architecture. The engineering lives in the contracts between the prompts,
not in any algorithm.

Here's the layout:

```
CodeScanner/
├── Skill/
│   ├── trace-variable-SKILL.md             the main pipeline
│   ├── trace-variable-sourceless-SKILL.md  the portable fallback pipeline
│   ├── review-csv-SKILL.md                 a separate reconciliation tool
│   └── brainstorming-SKILL.md              unrelated (see the odds and ends)
├── Agents/
│   ├── codebase-cartographer.md            } run once per application
│   ├── source-map-generator.md             } to set things up
│   ├── application-profiler.md             }
│   ├── source-tracer.md                    } the per-CDE pipeline
│   ├── business-lineage-tracer.md          }
│   ├── sourceless-lineage-tracer (1).md    }
│   ├── business-lineage-reviewer.md        }
│   ├── lineage-audit-reporter.md           }
│   ├── code-scanner-generator.md           }
│   └── stepwise-code-scanner-generator.md  not wired to anything
└── validate-lineage.sh                     the only real code
```

---

## Why it isn't one big prompt

This is the question you will definitely be asked, so it's worth being able to answer
it properly.

The obvious approach is: point Claude at the repository and say "trace RateType." It
fails for two reasons. The codebase doesn't fit in one context window. And even when
it does fit, a model asked to do everything at once gets sloppy — it invents a table
name, or skips a source, or stops tracing at a staging table because it's already
produced a lot of output and the answer looks complete enough.

So the job got chopped into pieces small enough that each one can be done carefully,
with a check after each piece.

That's the whole design philosophy. Everything else follows from it.

---

## The setup work, done once per application

Before you can trace any field, three things get built for the application. Each is
one agent producing one file.

**The cartographer** walks the codebase and writes `codebase-map.md`. Tech stack,
annotated directory tree, architectural layers, every way data enters and leaves the
system, the key data models, the naming conventions. It's an orientation document —
it exists so that no later agent has to work out from scratch where the calculators
live.

**The source map generator** writes `source-map.json`. For every source system in the
application, it catalogues every file, directory, stored procedure, SQL query, config
entry, and table that mentions that source. Its own description says the point is to
narrow the haystack so downstream agents don't have to search the whole codebase.

One nice detail in there: it verifies aliases. A source called `BROADRIDGE` might also
appear as `Broadridge`, `BRDG`, `BR`, or as the number 4. It greps for each candidate
alias and drops the ones that don't actually hit, because a made-up alias wastes every
downstream agent's time.

**The application profiler** writes `app-profile.md`. This goes deeper than the source
map — it reads actual code and records what the pipeline types are, which calculators
compute which fields, what the global gates and filters are and where the evidence
is, where output data lands, and a glossary translating code jargon into business
terms.

It also produces a table I'd call out separately: **partitions with no calculator
registered**. These are source/partition combinations where dependency injection wires
up nothing, so the field silently defaults to NULL. That's a controls finding, and no
other tool in your stack produces it. If you want one example of "the by-products are
independently valuable," that's the one to use.

These three files get written once and then reused for every CDE you trace afterward.

---

## The main pipeline, per CDE

Say the field you're tracing comes from twelve source systems.

**Stage one — twelve tracers in parallel.** The skill spawns twelve `source-tracer`
agents, six at a time. Each one is responsible for exactly one source. It only looks
at that source's files, listed in the source map. Because its scope is small, it can
afford to be thorough.

Each tracer works in two passes. Pass one is discovery: grep exhaustively for the
field name and every variant of it — case variants, column variants, SQL aliases,
XML field names — and record every hit in a numbered inventory. Pass two is
extraction: for each hit, read the *whole method*, not just the line the grep
matched. Work out what the code actually does. Write it as an IF/THEN/ELSE rule in
plain business language. List every value it can produce, including null. List every
field it depends on. Record the file and the line range that proves it.

Then there's a rule I'd call the strictest thing in the repo. It appears word for word
in four separate files:

> Never stop at intermediate tables. When a rule reads from a reference table or a
> staging table or a lookup table, always ask "where does THIS table get its data?"

And the standard it sets:

> A reviewer should be able to follow the lineage from the output column all the way
> to the specific input file and column where the data physically enters the system.

So if your field is computed from a lookup against `t_ref_fx_rate`, you don't stop at
that table. You find out that a stored procedure loads it from `FXRATE_DAILY_*.csv`,
and you record the CSV and its columns. And when the trail genuinely leaves the
codebase, you have to say so explicitly — "populated by an upstream ETL outside this
codebase" — rather than leaving a blank.

Before writing any rule the agent runs an eleven-item self-check. Did I read the
actual code, not just the grep hit? Does my rule text match the code branch by branch?
Are all the return values listed? Does the lookup table actually exist in the DDL? If
a check fails, re-read and correct. And if a rule can't be verified from code at all,
it doesn't get written — it gets recorded as unverifiable.

Each tracer writes `sub-traces/{SourceName}/trace.md`.

**Stage two — twelve reviewers.** Same batching, one per source, each reading a trace
and checking it against the code. Output is `review.md` alongside each trace.

There's a problem here. **The agent definition for the reviewer isn't in the zip.**
More on that below.

**Stage three — assembly.** One agent reads all twelve traces and reviews and glues
them into a single graph. Its instructions are unusually restrictive: *"Do not
re-interpret or rephrase business rules. Copy them exactly. Your job is assembly, not
re-analysis."*

That restriction is doing real work. Every time a downstream model rewords something,
it's another chance to drift away from what the code says. So the design confines
semantic judgement to the one agent that actually read the code, and everything after
that is mechanical copying.

The assembler does analyse two things itself, and only two: the global pre-conditions
that gate the field across all sources, and the output destinations. Those are
cross-source concerns, so no per-source tracer owns them, and it uses the search terms
and evidence paths from `app-profile.md` to find them.

It writes `business-lineage-output.md` — the graph — and `business-trace-log.md` — the
work log for humans debugging a bad result.

**Stage four — the reviewer.** This one is more interesting than it sounds. It parses
the markdown back into a graph, builds an adjacency list, finds the nodes with no
incoming edges and the nodes with no outgoing edges, and walks every path from source
to sink. Each path gets an ID and gets verified against the code independently.
Verdict per path: passed, corrected, or failed. Every correction has to cite a file
and line.

Two of its rules are worth memorising:

> Don't invent corrections. If you can't find code to verify a rule, mark it
> unverified, not failed.

> Distinguish code bugs from lineage bugs. If the code itself seems wrong, that's not
> a lineage error — the lineage correctly reflects the code.

That second one is the system's statement of purpose. Code Scanner documents what the
code does, not what the business believes it does. When those disagree, it doesn't
quietly split the difference — it records both and escalates it as an open question.

Output: `business-lineage-review.md` and `business-lineage-output-v2.md`.

**Stage five — the report.** A business-language audit document for auditors and risk
officers, 200 to 350 lines. Its nice feature is the "Technical Reference" blocks —
short blockquotes with the lookup table, join key, decision columns, and calculator
file, so production support can investigate a bad value without reading the codebase.

**Stage six — the CSV.** `Code_Scanner_{FieldName}.csv`. Seventeen columns in three
groups: INPUT, OUTPUT, TREATMENT. One row per source system. This is what Sherpa
consumes.

The generator reads four files — the corrected graph, the review, the trace log, and
the report — and reconciles them. Its instruction is that any source mentioned in
*any* of those files must appear in the CSV, with a precedence order when they
disagree: review beats graph beats trace log. But never drop a source just because one
file omitted it.

---

## The whole thing as a picture

```
   CDE register  ──── one scan per CDE ────┐
                                            │
   Application codebase ─────────────────── │ ────────────────┐
                                            │                 │
   ═══ SETUP, once per application ═════════│═════════════════│═══
                                            │                 │
     cartographer  → codebase-map.md        │   "where things are"
     source-map-gen → source-map.json       │   "where to grep"
     app-profiler  → app-profile.md         │   "what things mean"
                                            │                 │
   ═══ PER CDE ═════════════════════════════▼═════════════════▼═══

     Stage 1   12 × source-tracer  (6 at a time, parallel)
                  → sub-traces/{Source}/trace.md
                            ↓  gate
     Stage 2   12 × source-reviewer   ⚠ agent definition missing
                  → sub-traces/{Source}/review.md
                            ↓  gate
     Stage 3   business-lineage-tracer  (assembles, doesn't re-analyse)
                  → business-lineage-output.md  +  business-trace-log.md
                            ↓  gate
     Stage 4   business-lineage-reviewer  (walks every path, verifies)
                  → business-lineage-review.md  +  ...-output-v2.md
                            ↓  gate
     Stage 5   lineage-audit-reporter  → report.md
                            ↓  gate
     Stage 6   code-scanner-generator  → Code_Scanner_{CDE}.csv
                            ↓  gate
                        → Sherpa
```

---

## The trick that makes it work

Those agents can't talk to each other. They don't share a context window. A sub-agent
knows only what its spawning prompt told it.

So **the files on disk are the memory.**

That's why every artifact has a rigid template with exact headings, and why the
instructions say things like *"Do not add, remove, or rename any headings — the
assembler parses these by exact string match."* The next agent finds what it needs by
matching literal strings. If one agent renames a heading, the next one breaks.

It's also why the skill insists that each spawned agent's prompt be self-contained,
with the source's config inlined rather than referenced by path. A sub-agent can't see
what the orchestrator was holding.

This gives you a few things beyond just communication. The artifacts are checkpoints —
if stage four fails, you rerun from the graph file without re-tracing twelve sources.
They're an audit trail — every rule carries a file and line. And they're a debugging
surface — `business-trace-log.md` exists for no other reason than for a human to read
when the output looks wrong.

---

## The graph, and where it stops

The system defines a real graph, not a vague one. Nodes have types: source system,
business rule, source file, output variable, report, domain computation. Edges have
types: provides, conditional rule, default value, passthrough, enrichment, computed
from. Every node has a five-part identifier like
`socgen/liqor/liqor-flash/rule.ALISE.cashflow_rate/RateType`. There's an explicit
Edges table listing every connection. There are integrity rules — no orphan nodes, no
self-edges, no duplicate edges, every edge must point at a node that exists.

It just happens to be serialised as a markdown table rather than stored in a database.
That's a storage choice, not an absence of graph modelling, and it's worth being clear
about that distinction if someone tries to tell you this "isn't really a graph."

But here's the thing to actually notice, and it's the most important observation in
this document.

Take a field that arrives in a CSV, gets staged in `t_payment_stg`, gets FX-converted
against `t_ref_fx_rate`, and lands in `t_payment_reporting`. How many nodes?

Four artifacts, but only some become nodes. The source file, the source system, the
rule, and the output table are nodes. **`t_payment_stg` and `t_ref_fx_rate` are not.**
They live *inside* the rule node, as text in attribute tables called "File Origin" and
"Lookup Table Origin."

So the intermediate physical hops aren't first-class things in the graph. They're
properties of a rule.

That decision cascades. The CSV generator is explicitly told to collapse a source's
entire journey into a single row — every intermediate hop compressed into a prose cell
called "Treatment Description." And then there's a whole separate agent, the step-wise
generator, whose only job is to *un*-collapse it back into numbered sub-steps.

Read that again. One model compresses the path into prose. Later, another model
reconstructs the path from that prose. Nothing shared between them guarantees they
agree.

There are two ways to read this. The charitable one: Sherpa's schema demands one row
per source, so the compression is a requirement, and the step-wise CSV is how you
deliver the detail separately. The critical one: the physical hop chain is never a
first-class object anywhere in the system, so it gets re-derived by inference, and it
can be re-derived differently each time.

Ask them which it is. If it's the second, the fix is architectural — make hops into
nodes — and that would be the single highest-value change to the system.

---

## What's deterministic and what isn't

Worth being precise, because it's the question that separates people who've read the
repo from people who've skimmed it.

Deterministic: the shell script, directory creation, batch sizes, file naming, and the
stage ordering. That's the complete list.

Everything else is a language model. Discovery, reading code, classifying references,
extracting rules, enumerating values, resolving lookups, assembling the graph,
verifying paths, writing the report, generating the CSV.

Including — and this is the one that jumps out — **graph traversal**. The reviewer is
asked, in prose, to build adjacency lists and walk paths depth-first. That's a
textbook algorithm being executed by a language model. It's thirty lines of code in
any language. If you want one concrete, cheap, obviously-correct improvement to
suggest, that's it.

Where the LLM genuinely earns its place is the semantic work. Turning
`codcattau != null && datctttau != null` into "rate security has a floating
indicator." Deciding whether a rule is a transformation or a passthrough. Following a
chain from C# through a repository interface into SQL into a DDL file into a workflow
XML that references a CSV glob — no single-language static analyser spans that. That's
the honest case for this architecture, and it's a good one.

The shell script's role is a smoke test between stages. Does the file exist? Is it
non-empty? Does it have the sections it should? At least one rule? At least one edge?
Catch a failure immediately rather than letting it poison four downstream stages.

---

## Two pipelines, same job

There's a second pipeline, `/trace-variable-sourceless`. One agent does discovery,
tracing, verification, and assembly all by itself in a single pass. Its own
description says it combines the work of the tracer, the reviewer, and the assembler.

It works on any codebase with no setup files at all. But everything is in one context
window, so it doesn't hold up on an application with many sources.

So the two pipelines aren't two features. They're the same logical pipeline
decomposed at two different granularities, and the trade is context budget against
portability. That comparison is the cleanest way to explain why the parallel version
exists at all — the team built both, and the parallel one exists because the simple
one doesn't scale.

One asymmetry worth knowing: the sourceless tracer has a step that no other agent has.
It looks for rule-engine controls — validation rules, override rules, defaulting
rules — and it does something clever to find them. It resolves the field's *numeric
field IDs* from schema config files, then greps rule files for those IDs. That catches
controls that reference fields by number rather than by name, which a name-based grep
would miss entirely.

The downstream agents all know how to handle those control blocks. But the main
pipeline's tracer and assembler have no equivalent step, which means **the main
pipeline can't find rule-engine controls at all**. That's a real capability gap
between the two, and I'd ask about it.

---

## The problems I found

These are the things that will show you actually read the repository rather than
skimmed it.

**The reviewer agent for the main pipeline isn't in the zip.** The skill spawns
`source-reviewer`. The shell script validates its output against five named sections.
The assembler parses its "Reviewed Rules" section. Three files depend on it and
nothing produces it. Either it lives somewhere you weren't sent, or that path is
broken. This is the first question I'd ask.

**Three agents aren't wired to anything.** No skill invokes the cartographer, the
source map generator, or the step-wise generator. The trace skills check whether
`codebase-map.md` and `source-map.json` exist and use them if they do, but neither
skill ever creates them — only the profiler gets spawned automatically when its file
is missing. So the setup step is a manual, undocumented procedure, and the step-wise
CSV, which is arguably the most useful artifact for production support, has no entry
point at all.

**The validator has real bugs.** Four of them:

It checks for the literal string `**Evidence file:**` with a case-sensitive
fixed-string grep. The template writes `**Evidence File:**`, capital F. So the check
can never match a correctly-formed trace, and every source gets a spurious warning
about missing fields.

It counts rules by looking for `#### Rule:` with four hashes. The assembler writes
`### Rule:` with three. The rule count in the gate 3 report is structurally always
zero.

The CSV check splits rows on commas with `awk -F','`. But the generator is told to
quote any field containing a comma, and the Treatment Description column is IF/THEN
pseudo-code that essentially always contains commas. So the column count is almost
never seventeen, and the gate fails on correct output.

And it reads the wrong columns. It looks for Source Application in column 1 (that's
the physical column name), Target container in column 8 (that's Target Application),
Treatment Type in column 17 (that's the confidence score), and the step sequence in
column 1 again (it's actually column 16).

The pattern behind all four is more interesting than the bugs themselves: the
validator and the agent templates were written at different times and have drifted,
and there's no test that runs the validator against a known-good set of artifacts.
That's the underlying gap, and it's a better thing to say out loud than reciting four
defects.

---

## Odds and ends

The confidence score column isn't a confidence model. It's set to HIGH if the review
passed and MEDIUM otherwise. Don't describe it as anything more than a relabelled
review status.

`brainstorming-SKILL.md` has nothing to do with lineage. It's a general
design-before-you-code workflow that mentions `writing-plans`, `frontend-design`, and
a browser-based mockup companion. My guess is it's a development-workflow skill for
the team *building* Code Scanner, not part of the pipeline. Don't put it in your
diagram, but confirm.

The `/review-csv` skill compares two versions of a CSV, verifies every difference
against the code, and produces a merged best-of version with a divergence report. It's
genuinely useful — it's the closest thing to a repeatability check in the system,
since nothing else compares two runs of the same field. But it reads from a folder
called `csv-exports/` that no pipeline stage writes to. Someone copies and renames
files by hand between runs. That's the human-in-the-loop step, and it's undocumented.

The CSV generator is told not to read the sub-traces, while the step-wise generator is
told sub-traces are the richest evidence and it must prefer them. Both make sense
individually — one is managing context budget, the other needs hop-level detail — but
it's worth knowing they diverge.

The file `sourceless-lineage-tracer (1).md` has a download artifact in its name. The
agent name inside the file is correct, but if the runtime resolves agents by filename
this would break.

Nine of the ten agents pin `model: claude-opus-4-7`. The step-wise generator doesn't
pin a model at all.

Six agents set `memory: project`. The parallel source tracer deliberately doesn't,
which makes sense — twelve concurrent agents writing shared memory would race, and
memory would leak one source's findings into another's supposedly isolated context.
Whether the two setup agents' omission is deliberate or an oversight, I can't tell.

The CSV generator's process says "walk through categories 1 to 6," but only four
categories are defined in the file.

---

## Why the per-CDE detail matters so much

Coming back to it, now that the rest is in place.

Once you know a scan is one CDE from a governed register, several things that look
arbitrary become obvious.

There's no variable-discovery agent anywhere in the repo, and that's *correct*, not a
gap. The register decides what's in scope. A tool that went looking for interesting
fields on its own would be overstepping.

The field name is always a required argument, and if no tracer finds any match the
skill asks the user to confirm the name rather than reporting an empty result. That
makes sense for a controlled term — a miss means someone typed the wrong name, not
that the feature is broken.

The CSV has separate columns for the business name and the physical column name at
both the input and output end, and it explicitly forbids putting the business name in
the physical column. One CDE, many physical names across systems. Resolving that
mapping is literally the deliverable.

And the workload becomes a number you can calculate: applications × CDEs per
application. Finite, governed, growing only when the register or the portfolio
changes. That turns the scalability conversation away from "how do we scan everything
faster" and toward "how do we avoid re-scanning a CDE whose code didn't change," which
is a much sharper question.

One concern this raises. If the register uses business names, there's a resolution
step nobody handles. `RateType` happens to be both a CDE name and a greppable code
identifier — that's lucky. "Customer account balance" isn't greppable at all, and
every tracer's discovery pass assumes the name it's given is a code token. Is there an
upstream mapping from CDE to physical names, or is the operator expected to supply the
code-side name by hand?

Related: each CDE's graph is an island. A rule's dependency list routinely names other
fields, and some of those will be CDEs with their own trace folders. Nothing links
them.

---

## What to ask the team

1. Where is the `source-reviewer` agent? The main pipeline can't run without it.
2. How do `codebase-map.md` and `source-map.json` actually get created — manually, a
   wrapper script, a UI?
3. Is the step-wise CSV in production use? It's not wired to any skill.
4. Does Sherpa ingest the CSV, the graph markdown, or both? This decides which one is
   the real contract.
5. Where does the Target Application ID come from? The generator is told to ask the
   user if it's not in the source map.
6. Has the validator ever been run against a known-good set of artifacts?
7. Why can only the sourceless pipeline find rule-engine controls?
8. Does anything read the CDE register programmatically, or is each run launched by
   hand?
9. How does a CDE business name get resolved to a code identifier?
10. How many CDEs per application, and how long does one scan take? That's the
    capacity number the whole scalability discussion needs.
11. What triggers a re-scan — code change, register change, periodic attestation?
12. How does the Excalidraw diagram differ from this? I haven't seen it yet.

---

## Questions to check yourself

Short answers. If you can do these, you understand the system.

1. A field arrives in a CSV, gets staged, gets converted, gets written to a reporting
   table. Which of those four things become nodes in the graph, and which don't? Why
   does the difference matter?

2. Each spawned tracer's prompt must inline the source's full config rather than
   pointing at the source map file. What would break if it pointed instead?

3. The assembler is forbidden from rephrasing rules, but *required* to trace global
   pre-conditions itself. Why is the line drawn exactly there?

4. Why does the CSV column-count check fail on correct output?

5. A business analyst says a field should be NULL. The calculator returns `LIN`. What
   does the system do, and which file does that end up in?

6. Which part of "graph traversal" is done by an algorithm and which by a model?

7. There's no variable-discovery agent. Missing feature, or correct boundary? Defend
   your answer.
