#!/usr/bin/env python3
"""Q9 sensitivity analysis of the objective-QoE weights against subjective MOS.

Model (all terms already normalized to [0,1]):

    QoE   = delta_vid * Q_video + delta_Int * Q_Int   (delta_vid + delta_Int = 1)
    Q_Int = beta * Q_delay + (1 - beta) * Q_sync       (beta = 0.5)
    Q_sync  = 0.5 * (Q_Vsmooth + Q_Csmooth)
    Q_video = AvgVMAF / 100
    Q_delay = 1 / (1 + exp(k * (RT - RT0)))            (RT0 = 50 ms, k = 0.1)

For each game (and overall) we sweep delta_vid over a grid and, comparing the
model output against the mean subjective MOS (rescaled 1-5 -> [0,1]) across the
5 bandwidths x {real, synth} = 10 conditions, report:

    * best delta_vid / delta_Int   (minimizing MAE)
    * best MAE
    * MAE at the equal-weight operating point (delta_vid = 0.5)
    * Spearman rho between model QoE and MOS (evaluated at the best weight)

Two variants of the interactivity term are reported side by side:
    delay_exclusive : Q_Int = Q_sync                       (deployed QoE model)
    delay_inclusive : Q_Int = beta*Q_delay + (1-beta)*Q_sync (Fig. 9 quantity)

Outputs (written to supabase_qoe_plots/, per variant <v>):
    weight_sensitivity_table_<v>.tex   -- booktabs LaTeX table
    weight_sensitivity_sweep_<v>.pdf   -- MAE vs delta_vid curves per game
    weight_sensitivity_sweep_<v>.png

Run:  python3 weight_sensitivity_analysis.py
"""
import csv
import math
import os

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import spearmanr

HERE = os.path.dirname(os.path.abspath(__file__))  # .../supabase_qoe_plots/
EXP = os.path.dirname(HERE)                          # .../acm_tomm_experiments/
CSV_SUBJ = os.path.join(EXP, "supabase_responses_acm_tomm_subjective_qoe_rows.csv")
VMAF_REAL = os.path.join(EXP, "processed_data", "vmaf_metrics_real.csv")
VMAF_SYNTH = os.path.join(EXP, "processed_data", "vmaf_metrics_synth.csv")
OUT = HERE  # tables + figures live next to this script (supabase_qoe_plots/)

GAMES = ["Fortnite", "Forza", "Kombat"]
BW_LABELS = ["2Mbit", "4Mbit", "6Mbit", "8Mbit", "10Mbit"]
BW_VALUES = [2, 4, 6, 8, 10]

BETA = 0.5          # Q_Int = BETA*Q_delay + (1-BETA)*Q_sync
RT0, K = 50.0, 0.1  # Q_delay logistic parameters

# colors match the paper figures (tools/generate_graphs.py / overlay script)
GAME_COLORS = {"Fortnite": "#3E9BDD", "Forza": "#20CA06", "Kombat": "#F00505"}
# distinct line styles + markers so the curves stay legible in grayscale / print
SERIES_STYLE = {
    "Fortnite": {"color": "#3E9BDD", "ls": "-",            "marker": "o"},
    "Forza":    {"color": "#20CA06", "ls": (0, (5, 2)),    "marker": "s"},
    "Kombat":   {"color": "#F00505", "ls": (0, (3, 1, 1, 1)), "marker": "^"},
    "Overall":  {"color": "#222222", "ls": (0, (1, 1)),    "marker": "D"},
}


# --------------------------------------------------------------------------- #
# component computation (no cv2 dependency; mirrors tools/vmaf_scatter.py)
# --------------------------------------------------------------------------- #
def load_vmaf(path):
    out = {}
    with open(path) as f:
        for r in csv.DictReader(f):
            out[(r["Game"], r["BitrateLabel"])] = float(r["AvgVMAF"])
    return out


def _smooth_ratio(root, num, den):
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


def _mean_rt_ms(root):
    for sub in ("logs copy", "logs"):
        path = os.path.join(root, sub, "responsetime_CG.csv")
        if not os.path.exists(path):
            continue
        try:
            df = pd.read_csv(path)
            if "frame_timestamp" not in df.columns or "cmd_timestamp" not in df.columns:
                continue
            dt = (df["frame_timestamp"] - df["cmd_timestamp"]).astype(float)
            rt = (dt.abs() * 1000.0).to_numpy()
            if rt.size:
                return float(rt.mean())
        except Exception:
            continue
    return None


def _q_delay(rt_ms):
    q = 1.0 / (1.0 + math.exp(K * (rt_ms - RT0)))
    return float(max(0.0, min(1.0, q)))


def load_subjective():
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


def build_cells(use_delay):
    """Return list of (game, Q_video, Q_int, MOS_norm) over all valid conditions.

    use_delay=True  -> Q_int = beta*Q_delay + (1-beta)*Q_sync  (delay-inclusive)
    use_delay=False -> Q_int = Q_sync                          (delay-exclusive,
                       the interactivity term used in the deployed QoE model)
    """
    vmaf = {"real": load_vmaf(VMAF_REAL), "synth": load_vmaf(VMAF_SYNTH)}
    subj = load_subjective()
    cells = []
    for g in GAMES:
        for bl, bv in zip(BW_LABELS, BW_VALUES):
            for kind in ("real", "synth"):
                v = vmaf[kind].get((g, f"{bl}_{g}"))
                q_video = None if v is None else max(0.0, min(1.0, v / 100.0))
                rk = "reference_vs_real" if kind == "real" else "reference_vs_synth"
                root = os.path.join(EXP, rk, g, f"{bl}_{g}")
                vsm = _smooth_ratio(root, "received_fps", "current_srv_fps")
                csm = _smooth_ratio(root, "current_cps", "received_cps")
                q_int = None
                if vsm is not None and csm is not None:
                    q_sync = 0.5 * (vsm + csm)
                    if use_delay:
                        rt = _mean_rt_ms(root)
                        if rt is not None:
                            q_int = BETA * _q_delay(rt) + (1.0 - BETA) * q_sync
                    else:
                        q_int = q_sync
                scores = subj[g][bv][kind]
                mos = None if not scores else (float(np.mean(scores)) - 1.0) / 4.0
                if None in (q_video, q_int, mos):
                    continue
                cells.append((g, q_video, q_int, mos))
    return cells


# --------------------------------------------------------------------------- #
# sensitivity sweep
# --------------------------------------------------------------------------- #
def mae_curve(cells, grid):
    qv = np.array([c[1] for c in cells])
    qi = np.array([c[2] for c in cells])
    m = np.array([c[3] for c in cells])
    return np.array([np.mean(np.abs(w * qv + (1 - w) * qi - m)) for w in grid])


def summarize(cells, grid):
    qv = np.array([c[1] for c in cells])
    qi = np.array([c[2] for c in cells])
    m = np.array([c[3] for c in cells])
    curve = mae_curve(cells, grid)
    i = int(np.argmin(curve))
    w_best = float(grid[i])
    mae_best = float(curve[i])
    mae_half = float(np.mean(np.abs(0.5 * qv + 0.5 * qi - m)))
    pred = w_best * qv + (1 - w_best) * qi
    rho = float(spearmanr(pred, m).correlation)
    return {
        "delta_vid": w_best, "delta_int": 1 - w_best,
        "mae_best": mae_best, "mae_half": mae_half, "rho": rho, "n": len(cells),
    }


def latex_table(results, variant, int_desc):
    lines = [
        r"\begin{table}[t]",
        r"  \centering",
        r"  \caption{Sensitivity of the objective QoE model to the video/interactivity"
        r" weight ($\delta_{\mathrm{vid}}+\delta_{\mathrm{Int}}=1$), evaluated against"
        r" subjective MOS over 5 bandwidths $\times$ \{real, synth\}. MAE and MOS are"
        r" normalized to $[0,1]$; $\rho$ is Spearman rank correlation at the best weight."
        r" Interactivity term: " + int_desc + r".}",
        r"  \label{tab:weight-sensitivity-" + variant + r"}",
        r"  \begin{tabular}{lrrrrr}",
        r"    \toprule",
        r"    Game & $\delta_{\mathrm{vid}}^\star$ & $\delta_{\mathrm{Int}}^\star$"
        r" & Best MAE & MAE @ 0.5 & Spearman $\rho$ \\",
        r"    \midrule",
    ]
    for name in GAMES + ["Overall"]:
        r = results[name]
        bold = r"\textbf{" if name == "Overall" else ""
        endb = "}" if name == "Overall" else ""
        row = (
            f"    {bold}{name}{endb} & "
            f"{bold}{r['delta_vid']:.2f}{endb} & {bold}{r['delta_int']:.2f}{endb} & "
            f"{bold}{r['mae_best']:.3f}{endb} & {bold}{r['mae_half']:.3f}{endb} & "
            f"{bold}{r['rho']:.3f}{endb} \\\\"
        )
        lines.append(row)
        if name == GAMES[-1]:
            lines.append(r"    \midrule")
    lines += [r"    \bottomrule", r"  \end{tabular}", r"\end{table}", ""]
    return "\n".join(lines)


def plot_sweep(cells_by_game, cells_all, grid, out_base, title=None):
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    if title:
        ax.set_title(title, fontsize=14)

    def draw(name, curve):
        s = SERIES_STYLE[name]
        i = int(np.argmin(curve))
        ax.plot(grid, curve, color=s["color"], lw=2.4, ls=s["ls"],
                marker=s["marker"], ms=7, markevery=2, markeredgecolor="white",
                markeredgewidth=0.6, label=name, zorder=3)
        # highlight the per-series minimum with a ringed marker
        ax.scatter([grid[i]], [curve[i]], color=s["color"], s=110,
                   marker=s["marker"], edgecolor="black", linewidth=1.3, zorder=5)

    for g in GAMES:
        draw(g, mae_curve(cells_by_game[g], grid))
    draw("Overall", mae_curve(cells_all, grid))

    # equal-weight reference line (solid grey so it is not confused with a series)
    ax.axvline(0.5, color="#999999", ls="-", lw=1.2, zorder=1)
    ax.text(0.5, ax.get_ylim()[1], "  equal weights", ha="left", va="top",
            fontsize=11, color="#555555")

    ax.set_xlabel(r"$\delta_{\mathrm{vid}}$  (interactivity weight $=1-\delta_{\mathrm{vid}}$)",
                  fontsize=14)
    ax.set_ylabel("MAE vs. subjective MOS", fontsize=14)
    ax.set_xlim(0, 1)
    ax.tick_params(labelsize=12)
    ax.grid(True, ls="--", lw=0.6, alpha=0.7, color="#DDDDDD")
    ax.set_axisbelow(True)
    ax.legend(fontsize=12, framealpha=0.95, edgecolor="black")
    fig.tight_layout()
    fig.savefig(out_base + ".pdf")
    fig.savefig(out_base + ".png", dpi=300)
    plt.close(fig)


VARIANTS = [
    # (file suffix, use_delay, LaTeX interactivity description, figure title)
    ("delay_exclusive", False,
     r"$Q_{\mathrm{Int}}=Q_{\mathrm{sync}}=\tfrac12(Q_{\mathrm{Vsmooth}}+Q_{\mathrm{Csmooth}})$"
     r" (delay excluded; matches the deployed QoE model)",
     "Delay-exclusive  (interactivity = Q_sync)"),
    ("delay_inclusive", True,
     r"$Q_{\mathrm{Int}}=\beta Q_{\mathrm{delay}}+(1-\beta)Q_{\mathrm{sync}}$, $\beta=0.5$"
     r" (delay included; matches the Fig.~9 $Q_{\mathrm{Int}}$)",
     "Delay-inclusive  (interactivity = beta*Q_delay + (1-beta)*Q_sync)"),
]


def run_variant(suffix, use_delay, int_desc, title, grid):
    cells = build_cells(use_delay)
    cells_by_game = {g: [c for c in cells if c[0] == g] for g in GAMES}
    results = {g: summarize(cells_by_game[g], grid) for g in GAMES}
    results["Overall"] = summarize(cells, grid)

    print(f"\n=== {suffix} ===")
    print(f"{'Game':9}{'d_vid':>7}{'d_Int':>7}{'BestMAE':>9}{'MAE@0.5':>9}{'Spearman':>10}{'n':>4}")
    for name in GAMES + ["Overall"]:
        r = results[name]
        print(f"{name:9}{r['delta_vid']:7.2f}{r['delta_int']:7.2f}"
              f"{r['mae_best']:9.3f}{r['mae_half']:9.3f}{r['rho']:10.3f}{r['n']:4d}")

    tex_path = os.path.join(OUT, f"weight_sensitivity_table_{suffix}.tex")
    with open(tex_path, "w") as f:
        f.write(latex_table(results, suffix, int_desc))
    fig_base = os.path.join(OUT, f"weight_sensitivity_sweep_{suffix}")
    plot_sweep(cells_by_game, cells, grid, fig_base, title=title)
    print(f"[written] {tex_path}")
    print(f"[written] {fig_base}.pdf / .png")


def main():
    os.makedirs(OUT, exist_ok=True)
    grid = np.round(np.arange(0.0, 1.0001, 0.1), 2)
    for suffix, use_delay, int_desc, title in VARIANTS:
        run_variant(suffix, use_delay, int_desc, title, grid)


if __name__ == "__main__":
    main()
