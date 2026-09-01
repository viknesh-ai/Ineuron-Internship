#!/usr/bin/env python3
"""
Generates an Excalidraw diagram of the Code Scanner architecture.

Run:  python3 build_diagram.py
Out:  code-scanner-architecture.excalidraw

Import into Excalidraw:  excalidraw.com  ->  menu (top-left)  ->  Open  ->  pick the file.

--------------------------------------------------------------------------------
HOW THIS FILE IS ORGANISED
--------------------------------------------------------------------------------
  1. PALETTE      colours, one per kind of thing on the canvas
  2. PRIMITIVES   low-level element builders (rect, text, arrow)
  3. CANVAS       a tiny class that collects elements and wires arrow bindings
  4. LAYOUT       the actual diagram: coordinates and content
  5. WRITE        dumps the JSON

To change the diagram you almost always only touch section 5 (LAYOUT).
Everything above it is plumbing you can leave alone.

Coordinate system: x grows right, y grows down. Origin is arbitrary; Excalidraw
recentres on open. I lay the main pipeline out as one tall column on the left and
put the side material in a column on the right.
"""

import json
import random

# =============================================================================
# 1. PALETTE
# =============================================================================
# One colour per *category* of node. Keeping this consistent is what makes a
# diagram readable — the reader learns "purple = an agent" in three seconds and
# then never has to read the legend again.

PALETTE = {
    # LLM agents — the things that reason
    "agent":    {"stroke": "#6741d9", "bg": "#e5dbff"},
    # Setup-tier agents — same nature, different lifecycle, so a different hue
    "setup":    {"stroke": "#1971c2", "bg": "#a5d8ff"},
    # Artifacts — files written to disk
    "artifact": {"stroke": "#2f9e44", "bg": "#b2f2bb"},
    # Gates — the deterministic shell script
    "gate":     {"stroke": "#e03131", "bg": "#ffc9c9"},
    # Things outside the system
    "external": {"stroke": "#343a40", "bg": "#e9ecef"},
    # Annotations / notes
    "note":     {"stroke": "#f08c00", "bg": "#ffec99"},
    # Plain text, no box
    "plain":    {"stroke": "#1e1e1e", "bg": "transparent"},
}

# Hand-drawn look. fontFamily 1 is Excalidraw's handwriting font (Virgil).
# roughness 1 = "artist" (sketchy but legible). 2 = "cartoonist" (very rough).
FONT_HAND = 1
ROUGHNESS = 1
FILL_STYLE = "solid"      # "hachure" is more sketchy; "solid" reads better on a busy diagram


def _nonce():
    return random.randint(1, 2_000_000_000)


def _id(prefix, n):
    return f"{prefix}_{n}"


# =============================================================================
# 2. PRIMITIVES
# =============================================================================

def _base(eid, etype, x, y, w, h, stroke, bg, **kw):
    """Every Excalidraw element shares this skeleton."""
    el = {
        "id": eid,
        "type": etype,
        "x": x, "y": y,
        "width": w, "height": h,
        "angle": 0,
        "strokeColor": stroke,
        "backgroundColor": bg,
        "fillStyle": FILL_STYLE,
        "strokeWidth": 2,
        "strokeStyle": "solid",
        "roughness": ROUGHNESS,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "roundness": {"type": 3} if etype == "rectangle" else None,
        "seed": _nonce(),
        "version": 1,
        "versionNonce": _nonce(),
        "isDeleted": False,
        "boundElements": [],
        "updated": 1,
        "link": None,
        "locked": False,
    }
    el.update(kw)
    return el


def _text_el(eid, x, y, w, h, label, size, colour, container=None, align="center"):
    lines = label.split("\n")
    return _base(
        eid, "text", x, y, w, h, colour, "transparent",
        text=label,
        originalText=label,
        fontSize=size,
        fontFamily=FONT_HAND,
        textAlign=align,
        verticalAlign="middle",
        containerId=container,
        lineHeight=1.25,
        autoResize=True,
        roundness=None,
        # rough estimate; Excalidraw recomputes on open
        baseline=size,
        height=len(lines) * size * 1.25,
    )


# =============================================================================
# 3. CANVAS
# =============================================================================

class Canvas:
    """Collects elements, hands back ids, and wires arrow bindings.

    Binding matters: a bound arrow follows its boxes when you drag them. An
    unbound arrow stays put and the diagram falls apart the first time you tidy
    it up. Worth the extra bookkeeping.
    """

    def __init__(self):
        self.elements = []
        self.counter = 0
        self.by_id = {}

    def _next(self, prefix):
        self.counter += 1
        return _id(prefix, self.counter)

    def _add(self, el):
        self.elements.append(el)
        self.by_id[el["id"]] = el
        return el["id"]

    # -- shapes ------------------------------------------------------------

    def box(self, x, y, w, h, label, kind="agent", size=16, dashed=False):
        """A labelled rectangle. Returns its id."""
        c = PALETTE[kind]
        rid = self._next("box")
        tid = self._next("txt")

        rect = _base(rid, "rectangle", x, y, w, h, c["stroke"], c["bg"])
        if dashed:
            rect["strokeStyle"] = "dashed"
        rect["boundElements"] = [{"id": tid, "type": "text"}]

        lines = label.split("\n")
        th = len(lines) * size * 1.25
        txt = _text_el(tid, x + 8, y + (h - th) / 2, w - 16, th,
                       label, size, c["stroke"], container=rid)

        self._add(rect)
        self._add(txt)
        return rid

    def label(self, x, y, label, size=18, kind="plain", align="left"):
        """Free-floating text with no box — for band headings and asides."""
        c = PALETTE[kind]
        tid = self._next("txt")
        lines = label.split("\n")
        w = max(len(l) for l in lines) * size * 0.55
        h = len(lines) * size * 1.25
        self._add(_text_el(tid, x, y, w, h, label, size, c["stroke"], align=align))
        return tid

    # -- arrows ------------------------------------------------------------

    def arrow(self, src, dst, kind="plain", dashed=False, label=None,
              start_side="bottom", end_side="top"):
        """Bound arrow between two shapes. Sides: top/bottom/left/right."""
        a = self.by_id[src]
        b = self.by_id[dst]
        x1, y1 = self._anchor(a, start_side)
        x2, y2 = self._anchor(b, end_side)

        c = PALETTE[kind]
        aid = self._next("arw")
        arw = _base(aid, "arrow", x1, y1, abs(x2 - x1), abs(y2 - y1),
                    c["stroke"], "transparent",
                    points=[[0, 0], [x2 - x1, y2 - y1]],
                    startBinding={"elementId": src, "focus": 0, "gap": 4},
                    endBinding={"elementId": dst, "focus": 0, "gap": 4},
                    startArrowhead=None,
                    endArrowhead="arrow",
                    roundness={"type": 2},
                    elbowed=False)
        if dashed:
            arw["strokeStyle"] = "dashed"
        arw["strokeWidth"] = 1.5

        a["boundElements"].append({"id": aid, "type": "arrow"})
        b["boundElements"].append({"id": aid, "type": "arrow"})
        self._add(arw)

        if label:
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            self.label(mx + 8, my - 10, label, size=13, kind="plain")
        return aid

    @staticmethod
    def _anchor(el, side):
        x, y, w, h = el["x"], el["y"], el["width"], el["height"]
        return {
            "top":    (x + w / 2, y),
            "bottom": (x + w / 2, y + h),
            "left":   (x, y + h / 2),
            "right":  (x + w, y + h / 2),
        }[side]

    def dump(self, path):
        doc = {
            "type": "excalidraw",
            "version": 2,
            "source": "code-scanner-diagram-generator",
            "elements": self.elements,
            "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
            "files": {},
        }
        with open(path, "w") as f:
            json.dump(doc, f, indent=2)
        return len(self.elements)


# =============================================================================
# 4. LAYOUT CONSTANTS
# =============================================================================

BW, BH = 250, 68          # standard box
LEFT = 80                 # left column origin
COL = 290                 # horizontal step between parallel boxes
SIDE = 1260               # right-hand column origin

c = Canvas()

# =============================================================================
# 5. LAYOUT — the diagram itself
# =============================================================================

# ---- title ------------------------------------------------------------------
c.label(LEFT, -60, "Code Scanner (Tributary) — architecture", size=32)
c.label(LEFT, -18, "one run = one CDE, one application", size=16, kind="note")

# ---- inputs -----------------------------------------------------------------
cde   = c.box(LEFT,        60, BW, BH, "CDE Register\n(governed list)", "external")
code  = c.box(LEFT + COL,  60, BW, BH, "Application\nCodebase", "external")

# ---- SETUP band -------------------------------------------------------------
c.label(LEFT, 175, "SETUP  —  once per application", size=20, kind="setup")

carto = c.box(LEFT,           215, BW, BH, "codebase-\ncartographer", "setup")
smgen = c.box(LEFT + COL,     215, BW, BH, "source-map-\ngenerator", "setup")
prof  = c.box(LEFT + COL * 2, 215, BW, BH, "application-\nprofiler", "setup")

cmap  = c.box(LEFT,           330, BW, BH, "codebase-map.md\nwhere things are", "artifact", size=14)
smap  = c.box(LEFT + COL,     330, BW, BH, "source-map.json\nwhere to grep", "artifact", size=14)
aprof = c.box(LEFT + COL * 2, 330, BW, BH, "app-profile.md\nwhat things mean", "artifact", size=14)

c.arrow(code, carto)
c.arrow(code, smgen)
c.arrow(code, prof)
c.arrow(carto, cmap)
c.arrow(smgen, smap)
c.arrow(prof, aprof)
c.arrow(cmap, smgen, dashed=True, start_side="right", end_side="left")

c.label(LEFT + COL * 3 + 20, 340,
        "read by every\nstage below\n\nno skill generates\nthe first two —\nmanual bootstrap",
        size=13, kind="note")

# ---- PER-CDE band -----------------------------------------------------------
c.label(LEFT, 445, "PER CDE  —  /trace-variable", size=20, kind="agent")
c.label(LEFT, 475, "example: 12 source systems", size=14, kind="note")

# Stage 1 — fan-out
c.label(LEFT - 60, 520, "STAGE 1", size=15, kind="plain")
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
           "GATE 1   validate-lineage.sh   —   sections present · rules counted · fields present",
           "gate", size=14)
for t in (tr1, tr2, tr3):
    c.arrow(t, g1)

# Stage 2 — review fan-out
c.label(LEFT - 60, 830, "STAGE 2", size=15)
r1 = c.box(LEFT,           825, BW, BH, "source-reviewer\n⚠ not in repo", "agent", size=14, dashed=True)
r2 = c.box(LEFT + COL,     825, BW, BH, "source-reviewer\n⚠ not in repo", "agent", size=14, dashed=True)
r3 = c.box(LEFT + COL * 2, 825, BW, BH, "source-reviewer\n⚠ not in repo", "agent", size=14, dashed=True)
c.arrow(g1, r1); c.arrow(g1, r2); c.arrow(g1, r3)

rv1 = c.box(LEFT,           935, BW, BH, "review.md", "artifact", size=14)
rv2 = c.box(LEFT + COL,     935, BW, BH, "review.md", "artifact", size=14)
rv3 = c.box(LEFT + COL * 2, 935, BW, BH, "review.md", "artifact", size=14)
c.arrow(r1, rv1); c.arrow(r2, rv2); c.arrow(r3, rv3)

g2 = c.box(LEFT, 1035, BW * 3 + 80, 46,
           "GATE 2   —   review present · status parses · rule count vs trace (dropped rule?)",
           "gate", size=14)
for rv in (rv1, rv2, rv3):
    c.arrow(rv, g2)

# Stage 3 — fan-in
c.label(LEFT - 60, 1140, "STAGE 3", size=15)
asm = c.box(LEFT + COL - 40, 1135, BW + 160, BH,
            "business-lineage-tracer\nassemble only — never rephrase", "agent", size=15)
c.arrow(g2, asm)
c.arrow(aprof, asm, dashed=True, start_side="bottom", end_side="right")

glog = c.box(LEFT,           1245, BW, BH, "business-\ntrace-log.md", "artifact", size=14)
gout = c.box(LEFT + COL + 40, 1245, BW + 80, BH,
             "business-lineage-output.md\nTHE GRAPH", "artifact", size=14)
c.arrow(asm, glog); c.arrow(asm, gout)

c.label(SIDE - 190, 1240,
        "nodes: source · rule · file\n         output · report · domain\nedges: PROVIDES · CONDITIONAL\n         DEFAULT · PASSTHROUGH\n         ENRICHMENT · COMPUTED_FROM\nkey:   org/project/service/\n         qualifier/field",
        size=12, kind="note")

g3 = c.box(LEFT, 1350, BW * 3 + 80, 46,
           "GATE 3   —   metadata · SOURCE blocks · edge rows · preconditions · outputs",
           "gate", size=14)
c.arrow(gout, g3)

# Stage 4 — graph review
c.label(LEFT - 60, 1455, "STAGE 4", size=15)
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

# Stage 5 — report
c.label(LEFT - 60, 1770, "STAGE 5", size=15)
rep = c.box(LEFT + COL - 40, 1765, BW + 160, BH,
            "lineage-audit-reporter", "agent", size=15)
c.arrow(g4, rep)
repmd = c.box(LEFT + COL - 40, 1870, BW + 160, BH,
              "report.md\nbusiness language + technical breadcrumbs", "artifact", size=13)
c.arrow(rep, repmd)

g5 = c.box(LEFT, 1975, BW * 3 + 80, 46,
           "GATE 5   —   length > 50 lines · title · key sections", "gate", size=14)
c.arrow(repmd, g5)

# Stage 6 — CSV
c.label(LEFT - 60, 2080, "STAGE 6", size=15)
gen = c.box(LEFT + COL - 40, 2075, BW + 160, BH,
            "code-scanner-generator\nreconciles 4 files", "agent", size=15)
c.arrow(g5, gen)
for src in (vrev, glog, repmd):
    c.arrow(src, gen, dashed=True, start_side="right", end_side="left")

csv = c.box(LEFT + COL - 40, 2185, BW + 160, BH,
            "Code_Scanner_{CDE}.csv\n17 cols · 1 row per source", "artifact", size=14)
c.arrow(gen, csv)

g6 = c.box(LEFT, 2290, BW * 3 + 80, 46,
           "GATE 6   —   headers · data rows · step sequence · 17 columns · critical cells",
           "gate", size=14)
c.arrow(csv, g6)

sherpa = c.box(LEFT + COL - 40, 2370, BW + 160, BH, "SHERPA\nenterprise lineage", "external", size=16)
c.arrow(g6, sherpa)

# ---- gate behaviour note ----------------------------------------------------
c.label(SIDE - 190, 730,
        "GATES DO NOT LOOP\n\npass/warn  → continue\nfail       → STOP,\n             ask the human\n\nnever an automatic retry",
        size=13, kind="gate")

# ---- sourceless pipeline (right column) ------------------------------------
c.label(SIDE, 445, "ALTERNATIVE  —  /trace-variable-sourceless", size=17, kind="agent")
sless = c.box(SIDE, 490, BW + 60, BH * 2,
              "sourceless-lineage-tracer\n\ndiscovery + extraction\n+ verification + assembly\nall in one agent", "agent", size=13)
c.arrow(code, sless, dashed=True, start_side="right", end_side="top")
c.arrow(sless, gout, dashed=True, start_side="bottom", end_side="right")
c.label(SIDE, 640,
        "no setup files needed\nworks on any codebase\n\nonly pipeline that finds\nrule-engine controls\n(resolves numeric field IDs)\n\nrejoins at stage 4",
        size=13, kind="note")

# ---- detached pieces --------------------------------------------------------
c.label(SIDE, 2075, "NOT WIRED TO ANY SKILL", size=17, kind="note")
step = c.box(SIDE, 2120, BW + 60, BH,
             "stepwise-code-scanner-\ngenerator", "agent", size=14, dashed=True)
stepcsv = c.box(SIDE, 2225, BW + 60, BH,
                "StepWiseCodeScanner.csv\nhops as 1.1, 1.2, 1.3 …", "artifact", size=13, dashed=True)
c.arrow(csv, step, dashed=True, start_side="right", end_side="left")
c.arrow(step, stepcsv, dashed=True)
c.label(SIDE, 2320,
        "re-expands what stage 6\nwas told to collapse",
        size=13, kind="note")

rcsv = c.box(SIDE, 2400, BW + 60, BH,
             "/review-csv\nmanual: compare two runs", "agent", size=13, dashed=True)
c.label(SIDE, 2480,
        "reads csv-exports/ —\nnothing writes there.\nhuman copies by hand.",
        size=13, kind="note")

# ---- legend -----------------------------------------------------------------
lx, ly = SIDE, 60
c.label(lx, ly - 30, "LEGEND", size=18)
c.box(lx,       ly,      160, 40, "LLM agent",     "agent",    size=13)
c.box(lx + 175, ly,      160, 40, "setup agent",   "setup",    size=13)
c.box(lx,       ly + 50, 160, 40, "artifact",      "artifact", size=13)
c.box(lx + 175, ly + 50, 160, 40, "gate (bash)",   "gate",     size=13)
c.box(lx,       ly + 100, 160, 40, "external",     "external", size=13)
c.box(lx + 175, ly + 100, 160, 40, "dashed = gap", "note",     size=13, dashed=True)
c.label(lx, ly + 155,
        "the only deterministic code\nis the red band —\neverything else is a model",
        size=13, kind="note")

# =============================================================================
# WRITE
# =============================================================================
if __name__ == "__main__":
    n = c.dump("code-scanner-architecture.excalidraw")
    print(f"wrote code-scanner-architecture.excalidraw  ({n} elements)")
