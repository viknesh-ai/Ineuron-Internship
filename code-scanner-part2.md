# Code Scanner, Part 2 — Loops, Graphs, and What Static Analysis Can't See

Three topics you asked about specifically. Same style as before: read it once, start
to finish.

---

# Part A — Loops

You said you didn't just mean `for` and `while`, and you're right not to. In AI
engineering "loop" covers at least six different things, and they behave completely
differently. The useful exercise isn't listing them — it's working out which ones this
system actually has, because the answer turns out to be interesting.

## The six kinds

**A programming loop** repeats a fixed operation a known number of times. Boring,
predictable, deterministic.

**An analysis loop** repeats a search or a read to go deeper. You find a table, you
look up what fills that table, you find another table, you look that up too. The
number of iterations depends on what you find.

**An agentic loop** is where a model decides what to do next based on what it just
saw. Grep returned twelve files — which do I open? This one calls a service — do I
follow it? The control flow isn't written down anywhere; it's produced by the model
at runtime.

**A verification loop** is generate, check, correct, check again. The critical word is
*again*. If you don't re-check after correcting, it isn't a loop — it's a line.

**A graph traversal loop** walks nodes and edges until a stopping condition.

**A human-in-the-loop cycle** is where a person's judgement feeds back into another
machine iteration.

Now, which of these are actually in Code Scanner.

## The programming loops

There are two, and they're both about concurrency control rather than analysis.

The main pipeline splits the source list into **batches of six**, spawns all six in a
single message so they run concurrently, waits for the whole batch, then launches the
next. The CSV reconciliation skill does the same thing with **batches of four**, and
says why: each verification agent reads more code, so fewer at a time.

Worth noticing that this loop is *described in prose and executed by a language
model*. There's no scheduler. The skill file says "split into batches of 6, spawn,
wait, repeat," and Claude follows it. A deterministic loop implemented
non-deterministically. It works, but it's the kind of thing that would be one line of
code in an orchestrator and it's currently a paragraph of instructions.

## The analysis loop — the best one in the system

This is the deep origin tracing rule, and it's the most genuinely loop-shaped thing
here:

> Never stop at intermediate tables. When a rule reads from a reference table or a
> staging table or a lookup table, always ask "where does THIS table get its data?"
> Trace one more level to find the actual input file or external feed.

Follow it through with the FX example. The rule reads `t_ref_fx_rate`. Where does that
come from? A stored procedure loads it. What does the stored procedure read? A CSV
matching `FXRATE_DAILY_*.csv`. Where does *that* come from? Outside the codebase —
stop, and record the boundary explicitly.

That's descend-until-you-hit-a-terminal-condition. Two terminal conditions are
defined: you reach a physical file with named columns, or you reach the edge of the
codebase and mark it. The depth isn't fixed — it's however deep the chain goes.

What's missing is a **depth limit**. Nothing says "stop after five levels." In a
codebase where reference tables load from other reference tables, this could descend
much further than intended, and the only thing stopping it is the model's judgement
about when it has enough. Nobody has bounded it. Worth asking whether they've hit
this.

## The agentic loops — local, not global

Here's a distinction worth having ready, because it's the kind of thing that makes you
sound like you've actually thought about the architecture.

**Inside each tracer, the loop is genuinely agentic.** The agent greps, sees hits,
decides which files matter, opens one, finds a call to a service, decides to follow
it, reads the repository class, finds SQL, reads the DDL to confirm a table exists.
None of that path is written down in advance. The model produces it, step by step,
from what each tool call returns. That's real agency.

**But the pipeline itself is not agentic at all.** The stage order is hardcoded in the
skill file. Trace, then review, then assemble, then review, then report, then CSV. No
agent ever decides to skip a stage, or to re-run one, or to add an extra pass because
the output looked thin. There's no planner.

So: **local agency, global determinism.** The shape of the pipeline is fixed; the
exploration within each box is free.

That's a deliberate and defensible choice for a compliance tool. You want the process
to be the same every time so the audit trail is comparable across runs. You just don't
want to constrain how an agent finds evidence within its box. If someone asks why
there's no planner agent, that's the answer.

## The graph traversal loop

The reviewer does one. It parses the Edges table back into an adjacency list, finds
nodes with no incoming edges and nodes with no outgoing edges, and walks every path
between them depth-first. Each path becomes `PATH-1`, `PATH-2`, and so on, and each
gets verified separately.

I flagged this in Part 1 and it's worth repeating here because it belongs to this
topic: that traversal is done by a language model reading prose instructions. It is a
textbook algorithm. Thirty lines of code. It's the clearest case in the whole system
of work sitting on the wrong side of the deterministic/probabilistic line.

There's a second traversal, less obvious: the deep origin descent above is also a
graph walk, just over a graph that's being discovered as it's walked rather than one
that already exists.

## The verification loops — and this is the important finding

Now the one that matters most, and the answer isn't what you'd expect from a system
that talks about verification this much.

There are three places that look like verification loops. Only one of them actually
closes.

**The self-check inside a tracer does close.** Before writing any rule, the agent runs
an eleven-item checklist — did I read the real code, do all the branches match, are
all return values listed, does the lookup table exist in the DDL. And then: *"If any
check fails, re-read the code and correct the rule before recording it."* Draft,
check, correct, re-check, then write. That's a real closed loop, and it happens inside
a single agent before anything hits disk.

**The reviewer does not close.** It reads the graph, verifies every path against code,
finds errors, corrects them, and writes `business-lineage-output-v2.md`. Then the
pipeline moves on. **Nothing re-verifies v2.** Gate 4 checks that v2 exists, has a
metadata section, has at least one source block, has edges. It does not re-check
whether the corrections were correct. So the shape is generate → verify → correct →
*stop*. A line, not a loop.

**The gates do not close either.** This is the one that surprised me. When a gate
fails, the skill's instruction is to report the failure to the user and **ask what to
do**. It never says "re-run the failed stage and re-validate." The wording is
explicit: *"Do NOT silently skip failures"* — the concern is about not hiding
failures, not about fixing them automatically.

So the gates are checkpoints with a human escalation, not a retry mechanism.

## What that means

Put those together and you get a system that verifies a great deal and iterates
almost not at all.

There is no convergence criterion anywhere in this repository. Nothing says "keep
improving until quality reaches X." Nothing re-runs a stage. Nothing compares output
to a previous run and decides it got worse. The pipeline is a straight line with
inspection points, and when an inspection point fails, a human decides.

Whether that's right depends on what you think the failure mode is. If failures are
mostly *crashes* — an agent died mid-write, a file came out empty — then a human
decision is fine and an automatic retry would just burn tokens. If failures are mostly
*quality* problems — the trace missed a source, the rule is subtly wrong — then no
amount of re-running helps either, and you need a different tracer, not another
attempt.

My guess is the design assumes the first. That's probably correct for structural
gates. But it does mean the phrase "verification loop" oversells what's there. Say
"verification gates" and you'll be more accurate.

## The human loop

There is one, and it's real but undocumented.

The `/review-csv` skill compares two versions of a CSV for the same field, verifies
every difference against the actual code, and produces a merged version that takes the
best of each with a report explaining every decision. It's the only mechanism in the
system that catches non-repeatability — the only thing that answers "we ran this twice
and got different answers, which one is right?"

But it reads from a folder called `csv-exports/` that no pipeline stage ever writes
to. Somebody runs the pipeline, copies the CSV out by hand, renames it with a `v1_`
prefix, runs the pipeline again, copies that one out too, and then invokes the
comparison. That whole procedure exists only in someone's head.

So the loop is: run → export → run again → export → compare → merge. Entirely manual,
entirely undocumented, and it's the closest thing the system has to a quality
measurement.

## Loops that don't exist but you might be asked about

No re-run on gate failure. No iterate-until-good-enough. No loop across CDEs — each
one is a separate manual invocation, there's no driver iterating the register. No
incremental re-scan when code changes. No feedback from a downstream correction back
into the tracer that got it wrong. No loop that improves the prompts based on observed
failures.

If someone asks "where are your evaluation loops," the honest answer is that there
aren't any, and `/review-csv` is a manual stand-in.

---

# Part B — Is this graph engineering?

Yes, and more genuinely than I expected before reading it. But it's a specific kind of
graph, and being precise about which kind is where the interesting conversation is.

## It's an explicit graph, not an accidental one

Some systems have graph-shaped data by accident — you can squint at the file
relationships and call them edges. That's not what's happening here. This system
defines a graph on purpose.

There are **typed nodes**: source system, business rule, source file, output variable,
output report, domain computation. The sourceless pipeline adds a seventh, control,
for rule-engine rules.

There are **typed edges**: provides, conditional rule, default value, passthrough,
enrichment, computed from.

There's a **node identity scheme**:
`{org}/{project}/{service}/{qualifier}/{fieldName}`, where the qualifier carries the
type — `source.ALISE`, `rule.ALISE.cashflow_rate`, `output.indicator_trade_bale3`,
`precondition.banking_book_gate`.

There's an **explicit edge list**, a markdown table with From, To, Edge Type, and
Description.

And there are **integrity constraints**, checked twice — once by the assembler and
again by the reviewer. Every node key must have five segments. Every edge must
reference a node that exists. No orphan nodes. No self-edges. No duplicate edges.
Every source must have an outgoing edge. Every output must have an incoming one.

That's a schema. The fact that it's serialised as markdown instead of stored in Neo4j
is a storage decision, not an absence of graph modelling. If someone tries to tell you
this "isn't really a graph because there's no graph database," that's the answer — the
modelling is done, only the storage and the traversal are still prose.

Which leads to the genuinely useful observation: **the natural key scheme is already a
graph database schema.** They've done the hard part. Migrating to a real store would be
mostly mechanical, because stable typed identifiers already exist and are already
enforced.

## What kind of graph, precisely

You asked about code property graphs specifically, so let's be careful here, because
the terminology invites a wrong answer.

A code property graph merges three views of a *program*: the abstract syntax tree, the
control flow graph, and data dependencies. Its nodes are program elements —
expressions, statements, basic blocks, variables at particular program points. It's
built by a compiler front-end and it describes code structure.

**This is not that, and it isn't trying to be.** There's no AST anywhere in the repo.
No control flow graph. No basic blocks. Nothing parses source code into a syntax tree.

The nodes here are *business concepts*. "Source system ALISE." "The rule that converts
currency." "The reporting table." Those aren't program elements — they're domain
elements that happen to have code evidence attached.

The right name for what this is: a **per-field provenance graph at business
granularity**. Closest formal relative is a data lineage or provenance model, not a
code property graph. If you say "we've built a CPG" in the KT, someone will ask where
the AST is and you'll have nowhere to go.

The honest framing is better anyway: *we skip the program representation entirely and
use a language model to jump straight from source text to business-level provenance,
which is why we can span C#, SQL, XML and config files in one trace where a
conventional analyser would need a front-end per language.*

That's the real claim, and it's a strong one.

## How deep does it actually go

Shallow. Usually three hops.

```
source.CORE_BANKING/txnAmount
      │ SOURCE_PROVIDES
      ▼
rule.CORE_BANKING.fx_convert/txnAmount
      │ CONDITIONAL_RULE
      ▼
output.t_payment_reporting/txnAmount
      │ COMPUTED_FROM
      ▼
report.regulatory_daily/txnAmount
```

Plus a file node in front for file-import sources, plus preconditions hanging off to
the side gating the rules.

And as I said in Part 1 — the staging table and the FX reference table aren't in
there. They're text inside the rule node's attributes.

That's the crux of the graph question. The system models **who transforms the value**
as nodes, and **where the value physically sat along the way** as attributes. So the
graph is a graph of *logical* provenance, not *physical* movement. The physical
movement exists in the artifacts, but only as prose.

That's why the step-wise CSV has to be re-derived by a model rather than queried from
the graph. If hops were nodes, the step-wise output would be a traversal, not an
inference.

## Explicit, implicit, dynamic — where it sits on each

**Explicit?** Yes, for the lineage graph. Nodes and edges are written down with types
and identities.

**Implicit?** Yes, for a second graph nobody has written down. The artifacts form a
dependency DAG — the trace files feed the assembler, the assembler's output feeds the
reviewer, four files feed the CSV generator. That graph is real and it determines
execution order, but it exists only as prose scattered across skill files. Nothing
represents it. That's why the three orphaned agents went unnoticed: there's no
structure that would show you a node with no inbound edge.

**Dynamic?** Yes. The lineage graph doesn't exist until you run a trace. It's
discovered, per CDE, at runtime. There's no persistent graph that accumulates.

Which raises something absent: **no versioning.** Trace the same CDE next month after a
code change and you get a fresh folder. Nothing diffs the two graphs. Nothing tells
you "this rule changed." For a system whose purpose is regulatory attestation, being
able to say what changed between attestations seems like it would matter. Worth
asking.

## What would make it explicit graph engineering

If they wanted to go further, roughly in order of value per unit of effort:

**Write a parser.** Markdown to a real node/edge structure. The templates are already
rigid enough to parse deterministically — that rigidity was designed for exactly this,
it's just currently being consumed by a model doing string matching instead of a
function doing it. This one change moves path extraction, integrity checking, and
orphan detection from probabilistic to deterministic, in a day or two.

**Promote hops to nodes.** Staging tables, lookup tables, and reference tables become
first-class nodes with `table.` qualifiers. This is the significant one. It makes the
step-wise CSV a query instead of an inference, and it deepens the graph from three
hops to however many the data actually takes.

**Persist across CDEs.** Right now each field's graph is an island. Load them into one
store keyed by natural key and the source system nodes, output table nodes, and
precondition nodes automatically merge — because they already have stable identities.
Then you can ask questions nobody can ask today: which fields land in this table,
which fields does this gate affect, what breaks if we retire this source.

**Version it.** Snapshot per run, diff between runs.

Only after all that does graph-based retrieval become interesting — using the
accumulated graph to tell the next trace where to look. That's a real technique, but
it's four steps away and there's no point discussing it before the first one exists.

---

# Part C — Static versus dynamic

## What the system does

Purely static. Nothing runs the application. No instrumentation, no log ingestion, no
runtime capture, no test execution, no database queries against live data. Every claim
comes from reading files.

There's not a single line in the repository that touches a running system. The only
executable thing is a validator that greps output files.

## What static analysis can genuinely know here

Quite a lot, and it's worth being positive about this before getting to the limits.

It knows what code exists and what it says. It knows every branch a calculator can
take, which is why the "Possible Values" field lists *all* outcomes including null —
you get the complete set, not the ones you happened to observe. It knows literal
values and constants. It knows table structure from DDL. It knows what's declared in
config and workflow files. It knows dependency injection registrations, which matters
more than it sounds — I'll come back to that.

And there's one thing static analysis does *better* than runtime observation, which is
worth having ready because it inverts the usual argument.

**Static analysis can prove absence. Dynamic analysis can't.**

The profiler produces a table of partitions with no calculator registered — source and
partition combinations where DI wires up nothing, so the field is always NULL. That's
a proof. You've read the registration code and there's nothing there.

Watch a running system for a month and all you can say is "we never saw a value for
this partition." Maybe the code path exists and just wasn't exercised. You can't
distinguish "never happens" from "hasn't happened yet."

So for the specific question *is this field ever populated for this source*, static
analysis gives a stronger answer than runtime observation would. Keep that one in your
pocket — it's the best counter to "why not just instrument production."

## What it cannot know

**Which branch actually fires.** The trace says "IF currency is EUR then passthrough
else convert." It cannot tell you that in practice 94% of records are EUR. Both
branches are documented as equally real. For lineage that's arguably correct — you
want all paths — but anyone reading it should understand these are possibilities, not
observed behaviour.

**Runtime configuration and feature flags.** The profiler reads config files, but it
cannot know which profile is active in production, which flag is on, or what an
environment variable is set to. A branch that's dead in prod looks identical to a live
one.

**Dynamically constructed SQL.** If a query is built by string concatenation at
runtime, there's nothing to read. The tracers look at SQL files and stored procedures
— static artifacts. Whether this codebase does this at all, I can't tell, and it's
worth asking.

**Reflection and dynamic type resolution.** Same problem, no text to read.

**Message queues across applications.** The cartographer catalogues topics and queues
as entry and exit points, which is good. But it can only see one side. Who publishes
to the topic this application consumes is invisible from inside this codebase. That's
precisely the gap Sherpa exists to close — Code Scanner does intra-application, the
enterprise tool joins them up. Fine boundary, clearly drawn, but know where it is.

**External services.** Hard boundary, and the system handles it honestly rather than
guessing. The instruction to mark the boundary explicitly — "populated by upstream ETL
outside this codebase" — is good practice. An explicit unknown is much more useful than
a blank cell.

**Actual data.** The "Examples" column lists values derived from code, not values
observed in the table.

## Polymorphism, and the clever thing they do about it

Polymorphism is normally where static analysis falls over. Code calls an interface
method. Which implementation runs? Statically, you can't tell in general.

Except this application resolves it through dependency injection, declared in code.
And that's exactly why DI analysis is so prominent throughout the repo — the profiler
has a whole step for mapping which calculator class is registered for which partition,
the tracers classify DI references as `WIRES`, and the reviewer checks the wiring.

It's a smart move. Dependency injection turns a normally-dynamic dispatch decision
into a statically readable table. The system leans on that hard, and it's a genuinely
good answer to "how do you handle polymorphism."

The caveat: it only works when registration is static. If any wiring is conditional at
runtime, or driven by config the analyser can't resolve, the trick fails silently —
you'd read the registration and believe it, with no signal that it might be overridden.

## Where false results come from

**False positives** — lineage reported that doesn't happen in practice. Dead code that
still parses. A calculator registered for a partition that receives no data. A branch
that's unreachable given real inputs.

Partial mitigation exists, but only in one pipeline: the sourceless tracer captures
whether a rule-engine rule is active (`ACTIVE YES/NO`) and its version bounds. The
main pipeline has no equivalent, so it can't tell an active rule from a retired one.

**False negatives** — lineage that happens but isn't reported. Anything constructed at
runtime. Anything the grep missed because the identifier is spelled differently
somewhere. This is why the alias verification in the source map matters so much, and
why the tracers are told to search case variants, column variants, and SQL aliases —
it's all mitigation for the same underlying weakness, that grep only finds what you
think to look for.

The field-ID trick in the sourceless pipeline is the sharpest mitigation in the repo.
Resolve the field's numeric ID from schema config, then grep for that ID in rule
files. Catches controls that reference the field by number, which a name search would
never find. That the main pipeline lacks it is a real gap.

## Would dynamic analysis help

Not as a replacement — for lineage you want all paths, not just exercised ones.

But as *validation*, cheaply and obviously. You have a claim: this field can be FIX,
VAR, or null. You have an output table. Run one query: `SELECT DISTINCT` on that
column. If the code says three values and the table contains a fourth, something is
wrong with the trace, and you've found it in seconds.

That would give the confidence score something real behind it instead of being a
relabelled review status. It's not implemented anywhere and it's the cheapest quality
win I can see in the whole system.

Something similar for row counts by source would catch registered-but-never-used
calculators, which is exactly the false-positive class above.

Neither exists. Neither would be hard.

---

# Check yourself

1. The self-check inside a tracer is a closed loop. The reviewer's correction step
   isn't. What's the actual difference, and why does it matter?

2. Why is it fair to say the pipeline has local agency but global determinism? Give an
   example of each.

3. Somebody says "this isn't real graph engineering, there's no graph database."
   Answer them in three sentences.

4. Why is it wrong to call this a code property graph? What is it instead?

5. Static analysis can prove something that watching production can't. What, and why?

6. Dependency injection makes one normally-hard static problem easy. Which one, and
   when does the trick stop working?

7. The deep origin trace descends until it hits a file or the codebase boundary.
   What's missing from that stopping condition?
