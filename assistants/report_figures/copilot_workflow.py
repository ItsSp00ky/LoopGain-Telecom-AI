"""Figure 9 of the final report: one copilot turn, and how a work order is confirmed.

Drawn in the style of the chatbot's Figure 7.

Run: uv run --no-project --python 3.12 --with matplotlib python copilot_workflow.py
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

BLUE_FILL, BLUE_EDGE = "#EEF4FC", "#4A86C8"
GREEN_FILL, GREEN_EDGE = "#E8F6EE", "#3DA26A"
ORANGE_FILL, ORANGE_EDGE = "#FDF1EA", "#E07A45"
TITLE = "#2A78D6"
TEXT = "#1F2A37"
ARROW = "#555E68"
S = 7.8

fig, ax = plt.subplots(figsize=(12, 6.3), dpi=220)
ax.set_xlim(0, 120)
ax.set_ylim(0, 61)
ax.axis("off")


def box(x, y, w, h, lines, fill=BLUE_FILL, edge=BLUE_EDGE, size=S):
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.35,rounding_size=1.2",
            linewidth=1.1,
            edgecolor=edge,
            facecolor=fill,
        )
    )
    ax.text(
        x + w / 2,
        y + h / 2,
        "\n".join(lines),
        ha="center",
        va="center",
        fontsize=size,
        color=TEXT,
        linespacing=1.25,
    )
    return (x, y, w, h)


def arrow(start, end, label=None, color=ARROW, style="-|>", ls="-", label_offset=(0, 0)):
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle=style,
            mutation_scale=11,
            linewidth=1.1,
            color=color,
            linestyle=ls,
        )
    )
    if label:
        mx = (start[0] + end[0]) / 2 + label_offset[0]
        my = (start[1] + end[1]) / 2 + label_offset[1]
        ax.text(mx, my, label, ha="center", va="center", fontsize=6.6, color=color)


ax.text(
    1,
    59.5,
    "One copilot turn (the model only picks a tool and phrases; "
    "a person confirms every work order)",
    fontsize=9.5,
    color=TITLE,
    weight="bold",
    va="center",
)

# Row 1: the turn.
y1, h1 = 46, 10.5
box(1, y1, 14, h1, ["Employee message", "(Arabic or English)"], GREEN_FILL, GREEN_EDGE)
box(
    18.5,
    y1,
    19.5,
    h1,
    ["Code sets the language,", "removes phone numbers,", "adds the data's date"],
)
box(41.5, y1, 16, h1, ["Model picks a tool", "(GPT-OSS 120B", "on Groq)"])
box(65.5, y1, 16, h1, ["Model phrases", "the answer"])
box(
    88,
    y1,
    22,
    h1,
    ["Checks in code:", "every number grounded,", "no phone number"],
    ORANGE_FILL,
    ORANGE_EDGE,
)
arrow((15.4, y1 + h1 / 2), (18.1, y1 + h1 / 2))
arrow((38.4, y1 + h1 / 2), (41.1, y1 + h1 / 2))
arrow((81.9, y1 + h1 / 2), (87.6, y1 + h1 / 2))

# Row 2: the tools, run in code.
y2, h2 = 28, 10
net = box(20, y2, 16.5, h2, ["tower_alerts", "tower_status", "network_overview"])
gis = box(38, y2, 16.5, h2, ["expansion_priorities", "explain_location"])
cus = box(56, y2, 15.5, h2, ["portfolio_summary", "subscriber_risk"])
drf = box(73, y2, 14, h2, ["draft_work_order", "(saves nothing)"], ORANGE_FILL, ORANGE_EDGE)
ax.text(
    54, y2 + h2 + 2.2, "Tools, run in code", ha="center", fontsize=7.4, color=TITLE, weight="bold"
)
arrow((47, y1 - 0.4), (45, y2 + h2 + 0.6))
arrow(
    (68, y2 + h2 + 0.6), (72.5, y1 - 0.4), label="tool result", color=TITLE, label_offset=(4.6, 0)
)

# Row 3: the team's outputs the tools read.
y3, h3 = 13.5, 8.5
box(
    15.5,
    y3,
    23,
    h3,
    ["Network team: daily KPIs", "for 1,067 towers (committed files)"],
    GREEN_FILL,
    GREEN_EDGE,
    size=7.2,
)
box(
    40,
    y3,
    14.5,
    h3,
    ["GIS team: ranked", "sites in Tripoli", "(committed release)"],
    GREEN_FILL,
    GREEN_EDGE,
    size=7.2,
)
box(
    56,
    y3,
    15.5,
    h3,
    ["Prepaid module:", "read-only API", "(copilot key)"],
    GREEN_FILL,
    GREEN_EDGE,
    size=7.2,
)
for tool, x in ((net, 28.25), (gis, 47.25), (cus, 63.75)):
    arrow((x, tool[1] - 0.4), (x, y3 + h3 + 0.4), style="<|-|>")

# The answer, or the safe answer.
box(
    89.5, 28, 16, 10, ["Answer in the", "employee's language,", 'with "What I looked up"'], size=7.2
)
box(
    107.5,
    28,
    12,
    10,
    ["Safe answer", "built only from", "the tool results"],
    ORANGE_FILL,
    ORANGE_EDGE,
)
arrow((95.5, y1 - 0.4), (97.5, 38.4), label="passed", color=TITLE, label_offset=(-3.6, 0))
arrow(
    (104, y1 - 0.4),
    (112.5, 38.4),
    label="failed",
    color=ORANGE_EDGE,
    ls="--",
    label_offset=(3.6, 0),
)

# The work order lane: only a named employee's Confirm writes anything.
y4, h4 = 1.2, 8.3
box(
    76,
    y4,
    14.5,
    h4,
    ["Draft shown on", "screen; nothing", "is saved yet"],
    ORANGE_FILL,
    ORANGE_EDGE,
)
box(
    93.5,
    y4,
    13.5,
    h4,
    ["Employee types a", "name and presses", "Confirm"],
    GREEN_FILL,
    GREEN_EDGE,
)
box(110, y4, 9.5, h4, ["Work order", "saved"], GREEN_FILL, GREEN_EDGE)
arrow((80, y2 - 0.4), (81, y4 + h4 + 0.4))
arrow((90.9, y4 + h4 / 2), (93.1, y4 + h4 / 2))
arrow((107.4, y4 + h4 / 2), (109.6, y4 + h4 / 2))

box(
    1,
    y4,
    30,
    h4,
    ["Tower alerts on the page: rules in code", "on the latest day, no model involved"],
    BLUE_FILL,
    BLUE_EDGE,
    size=7.2,
)
arrow((21, y3 - 0.4), (17, y4 + h4 + 0.4))

ax.text(
    1,
    33,
    "\n".join(
        [
            "The model never",
            "acts: it cannot",
            "send, apply or",
            "approve, and has",
            "no path to the",
            "saved work order.",
        ]
    ),
    fontsize=7.2,
    color=ORANGE_EDGE,
    weight="bold",
    va="center",
    linespacing=1.3,
)

fig.savefig("copilot_workflow.png", bbox_inches="tight", pad_inches=0.08, facecolor="white")
print("saved")
