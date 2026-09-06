# Code Scanner (Tributary) — How It Works, End to End

This is written to be read from top to bottom in one sitting. It explains what the Code Scanner is, why it exists, what happens when a scan runs, and why it was built the way it was. The four ideas your lead asked you to connect — context engineering, harness engineering, loop engineering and graph engineering — are introduced at the exact point in the flow where they show up, so you see them doing work rather than as abstract definitions. There is a short recap of all four at the end.

---

## 1. The problem this tool solves

Société Générale has to produce regulatory reports. One of the central artifacts is the KDO report, and every number in it is built from many pieces of business data (Critical Data Elements, or CDEs) that flow through many applications before they land in the report. Regulators and internal auditors ask a simple question about each CDE: *where did this value come from, which systems did it pass through, and was it changed along the way?* That question is called data lineage.

There are two levels of lineage, owned by two different teams.

The enterprise-level lineage is owned by the Sherpa team. Sherpa stitches together the flow *between* applications: CDE X enters application A, goes to B, then to C, then into the KDO report. You can open Sherpa and see that chain. But Sherpa only sees the outside of each application — it knows a value went in and a value came out. It does not know what happened inside.

That is where the Code Scanner comes in. Its job is the *intra-application* view. For a single application and a single CDE, it reads the actual source code and answers: which upstream source systems feed this CDE, what business rule is applied in each case, is the value passed through unchanged or transformed, which lookup tables and input files are involved, and which output tables and reports does it finally land in. The result is exported as a CSV in a fixed 17-column layout that the Sherpa team can load into their tool to fill in the "inside the box" detail for each application in the chain.

So the mental model is: Sherpa draws the boxes and the arrows between them. Code Scanner fills in what happens inside each box. Together they give a complete, evidence-backed lineage from the physical input file all the way to the regulatory report.

One more thing to fix in your head before going further: a scan is per CDE, not per codebase. You do not run the scanner and get "all lineage for application X". You run it for `RateType` in Liqor, and you get a folder of results for that one variable. The application has a governed list of CDEs, and each one gets its own run.

---

## 2. What the repository actually contains

If you unzip the repo expecting Java or Python you will be confused, because there is almost no executable code. What you get is fourteen markdown files and one bash script:

The `Skill/` folder holds the orchestrators. `trace-variable-SKILL.md` is the main one — it is the recipe for a full run. `trace-variable-sourceless-SKILL.md` is a lighter alternative for codebases that have not been set up yet. `review-csv-SKILL.md` compares two CSV outputs. `brainstorming-SKILL.md` is a generic design-discussion skill that is not part of the lineage pipeline.

The `Agents/` folder holds the workers. Each file is a full job description for one specialised sub-agent: what inputs it gets, what steps to follow, what template to write, and what rules it must never break. There are three setup agents (codebase-cartographer, source-map-generator, application-profiler), the six pipeline agents (source-tracer, source-reviewer, business-lineage-tracer, business-lineage-reviewer, lineage-audit-reporter, code-scanner-generator), and two extras (sourceless-lineage-tracer, stepwise-code-scanner-generator). The `source-reviewer.md` you were given separately is one of the six pipeline agents and was simply missing from the zip.

The one script, `validate-lineage.sh`, is a set of structural checks that run between stages.

All of this is executed by Claude Code running in headless mode (`claude -p`). The developer on your team built a small local UI on top: you pick an application, all its repos are cloned locally, and then `/trace-variable {CDE}` is invoked. Claude Code reads the skill file and follows it like a runbook, spawning the agents as needed using its Agent tool.

This is the first concept, and it is the frame for everything else.

### Harness engineering — the scaffold is the product

When people first use an LLM for a hard task, they try to write one very good prompt. That works for small tasks and fails for anything that needs to be exhaustive, reproducible and auditable. Reading a 700-file banking codebase and producing a regulator-grade lineage of one variable is that kind of task. No single prompt survives contact with it.

Harness engineering is the practice of building the *structure around* the model so that the model's job at any one moment is small, well-defined and checkable. This repository *is* a harness. Look at what the fourteen files and the script give you:

The work is decomposed into stages with a fixed order. Each stage is a separate agent with a separate prompt. Every agent has a rigid output template. Between stages, a deterministic script checks that the template was respected. Failures stop the pipeline and ask a human. Each agent gets its inputs copied inline into its prompt so it depends on nothing outside its own context window. The filesystem is the only shared state.

None of that is "prompting". It is engineering the environment the model runs in. The key insight is that the LLM is unreliable in a specific way — it is very good at local reasoning (read this method, tell me the business rule) and unreliable at global discipline (did you check all twelve sources, did you keep the heading format exactly). The harness takes the global discipline away from the model and puts it in the scaffold: the skill file enumerates the sources, the batch loop guarantees each gets an agent, the template forces the format, the bash gate verifies it. The model is left with only the part it is good at.

When you read the rest of this document, every design choice can be traced back to this one idea: make the model's job small, make the structure around it strict.

---

## 3. Setup — once per application

Before you can trace a single variable, the application needs three reference files sitting at its codebase root. These are generated once and reused by every CDE run afterwards.

`codebase-map.md` is produced by the **codebase-cartographer** agent. It is a minimap of the codebase: tech stack, annotated directory tree, architectural layers, entry points, data models, naming conventions, and a "if you need X, look in Y" quick reference. Nothing in it is specific to lineage. It exists so that every later agent can orient itself in seconds instead of spending its first twenty tool calls wandering around the folder tree.

`source-map.json` is produced by the **source-map-generator** agent. For every upstream source system (BROADRIDGE, ALISE, FIRST, and so on), it catalogues every place in the codebase where that source is mentioned — directories, files named after it, code references grouped by role (compute, wiring, tests, docs), SQL references (stored procedures, queries, views, DDL), data artifacts (tables read and written, file patterns, workflow configs) and external wiring (DI registrations, schedulers). Crucially it also records *aliases*: BROADRIDGE may appear in code as `Broadridge`, `BRDG`, `BR` or as the numeric ID `4`, and a grep that only knows one spelling misses half the hits. The generator verifies each alias actually occurs before recording it. The schema is deliberately generic — no application-specific pipeline names or business taxonomy — so the same structure works for Liqor, MCG or GDPR.

`app-profile.md` is produced by the **application-profiler** agent and is the one file that *is* application-specific. It goes deeper than the source map: which pipeline types exist (e.g. `BACARDI_POS`, `FILE_IMPORT`), which calculator class is registered for which partition and which partitions have none, which enrichment services exist, which global pre-conditions gate computation (things like a banking-book filter that sets a value to NULL regardless of source), which output tables, reports and domain computations consume the data, and a business-terminology table that maps code identifiers to analyst-friendly names. Every fact in it must carry a file path and line number.

The trace-variable skill checks for these at the start of every run. If `app-profile.md` is missing it spawns the profiler automatically. The other two are a manual bootstrap.

### Context engineering — deciding what the model sees

An LLM has a finite context window, and everything you put in it competes for the model's attention. A 700-file codebase does not fit, and even if it did, dumping it in would drown the relevant methods in noise. Context engineering is the deliberate design of *what goes into each agent's window and what is kept out*.

The three setup files are context engineering in its purest form. Each one is a pre-computed, compressed view of the codebase, built once so that the expensive discovery work is not repeated on every run and every agent. When a source-tracer is spawned for BROADRIDGE, it does not receive "here is the codebase, find RateType". It receives the BROADRIDGE block from source-map.json — the exact directories, stored procedures, DI files and aliases to grep — plus the app profile telling it which pipeline type BROADRIDGE uses and which pre-conditions are *not* its job. Its search space has been narrowed from the whole repository to a curated list of perhaps thirty files before it reads a single line.

The narrowing works in both directions. The source-tracer prompt explicitly says: do not trace global pre-conditions, do not trace output destinations, do not trace other sources. Those exclusions are as important as the inclusions. A tracer that wanders into cross-source territory produces overlapping, contradictory rules that the assembler cannot reconcile.

You will see the same discipline everywhere in the pipeline. The code-scanner-generator is told to read the four root-level files and *not* the sub-traces folder. The stepwise generator, which needs hop-level detail, is told the opposite. Same repository, opposite instructions, because each agent needs a different slice. Context is never "everything available" — it is exactly what this agent needs for this job.

Notice also that retrieval here is lexical, not semantic. There are no embeddings, no vector database, no RAG. The agents grep. The source map gives them alias expansion so the grep is complete, and the codebase map tells them where to grep first. For code, exact-string search over a precomputed index is more reliable than similarity search, and every hit comes with a file and line number that becomes evidence.

---

## 4. The per-CDE pipeline — `/trace-variable RateType`

Now the real work. The skill file describes six stages, each followed by a verification gate. The rule stated at the top of the skill is: *do not silently continue past failures.*

Before Stage 1 the skill resolves context: which codebase root, what short name for the application (used in the output folder path), and the org/project/service triple (e.g. `socgen/liqor/liqor-flash`) that becomes the prefix of every node identifier in the graph. Then it reads `source-map.json` to get the list of sources. For Liqor that is around twelve. It creates the output folder `lineage-traces/Liqor/RateType/` with a `sub-traces/` subfolder containing one directory per source.

### Stage 1 — Sub-trace, one agent per source, six at a time

For each source, a **source-tracer** agent is spawned. The skill launches them in batches of six: six Agent tool calls in a single message so they run concurrently, wait for all six to finish, then launch the next batch. Each agent's prompt is self-contained — the source's config is copied into the prompt, not referenced by path, because sub-agents share no context with each other or with the orchestrator.

The tracer works in two passes.

Pass 1 is discovery. Using the source-map paths and aliases, it greps exhaustively for the variable — exact name, case variants, column variants, SQL aliases, XML field names. Every hit is recorded in a reference inventory with a label like `[C1]` for calculators, `[S1]` for stored procedures, `[D1]` for DI registrations, `[Q1]` for queries, `[E1]` for enrichment, `[F1]` for file imports. Then every hit is classified: SETS (code assigns or computes the value), READS (code uses it as a filter or routing key), PASSES (copies without change), WIRES (DI config that connects things but does not compute), or COVERED (already represented by another rule). The instruction is blunt: do not stop at the first calculator. The variable may be set in a calculator *and* a stored procedure *and* an enrichment service, and each is a separate reference.

Pass 2 is extraction. For each SETS, READS or PASSES reference, the tracer reads the *full method or SQL statement*, not just the grep line. It follows the chain: if the calculator calls a service, read the service; if the service calls a repository, read the repository; if the repository runs SQL, read the SQL. It then writes a business rule in IF/THEN/ELSE form, enumerates every possible output value by walking every branch to its terminal (including null and exception paths), lists every dependency the code reads, and classifies the rule as CONDITIONAL_RULE, DEFAULT_VALUE or PASSTHROUGH. If a lookup table is involved it must confirm the table exists in DDL, find the join key from the repository code, and then — this is the "deep origin" requirement — ask *how does that lookup table itself get populated*, and trace that to an INSERT, a file import workflow or an explicit "external, outside this codebase" boundary. If the value comes from a CSV or XML, it must find the column name or index in the workflow XML, the staging table and column, and any truncation or casting on the way. The quality bar stated in the prompt: a reviewer should be able to follow the lineage from the output column all the way to the physical input file and column.

Before writing each rule, the tracer must run an eleven-item self-verification checklist: did I read the actual code, does my rule match branch by branch, are all return values listed, is every dependency in depends_on, is the evidence line range precise (never "1-705" for a whole file), does the lookup table exist, did I trace its origin, is the rule type right. If any check fails, re-read and correct before writing. If a rule cannot be verified from code, the legal outcome is to write `UNVERIFIABLE` rather than guess.

The output is `sub-traces/{Source}/trace.md` in a rigid template — source metadata, calculator search results, discovery inventory counts, then one `### Rule:` block per rule with fixed field labels. The template warning is explicit: do not rename any heading, the assembler parses by exact string match.

After writing, each tracer runs `bash validate-lineage.sh {folder} gate1 {Source}` on its own output and reads the result back into its response.

### Loop engineering — where the system loops, and where it deliberately does not

This is a good place to introduce the third concept, because Stage 1 contains the one true closed loop in the whole system, and Gate 1 is the first example of a thing that looks like a loop but is not.

"Loop engineering" is the design of *how an agent iterates* — what triggers another cycle, what closes it, and where iteration is forbidden. In agentic systems there are several distinct loops, and confusing them leads to systems that either spin forever or never correct themselves.

The **agentic loop** is the basic one: the model calls a tool, reads the result, decides the next tool call. Inside a source-tracer this is grep → open the file → read the method → follow the service call → open the SQL → open the DDL. Each next action is chosen from the last result. This loop is unscripted; the prompt gives goals and rules, not a sequence of commands.

The **analysis loop** is the "never stop at intermediate tables" instruction. Every time the tracer lands on a table, it must ask "where does *this* get its data?" and descend one more level, until it reaches a physical file or an external boundary. It is a recursion with an explicit termination condition.

The **verification loop** is the eleven-item self-check: draft the rule, check it against the code, correct, re-check, and only then write. This is a closed loop — the output of the check feeds back into the thing being checked, and the loop only exits on pass. It is the only place in the system where an agent corrects its own work in-cycle.

Then there are the **gates**, which are *not* loops. Gate 1 runs a bash script that checks trace.md has the four required sections, at least one `### Rule:` block, and the mandatory field labels. It reports PASS, WARN or FAIL. On FAIL the skill does not retry the tracer. It reports to the user and asks: continue with the passing sources, or stop and investigate. That is a detect-and-escalate mechanism, not a correct-and-retry one. The distinction is deliberate. An automatic retry on a semantic task risks the model "fixing" the output to satisfy the check rather than fixing the underlying analysis; escalating to a human keeps the human in control at every stage boundary.

Keep these two shapes in mind for the rest of the pipeline: closed loops for local self-correction inside an agent, open gates for global control between agents.

### Gate 1 and Stage 2 — Sub-review, again one agent per source

Once all batches finish, the skill runs Gate 1 across the whole folder and shows the report. Sources with PASS or WARN proceed. Then a **source-reviewer** agent is spawned per source (again in batches of six), and this is the file you were given separately.

The reviewer is not the tracer re-reading its own work. It is a fresh agent that did not do the tracing, given the trace.md, the source map and the codebase, and told to distrust the trace. For every rule it must re-find the code — using the evidence path from the trace *and* an independent search from the source map — and check the business rule text branch by branch, the possible values against every return path, the depends_on list against what the code actually reads, the rule type, the lookup details (table exists, key correct, columns read correct, resolution logic correct), the lookup table origin, the file origin, the evidence line precision, and whether the rule's inventory refs actually exist. Each check gets a verdict: PASS, CORRECTED or FAILED. Then it runs its own discovery search and compares to the tracer's inventory to find anything missed; a missed reference that represents an uncaptured rule marks the review CORRECTED and the rule gets added.

Three objectivity rules govern it. Report what the code says, not what the analyst expects. Don't invent corrections — if you cannot find code, mark FAILED, don't guess. And distinguish code bugs from trace bugs: if the code itself seems wrong, that is not a trace error; the trace must reflect the code as-is.

The output `review.md` has a `## Reviewed Rules` section containing the *final* version of every rule — corrected ones with corrections applied, passed ones copied verbatim — in exactly the trace.md template. This matters: the assembler downstream reads the Reviewed Rules section, not the original trace.

The pattern here is adversarial pairing. Every producer gets a second opinion from an agent that did not produce the work. It happens twice in the pipeline (here per source, and again at Stage 4 for the whole graph).

Gate 2 checks review.md has its required sections, the Overall Status parses to PASS/CORRECTED/FAILED, and the reviewed rule count is not lower than the trace rule count (a dropped rule is a WARN).

### Stage 3 — Assemble

Now a single **business-lineage-tracer** agent runs in assembler mode. Its job description is deliberately narrow: it does *not* trace sources. It reads every `review.md` (falling back to `trace.md` where a review is missing, with a logged warning), and copies the reviewed rules into one document without rephrasing them. The prompt says it directly: "Do not re-interpret or rephrase business rules. Copy them exactly. Your job is assembly, not re-analysis."

It does do two pieces of its own tracing, because they cross all sources and no per-source agent could own them: global pre-conditions (from the app profile's list, with search terms to grep for and evidence to confirm) and output destinations (output tables via DDL, reports via restitution SQL, domain computations via their directories).

Then it assembles `business-lineage-output.md`. This document is the graph.

### Graph engineering — the lineage as nodes and edges

Every entity in the lineage becomes a node with a natural key of the form `{org}/{project}/{service}/{qualifier}/{variable}`. The qualifier encodes the node type: `source.ALISE`, `rule.ALISE.cashflow_rate`, `precondition.banking_book_gate`, `file.CPM.ACP-ADV_Cashflow`, `output.indicator_trade_bale3`, `report.basylib_r18`, `domain.irrbb_tau`. The node types are SOURCE_SYSTEM, BUSINESS_RULE, SOURCE_FILE, BUSINESS_VARIABLE, OUTPUT_REPORT and DOMAIN_COMPUTATION.

Edges are listed in a table with a type from a fixed set: SOURCE_PROVIDES (source → rule, or file → source), CONDITIONAL_RULE / DEFAULT_VALUE / PASSTHROUGH (rule → output), ENRICHMENT, and COMPUTED_FROM (output → aggregate, report or domain).

The assembler must validate the graph before writing: every block has a valid 5-segment key, every edge references keys that exist as blocks, no orphan blocks, no self-edges, no duplicate edges, required text non-empty.

Graph engineering is the choice to represent lineage this way — as a typed, keyed, integrity-checked graph serialised in markdown — rather than as free prose or a flat table. The benefits show up immediately downstream. The reviewer in Stage 4 can build adjacency lists and enumerate every source-to-sink path mechanically. The CSV generator can walk edges to find "the furthest downstream table this source reaches". The natural keys are stable across runs, so two runs of the same CDE can be diffed. And because the keys carry org/project/service, the nodes are ready to be merged into an enterprise graph — which is the shape Sherpa needs.

It is worth being precise about what kind of graph this is *not*. It is not a code property graph. There is no AST, no control-flow graph, no parser. The nodes are business concepts (a source system, a business rule) with code locations attached as attributes, not program elements. That is a deliberate abstraction level: an auditor wants "BROADRIDGE → rate security lookup rule → output table", not the call graph.

And one gap worth knowing: intermediate hops are not nodes. The staging table, the lookup table and the enrichment step live as *text inside a rule's attributes* (Lookup Details, File Origin, Input Field Origins), not as their own nodes with their own edges. This is why Stage 6 has to collapse each source's chain into one CSV row, and why the separate stepwise generator exists to re-expand it. If the team ever wants hop-level graph queries, promoting those attributes to nodes is the change.

Gate 3 checks the assembled file has the metadata block with Lineage Type BUSINESS, SOURCE blocks, an Edges table with numbered rows, a Pre-conditions section and an Output Destinations section. A FAIL here stops the pipeline outright.

### Stage 4 — Final review of the whole graph

A single **business-lineage-reviewer** agent takes `business-lineage-output.md` and treats it as a graph. It parses nodes and edges, builds forward and reverse adjacency lists, identifies sources (no incoming edges) and sinks (no outgoing edges), and extracts every path from every source to every reachable sink using DFS. Each path gets an ID — PATH-1, PATH-2 — and a task.

For each path it re-verifies every node against the codebase: source metadata against the source map, business rule text and possible values against the calculator or SP, evidence file and lines, edge type correctness, lookup details, file origin, output column existence in the DDL, and pre-condition WHERE clauses. Every finding is logged with PASS / FAIL / CORRECTED and the file and line that proves it.

It then writes `business-lineage-output-v2.md` — the same rigid template with corrections applied — and `business-lineage-review.md` with per-path findings, a corrections table, statistics, and an "Open Questions for Business" list for discrepancies between what the code does and what the business expected.

This is the graph-traversal loop, and it is worth noticing that it is executed by a language model reasoning in prose, not by a graph library. That is a design decision with a tradeoff: it works on a markdown file with zero infrastructure, but a graph of thirty nodes and thirty edges is small enough for the model to hold; a much larger one would need real tooling.

There is also an open loop here worth naming. The reviewer corrects into v2, and nothing re-verifies v2 semantically. Gate 4 checks v2 structurally (metadata present, source count not lower than v1, edges present, output blocks present) but does not re-read code. The system trusts the reviewer's corrections at this point. That is the pragmatic choice — reviewing the review would double the cost — but it is where a wrong correction would slip through.

### Stage 5 — Audit report

The **lineage-audit-reporter** reads the trace log, v1, v2 and the review, and writes `report.md` for a different audience: auditors, risk officers and compliance analysts, not developers. It translates code identifiers to business terminology from the app profile. Sections cover definition and purpose of the variable, global controls, source-by-source lineage split into conditional rules / fixed values / file pass-throughs, output destinations, review findings with severity, open items with risk level, and a coverage summary with a conclusion.

For sources that use lookups or file imports it adds "Technical Reference" blocks with exact table names, join keys and file patterns, so production support has breadcrumbs without reading the full codebase. That is a decomposition by *audience*: a whole agent exists because the reader is different, not because the underlying task is.

Gate 5 checks the report is at least 50 lines, has a title with the variable name, and has at least two of the expected sections.

### Stage 6 — Code Scanner CSV

The **code-scanner-generator** reads the four root-level files — v2 (primary source of truth), the review (corrected rules override v2), the trace log, and the report — plus the source map and app profile. It is told not to look in sub-traces. It reconciles all four into a master list of sources, outputs, rules and paths, so that a source mentioned in any file appears in the CSV.

The CSV has two header rows and seventeen columns in three groups. INPUT: physical column at point of entry, business data description, source application and ID, source container (file pattern or first table). OUTPUT: physical column at final destination, business data, target application and ID, target container (the furthest downstream table). TREATMENT: treatment type (Transformation / Passthrough / Default Value / Derived / Control), code repository with line numbers, treatment description as IF/THEN/ELSE pseudo-code, example values, controls, step sequence, confidence score.

Rows come in categories: exactly one row per source system with the *entire* chain collapsed into it (file import folded in, not a separate row), then cross-source internal flows, table-to-report rows, and table-to-domain rows. The generator must print a self-check confirming every source has exactly one row before writing.

Gate 6 checks the header rows, that there is at least one data row, that each row has seventeen fields, that the critical cells are non-empty, and that step sequence is contiguous.

That CSV is the deliverable that goes to the Sherpa team.

---

## 5. The things outside the main pipeline

`/trace-variable-sourceless` is the alternative path for a codebase that has no source-map.json. It uses the **sourceless-lineage-tracer**, which combines discovery, extraction, verification and assembly in one agent, then feeds the result into Stages 4, 5 and 6 unchanged because it writes the same rigid template. It is less reproducible (no parallel per-source decomposition, no per-source review) but works anywhere, and it is the only pipeline that resolves rule-engine controls by numeric field ID.

The **stepwise-code-scanner-generator** takes an existing Code_Scanner CSV and, under each main row, inserts sub-rows 1.1, 1.2, 1.3 for every physical hop — file import, lookup, enrichment, SP propagation, entity initialisation, computation, persistence, restitution. It is told to *prefer* the sub-traces, the opposite of Stage 6. It is not wired to any skill; someone invokes it manually.

`/review-csv` compares two versions of a CSV for the same variable, matches rows by source + ID + target container, verifies each divergence against the codebase, and writes a reconciled version. It reads a `csv-exports/` folder that nothing in the pipeline writes to — a human copies files there by hand.

---

## 6. Why it is designed this way — the four concepts in one place

**Harness engineering.** The repository is a scaffold, not a prompt. Stages in fixed order, one agent per stage, rigid templates, deterministic gates, human escalation on failure, self-contained prompts, filesystem as the only shared memory. The model is only ever asked to do the local thing it is good at; the global discipline lives in the structure. The deterministic surface is small and explicit: the script, the batch size, the file names, the stage order. Everything else is the model reasoning.

**Context engineering.** Three precomputed setup files narrow each agent's world from a whole codebase to a curated list. Every agent is told what to read *and* what not to read. Sub-agents get their config copied inline. Retrieval is lexical with alias expansion, so every fact has a file and line. The result is that a tracer's context window holds the thirty relevant files, not the seven hundred irrelevant ones.

**Loop engineering.** Inside an agent: an unscripted agentic loop for tool use, a recursive analysis loop that descends until it hits a physical file, and a closed verification loop that drafts, checks, corrects and re-checks before writing. Between agents: gates that detect and escalate but never auto-retry. Adversarial pairing at two levels (per source, then whole graph) so every producer gets a reviewer that did not produce the work. One known open loop — v2 is not re-verified semantically.

**Graph engineering.** Lineage is a typed graph with stable natural keys, a fixed edge vocabulary, and integrity rules enforced at assembly and re-checked at review. This is what makes path enumeration, CSV generation and cross-run diffing mechanical, and what makes the output mergeable into Sherpa's enterprise graph. It is a business-concept graph, not a code property graph, and its known limitation is that intermediate hops are attributes rather than nodes.

The through-line connecting all four: local agency, global determinism. Inside each agent the exploration is free. The shape of the pipeline — what runs, in what order, what it must produce, what is checked — is hard-coded. That combination is what turns a language model into something a regulator can trust.

---

## 7. Where the team wants to go next

From what you've said, the open items are: scanning multiple applications in one run rather than one at a time (which the natural key format already anticipates), token optimisation (the profile and source map are the main levers — a tighter source map means a smaller tracer context; batch size and the "read the whole method" rule are the main cost drivers), and applying agentic techniques more deliberately. Two concrete gaps from the analysis above are worth raising: there is no evaluation layer (verification checks whether *this trace* is right; nothing checks whether the *system* is good over time — no test set of known-correct lineages, no regression comparison between runs), and intermediate hops are not graph nodes. Both are natural first contributions for someone joining the team.
