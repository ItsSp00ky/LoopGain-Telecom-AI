"""Figure 7 of the final report: one chatbot turn.

Drawn in the style of the prepaid part's Figures 1 and 2.

Run: uv run --no-project --python 3.12 --with matplotlib python chatbot_workflow.py
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

fig, ax = plt.subplots(figsize=(12, 5.4), dpi=220)
ax.set_xlim(0, 120)
ax.set_ylim(0, 54)
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
    51.5,
    "One chatbot turn (the model only picks a tool and phrases what it returns)",
    fontsize=9.5,
    color=TITLE,
    weight="bold",
    va="center",
)

y1, h1 = 33, 11
box(1, y1, 14, h1, ["Customer message", "(Arabic or English)"], GREEN_FILL, GREEN_EDGE)
box(
    18.5,
    y1,
    19.5,
    h1,
    ["Code decides the", "language, the sign-in and", "any other account number"],
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

y2, h2 = 13.5, 10.5
fp = box(37, y2, 14.5, h2, ["find_packages", "filter and sort in", "code, up to 10"])
mo = box(53.5, y2, 14.5, h2, ["my_offer", "signed-in customer", "only, no arguments"])
box(70, y2, 15, h2, ["find_service_point", "waiting for the", "shop list"])
ax.text(
    61, y2 + h2 + 2.0, "Tools, run in code", ha="center", fontsize=7.4, color=TITLE, weight="bold"
)
arrow((47, y1 - 0.4), (44.2, y2 + h2 + 0.6))
arrow(
    (77.5, y2 + h2 + 0.6), (73.5, y1 - 0.4), label="tool result", color=TITLE, label_offset=(4.2, 0)
)

box(
    37,
    1,
    48,
    7.5,
    [
        "Prepaid customer module: read-only API service (chatbot key)",
        "/catalogue  ·  /subscribers/{id}/retention (customer message only)",
    ],
    GREEN_FILL,
    GREEN_EDGE,
    size=7.4,
)
for t in (fp, mo):
    arrow((t[0] + t[2] / 2, y2 - 0.4), (t[0] + t[2] / 2, 8.9), style="<|-|>")

box(86, 16, 17, 9, ["Answer in the", "customer's language,", 'with "What I looked up"'])
box(
    106, 16, 13, 9, ["Safe answer built", "only from the", "tool results"], ORANGE_FILL, ORANGE_EDGE
)
arrow((95.5, y1 - 0.4), (94.2, 25.4), label="passed", color=TITLE, label_offset=(-3.4, 0))
arrow(
    (104, y1 - 0.4),
    (112.5, 25.4),
    label="failed",
    color=ORANGE_EDGE,
    ls="--",
    label_offset=(3.6, 0),
)

ax.text(
    1,
    18.5,
    "\n".join(
        [
            "No language model sets an offer,",
            "a price or a number.",
            "The subscriber ID never",
            "reaches the model.",
        ]
    ),
    fontsize=7.2,
    color=ORANGE_EDGE,
    weight="bold",
    va="center",
    linespacing=1.3,
)

fig.savefig("chatbot_workflow.png", bbox_inches="tight", pad_inches=0.08, facecolor="white")
print("saved")
