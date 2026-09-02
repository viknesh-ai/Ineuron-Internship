#!/usr/bin/env python3
"""
build_diagram.py — the Code Scanner architecture, with the AI-engineering
concepts layered onto it.

Run:  python3 build_diagram.py
Out:  code-scanner-architecture.excalidraw

Import: excalidraw.com -> menu (top-left) -> Open -> pick the file.

--------------------------------------------------------------------------------
THE CANVAS HAS THREE BANDS
--------------------------------------------------------------------------------
    FAR LEFT   (teal)   the AI-engineering concept, joined by a dashed line to
                        the exact stage where it shows up
    CENTRE              the real architecture — setup tier, fan-out, gates,
                        fan-in, and the terminal CSV
    RIGHT               the side material: legend, the sourceless pipeline, and
                        the two pieces nothing invokes

So the middle is the system, and the left tells you what to call each part of it.

--------------------------------------------------------------------------------
HOW THE FILE IS ORGANISED
--------------------------------------------------------------------------------
    1. GEOMETRY        column positions and box sizes
    2. ConceptColumn   places concept boxes beside the stage they annotate
    3. ARCHITECTURE    the diagram itself
    4. CONCEPTS        one line per concept, anchored to a stage id
    5. WRITE

Plumbing (rectangles, text, bound arrows) lives in excalidraw_kit.py.

The concept column places each box next to its anchor where there's room, and
slides it down when there isn't — so boxes never overlap no matter how many you
add. That's why you give it an anchor id rather than a y coordinate.
"""

from excalidraw_kit import Canvas

# =============================================================================
# 1. GEOMETRY
# =============================================================================

BW, BH = 250, 68        # a standard box in the centre band
LEFT = 80               # centre band origin
COL = 290               # horizontal step between parallel boxes
SIDE = 1260             # right band origin

KX, KW = -620, 470      # concept column: x position and width
K_LINE = 19             # px per line of concept body text
K_PAD = 30              # title line + padding
K_GAP = 12              # vertical gap between concept boxes

c = Canvas()


# =============================================================================
# 2. CONCEPT COLUMN
# =============================================================================

class ConceptColumn:
    """Concept boxes down the far left, each tied to a stage in the centre.

    You pass the id of the box it describes. The column puts it level with that
    box if there's space, or just below the previous concept if there isn't, and
    then draws a dashed line to the anchor so the link is unambiguous even when
    the box has been pushed down.
    """

    def __init__(self, canvas):
        self.c = canvas
        self.cursor = None

    def add(self, anchor_id, title, body, connect=True):
        anchor = self.c.by_id[anchor_id]
        h = K_PAD + len(body.split("\n")) * K_LINE

        want = anchor["y"] + (anchor["height"] - h) / 2
        y = want if self.cursor is None else max(want, self.cursor)

        bid = self.c.box(KX, y, KW, h, f"{title}\n{body}",
                         "concept", size=14, align="left")
        if connect:
            self.c.arrow(bid, anchor_id, kind="concept", dashed=True,
                         start_side="right", end_side="left", width=1)
        self.cursor = y + h + K_GAP
        return bid


# =============================================================================
# 3. ARCHITECTURE  — the centre and right bands
# =============================================================================

c.label(KX, -150, "Code Scanner (Tributary)", size=34)
c.label(KX, -104, "the architecture, with the AI-engineering concepts named on the left",
        size=17, kind="note")
c.label(KX, -74, "one run  =  one CDE, one application", size=15, kind="note")

# ---- inputs -----------------------------------------------------------------
cde  = c.box(LEFT,       60, BW, BH, "CDE Register\n(governed list)", "external")
code = c.box(LEFT + COL, 60, BW, BH, "Application\nCodebase", "external")

# ---- setup tier -------------------------------------------------------------
c.label(LEFT, 175, "SETUP  —  once per application", size=20, kind="setup")

carto = c.box(LEFT,           215, BW, BH, "codebase-\ncartographer", "setup")
smgen = c.box(LEFT + COL,     215, BW, BH, "source-map-\ngenerator", "setup")
prof  = c.box(LEFT + COL * 2, 215, BW, BH, "application-\nprofiler", "setup")

cmap  = c.box(LEFT,           330, BW, BH, "codebase-map.md\nwhere things are", "artifact", size=14)
smap  = c.box(LEFT + COL,     330, BW, BH, "source-map.json\nwhere to grep", "artifact", size=14)
aprof = c.box(LEFT + COL * 2, 330, BW, BH, "app-profile.md\nwhat things mean", "artifact", size=14)

for a in (carto, smgen, prof):
    c.arrow(code, a)
c.arrow(carto, cmap)
c.arrow(smgen, smap)
c.arrow(prof, aprof)
c.arrow(cmap, smgen, dashed=True, start_side="right", end_side="left")

c.label(LEFT + COL * 3 + 20, 340,
        "read by every stage below\n\nno skill generates the\nfirst two — manual bootstrap",
        size=13, kind="note")

# ---- per-CDE pipeline -------------------------------------------------------
c.label(LEFT, 445, "PER CDE  —  /trace-variable", size=20, kind="agent")
c.label(LEFT, 475, "example: 12 source systems", size=14, kind="note")

c.label(LEFT - 62, 520, "STAGE 1", size=15)
t1 = c.box(LEFT,           515, BW, BH, "source-tracer\nsource 1", "agent", size=14)
t2 = c.box(LEFT + COL,     515, BW, BH, "source-tracer\nsource 2", "agent", size=14)
t3 = c.box(LEFT + COL * 2, 515, BW, BH, "source-tracer\nsource 3", "agent", size=14)
c.label(LEFT + COL * 3 + 20, 525, "… × 12\n6 concurrent\nper batch", size=14, kind="note")
for t in (t1, t2, t3):
    c.arrow(smap, t, dashed=True)

tr1 = c.box(LEFT,           625, BW, BH, "trace.md", "artifact", size=14)
tr2 = c.box(LEFT + COL,     625, BW, BH, "trace.md", "artifact", size=14)
tr3 = c.box(LEFT + COL * 2, 625, BW, BH, "trace.md", "artifact", size=14)
c.arrow(t1, tr1); c.arrow(t2, tr2); c.arrow(t3, tr3)

g1 = c.box(LEFT, 725, BW * 3 + 80, 46,
           "GATE 1   validate-lineage.sh   —   sections · rule count · field labels",
           "gate", size=14)
for t in (tr1, tr2, tr3):
    c.arrow(t, g1)

c.label(LEFT - 62, 830, "STAGE 2", size=15)
r1 = c.box(LEFT,           825, BW, BH, "source-reviewer\n⚠ not in repo", "agent", size=14, dashed=True)
r2 = c.box(LEFT + COL,     825, BW, BH, "source-reviewer\n⚠ not in repo", "agent", size=14, dashed=True)
r3 = c.box(LEFT + COL * 2, 825, BW, BH, "source-reviewer\n⚠ not in repo", "agent", size=14, dashed=True)
for r in (r1, r2, r3):
    c.arrow(g1, r)

rv1 = c.box(LEFT,           935, BW, BH, "review.md", "artifact", size=14)
rv2 = c.box(LEFT + COL,     935, BW, BH, "review.md", "artifact", size=14)
rv3 = c.box(LEFT + COL * 2, 935, BW, BH, "review.md", "artifact", size=14)
c.arrow(r1, rv1); c.arrow(r2, rv2); c.arrow(r3, rv3)

g2 = c.box(LEFT, 1035, BW * 3 + 80, 46,
           "GATE 2   —   review present · status parses · rule count vs trace",
           "gate", size=14)
for rv in (rv1, rv2, rv3):
    c.arrow(rv, g2)

c.label(LEFT - 62, 1140, "STAGE 3", size=15)
asm = c.box(LEFT + COL - 40, 1135, BW + 160, BH,
            "business-lineage-tracer\nassemble only — never rephrase", "agent", size=15)
c.arrow(g2, asm)
c.arrow(aprof, asm, dashed=True, start_side="bottom", end_side="right")

glog = c.box(LEFT,            1245, BW, BH, "business-\ntrace-log.md", "artifact", size=14)
gout = c.box(LEFT + COL + 40, 1245, BW + 80, BH,
             "business-lineage-output.md\nTHE GRAPH", "artifact", size=14)
c.arrow(asm, glog); c.arrow(asm, gout)

c.label(SIDE - 195, 1235,
        "nodes:  source · rule · file\n            output · report · domain\n"
        "edges:  PROVIDES · CONDITIONAL\n            DEFAULT · PASSTHROUGH\n"
        "            ENRICHMENT · COMPUTED_FROM\nkey:      org/project/service/\n            qualifier/field",
        size=12, kind="note")

g3 = c.box(LEFT, 1350, BW * 3 + 80, 46,
           "GATE 3   —   metadata · SOURCE blocks · edges · preconditions · outputs",
           "gate", size=14)
c.arrow(gout, g3)

c.label(LEFT - 62, 1455, "STAGE 4", size=15)
rev = c.box(LEFT + COL - 40, 1450, BW + 160, BH,
            "business-lineage-reviewer\nparse graph → extract paths → verify each", "agent", size=15)
c.arrow(g3, rev)

vrev = c.box(LEFT,            1560, BW, BH, "business-\nlineage-review.md", "artifact", size=13)
v2   = c.box(LEFT + COL + 40, 1560, BW + 80, BH,
             "business-lineage-output-v2.md\ncorrected graph", "artifact", size=13)
c.arrow(rev, vrev); c.arrow(rev, v2)

g4 = c.box(LEFT, 1665, BW * 3 + 80, 46,
           "GATE 4   —   paths extracted · v2 present · v2 source count vs v1",
           "gate", size=14)
c.arrow(v2, g4)

c.label(LEFT - 62, 1770, "STAGE 5", size=15)
rep = c.box(LEFT + COL - 40, 1765, BW + 160, BH, "lineage-audit-reporter", "agent", size=15)
c.arrow(g4, rep)
repmd = c.box(LEFT + COL - 40, 1870, BW + 160, BH,
              "report.md\nbusiness language + technical breadcrumbs", "artifact", size=13)
c.arrow(rep, repmd)

g5 = c.box(LEFT, 1975, BW * 3 + 80, 46,
           "GATE 5   —   length > 50 lines · title · key sections", "gate", size=14)
c.arrow(repmd, g5)

c.label(LEFT - 62, 2080, "STAGE 6", size=15)
gen = c.box(LEFT + COL - 40, 2075, BW + 160, BH,
            "code-scanner-generator\nreconciles 4 files", "agent", size=15)
c.arrow(g5, gen)
for src in (vrev, glog, repmd):
    c.arrow(src, gen, dashed=True, start_side="right", end_side="left")

csv = c.box(LEFT + COL - 40, 2185, BW + 160, BH,
            "Code_Scanner_{CDE}.csv\n17 cols · 1 row per source", "artifact", size=14)
c.arrow(gen, csv)

g6 = c.box(LEFT, 2290, BW * 3 + 80, 46,
           "GATE 6   —   headers · data rows · step sequence · 17 columns", "gate", size=14)
c.arrow(csv, g6)

sherpa = c.box(LEFT + COL - 40, 2370, BW + 160, BH, "SHERPA\nenterprise lineage", "external", size=16)
c.arrow(g6, sherpa)

# ---- right band: gate behaviour ---------------------------------------------
c.label(SIDE - 195, 730,
        "GATES DO NOT LOOP\n\npass / warn  → continue\nfail         → STOP,\n                 ask the human\n\nnever an automatic retry",
        size=13, kind="gate")

# ---- right band: sourceless pipeline ----------------------------------------
c.label(SIDE, 445, "ALTERNATIVE  —  /trace-variable-sourceless", size=17, kind="agent")
sless = c.box(SIDE, 490, BW + 60, BH * 2,
              "sourceless-lineage-tracer\n\ndiscovery + extraction\n+ verification + assembly\nall in one agent",
              "agent", size=13)
c.arrow(code, sless, dashed=True, start_side="right", end_side="top")
c.arrow(sless, gout, dashed=True, start_side="bottom", end_side="right")
c.label(SIDE, 640,
        "no setup files needed\nworks on any codebase\n\nonly pipeline that finds\nrule-engine controls\n(resolves numeric field IDs)\n\nrejoins at stage 4",
        size=13, kind="note")

# ---- right band: detached pieces --------------------------------------------
c.label(SIDE, 2075, "NOT WIRED TO ANY SKILL", size=17, kind="note")
step = c.box(SIDE, 2120, BW + 60, BH, "stepwise-code-scanner-\ngenerator", "agent", size=14, dashed=True)
stepcsv = c.box(SIDE, 2225, BW + 60, BH, "StepWiseCodeScanner.csv\nhops as 1.1, 1.2, 1.3 …", "artifact", size=13, dashed=True)
c.arrow(csv, step, dashed=True, start_side="right", end_side="left")
c.arrow(step, stepcsv, dashed=True)
c.label(SIDE, 2320, "re-expands what stage 6\nwas told to collapse", size=13, kind="note")

rcsv = c.box(SIDE, 2400, BW + 60, BH, "/review-csv\nmanual: compare two runs", "agent", size=13, dashed=True)
c.label(SIDE, 2480, "reads csv-exports/ —\nnothing writes there.\nhuman copies by hand.", size=13, kind="note")

# ---- right band: legend -----------------------------------------------------
lx, ly = SIDE, 60
c.label(lx, ly - 30, "LEGEND", size=18)
c.box(lx,       ly,       160, 40, "LLM agent",     "agent",    size=13)
c.box(lx + 175, ly,       160, 40, "setup agent",   "setup",    size=13)
c.box(lx,       ly + 50,  160, 40, "artifact",      "artifact", size=13)
c.box(lx + 175, ly + 50,  160, 40, "gate (bash)",   "gate",     size=13)
c.box(lx,       ly + 100, 160, 40, "external",      "external", size=13)
c.box(lx + 175, ly + 100, 160, 40, "concept",       "concept",  size=13)


# =============================================================================
# 4. CONCEPTS  — anchored to the stage where each one appears
# =============================================================================

k = ConceptColumn(c)

c.box(KX, -30, KW, 78,
      "HARNESS ENGINEERING\nthe whole repo is this: 14 prompt files + 1 shell script.\n"
      "not one good prompt — the scaffold that makes a hundred\nprompt runs produce a checkable artifact.",
      "concept", size=14, align="left")

k.add(smap, "CONTEXT ENGINEERING",
      "what the model sees, and what it must not.\n"
      "source-map narrows grep from the whole repo to one\n"
      "source's file list. app-profile precomputes meaning.\n"
      "the most engineered thing in the system.")

k.add(smap, "RETRIEVAL — lexical, NOT RAG",
      "grep over a precomputed index + alias expansion\n"
      "(BROADRIDGE / BRDG / BR / 4). no embeddings, no vectors.\n"
      "correct: lineage needs the exact line, not similar code.")

k.add(t1, "MULTI-AGENT DECOMPOSITION",
      "split by SCOPE (one tracer per source), by FUNCTION\n"
      "(trace / assemble / review / report), by AUDIENCE.\n"
      "the one-big-agent version is the sourceless pipeline —\n"
      "it exists, and it doesn't scale.")

k.add(t1, "PROMPT ASSEMBLY",
      "each tracer's config is COPIED into its prompt, never\n"
      "referenced by path — sub-agents share no context window.")

k.add(t1, "AGENTIC LOOP  (local)",
      "grep → open method → follow service → SQL → DDL.\n"
      "the model picks each next action from the last result.\n"
      "nothing scripted this path.")

k.add(t1, "TOOL USE",
      "grep · read · glob · bash. the tracer even runs the\n"
      "validator on ITS OWN output and reads the result back.\n"
      "gap: no agent declares a tools: field — no least privilege.")

k.add(t1, "ANALYSIS LOOP",
      "'never stop at intermediate tables — ask where THIS\n"
      "table gets its data.' descend to a physical file or the\n"
      "codebase edge. gap: no depth limit anywhere.")

k.add(t1, "VERIFICATION LOOP — CLOSED",
      "11-item self-check: draft → check → correct → RE-CHECK\n"
      "→ write. the ONLY loop in the system that closes.")

k.add(tr1, "PROVENANCE + ESCAPE HATCHES",
      "every rule carries evidence file + line range.\n"
      "'UNVERIFIABLE' is a legal outcome — the model always has\n"
      "a truthful way to say 'I don't know', so it never invents\n"
      "something just to fill a field.")

k.add(tr1, "STRUCTURED OUTPUT CONTRACT",
      "'do not rename any heading — the assembler parses by\n"
      "exact string match.' enforced at GENERATION time, not\n"
      "parse time: strict producers, not a tolerant parser.")

k.add(g1, "THE DETERMINISTIC SURFACE",
      "this script + batch sizes + file naming + stage order.\n"
      "that is the COMPLETE list. everything else is a model.")

k.add(g1, "VERIFICATION GATE  ≠  LOOP",
      "a gate detects and escalates. a loop corrects and\n"
      "re-checks. no automatic retry, no convergence criterion.\n"
      "the escalation is HUMAN IN THE LOOP (1 of 3).")

k.add(r1, "ADVERSARIAL PAIRING",
      "every producer gets a second opinion from an agent that\n"
      "didn't produce the work. happens twice — here, and again\n"
      "at graph level in stage 4.")

k.add(asm, "DRIFT CONTROL",
      "the tracer is the only agent that read the code. every\n"
      "rewording afterwards is a chance to slide away from it,\n"
      "and errors compound. so semantic judgement stays in one\n"
      "place and the rest is mechanical copying.")

k.add(asm, "FILESYSTEM AS MEMORY",
      "agents share no context, so disk is the only shared state.\n"
      "every artifact must be readable COLD by something that saw\n"
      "none of the work behind it → rigid templates, self-contained\n"
      "prompts. free: checkpoints, audit trail, debugging surface.")

k.add(gout, "GRAPH ENGINEERING",
      "schema + serialisation + integrity rules + traversal.\n"
      "only the DATABASE is missing — that's storage, not modelling.\n"
      "the natural key scheme IS already a graph-DB schema.")

k.add(gout, "…BUT NOT A CODE PROPERTY GRAPH",
      "no AST, no CFG, no parser. CPG nodes are program elements;\n"
      "these are business concepts with code evidence attached.\n"
      "correct name: per-CDE PROVENANCE GRAPH. and skipping program\n"
      "representation is exactly why one trace spans C# + SQL + XML.")

k.add(gout, "GAP — HOPS ARE NOT NODES",
      "staging and lookup tables live as TEXT inside a rule's\n"
      "attributes. so stage 6 collapses the chain to one row and a\n"
      "detached agent re-expands it: one model compresses a path\n"
      "into prose, another rebuilds it from that prose.")

k.add(rev, "GRAPH TRAVERSAL LOOP",
      "adjacency lists → DFS → every source-to-sink path.\n"
      "executed by a MODEL reasoning in prose. it's a 30-line\n"
      "function — the clearest misplaced determinism boundary.")

k.add(rev, "OPEN LOOP",
      "the reviewer corrects into v2 and nothing re-verifies v2.\n"
      "gate 4 checks it structurally, not semantically.\n"
      "generate → verify → correct → STOP.")

k.add(rep, "DECOMPOSITION BY AUDIENCE",
      "a whole agent exists because the READER is different,\n"
      "not because the task is.")

k.add(gen, "CONTEXT EXCLUSION",
      "told NOT to read sub-traces. the stepwise generator is told\n"
      "to PREFER them. same repo, opposite instruction — different\n"
      "jobs need different context.")

k.add(csv, "GAP — EVALUATION IS ABSENT",
      "verification (is THIS right?) is covered. evaluation (is the\n"
      "SYSTEM good?) is not: no test set, no metric, no regression.\n"
      "'confidence' = HIGH if the review passed. a relabelled status.\n"
      "cheapest fix: SELECT DISTINCT on the output column.")

# ---- closing banner ---------------------------------------------------------
c.box(KX, max(k.cursor + 30, 2470), KW + 1620, 86,
      "LOCAL AGENCY, GLOBAL DETERMINISM\n"
      "inside each agent the exploration is free and unscripted   ·   the pipeline shape is hardcoded: six stages, fixed order, no planner\n"
      "for a compliance tool that is the correct trade — the process stays identical across runs, so audit trails stay comparable",
      "concept", size=14)


# =============================================================================
# 5. WRITE
# =============================================================================
if __name__ == "__main__":
    n = c.dump("code-scanner-architecture.excalidraw")
    print(f"wrote code-scanner-architecture.excalidraw  ({n} elements)")
