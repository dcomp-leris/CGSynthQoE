#!/usr/bin/env python3
"""
Subjective QoE experiment plots for the ACM TOMM revision.

Maps the subjective study (supabase_responses_acm_tomm_subjective_qoe_rows.csv)
onto the paper's objective QoE model. Each participant rated a *real* (original
encode) and a *synth* (RIFE frame-interpolated) video of the same game/bandwidth
on a 1-5 MOS scale, and guessed which one was real (discrimination test).

Figures produced (PDF + PNG, 300 dpi):
  fig1_mos_vs_bandwidth_overall      MOS[0,1] vs bandwidth, real vs synth, log fit
  fig1_mos_vs_bandwidth_per_game     same, 3 game facets
  fig2_objective_vs_subjective       AvgVMAF (+PSNR/SSIM/LPIPS) vs MOS, regression
  fig3_discrimination_accuracy       % correct real/synth ID vs bandwidth, chance line
  fig4_real_synth_mos_gap            (synth-real) MOS deviation per condition
  fig5_rating_distribution           diverging 1-5 rating distribution, real vs synth
  fig6_which_real_composition        A/B/Both/None response composition per bandwidth

Run:  python3 generate_qoe_subjective_plots.py
"""
import csv
import os
import math
from collections import defaultdict

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(HERE)  # acm_tomm_experiments/
CSV = os.path.join(EXP, "supabase_responses_acm_tomm_subjective_qoe_rows.csv")
VMAF_REAL = os.path.join(EXP, "processed_data", "vmaf_metrics_real.csv")
VMAF_SYNTH = os.path.join(EXP, "processed_data", "vmaf_metrics_synth.csv")
OUT = HERE

# ---- palette (validated CVD-safe: dataviz validate_palette.js, all checks pass)
C_REAL = "#0072B2"   # Okabe-Ito blue
C_SYNTH = "#D55E00"  # Okabe-Ito vermillion
# game identity (matches paper figures) + distinct markers for CVD safety
GAME_COLOR = {"Fortnite": "#3E9BDD", "Forza": "#20CA06", "Kombat": "#F00505"}
GAME_MARKER = {"Fortnite": "o", "Forza": "s", "Kombat": "^"}
# hatch textures matching the paper figures (Fortnite none, Forza //, Kombat xx)
GAME_HATCH = {"Fortnite": "", "Forza": "//", "Kombat": "xx"}
GAMES = ["Fortnite", "Forza", "Kombat"]
INK = "#222222"
MUTED = "#666666"
GRID = "#DDDDDD"

plt.rcParams.update({
    "figure.dpi": 120,
    "savefig.dpi": 300,
    "font.size": 11,
    "font.family": "DejaVu Sans",
    "axes.edgecolor": MUTED,
    "axes.labelcolor": INK,
    "text.color": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "axes.axisbelow": True,
    "legend.frameon": False,
})


def save(fig, name):
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(OUT, f"{name}.{ext}"), bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {name}.pdf / .png")


# --------------------------------------------------------------------------- #
# Load & reshape subjective data
# --------------------------------------------------------------------------- #
def load_trials():
    """One record per trial with paired real/synth scores."""
    trials = []
    with open(CSV) as f:
        for r in csv.DictReader(f):
            try:
                sa, sb = int(r["score_a"]), int(r["score_b"])
                bw = float(r["bandwidth_mbit"])
            except (ValueError, KeyError):
                continue
            if r["video_a_kind"] == "real":
                real_s, synth_s = sa, sb
            else:
                real_s, synth_s = sb, sa
            trials.append({
                "game": r["game"],
                "bw": bw,
                "real": real_s,
                "synth": synth_s,
                "pid": r["participant_id"],
                "is_correct": r["is_correct"].strip().lower() == "true",
                "which_real": r["which_real"].strip(),
            })
    return trials


def outcome(t):
    """Classify a trial: correctly distinguished / fooled / couldn't tell."""
    if t["is_correct"]:
        return "correct"
    if t["which_real"] in ("Both", "None"):
        return "couldnt_tell"
    return "fooled"  # pointed at a specific clip, but it was the synthetic one


def load_vmaf(path):
    """(game, bw) -> {AvgVMAF, AvgPSNR, AvgSSIM, AvgLPIPS}"""
    out = {}
    with open(path) as f:
        for r in csv.DictReader(f):
            key = (r["Game"], float(r["Bandwidth"]))
            out[key] = {
                "VMAF": float(r["AvgVMAF"]),
                "PSNR": float(r["AvgPSNR"]),
                "SSIM": float(r["AvgSSIM"]),
                "LPIPS": float(r["AvgLPIPS"]),
            }
    return out


def rescale(mos):
    """1-5 MOS -> [0,1] to align with the objective QoE model range."""
    return (np.asarray(mos, float) - 1.0) / 4.0


def mean_ci(values, conf=0.95):
    v = np.asarray(values, float)
    n = len(v)
    m = v.mean()
    if n < 2:
        return m, 0.0
    sem = v.std(ddof=1) / math.sqrt(n)
    h = sem * stats.t.ppf(0.5 + conf / 2.0, n - 1)
    return m, h


def wilson_ci(k, n, z=1.96):
    """Wilson score interval for a proportion."""
    if n == 0:
        return 0.0, 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return p, max(0.0, center - half), min(1.0, center + half)


def log_fit(bws, ys):
    """Fit y = a*ln(bw)+b; return (a, b, r2, xline, yline)."""
    x = np.log(np.asarray(bws, float))
    y = np.asarray(ys, float)
    a, b = np.polyfit(x, y, 1)
    yhat = a * x + b
    ss_res = np.sum((y - yhat) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    xl = np.linspace(min(bws), max(bws), 100)
    return a, b, r2, xl, a * np.log(xl) + b


# --------------------------------------------------------------------------- #
# Aggregations
# --------------------------------------------------------------------------- #
def agg_by_bw(trials, games=None):
    """bw -> (real_mos_list, synth_mos_list) filtered by games."""
    d = defaultdict(lambda: ([], []))
    for t in trials:
        if games and t["game"] not in games:
            continue
        d[t["bw"]][0].append(t["real"])
        d[t["bw"]][1].append(t["synth"])
    return dict(sorted(d.items()))


# --------------------------------------------------------------------------- #
# FIGURE 1: MOS vs bandwidth (rescaled [0,1]) + logarithmic QoE-law fit
# --------------------------------------------------------------------------- #
def fig1_overall(trials):
    d = agg_by_bw(trials)
    bws = list(d.keys())
    fig, ax = plt.subplots(figsize=(6.2, 4.4))
    for label, col, mk, ls in [("real", C_REAL, "o", "-"),
                               ("synth", C_SYNTH, "s", "--")]:
        means, errs = [], []
        for bw in bws:
            vals = rescale(d[bw][0] if label == "real" else d[bw][1])
            m, h = mean_ci(vals)
            means.append(m)
            errs.append(h)
        a, b, r2, xl, yl = log_fit(bws, means)
        ax.plot(xl, yl, ":", color=col, lw=1.3, alpha=0.6, zorder=2)
        ax.errorbar(bws, means, yerr=errs, color=col, marker=mk, ms=7, lw=2,
                    ls=ls, capsize=3, zorder=3,
                    markeredgecolor="white", markeredgewidth=0.6,
                    label=f"{label.capitalize()}  ($R^2$={r2:.2f})")
    ax.set_xlabel("Bandwidth (Mbit/s)")
    ax.set_ylabel("Subjective QoE  (MOS rescaled to [0,1])")
    ax.set_title("Subjective QoE vs bandwidth — real vs synthetic\n"
                 "(dotted = fitted logarithmic QoE law  $Q=a\\,\\ln b + c$)",
                 fontsize=11)
    ax.set_xticks(bws)
    ax.set_ylim(0, 1)
    ax.legend(loc="lower right", title="mean ± 95% CI")
    save(fig, "fig1_mos_vs_bandwidth_overall")


def _draw_game_panel(ax, trials, game, fs=9):
    """Draw one game's real-vs-synth MOS[0,1] curves + log fits onto ax."""
    d = agg_by_bw(trials, games=[game])
    bws = list(d.keys())
    for label, col, mk, ls in [("real", C_REAL, "o", "-"),
                               ("synth", C_SYNTH, "s", "--")]:
        means, errs = [], []
        for bw in bws:
            vals = rescale(d[bw][0] if label == "real" else d[bw][1])
            m, h = mean_ci(vals)
            means.append(m)
            errs.append(h)
        a, b, r2, xl, yl = log_fit(bws, means)
        ax.plot(xl, yl, ":", color=col, lw=1.2, alpha=0.6, zorder=2)
        ax.errorbar(bws, means, yerr=errs, color=col, marker=mk, ms=6,
                    lw=1.8, ls=ls, capsize=3, zorder=3,
                    markeredgecolor="white", markeredgewidth=0.6,
                    label=f"{label.capitalize()} ($R^2$={r2:.2f})")
    ax.set_title(game, color=GAME_COLOR[game], fontweight="bold")
    ax.set_xlabel("Bandwidth (Mbit/s)")
    ax.set_xticks(bws)
    ax.set_ylim(0, 1)
    ax.legend(loc="lower right", fontsize=fs)


def fig1_per_game(trials):
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2), sharey=True)
    for ax, game in zip(axes, GAMES):
        _draw_game_panel(ax, trials, game)
    axes[0].set_ylabel("Subjective QoE  (MOS → [0,1])")
    fig.suptitle("Subjective QoE vs bandwidth per game — real vs synthetic "
                 "(dotted = logarithmic QoE-law fit)", y=1.02, fontsize=12)
    save(fig, "fig1_mos_vs_bandwidth_per_game")


def fig1_single_games(trials):
    """One standalone figure per game."""
    for game in GAMES:
        fig, ax = plt.subplots(figsize=(6.2, 4.4))
        _draw_game_panel(ax, trials, game, fs=10)
        ax.set_ylabel("Subjective QoE  (MOS rescaled to [0,1])")
        ax.set_title(f"{game} — subjective QoE vs bandwidth (real vs synthetic)\n"
                     "dotted = fitted logarithmic QoE law",
                     color=GAME_COLOR[game], fontweight="bold", fontsize=11)
        save(fig, f"fig1_mos_vs_bandwidth_{game.lower()}")


# --------------------------------------------------------------------------- #
# FIGURE 2: Objective metric vs subjective MOS  (the "map to the model" plot)
# --------------------------------------------------------------------------- #
def _cond_means(trials):
    """(game, bw, kind) -> mean MOS."""
    acc = defaultdict(list)
    for t in trials:
        acc[(t["game"], t["bw"], "real")].append(t["real"])
        acc[(t["game"], t["bw"], "synth")].append(t["synth"])
    return {k: float(np.mean(v)) for k, v in acc.items()}


def _scatter_metric(ax, cond, vmaf_real, vmaf_synth, metric, invert=False):
    xs, ys = [], []
    for (game, bw, kind), mos in cond.items():
        table = vmaf_real if kind == "real" else vmaf_synth
        if (game, bw) not in table:
            continue
        x = table[(game, bw)][metric]
        xs.append(x)
        ys.append(mos)
        ax.scatter(x, mos, color=(C_REAL if kind == "real" else C_SYNTH),
                   marker=GAME_MARKER[game], s=70, alpha=0.9,
                   edgecolors="white", linewidths=0.6, zorder=3)
    xs, ys = np.array(xs), np.array(ys)
    # regression + correlation
    sl, ic, r, p, se = stats.linregress(xs, ys)
    rho, _ = stats.spearmanr(xs, ys)
    xl = np.linspace(xs.min(), xs.max(), 100)
    ax.plot(xl, sl * xl + ic, color=MUTED, lw=1.6, ls="--", zorder=2)
    ax.set_xlabel(f"Objective {metric}" + (" (↓ better)" if invert else ""))
    ax.set_ylabel("Subjective MOS (1–5)")
    ax.set_title(f"{metric}   Pearson r={r:.2f}, "
                 f"Spearman ρ={rho:.2f}, $R^2$={r**2:.2f}",
                 fontsize=10)
    ax.set_ylim(1, 5)


def fig2_objective_vs_subjective(trials, vmaf_real, vmaf_synth):
    cond = _cond_means(trials)
    # main single-panel VMAF figure
    fig, ax = plt.subplots(figsize=(6.4, 4.8))
    _scatter_metric(ax, cond, vmaf_real, vmaf_synth, "VMAF")
    # dual legends: color=kind, marker=game
    kind_handles = [
        plt.Line2D([], [], marker="o", color=C_REAL, ls="", ms=8, label="Real"),
        plt.Line2D([], [], marker="o", color=C_SYNTH, ls="", ms=8, label="Synth"),
    ]
    game_handles = [
        plt.Line2D([], [], marker=GAME_MARKER[g], color=MUTED, ls="", ms=8,
                   label=g) for g in GAMES
    ]
    leg1 = ax.legend(handles=kind_handles, loc="upper left", title="Traffic")
    ax.add_artist(leg1)
    ax.legend(handles=game_handles, loc="lower right", title="Game")
    stats_line = ax.get_title().split("   ", 1)[1]  # drop leading "VMAF"
    ax.set_title("Objective VMAF vs subjective MOS\n" + stats_line, fontsize=11)
    save(fig, "fig2_objective_vs_subjective")

    # 2x2 panel across all objective metrics
    fig, axes = plt.subplots(2, 2, figsize=(11, 8.5))
    for ax, (metric, inv) in zip(
        axes.ravel(), [("VMAF", False), ("PSNR", False),
                       ("SSIM", False), ("LPIPS", True)]):
        _scatter_metric(ax, cond, vmaf_real, vmaf_synth, metric, invert=inv)
    axes[0, 0].legend(handles=kind_handles + game_handles,
                      loc="lower right", fontsize=8, ncol=1)
    fig.suptitle("Objective quality metrics vs subjective MOS "
                 "(each point = game × bandwidth × traffic)",
                 fontsize=12, y=0.995)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    save(fig, "fig2_objective_vs_subjective_all_metrics")


# --------------------------------------------------------------------------- #
# FIGURE 3: Discrimination (Turing-test) accuracy vs bandwidth
# --------------------------------------------------------------------------- #
def fig3_discrimination(trials):
    fig, ax = plt.subplots(figsize=(6.6, 4.6))
    # overall
    by_bw = defaultdict(lambda: [0, 0])  # bw -> [correct, n]
    for t in trials:
        by_bw[t["bw"]][0] += int(t["is_correct"])
        by_bw[t["bw"]][1] += 1
    bws = sorted(by_bw)
    ps, los, his = [], [], []
    for bw in bws:
        k, n = by_bw[bw]
        p, lo, hi = wilson_ci(k, n)
        ps.append(p * 100); los.append((p - lo) * 100); his.append((hi - p) * 100)
    ax.axhline(50, color=MUTED, ls=":", lw=1.4, zorder=1)
    ax.text(bws[-1], 51.5, "chance (50%)", color=MUTED, ha="right", fontsize=9)
    ax.errorbar(bws, ps, yerr=[los, his], color=INK, marker="D", ms=7, lw=2,
                capsize=3, zorder=4, label="All games (95% Wilson CI)")
    # per game (thin lines)
    for game in GAMES:
        g = defaultdict(lambda: [0, 0])
        for t in trials:
            if t["game"] != game:
                continue
            g[t["bw"]][0] += int(t["is_correct"]); g[t["bw"]][1] += 1
        gb = sorted(g)
        gp = [100 * g[bw][0] / g[bw][1] for bw in gb]
        ax.plot(gb, gp, color=GAME_COLOR[game], marker=GAME_MARKER[game],
                ms=5, lw=1.2, alpha=0.8, zorder=3, label=game)
    ax.set_xlabel("Bandwidth (Mbit/s)")
    ax.set_ylabel("Correct real/synth identification (%)")
    ax.set_title("Can participants tell synthetic from real?\n"
                 "Discrimination accuracy near chance → perceptually "
                 "indistinguishable", fontsize=11)
    ax.set_xticks(bws)
    ax.set_ylim(0, 100)
    ax.legend(loc="upper right", fontsize=9)
    save(fig, "fig3_discrimination_accuracy")


# --------------------------------------------------------------------------- #
# FIGURE 7: how often did users correctly distinguish real vs synth?
# --------------------------------------------------------------------------- #
C_CORRECT = "#009E73"   # Okabe-Ito bluish green
C_FOOLED = "#D55E00"    # Okabe-Ito vermillion
C_UNSURE = "#999999"    # neutral gray


def _draw_outcome_breakdown(ax, trials, label_fs=11, val_fs=12, note_fs=10,
                            axlabel_fs=11, tick_fs=11, title_fs=12):
    """Panel A: overall correct / fooled / couldn't-tell breakdown."""
    n = len(trials)
    counts = {k: sum(outcome(t) == k for t in trials)
              for k in ("correct", "fooled", "couldnt_tell")}
    cats = [
        ("correct", "Correctly identified\nthe real clip", C_CORRECT, "//"),
        ("fooled", "Fooled — chose the\nsynthetic clip as real", C_FOOLED, "xx"),
        ("couldnt_tell", 'Could not tell\n("Both" / "None")', C_UNSURE, ".."),
    ]
    ypos = np.arange(len(cats))[::-1]
    for y, (key, _label, col, hatch) in zip(ypos, cats):
        pct = 100 * counts[key] / n
        ax.barh(y, pct, color=col, edgecolor="black", linewidth=1.0,
                hatch=hatch, height=0.62, zorder=3)
        ax.text(pct + 1.5, y, f"{pct:.1f}%  ({counts[key]}/{n})",
                va="center", ha="left", fontsize=val_fs, color=INK)
    ax.axvline(50, color=INK, ls="--", lw=1.4, zorder=2)
    ax.text(51, -0.42, "50% chance", va="bottom", ha="left",
            fontsize=note_fs, color=MUTED)
    ax.set_yticks(ypos)
    ax.set_yticklabels([c[1] for c in cats], fontsize=label_fs)
    ax.set_xlim(0, 100)
    ax.set_xlabel(f"Share of all {n} trials (%)", fontsize=axlabel_fs)
    ax.tick_params(axis="x", labelsize=tick_fs)
    ax.grid(True, axis="x", color=GRID, lw=0.8)
    ax.set_title("How often did participants correctly\n"
                 "distinguish real from synthetic?", fontsize=title_fs,
                 fontweight="bold")
    return counts


def _draw_participant_accuracy(ax, trials):
    """Panel B: per-participant accuracy vs the 50% chance line."""
    pp = defaultdict(lambda: [0, 0])
    for t in trials:
        pp[t["pid"]][0] += int(t["is_correct"])
        pp[t["pid"]][1] += 1
    accs = sorted(100 * c / tot for c, tot in pp.values())
    y = np.arange(len(accs))
    colors = [C_CORRECT if a > 50 else C_FOOLED for a in accs]
    hatches = ["//" if a > 50 else "xx" for a in accs]
    for yi, a, col, h in zip(y, accs, colors, hatches):
        ax.barh(yi, a, color=col, edgecolor="black", linewidth=0.8,
                hatch=h, height=0.72, zorder=3)
    ax.axvline(50, color=INK, ls="--", lw=1.4, zorder=2)
    n_above = sum(a > 50 for a in accs)
    ax.text(51, -1.1, "50% chance", va="bottom", ha="left",
            fontsize=10, color=MUTED)
    ax.set_yticks([])
    ax.set_ylabel(f"{len(accs)} participants (sorted)")
    ax.set_xlim(0, 100)
    ax.set_xlabel("Per-participant identification accuracy (%)")
    ax.grid(True, axis="x", color=GRID, lw=0.8)
    ax.set_title(f"Only {n_above} of {len(accs)} participants\n"
                 "beat chance", fontsize=12, fontweight="bold")
    return n_above, len(accs)


def fig7_distinguishability(trials):
    fig, (axL, axR) = plt.subplots(
        1, 2, figsize=(13, 5.0), gridspec_kw={"width_ratios": [1.05, 1.0]})
    counts = _draw_outcome_breakdown(axL, trials)
    _draw_participant_accuracy(axR, trials)
    overall = 100 * counts["correct"] / len(trials)
    fig.suptitle(
        f"Real-vs-synthetic discrimination: {overall:.1f}% of trials correctly "
        f"identified — below the 50% chance line",
        fontsize=13, y=1.02)
    fig.tight_layout()
    save(fig, "fig7_distinguishability")


def fig7a_outcome_breakdown(trials):
    # larger fonts — intended for a small single-column figure in the paper
    fig, ax = plt.subplots(figsize=(7.4, 4.8))
    _draw_outcome_breakdown(ax, trials, label_fs=17, val_fs=17, note_fs=15,
                            axlabel_fs=18, tick_fs=16, title_fs=18)
    fig.tight_layout()
    save(fig, "fig7a_outcome_breakdown")


def fig7b_participant_accuracy(trials):
    fig, ax = plt.subplots(figsize=(7.0, 4.6))
    _draw_participant_accuracy(ax, trials)
    fig.tight_layout()
    save(fig, "fig7b_participant_accuracy")


# --------------------------------------------------------------------------- #
# FIGURE 4: real - synth MOS gap per condition
# --------------------------------------------------------------------------- #
def fig4_gap(trials):
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    width = 0.25
    bws = sorted({t["bw"] for t in trials})
    x = np.arange(len(bws))
    for i, game in enumerate(GAMES):
        gaps = []
        for bw in bws:
            reals = [t["real"] for t in trials if t["game"] == game and t["bw"] == bw]
            synths = [t["synth"] for t in trials if t["game"] == game and t["bw"] == bw]
            gaps.append(np.mean(synths) - np.mean(reals) if reals else 0.0)
        ax.bar(x + (i - 1) * width, gaps, width, color=GAME_COLOR[game],
               label=game, edgecolor="black", linewidth=1.0,
               hatch=GAME_HATCH[game])
    ax.axhline(0, color=INK, lw=1)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{int(b)}" for b in bws])
    ax.set_xlabel("Bandwidth (Mbit/s)")
    ax.set_ylabel("Mean MOS gap  (synth − real)")
    ax.set_title("Synthetic–real MOS deviation per condition\n"
                 "(near zero → synthetic preserves perceived quality)",
                 fontsize=11)
    ax.legend(title="Game")
    save(fig, "fig4_real_synth_mos_gap")


# --------------------------------------------------------------------------- #
# FIGURE 5: rating distribution (diverging 1-5) real vs synth
# --------------------------------------------------------------------------- #
def fig5_rating_distribution(trials):
    # sequential blues for the 5 ordinal categories
    cmap = plt.cm.Blues(np.linspace(0.30, 0.95, 5))
    fig, ax = plt.subplots(figsize=(7.6, 3.4))
    groups = [("Real", [t["real"] for t in trials]),
              ("Synth", [t["synth"] for t in trials])]
    for row, (label, scores) in enumerate(groups):
        n = len(scores)
        counts = np.array([scores.count(s) for s in range(1, 6)], float)
        props = counts / n * 100
        # diverging: center between rating 3
        left = -(props[0] + props[1] + props[2] / 2)
        start = left
        for s in range(5):
            ax.barh(row, props[s], left=start, color=cmap[s],
                    edgecolor="white", height=0.62)
            if props[s] > 6:
                ax.text(start + props[s] / 2, row, f"{props[s]:.0f}",
                        ha="center", va="center", fontsize=9,
                        color="white" if s >= 3 else INK)
            start += props[s]
    ax.axvline(0, color=INK, lw=1)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["Real", "Synth"])
    ax.set_xlabel("Share of ratings (%)  ← lower quality | higher quality →")
    ax.set_title("Distribution of 1–5 quality ratings", fontsize=11)
    handles = [plt.Rectangle((0, 0), 1, 1, color=cmap[s]) for s in range(5)]
    ax.legend(handles, [f"{s}" for s in range(1, 6)], title="Rating",
              ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.30),
              fontsize=9)
    ax.grid(False)
    ax.spines["left"].set_visible(False)
    save(fig, "fig5_rating_distribution")


# --------------------------------------------------------------------------- #
# FIGURE 6: which_real composition per bandwidth
# --------------------------------------------------------------------------- #
def fig6_which_real(trials):
    cats = ["Video A", "Video B", "Both", "None"]
    catcol = {"Video A": "#4C78A8", "Video B": "#F58518",
              "Both": "#999999", "None": "#CCCCCC"}
    cathatch = {"Video A": "", "Video B": "//", "Both": "xx", "None": ".."}
    bws = sorted({t["bw"] for t in trials})
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    bottom = np.zeros(len(bws))
    for cat in cats:
        vals = []
        for bw in bws:
            sub = [t for t in trials if t["bw"] == bw]
            n = len(sub)
            k = sum(1 for t in sub if t["which_real"] == cat)
            vals.append(100 * k / n if n else 0)
        vals = np.array(vals)
        ax.bar([str(int(b)) for b in bws], vals, bottom=bottom,
               color=catcol[cat], label=cat, edgecolor="black", linewidth=0.8,
               hatch=cathatch[cat])
        bottom += vals
    ax.set_xlabel("Bandwidth (Mbit/s)")
    ax.set_ylabel("Response share (%)")
    ax.set_title('"Which video is real?" response composition\n'
                 '(more "Both"/"None" → harder to distinguish)', fontsize=11)
    ax.set_ylim(0, 100)
    ax.legend(title="Answer", loc="upper center",
              bbox_to_anchor=(0.5, -0.16), ncol=4, fontsize=9)
    ax.grid(axis="x")
    save(fig, "fig6_which_real_composition")


# --------------------------------------------------------------------------- #
def main():
    trials = load_trials()
    vmaf_real = load_vmaf(VMAF_REAL)
    vmaf_synth = load_vmaf(VMAF_SYNTH)
    print(f"Loaded {len(trials)} trials, "
          f"{len(vmaf_real)} real / {len(vmaf_synth)} synth VMAF conditions")
    print("Generating figures ->", OUT)
    fig1_overall(trials)
    fig1_per_game(trials)
    fig1_single_games(trials)
    fig2_objective_vs_subjective(trials, vmaf_real, vmaf_synth)
    fig3_discrimination(trials)
    fig7_distinguishability(trials)
    fig7a_outcome_breakdown(trials)
    fig7b_participant_accuracy(trials)
    fig4_gap(trials)
    fig5_rating_distribution(trials)
    fig6_which_real(trials)
    print("Done.")


if __name__ == "__main__":
    main()
