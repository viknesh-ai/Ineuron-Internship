# Reverse KT — Code Scanner (Tributary)

*Spoken script, around 20–30 minutes. Written the way you would actually say it. The lines in italics inside brackets are notes for you, not to be read out. Pause where it says pause and let them jump in — a reverse KT is a conversation, not a lecture.*

---

## Opening (1 min)

Hi, so this is my reverse KT on the Code Scanner. I went through the whole repo — the skill files, all the agent files including the source-reviewer one which was missing from the zip, and the validate script. I'll walk through it in the order a scan actually runs, and wherever the four concepts come up — context engineering, harness engineering, loop engineering, graph engineering — I'll call them out at that point instead of separately at the end. Please stop me anywhere if my understanding is wrong, that's the whole point of this.

---

## Part 1 — What problem are we solving (3 min)

So first, why does this tool exist at all.

The bank has to produce regulatory reports, and one of the main ones is the KDO report. Every number in that report is built from CDEs — critical data elements — and those CDEs flow through many applications before they reach the report. Regulators and audit ask one question for every CDE: where did this value come from, which systems did it go through, and did anybody change it on the way. That's data lineage.

Now there are two levels of this. The Sherpa team owns the enterprise level. They stitch together the flow *between* applications — this CDE enters app A, goes to app B, then app C, then into the report. You open Sherpa and you can see that chain. But Sherpa only sees the outside of each application. It knows a value went in and a value came out. It has no idea what happened inside.

That inside part is us. Code Scanner takes one application and one CDE, reads the actual source code, and answers — which upstream sources feed this CDE, what business rule is applied for each one, is it passed through as-is or transformed, which lookup tables and input files are involved, and where does it finally land. The output is a CSV in a fixed 17-column format, and Sherpa loads that to fill in the "inside the box" detail.

So the simple way I think of it — Sherpa draws the boxes and the arrows between them. We fill in what happens inside each box.

One thing I want to make sure I have right — a scan is per CDE, not per codebase. We don't run it once and get everything for Liqor. We run it for RateType in Liqor, and we get a folder for RateType. Each CDE in the application's list gets its own run.

*(Pause. "Is that correct so far?")*

---

## Part 2 — What's actually in the repo, and harness engineering (4 min)

When I opened the repo I was expecting code. There's almost none. It's fourteen markdown files and one bash script.

The Skill folder has the orchestrators. `trace-variable` is the main one — it's basically the runbook for a full scan. There's `trace-variable-sourceless` for codebases that haven't been set up yet, and `review-csv` for comparing two outputs.

The Agents folder has the workers. Each file is a full job description for one sub-agent — what inputs it gets, what steps to follow, what template to write, what it must never do. Three setup agents, six pipeline agents, and two extras.

And one script, `validate-lineage.sh`, which runs checks between stages.

All of this runs on Claude Code in headless mode. The UI that was built on top picks the application, clones the repos locally, and then invokes `/trace-variable` with the CDE name. Claude Code reads the skill file and follows it step by step, spawning the agents.

So this is where the first concept comes in — **harness engineering**.

The way I understand it — if you try to do this with one big prompt, "here's the codebase, give me lineage for RateType", it will fail. Not because the model is dumb, but because the task needs it to be exhaustive across twelve sources, keep a strict format, and be auditable. Models are good at the local thing — read this method, tell me the rule. They're bad at the global discipline — did I check all twelve, did I keep the heading format exactly.

Harness engineering is building the structure *around* the model so that the model only ever does the local thing. That's what this repo is. Stages in a fixed order. One agent per stage. Rigid templates. A bash gate between every stage. Failures stop and ask a human. Every agent's prompt is self-contained. The filesystem is the only shared memory.

None of that is prompting. It's engineering the environment. The skill file makes sure every source gets an agent — not the model. The template forces the format — not the model. The bash script checks it — not the model. The model is left with only what it's good at.

Once I saw that, every other design choice in the repo made sense as "make the model's job small, make the structure strict."

*(Pause. Your lead may want to add to this — let them.)*

---

## Part 3 — Setup files and context engineering (4 min)

Before you can trace anything, the application needs three files at its root. These are made once and reused for every CDE.

First, `codebase-map.md`, from the codebase-cartographer agent. It's a minimap — tech stack, folder tree with one-line notes, layers, entry points, data models, naming conventions, and a "if you need X look in Y" table. Nothing lineage-specific. It's there so every later agent can orient itself in seconds instead of wasting its first twenty tool calls wandering around.

Second, `source-map.json`, from the source-map-generator. For every upstream source — BROADRIDGE, ALISE, FIRST and so on — it lists every place in the codebase that mentions that source. Directories, files, code references, stored procedures, queries, DDL, tables read and written, file patterns, DI registrations. And importantly, aliases. BROADRIDGE might appear as `Broadridge`, `BRDG`, `BR`, or as the number 4. If you grep for one spelling you miss half. The generator checks each alias actually exists before writing it. And the schema is generic — no Liqor-specific words in the keys — so the same shape works for MCG or GDPR.

Third, `app-profile.md`, from the application-profiler. This one *is* application-specific. Pipeline types, which calculator is registered for which partition and which partitions have none, enrichment services, the global pre-conditions — things like a banking-book gate that sets a value to null no matter what source — output tables, reports, domain computations, and a business terminology table. Every entry needs a file path and line number.

The skill checks for these at the start. If app-profile is missing it spawns the profiler automatically. The other two are manual for now.

This is **context engineering**.

The model has a limited window, and everything you put in it competes for attention. You cannot put a 700-file codebase in, and even if you could, the relevant methods would drown in noise. Context engineering is deciding what each agent sees, and what it does *not* see.

These three files are exactly that. When a tracer is spawned for BROADRIDGE, it doesn't get "here's the codebase, find RateType". It gets the BROADRIDGE block from the source map — the exact folders, SPs, DI files and aliases — plus the profile telling it which pipeline type BROADRIDGE uses. Its world is narrowed from 700 files to maybe 30 before it reads one line.

And the exclusions matter as much. The tracer is told — do not trace global pre-conditions, do not trace outputs, do not trace other sources. If it wanders into cross-source stuff, the assembler gets overlapping rules it can't reconcile.

You see this everywhere. The CSV generator is told read the four root files, do *not* open sub-traces. The stepwise generator is told the opposite, prefer sub-traces. Same repo, opposite instructions, because each agent needs a different slice.

One more thing I noticed — retrieval is grep, not RAG. No embeddings, no vector DB. The source map gives alias expansion so grep is complete, the codebase map says where to grep first. For code that's actually better, because every hit comes with a file and line number, and that becomes the evidence.

*(Pause.)*

---

## Part 4 — Stage 1 and 2, and loop engineering (6 min)

Okay, now the actual scan. `/trace-variable RateType`. Six stages, each followed by a gate. The rule at the top of the skill is — never silently continue past a failure.

Before stage 1, the skill resolves the codebase root, the short app name for the output folder, and the org/project/service — like `socgen/liqor/liqor-flash` — which becomes the prefix for every node in the graph. It reads the source map to get the source list, around twelve for Liqor, and creates `lineage-traces/Liqor/RateType/sub-traces/` with one folder per source.

**Stage 1** — one source-tracer per source. Launched six at a time — six Agent calls in one message so they run in parallel, wait for all six, then next batch. Each prompt is self-contained, the source's config is copied in, not referenced by path, because sub-agents share nothing with each other.

The tracer works in two passes.

Pass 1 is discovery. Using the source-map paths and aliases, it greps for everything — exact name, case variants, column names, SQL aliases, XML field names. Every hit goes into an inventory with a tag — C1 for calculator, S1 for stored procedure, D1 for DI, Q1 for query, E1 for enrichment, F1 for file import. Then every hit is classified — SETS, READS, PASSES, WIRES or COVERED. The prompt says very clearly, don't stop at the first calculator. The variable might be set in a calculator *and* an SP *and* an enrichment service, and each one is a separate rule.

Pass 2 is extraction. For each hit it reads the *full* method or SQL, not just the grep line. Follows the chain — calculator calls a service, read the service; service calls a repository, read the repository; repository runs SQL, read the SQL. Then it writes the rule as IF/THEN/ELSE, lists every possible output value by walking every branch including null, lists every field the code reads, and classifies it — CONDITIONAL_RULE, DEFAULT_VALUE or PASSTHROUGH.

If there's a lookup table, it must confirm the table exists in DDL, get the join key from the repository, and then — this is the "deep origin" rule — ask how does that lookup table *itself* get filled, and trace that to an INSERT or a file import or say explicitly "external, outside this codebase". If the value comes from a CSV, it must find the column in the workflow XML, the staging table, and any truncation. The quality bar in the prompt is — a reviewer should be able to go from the output column all the way back to the physical file and column.

Before writing each rule there's an eleven-point self-check. Did I read the actual code. Does my rule match branch by branch. All values listed. All dependencies listed. Is the evidence line range precise — never "1 to 705" for a whole file. If any check fails, re-read and fix before writing. And if it genuinely can't verify something, it's allowed to write UNVERIFIABLE instead of guessing.

The output is `trace.md` in a rigid template. The prompt says don't rename any heading, the assembler parses by exact string match.

And then each tracer runs the validate script on its *own* output and reads the result back.

This is where I'd bring in **loop engineering**, because stage 1 has the one real closed loop in the whole system, and gate 1 is the first example of something that looks like a loop but isn't.

The way I understand loop engineering — it's designing how an agent iterates. What triggers another cycle, what closes it, and where iteration is not allowed. There are a few different loops here and they're not the same thing.

The agentic loop is the basic one — call a tool, read the result, pick the next tool. Grep, open file, read method, follow service, open SQL, open DDL. Unscripted. The prompt gives goals, not a sequence.

The analysis loop is "never stop at intermediate tables". Every time you land on a table, ask where does *this* get its data, go one level deeper, until you hit a physical file or an external boundary. Recursion with a stop condition.

The verification loop is the eleven-point self-check. Draft, check against code, correct, re-check, then write. That's a closed loop — it only exits on pass. It's the only place an agent corrects its own work in-cycle.

And then the gates — which are *not* loops. Gate 1 checks trace.md has the four sections, at least one rule, the required labels. PASS, WARN or FAIL. On FAIL the skill does not retry. It asks the user — continue with passing sources, or stop. That's detect and escalate, not correct and retry. And I think that's deliberate — if you auto-retry a semantic task, the model may just fix the output to satisfy the check rather than fix the actual analysis. Escalating keeps a human in control at every boundary.

So the two shapes — closed loops inside an agent for local self-correction, open gates between agents for global control.

*(Pause. This is the part most likely to get questions.)*

**Stage 2** — after gate 1 passes, one source-reviewer per source, again six at a time. This is the file that was missing from the zip.

The reviewer is not the tracer checking itself. It's a fresh agent that didn't do the tracing, told to distrust the trace. For every rule it re-finds the code — using the evidence path from the trace *and* an independent search from the source map — and checks the rule text branch by branch, the possible values, the dependencies, the rule type, the lookup details, the lookup origin, the file origin, the evidence line precision, and whether the inventory refs exist. Each check gets PASS, CORRECTED or FAILED. Then it runs its own discovery search and compares to the tracer's inventory to catch anything missed.

Three rules it follows — report what the code says, not what the analyst expects. Don't invent corrections — if you can't find the code, mark FAILED, don't guess. And distinguish code bugs from trace bugs — if the code itself looks wrong, that's not a trace error, the trace should reflect the code as-is.

The output `review.md` has a Reviewed Rules section with the final version of every rule, in the same template. The assembler reads *that* section, not the original trace.

This pattern is called adversarial pairing. Every producer gets a second opinion from someone who didn't produce it. Happens twice — here per source, and again at stage 4 for the whole graph.

Gate 2 checks the review has its sections, the status parses, and the reviewed rule count isn't lower than the trace rule count.

---

## Part 5 — Stage 3 and graph engineering (4 min)

**Stage 3** — one business-lineage-tracer in assembler mode. Its job is deliberately narrow. It does *not* trace sources. It reads every review.md, falls back to trace.md if a review is missing with a logged warning, and copies the reviewed rules into one document without changing the wording. The prompt literally says — your job is assembly, not re-analysis.

It does two bits of its own tracing because they cross all sources — global pre-conditions from the app profile's list, and output destinations — output tables via DDL, reports via restitution SQL, domain computations via their folders.

Then it writes `business-lineage-output.md`, and this is the graph.

**Graph engineering** — every entity becomes a node with a natural key like `org/project/service/qualifier/variable`. The qualifier tells you the type — `source.ALISE`, `rule.ALISE.cashflow_rate`, `precondition.banking_book_gate`, `output.indicator_trade_bale3`, `report.basylib_r18`, `domain.irrbb_tau`. Six node types. Edges are in a table with a fixed vocabulary — SOURCE_PROVIDES, CONDITIONAL_RULE, DEFAULT_VALUE, PASSTHROUGH, ENRICHMENT, COMPUTED_FROM.

Before writing, the assembler validates the graph — every block has a valid 5-part key, every edge points to keys that exist, no orphan nodes, no self-edges, no duplicates.

So graph engineering is the choice to represent lineage as a typed, keyed graph with integrity rules, instead of free text or a flat table. And you see the payoff immediately downstream. Stage 4 can build adjacency lists and enumerate every source-to-sink path mechanically. Stage 6 can walk edges to find the furthest downstream table. The keys are stable across runs so you can diff two runs. And because keys carry org/project/service, they're ready to merge into an enterprise graph — which is what Sherpa needs.

Two things I want to be precise about. First, this is *not* a code property graph. No AST, no control flow, no parser. Nodes are business concepts — a source, a rule — with code locations as attributes. That's on purpose — an auditor wants "BROADRIDGE → lookup rule → output table", not the call graph.

Second, a gap — intermediate hops are not nodes. The staging table, the lookup table, the enrichment step live as text inside a rule's attributes, not as their own nodes. That's why stage 6 has to collapse each source into one row, and why the stepwise generator exists to re-expand it. If we ever want hop-level queries, promoting those attributes to nodes is the change.

Gate 3 checks metadata, SOURCE blocks, edges, pre-conditions, outputs. FAIL here stops the pipeline completely.

*(Pause.)*

---

## Part 6 — Stages 4, 5, 6 (4 min)

**Stage 4** — business-lineage-reviewer. It takes the assembled file and treats it as a graph. Parses nodes and edges, builds forward and reverse adjacency, finds sources — no incoming edges — and sinks — no outgoing — and extracts every path with DFS. Each path gets an ID and a task.

For each path it re-verifies every node against code — source metadata against source map, rule text and values against the calculator or SP, evidence lines, edge type, lookup details, file origin, output column in DDL, pre-condition WHERE clauses. Logs PASS, FAIL or CORRECTED with the file and line that proves it.

Writes `business-lineage-output-v2.md` — same template, corrections applied — and `business-lineage-review.md` with per-path findings, a corrections table, and open questions for business where code and expectation don't match.

Two things I noticed here. The graph traversal is done by the model reasoning in prose, not a graph library. Works fine at thirty nodes, wouldn't at three thousand. And there's an open loop — the reviewer corrects into v2, and nothing re-verifies v2 semantically. Gate 4 checks it structurally only. So a wrong correction would slip through here. Pragmatic choice, reviewing the review doubles cost, but worth knowing.

**Stage 5** — lineage-audit-reporter. Reads trace log, v1, v2, review, writes `report.md` for a different audience — auditors and risk, not developers. Translates code names to business terms from the profile. Sections for definition, global controls, source-by-source lineage, outputs, review findings with severity, open items, coverage summary. For lookup and file-import sources it adds technical reference blocks with exact table names and join keys so production support has breadcrumbs. Whole agent exists because the reader is different, not the task.

Gate 5 — at least 50 lines, title, at least two key sections.

**Stage 6** — code-scanner-generator. Reads the four root files — v2 as primary truth, review's corrections override v2, trace log, report — plus source map and profile. Told not to open sub-traces. Reconciles all four into a master list so a source mentioned in *any* file gets a row.

The CSV — two header rows, seventeen columns in three groups. INPUT — physical column at entry, business description, source app and ID, source container. OUTPUT — physical column at destination, description, target app and ID, target container. TREATMENT — type, code repository with lines, pseudo-code description, example values, controls, step sequence, confidence.

Exactly one row per source with the whole chain collapsed into it — file import folded in, not a separate row. Then cross-source flows, table-to-report rows, table-to-domain rows. It has to print a self-check confirming every source has exactly one row before writing.

Gate 6 — headers, at least one row, seventeen fields each, critical cells filled, step sequence contiguous.

That CSV is what goes to Sherpa.

---

## Part 7 — The extras, and where I think we go next (3 min)

Quickly on the things outside the main path.

`trace-variable-sourceless` — for a codebase with no source map. One agent does discovery, extraction, verification and assembly together, then feeds stages 4, 5, 6 unchanged because it writes the same template. Less reproducible, but works anywhere, and it's the only path that resolves rule-engine controls by numeric field ID.

`stepwise-code-scanner-generator` — takes an existing CSV and under each row adds sub-rows 1.1, 1.2, 1.3 for every physical hop. Told to prefer sub-traces, opposite of stage 6. Not wired to any skill, run manually.

`review-csv` — compares two CSV versions, matches rows by source plus ID plus target container, checks divergences against code, writes a reconciled one. Reads a `csv-exports` folder that nothing writes to — someone copies by hand.

And putting the four concepts together in one line — inside each agent the exploration is free, the shape of the pipeline is hard-coded. Local agency, global determinism. That combination is what makes a language model into something audit can trust.

On next steps — from what I understand the team wants multi-application scanning, token optimisation, and more deliberate agentic techniques. Two gaps I'd flag from reading the repo. One, there's no evaluation layer — verification checks if *this trace* is right, nothing checks if the *system* is good over time. No test set of known-correct lineages, no regression comparison between runs. Two, the hops-as-attributes thing I mentioned. Both feel like reasonable first things for me to pick up, but I'd want your view.

*(Stop here. "That's my understanding. Where am I wrong, and what did I miss?")*

---

## If they ask — quick answers to keep ready

**"Why batches of six?"** — Concurrency control. Six parallel agents is the balance between speed and not overloading. It's one of the few hard-coded numbers.

**"Why not auto-retry on gate failure?"** — Because a retry on a semantic task risks the model fixing the output to pass the check instead of fixing the analysis. Human escalation keeps control at every boundary.

**"Why copy config into the prompt instead of a path?"** — Sub-agents share no context. If the prompt says "read source-map.json for your config", the agent has to spend tool calls and tokens finding and parsing it, and could read the wrong block. Copying makes each prompt self-contained.

**"Why markdown for the graph and not a database?"** — Zero infrastructure, human-readable, diffable, and the model can parse it. The schema, keys and integrity rules are all there — only the storage is missing. A database is a later step if scale needs it.

**"What's the difference between source-reviewer and business-lineage-reviewer?"** — Source-reviewer checks one source's rules in isolation, before assembly. Business-lineage-reviewer checks the whole graph — paths across sources, edges, pre-conditions, outputs — after assembly. Different scope, same adversarial idea.

**"Why does stage 6 read the report if v2 is the truth?"** — For the business descriptions in the CSV's business-data columns, and as a cross-check that no source or destination was dropped between files.
