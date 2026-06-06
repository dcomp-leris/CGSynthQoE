#!/usr/bin/env python3
"""
CGReplay QoE plots — 3 comparative figures.

Run from CGReplay/ root after running post_process.py for each mode:
    python3 tools/plot_qoe.py

Outputs (saved to player/logs/):
    fig1_ssim.png       — Video quality (SSIM) vs time
    fig2_rt.png         — Response time (ms) vs time
    fig3_qoe.png        — QoE vs time
"""

import os
import sys
import pandas as pd
import matplotlib
matplotlib.use("Agg")   # non-interactive backend (works without DISPLAY)
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

LOGS_DIR  = os.path.join("player", "logs")
MODES     = ["quic", "rtp", "scream"]
COLORS    = {"quic": "#1f77b4", "rtp": "#ff7f0e", "scream": "#2ca02c"}
LABELS    = {"quic": "QUIC", "rtp": "Pure UDP (RTP)", "scream": "SCReAM"}

FIG_DPI   = 300
FIG_SIZE  = (8, 4)


def load(mode: str) -> pd.DataFrame | None:
    path = os.path.join(LOGS_DIR, f"metrics_{mode}.csv")
    if not os.path.exists(path):
        print(f"  [skip] {path} not found")
        return None
    return pd.read_csv(path)


def styled_ax(ax, ylabel: str, title: str):
    ax.set_xlabel("Time (s)", fontsize=11)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.legend(fontsize=10)
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    plt.tight_layout()


def plot_figure(col: str, ylabel: str, title: str, filename: str,
                ylim=None, smooth_window: int = 3):
    fig, ax = plt.subplots(figsize=FIG_SIZE)
    plotted = False
    for mode in MODES:
        df = load(mode)
        if df is None or col not in df.columns:
            continue
        y = df[col].rolling(smooth_window, min_periods=1, center=True).mean()
        ax.plot(df["second"], y,
                color=COLORS[mode], label=LABELS[mode], linewidth=1.8)
        plotted = True
    if not plotted:
        print(f"  [skip] no data for {col}")
        plt.close()
        return
    if ylim:
        ax.set_ylim(*ylim)
    styled_ax(ax, ylabel, title)
    out = os.path.join(LOGS_DIR, filename)
    fig.savefig(out, dpi=FIG_DPI, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out}")


if __name__ == "__main__":
    print("[plot_qoe] Generating figures ...")

    plot_figure(
        col="SSIM",
        ylabel="Video Quality (SSIM)",
        title="Fig. 1 — Video Quality vs Time",
        filename="fig1_ssim.png",
        ylim=(0, 1),
    )

    plot_figure(
        col="response_time_ms",
        ylabel="Response Time (ms)",
        title="Fig. 2 — Response Time vs Time",
        filename="fig2_rt.png",
    )

    plot_figure(
        col="QoE",
        ylabel="QoE  [SSIM × FPS / FPS_target]",
        title="Fig. 3 — QoE vs Time",
        filename="fig3_qoe.png",
        ylim=(0, 1),
    )

    print("[plot_qoe] Done.")
