#!/usr/bin/env python3
"""
Overlay the subjective QoE (MOS) on the paper's objective QoE-vs-bandwidth
figures, per game.

The objective QoE model output is already normalized to [0,1]
(QoE = 0.5*Q_video + 0.5*Q_sync, with Q_video = AvgVMAF/100 and
 Q_sync = 0.5*(Q_Vsmooth + Q_Csmooth); same computation as
 tools/generate_graphs.py::plot_qoe_real_vs_synth).

Because the subjective MOS is rescaled to the SAME [0,1] range, objective and
subjective QoE live on one shared scale — they are drawn on a single y-axis and
are directly comparable. A right-hand axis mirrors the identical 0-1 scale so
the subjective series can be read off the right, per request; it is NOT a second,
different scale (that would be a misleading dual-axis chart).

Objective  -> grouped bars   (colors/hatches match the existing paper figures)
Subjective -> line + markers  (Okabe-Ito blue/vermillion, 95% CI)

Outputs (per game): qoe_overlay_objective_subjective_<game>.{pdf,png}

Run:  python3 generate_objective_subjective_overlay.py
"""
import csv
import math
import os

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from scipy import stats

try:
    import pandas as pd
except ImportError:
    pd = None

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(HERE)                      # acm_tomm_experiments/
REPO = os.path.dirname(EXP)                       # repo root
CSV_SUBJ = os.path.join(EXP, "supabase_responses_acm_tomm_subjective_qoe_rows.csv")
VMAF_REAL = os.path.join(EXP, "processed_data", "vmaf_metrics_real.csv")
VMAF_SYNTH = os.path.join(EXP, "processed_data", "vmaf_metrics_synth.csv")
OUT = HERE

GAMES = ["Fortnite", "Forza", "Kombat"]
BW_LABELS = ["2Mbit", "4Mbit", "6Mbit", "8Mbit", "10Mbit"]
BW_VALUES = [2, 4, 6, 8, 10]

# objective-bar colors/hatches — identical to tools/generate_graphs.py
GAME_COLORS = {
    "Fortnite": {"real": "#BEDDF7", "synth": "#3E9BDD"},
    "Forza":    {"real": "#BEEBB3", "synth": "#20CA06"},
    "Kombat":   {"real": "#FCA7A7", "synth": "#F00505"},
}
GAME_HATCHES = {"Fortnite": "", "Forza": "//", "Kombat": "xx"}
# subjective-line colors — CVD-safe Okabe-Ito, distinct from the bars
C_REAL = "#0072B2"
C_SYNTH = "#D55E00"
INK, MUTED, GRID = "#222222", "#666666", "#DDDDDD"

plt.rcParams.update({
    "figure.dpi": 120, "savefig.dpi": 300, "font.size": 12,
    "font.family": "DejaVu Sans", "axes.edgecolor": MUTED,
    "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": INK, "ytick.color": INK,
    "axes.axisbelow": True, "legend.frameon": True,
})


# --------------------------------------------------------------------------- #
# objective QoE  (replicates generate_graphs.py, without the cv2 import chain)
# --------------------------------------------------------------------------- #
def load_vmaf(path):
    out = {}
    with open(path) as f:
        for r in csv.DictReader(f):
            out[(r["Game"], r["BitrateLabel"])] = float(r["AvgVMAF"])
    return out


def _smooth_ratio(root, num, den):
    """Mean clipped ratio num/den from srv_QoEMetrics.csv (logs copy | logs)."""
    if pd is None:
        return None
    for sub in ("logs copy", "logs"):
        path = os.path.join(root, sub, "srv_QoEMetrics.csv")
        if not os.path.exists(path):
            continue
        try:
            df = pd.read_csv(path)
            if num not in df.columns or den not in df.columns:
                continue
            df = df[df[den] > 0]
            if df.empty:
                continue
            return float((df[num] / df[den]).clip(lower=0.0, upper=1.0).mean())
        except Exception:
            continue
    return None


def objective_qoe(game, bw_label, vmaf_cache, kind):
    """kind in {'real','synth'}; returns QoE in [0,1] or None."""
    key = (game, f"{bw_label}_{game}")
    vmaf = vmaf_cache.get(key)
    if vmaf is None:
        return None
    q_video = max(0.0, min(1.0, vmaf / 100.0))
    root_kind = "reference_vs_real" if kind == "real" else "reference_vs_synth"
    root = os.path.join(EXP, root_kind, game, f"{bw_label}_{game}")
    vsmooth = _smooth_ratio(root, "received_fps", "current_srv_fps")
    csmooth = _smooth_ratio(root, "current_cps", "received_cps")
    if vsmooth is None or csmooth is None:
        return None
    q_sync = 0.5 * (vsmooth + csmooth)
    return 0.5 * q_video + 0.5 * q_sync


# --------------------------------------------------------------------------- #
# subjective MOS  (rescaled to [0,1], with 95% CI)
# --------------------------------------------------------------------------- #
def load_subjective():
    """game -> bw(int) -> {'real':[...], 'synth':[...]}"""
    data = {g: {b: {"real": [], "synth": []} for b in BW_VALUES} for g in GAMES}
    with open(CSV_SUBJ) as f:
        for r in csv.DictReader(f):
            g = r["game"]
            try:
                bw = int(float(r["bandwidth_mbit"]))
                sa, sb = int(r["score_a"]), int(r["score_b"])
            except (ValueError, KeyError):
                continue
            if g not in data or bw not in data[g]:
                continue
            real_s, synth_s = (sa, sb) if r["video_a_kind"] == "real" else (sb, sa)
            data[g][bw]["real"].append(real_s)
            data[g][bw]["synth"].append(synth_s)
    return data


def _mean_ci(v):
    v = np.asarray(v, float)
    n = len(v)
    if n == 0:
        return np.nan, 0.0
    m = v.mean()
    if n < 2:
        return m, 0.0
    return m, v.std(ddof=1) / math.sqrt(n) * stats.t.ppf(0.975, n - 1)


def mos01_ci(scores):
    """(mean, halfwidth) of (score-1)/4 (rescaled to [0,1]) with 95% t CI."""
    return _mean_ci((np.asarray(scores, float) - 1.0) / 4.0)


def mos_native_ci(scores):
    """(mean, halfwidth) of raw 1-5 MOS with 95% t CI."""
    return _mean_ci(scores)


# --------------------------------------------------------------------------- #
def plot_game(game, vmaf_real, vmaf_synth, subj, scale="shared"):
    """scale='shared' -> subjective rescaled to [0,1] on a mirrored right axis.
       scale='native' -> subjective on a native 1-5 right axis (true dual-axis)."""
    x = np.arange(len(BW_VALUES))
    bw = 0.35
    real_c = GAME_COLORS[game]["real"]
    synth_c = GAME_COLORS[game]["synth"]
    hatch = GAME_HATCHES[game]
    native = scale == "native"

    obj_r = [objective_qoe(game, b, vmaf_real, "real") for b in BW_LABELS]
    obj_s = [objective_qoe(game, b, vmaf_synth, "synth") for b in BW_LABELS]
    obj_r = [v if v is not None else 0.0 for v in obj_r]
    obj_s = [v if v is not None else 0.0 for v in obj_s]

    ci = mos_native_ci if native else mos01_ci
    subj_r = [ci(subj[game][b]["real"]) for b in BW_VALUES]
    subj_s = [ci(subj[game][b]["synth"]) for b in BW_VALUES]
    sr_m, sr_e = [m for m, _ in subj_r], [e for _, e in subj_r]
    ss_m, ss_e = [m for m, _ in subj_s], [e for _, e in subj_s]

    fig, ax = plt.subplots(figsize=(8.4, 5.6))

    # ---- objective QoE bars (left, 0-1)
    ax.bar(x - bw / 2, obj_r, width=bw, color=real_c, edgecolor="black",
           linewidth=1.0, hatch=hatch, zorder=2, label="Objective QoE — Real")
    ax.bar(x + bw / 2, obj_s, width=bw, color=synth_c, edgecolor="black",
           linewidth=1.0, hatch=hatch, zorder=2, label="Objective QoE — Synth")

    AX_FS, TICK_FS = 20, 18  # larger fonts — used as a small figure in the paper
    ax.set_xticks(x)
    ax.set_xticklabels([str(b) for b in BW_VALUES])
    ax.set_xlabel("Bandwidth (Mbit/s)", fontsize=AX_FS)
    ax.set_ylabel("Objective QoE model score (0–1)", fontsize=AX_FS)
    ax.set_ylim(0.0, 1.0)
    ax.tick_params(axis="both", labelsize=TICK_FS)
    ax.grid(True, axis="y", linestyle="--", linewidth=0.6, alpha=0.7,
            color=GRID, zorder=0)
    ax.set_axisbelow(True)

    # ---- right axis + subjective overlay
    ax2 = ax.twinx()
    if native:
        ax2.set_ylim(1.0, 5.0)
        ax2.set_yticks(range(1, 6))
        ax2.set_ylabel("Subjective MOS (1–5)", color=INK, fontsize=AX_FS)
        subj_axis = ax2  # points live on the 1-5 axis
    else:
        ax2.set_ylim(0.0, 1.0)  # mirror of the left scale
        ax2.set_ylabel("Subjective QoE  (MOS 0-1)", color=INK,
                       fontsize=AX_FS)
        subj_axis = ax      # points share the 0-1 axis
    ax2.tick_params(axis="y", labelcolor=INK, labelsize=TICK_FS)

    subj_axis.errorbar(x - bw / 2, sr_m, yerr=sr_e, color='silver', marker="o",
                       ms=8, lw=4, ls="-", capsize=4, zorder=5,
                       markeredgecolor="white", markeredgewidth=0.8)
    subj_axis.errorbar(x + bw / 2, ss_m, yerr=ss_e, color='black', marker="s",
                       ms=8, lw=4, ls="--", capsize=4, zorder=5,
                       markeredgecolor="white", markeredgewidth=0.8)

    #ax.set_title(f"{game}: objective QoE model vs subjective MOS",
    #             color=synth_c, fontweight="bold", fontsize=15)

    handles = [
        mpatches.Patch(facecolor=real_c, edgecolor="black", hatch=hatch,
                       label="Objective QoE — Real"),
        mpatches.Patch(facecolor=synth_c, edgecolor="black", hatch=hatch,
                       label="Objective QoE — Synth"),
        plt.Line2D([], [], color='silver', marker="o", ms=8, lw=4, ls="-",
                   label="Subjective MOS — Real"),
        plt.Line2D([], [], color='black', marker="s", ms=8, lw=4, ls="--",
                   label="Subjective MOS — Synth"),
    ]
    ax2.legend(handles=handles, loc="lower right", fontsize=18,
               framealpha=0.95, edgecolor="black")

    fig.tight_layout()
    stem = ("qoe_overlay_objective_subjective_non_scaled" if native
            else "qoe_overlay_objective_subjective")
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(OUT, f"{stem}_{game.lower()}.{ext}"),
                    bbox_inches="tight")
    plt.close(fig)
    tag = "subjMOS15" if native else "subjMOS01"
    print(f"{game} [{scale}]:")
    for i, b in enumerate(BW_VALUES):
        print(f"  {b:>2} Mbit  obj[real={obj_r[i]:.3f} synth={obj_s[i]:.3f}]  "
              f"{tag}[real={sr_m[i]:.3f} synth={ss_m[i]:.3f}]")


def main():
    if pd is None:
        print("[WARN] pandas not available — objective Q_sync cannot be computed.")
    vmaf_real = load_vmaf(VMAF_REAL)
    vmaf_synth = load_vmaf(VMAF_SYNTH)
    subj = load_subjective()
    print("Generating objective+subjective overlays ->", OUT)
    for game in GAMES:
        plot_game(game, vmaf_real, vmaf_synth, subj, scale="shared")
        plot_game(game, vmaf_real, vmaf_synth, subj, scale="native")
    print("Done.")


if __name__ == "__main__":
    main()
