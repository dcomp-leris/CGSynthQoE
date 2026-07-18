#!/usr/bin/env python3
"""
Game Interaction-Throughput Scatter Plot
Scatter plot showing average input rate vs average downstream bitrate
across different cloud gaming sessions.

Uses:
  - ratelog_CG.csv for input rate (cps = commands per second)
  - PCAP files for downstream throughput (via pcap_throughput_analyzer)
"""

import os
import sys
import argparse
import csv
import numpy as np
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pcap_throughput_analyzer import analyze_pcap_throughput

GAME_MARKERS = {"Fortnite": "o", "Forza": "s", "Kombat": "D"}
GAME_COLORS = {"Fortnite": "#3E9BDD", "Forza": "#20CA06", "Kombat": "#F00505"}
GAME_NAMES = {"Fortnite": "Fortnite", "Forza": "Forza Horizon 5", "Kombat": "Mortal Kombat 11"}


def extract_avg_cps(repo_root: str) -> Dict[Tuple, float]:
    real_root = os.path.join(repo_root, "acm_tomm_experiments", "reference_vs_real")
    games = ["Fortnite", "Forza", "Kombat"]
    bandwidths = ["2Mbit", "4Mbit", "6Mbit", "8Mbit", "10Mbit"]

    result = {}

    for game in games:
        for bw in bandwidths:
            bitrate_label = f"{bw}_{game}"
            ratelog_path = os.path.join(real_root, game, bitrate_label, "logs", "ratelog_CG.csv")

            if not os.path.exists(ratelog_path):
                print(f"[WARN] No ratelog: {game} @ {bw}")
                continue

            seen = {}
            with open(ratelog_path, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        fid = row['frame_id']
                        cps = float(row['cps'])
                        if fid not in seen:
                            seen[fid] = cps
                    except (ValueError, KeyError):
                        continue

            if seen:
                first_cps = list(seen.values())
                avg_cps = np.mean(first_cps)
                result[(game, bw)] = avg_cps
                dup = len(first_cps)
                print(f"  {game:10s} @ {bw:7s}:  avg cps = {avg_cps:.2f}  (n={dup} unique)")

    return result


def extract_throughput(repo_root: str) -> Dict[Tuple, float]:
    real_root = os.path.join(repo_root, "acm_tomm_experiments", "reference_vs_real")
    games = ["Fortnite", "Forza", "Kombat"]
    bandwidths = ["2Mbit", "4Mbit", "6Mbit", "8Mbit", "10Mbit"]

    result = {}

    for game in games:
        for bw in bandwidths:
            bitrate_label = f"{bw}_{game}"
            pcap_path = os.path.join(real_root, game, bitrate_label, "output.pcap")

            if not os.path.exists(pcap_path):
                print(f"[WARN] No PCAP: {game} @ {bw}")
                continue

            data = analyze_pcap_throughput(pcap_path)
            if data:
                tput = data.get('rtp_throughput_mbps') or data.get('udp_throughput_mbps')
                if tput is not None:
                    result[(game, bw)] = tput

    return result


def generate_scatter_plot(
    interaction_data: Dict[Tuple, float],
    throughput_data: Dict[Tuple, float],
    repo_root: str,
    output_suffix: str = "_real",
) -> str:
    games = ["Fortnite", "Forza", "Kombat"]

    data_points = []
    for game in games:
        for bw in ["2Mbit", "4Mbit", "6Mbit", "8Mbit", "10Mbit"]:
            key = (game, bw)
            if key in interaction_data and key in throughput_data:
                data_points.append({
                    'game': game,
                    'bw': bw,
                    'bw_mbps': int(bw.replace("Mbit", "")),
                    'avg_cps': interaction_data[key],
                    'throughput_mbps': throughput_data[key],
                })

    if not data_points:
        print("[ERROR] No overlapping data points")
        return ""

    fig, ax = plt.subplots(figsize=(10, 7))

    for game in games:
        game_points = [d for d in data_points if d['game'] == game]
        if not game_points:
            continue

        x_vals = [d['avg_cps'] for d in game_points]
        y_vals = [d['throughput_mbps'] for d in game_points]
        bw_labels = [f"{d['bw_mbps']}M" for d in game_points]

        ax.scatter(
            x_vals, y_vals,
            marker=GAME_MARKERS[game],
            color=GAME_COLORS[game],
            s=200,
            edgecolors='black',
            linewidths=1.2,
            label=game,
            zorder=5,
        )

        for x, y, label in zip(x_vals, y_vals, bw_labels):
            ax.annotate(
                label,
                (x, y),
                textcoords="offset points",
                xytext=(8, 6),
                fontsize=10,
                alpha=0.7,
            )

    ax.set_xlabel("Average Input Rate (commands/s)", fontsize=18)
    ax.set_ylabel("Average Downstream Throughput (Mbps)", fontsize=18)
    ax.tick_params(axis='both', labelsize=14)
    ax.grid(True, linestyle='--', linewidth=0.5, alpha=0.6)
    ax.legend(fontsize=14, frameon=True, edgecolor='black', facecolor='white', framealpha=1)

    # Add headroom
    all_x = [d['avg_cps'] for d in data_points]
    all_y = [d['throughput_mbps'] for d in data_points]
    x_pad = (max(all_x) - min(all_x)) * 0.15
    y_pad = (max(all_y) - min(all_y)) * 0.15
    ax.set_xlim(min(all_x) - x_pad, max(all_x) + x_pad)
    ax.set_ylim(0, max(all_y) + y_pad)

    fig.tight_layout()

    graph_dir = os.path.join(repo_root, "acm_tomm_experiments", "new_graphs")
    os.makedirs(graph_dir, exist_ok=True)
    out_path = os.path.join(graph_dir, f"interaction_throughput_scatter{output_suffix}.pdf")
    fig.savefig(out_path, dpi=150)
    print(f"\n[INFO] Saved to {out_path}")
    plt.close(fig)

    return out_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate interaction-throughput scatter plot for real cloud gaming sessions"
    )
    parser.add_argument("--repo-root", default="/home/ariel/git/CGSynth",
                        help="Repository root path")
    parser.add_argument("--throughput-csv",
                        help="Pre-computed throughput CSV from pcap_throughput_analyzer.py")
    args = parser.parse_args()

    repo_root = args.repo_root

    print("=== Extracting average input rate (cps) from ratelog_CG.csv ===")
    interaction_data = extract_avg_cps(repo_root)

    if args.throughput_csv and os.path.exists(args.throughput_csv):
        print(f"\n=== Loading throughput from {args.throughput_csv} ===")
        throughput_data = {}
        with open(args.throughput_csv, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                game = row['game']
                bw = row['bitrate_label'].split('_')[0]
                tput = float(row['rtp_throughput_mbps'])
                throughput_data[(game, bw)] = tput
        for (game, bw), tput in sorted(throughput_data.items()):
            print(f"  {game:10s} @ {bw:7s}:  {tput:.2f} Mbps")
    else:
        print("\n=== Extracting average throughput from PCAP files ===")
        throughput_data = extract_throughput(repo_root)

    print(f"\n=== Generating scatter plot ({len(interaction_data)} cps points x "
          f"{len(throughput_data)} throughput points) ===")

    out_path = generate_scatter_plot(interaction_data, throughput_data, repo_root)

    if out_path:
        print(f"\nDone. Figure: {out_path}")
        print("\nData summary:")
        print(f"  {'Game':12s} {'BW':>6s}  {'CPS (input/s)':>14s}  {'Throughput (Mbps)':>18s}")
        print(f"  {'-'*12} {'-'*6}  {'-'*14}  {'-'*18}")
        games = ["Fortnite", "Forza", "Kombat"]
        for game in games:
            for bw in ["2Mbit", "4Mbit", "6Mbit", "8Mbit", "10Mbit"]:
                key = (game, bw)
                if key in interaction_data and key in throughput_data:
                    print(f"  {game:12s} {bw:>6s}  {interaction_data[key]:14.2f}  {throughput_data[key]:18.2f}")


if __name__ == "__main__":
    main()
