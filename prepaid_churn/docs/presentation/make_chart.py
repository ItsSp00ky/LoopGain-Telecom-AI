"""Redraw `churn_results.png`, the two-panel results chart used in the mentoring session.

Every number is copied from `reports/evaluation_all.md` (the frozen T7 test month), so
the chart needs no model and no data: run it with
`uv run python docs/presentation/make_chart.py` from `prepaid_churn/`.
If a number in that report ever changes, change it here too.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

OUT = Path(__file__).with_name("churn_results.png")

# reports/evaluation_all.md, "Top of the ranking" and "Risk bands on test"
CONTACTED = [0, 5, 10, 20, 100]
CAUGHT = [0, 42.0, 61.5, 79.8, 100]
BANDS = ["High", "Medium", "Low"]
BAND_RATES = [38.4, 12.0, 1.3]
BAND_CUSTOMERS = [450, 1238, 7989]
BASE_RATE = 4.35


def main() -> None:
    plt.rcParams.update({"font.size": 13, "axes.spines.top": False, "axes.spines.right": False})
    fig, (left, right) = plt.subplots(1, 2, figsize=(13, 5.4))

    left.plot(CONTACTED, CAUGHT, marker="o", linewidth=2.5, color="#1f4e79", label="Our model")
    left.plot([0, 100], [0, 100], "--", linewidth=1.5, color="#9a9a9a", label="Contact at random")
    left.annotate(
        "Contact the riskiest 10%,\nreach 61.5% of next\nmonth's churners",
        xy=(10, 61.5),
        xytext=(30, 38),
        fontsize=12,
        arrowprops={"arrowstyle": "->", "color": "#1f4e79"},
    )
    left.set_xlabel("Customers contacted (%)")
    left.set_ylabel("Churners reached (%)")
    left.set_title("Who the model finds", fontweight="bold", loc="left")
    left.legend(frameon=False, loc="lower right")
    left.set_xlim(0, 100)
    left.set_ylim(0, 102)

    bars = right.bar(BANDS, BAND_RATES, color=["#c0392b", "#e08e45", "#4f7a4f"], width=0.6)
    for bar, rate, count in zip(bars, BAND_RATES, BAND_CUSTOMERS, strict=True):
        middle = bar.get_x() + bar.get_width() / 2
        right.text(middle, rate + 1.5, f"{rate}%", ha="center", fontweight="bold")
        right.text(middle, -3.4, f"{count:,} customers", ha="center", fontsize=11, color="#555555")
    right.axhline(BASE_RATE, color="#444444", linestyle="--", linewidth=1.3)
    right.text(-0.45, BASE_RATE + 1.05, "Everyone: 4.4%", fontsize=11, color="#444444")
    right.set_ylabel("Went silent next month (%)")
    right.set_title("How each risk band behaved", fontweight="bold", loc="left")
    right.set_ylim(0, 45)
    right.tick_params(axis="x", pad=22)

    fig.suptitle(
        "Prepaid churn: 9,677 customers, one month the model had never seen",
        fontsize=15,
        fontweight="bold",
        x=0.015,
        ha="left",
    )
    fig.text(
        0.015,
        0.015,
        "upGrad prepaid data, LightGBM, calibrated. Test ROC-AUC 0.891. Team Loop Gain.",
        fontsize=10,
        color="#555555",
    )
    fig.tight_layout(rect=[0, 0.04, 1, 0.93])
    fig.savefig(OUT, dpi=160)
    print(f"Chart written to {OUT}")


if __name__ == "__main__":
    main()
