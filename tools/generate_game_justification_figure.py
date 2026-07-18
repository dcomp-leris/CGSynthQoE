#!/usr/bin/env python3
"""
Multi-panel justification figure for CGSynth game selection.

Three panels showing encoding complexity diversity across Fortnite, Forza, Kombat:
  (a) VMAF   vs bandwidth  (objective quality, higher = better)
  (b) LPIPS  vs bandwidth  (perceptual quality, lower = better)
  (c) SSIM   vs bandwidth  (structural quality, higher = better)
"""

import os
import csv
import numpy as np
import matplotlib.pyplot as plt

REPO_ROOT = "/home/ariel/git/CGSynth"
GAMES = ["Fortnite", "Forza", "Kombat"]
BW_VALUES = [2, 4, 6, 8, 10]

C = {"Fortnite": "#3E9BDD", "Forza": "#20CA06", "Kombat": "#F00505"}
M = {"Fortnite": "o", "Forza": "s", "Kombat": "D"}
L = {"Fortnite": "Fortnite (shooter)", "Forza": "Forza Horizon 5 (racing)", "Kombat": "Mortal Kombat 11 (combat)"}


def load_metrics():
    path = os.path.join(REPO_ROOT, "acm_tomm_experiments", "processed_data", "vmaf_metrics_real.csv")
    data = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            g = row["Game"]
            b = int(row["BitrateLabel"].split("_")[0].replace("Mbit", ""))
            data[(g, b)] = {
                "vmaf": float(row["AvgVMAF"]),
                "lpips": float(row["AvgLPIPS"]),
                "ssim": float(row["AvgSSIM"]),
            }
    return data


def main():
    d = load_metrics()

    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))

    panels = [
        (0, "vmaf",  "VMAF Score",          (0, 100), "(a) Objective Quality (VMAF)"),
        (1, "lpips", "LPIPS (lower=better)",  None,     "(b) Perceptual Quality (LPIPS)"),
        (2, "ssim",  "SSIM",                 (0, 1),   "(c) Structural Quality (SSIM)"),
    ]

    for idx, key, ylabel, ylim, title in panels:
        ax = axes[idx]
        for game in GAMES:
            xs, ys = [], []
            for bw in BW_VALUES:
                k = (game, bw)
                if k in d:
                    xs.append(bw)
                    ys.append(d[k][key])
            if xs:
                ax.plot(xs, ys, marker=M[game], color=C[game],
                        linewidth=2.2, markersize=9, label=L[game])
        ax.set_xlabel("Bandwidth (Mbps)", fontsize=14)
        ax.set_ylabel(ylabel, fontsize=14)
        if ylim:
            ax.set_ylim(*ylim)
        ax.set_title(title, fontsize=15, fontweight="bold")
        ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.6)
        ax.tick_params(labelsize=12)
        ax.legend(fontsize=9, frameon=True, edgecolor="black",
                  facecolor="white", framealpha=1)

    fig.tight_layout()

    out_dir = os.path.join(REPO_ROOT, "acm_tomm_experiments", "new_graphs")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "game_justification_multipanel.pdf")
    fig.savefig(out_path, dpi=150)
    print(f"Saved: {out_path}")
    plt.close(fig)


if __name__ == "__main__":
    main()
