#!/usr/bin/env python3

import os
import sys
import argparse
import numpy as np
import matplotlib.pyplot as plt
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vmaf_scatter import (
    load_metrics_cache,
    parse_bandwidth_from_label,
    compute_vsmooth_from_qoe_logs,
    compute_csmooth_from_qoe_logs,
    compute_qdelay,
    compute_qint_from_components,
    compute_mean_rt_from_logs,
    compute_mean_video_delay_from_qoe_logs,
)

GAME_COLORS = {
    "Fortnite": {"real": "#BEDDF7", "synth": "#3E9BDD"},
    "Forza":    {"real": "#BEEBB3", "synth": "#20CA06"},
    "Kombat":   {"real": "#FCA7A7", "synth": "#F00505"},
}


def get_game_color(series_label: str) -> str:
    parts = series_label.rsplit(" ", 1)
    if len(parts) == 2:
        game, exp_type = parts
        if game in GAME_COLORS:
            return GAME_COLORS[game][exp_type.lower()]
    return "#CCCCCC"


GAME_HATCHES = {
    "Fortnite": "",
    "Forza": "//",
    "Kombat": "xx",
}


def get_hatch(series_label: str) -> str:
    parts = series_label.rsplit(" ", 1)
    if len(parts) == 2:
        game = parts[0]
        return GAME_HATCHES.get(game, "")
    return ""


def plot_vmaf_real_vs_synth(
    repo_root: str,
    games: List[str],
    bandwidths: List[str],
    labels: List[str],
    real_cache: Dict[tuple, Dict],
    synth_cache: Dict[tuple, Dict],
    output_suffix: str = "_real_vs_synth",
) -> None:
    series_rows = []
    for game in games:
        for bandwidth_base, label in zip(bandwidths, labels):
            bitrate_label = f"{bandwidth_base}_{game}"
            key = (game, bitrate_label)
            target_bw = parse_bandwidth_from_label(bandwidth_base, label)

            if key in real_cache:
                data = real_cache[key]
                bw_value = target_bw if target_bw is not None else data.get("bandwidth", 0)
                series_rows.append({
                    "series": f"{game} Real",
                    "bandwidth": bw_value,
                    "vmaf": data.get("avg_vmaf", 0),
                })

            if key in synth_cache:
                data = synth_cache[key]
                bw_value = target_bw if target_bw is not None else data.get("bandwidth", 0)
                series_rows.append({
                    "series": f"{game} Synth",
                    "bandwidth": bw_value,
                    "vmaf": data.get("avg_vmaf", 0),
                })

    if not series_rows:
        print("[WARN] No data for VMAF summary plot.")
        return

    sorted_bandwidths = sorted(set(r["bandwidth"] for r in series_rows))
    series_labels = sorted(set(r["series"] for r in series_rows))

    x_positions = np.arange(len(sorted_bandwidths))
    n_series = max(len(series_labels), 1)
    bar_width = 0.8 / n_series

    graph_dir = os.path.join(repo_root, "acm_tomm_experiments", "new_graphs")
    os.makedirs(graph_dir, exist_ok=True)
    safe_games = "_".join(games)

    fig, ax = plt.subplots(figsize=(8, 5))

    metric_max = 0.0

    for si, series in enumerate(series_labels):
        rows = [r for r in series_rows if r["series"] == series]
        positions = []
        values = []
        for bw in sorted_bandwidths:
            matching = [r for r in rows if r["bandwidth"] == bw]
            if matching:
                positions.append(x_positions[sorted_bandwidths.index(bw)] + si * bar_width)
                values.append(matching[0]["vmaf"])

        if not positions:
            continue

        local_max = max(values)
        if local_max > metric_max:
            metric_max = local_max

        ax.bar(
            positions, values, bar_width,
            label=series, edgecolor="black", linewidth=0.9,
            color=get_game_color(series), hatch=get_hatch(series),
        )

    ax.set_xlabel("Bandwidth (Mbps)", fontsize=22)
    ax.set_ylabel("VMAF Score", fontsize=22)
    ax.set_xticks(x_positions + bar_width * n_series / 2)
    ax.set_xticklabels([f"{bw:.0f}" for bw in sorted_bandwidths])
    ax.tick_params(axis="both", labelsize=20)

    upper = 110
    ax.set_ylim(0, upper)
    ax.set_axisbelow(True)
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.7, zorder=0)
    ax.legend(fontsize=14, frameon=True, edgecolor="black", ncol=3, loc="upper right", facecolor="white", framealpha=1)

    fig.tight_layout()
    out_path = os.path.join(graph_dir, f"vmaf_summary_{safe_games}{output_suffix}.pdf")
    fig.savefig(out_path, dpi=150)
    print(f"Saved VMAF Score Real vs Synth summary plot to: {out_path}")
    plt.close(fig)


def plot_psnr_real_vs_synth(
    repo_root: str,
    games: List[str],
    bandwidths: List[str],
    labels: List[str],
    real_cache: Dict[tuple, Dict],
    synth_cache: Dict[tuple, Dict],
    output_suffix: str = "_real_vs_synth",
) -> None:
    series_rows = []
    for game in games:
        for bandwidth_base, label in zip(bandwidths, labels):
            bitrate_label = f"{bandwidth_base}_{game}"
            key = (game, bitrate_label)
            target_bw = parse_bandwidth_from_label(bandwidth_base, label)

            if key in real_cache:
                data = real_cache[key]
                bw_value = target_bw if target_bw is not None else data.get("bandwidth", 0)
                series_rows.append({
                    "series": f"{game} Real",
                    "bandwidth": bw_value,
                    "psnr": data.get("avg_psnr", 0),
                })

            if key in synth_cache:
                data = synth_cache[key]
                bw_value = target_bw if target_bw is not None else data.get("bandwidth", 0)
                series_rows.append({
                    "series": f"{game} Synth",
                    "bandwidth": bw_value,
                    "psnr": data.get("avg_psnr", 0),
                })

    if not series_rows:
        print("[WARN] No data for PSNR summary plot.")
        return

    sorted_bandwidths = sorted(set(r["bandwidth"] for r in series_rows))
    series_labels = sorted(set(r["series"] for r in series_rows))

    x_positions = np.arange(len(sorted_bandwidths))
    n_series = max(len(series_labels), 1)
    bar_width = 0.8 / n_series

    graph_dir = os.path.join(repo_root, "acm_tomm_experiments", "new_graphs")
    os.makedirs(graph_dir, exist_ok=True)
    safe_games = "_".join(games)

    fig, ax = plt.subplots(figsize=(8, 5))

    metric_max = 0.0

    for si, series in enumerate(series_labels):
        rows = [r for r in series_rows if r["series"] == series]
        positions = []
        values = []
        for bw in sorted_bandwidths:
            matching = [r for r in rows if r["bandwidth"] == bw]
            if matching:
                positions.append(x_positions[sorted_bandwidths.index(bw)] + si * bar_width)
                values.append(matching[0]["psnr"])

        if not positions:
            continue

        local_max = max(values)
        if local_max > metric_max:
            metric_max = local_max

        ax.bar(
            positions, values, bar_width,
            label=series, edgecolor="black", linewidth=0.9,
            color=get_game_color(series), hatch=get_hatch(series),
        )

    ax.set_xlabel("Bandwidth (Mbps)", fontsize=22)
    ax.set_ylabel("PSNR (dB)", fontsize=22)
    ax.set_xticks(x_positions + bar_width * n_series / 2)
    ax.set_xticklabels([f"{bw:.0f}" for bw in sorted_bandwidths])
    ax.tick_params(axis="both", labelsize=20)

    upper = max(20, metric_max * 1.1) if metric_max > 0 else 20
    ax.set_ylim(0, upper)
    ax.set_axisbelow(True)
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.7, zorder=0)
    ax.legend(fontsize=14, frameon=True, edgecolor="black", ncol=3, loc="lower right", facecolor="white", framealpha=1)

    fig.tight_layout()
    out_path = os.path.join(graph_dir, f"psnr_summary_{safe_games}{output_suffix}.pdf")
    fig.savefig(out_path, dpi=150)
    print(f"Saved PSNR (dB) Real vs Synth summary plot to: {out_path}")
    plt.close(fig)


def plot_ssim_real_vs_synth(
    repo_root: str,
    games: List[str],
    bandwidths: List[str],
    labels: List[str],
    real_cache: Dict[tuple, Dict],
    synth_cache: Dict[tuple, Dict],
    output_suffix: str = "_real_vs_synth",
) -> None:
    series_rows = []
    for game in games:
        for bandwidth_base, label in zip(bandwidths, labels):
            bitrate_label = f"{bandwidth_base}_{game}"
            key = (game, bitrate_label)
            target_bw = parse_bandwidth_from_label(bandwidth_base, label)

            if key in real_cache:
                data = real_cache[key]
                bw_value = target_bw if target_bw is not None else data.get("bandwidth", 0)
                series_rows.append({
                    "series": f"{game} Real",
                    "bandwidth": bw_value,
                    "ssim": data.get("avg_ssim", 0),
                })

            if key in synth_cache:
                data = synth_cache[key]
                bw_value = target_bw if target_bw is not None else data.get("bandwidth", 0)
                series_rows.append({
                    "series": f"{game} Synth",
                    "bandwidth": bw_value,
                    "ssim": data.get("avg_ssim", 0),
                })

    if not series_rows:
        print("[WARN] No data for SSIM summary plot.")
        return

    sorted_bandwidths = sorted(set(r["bandwidth"] for r in series_rows))
    series_labels = sorted(set(r["series"] for r in series_rows))

    x_positions = np.arange(len(sorted_bandwidths))
    n_series = max(len(series_labels), 1)
    bar_width = 0.8 / n_series

    graph_dir = os.path.join(repo_root, "acm_tomm_experiments", "new_graphs")
    os.makedirs(graph_dir, exist_ok=True)
    safe_games = "_".join(games)

    fig, ax = plt.subplots(figsize=(8, 5))

    metric_max = 0.0

    for si, series in enumerate(series_labels):
        rows = [r for r in series_rows if r["series"] == series]
        positions = []
        values = []
        for bw in sorted_bandwidths:
            matching = [r for r in rows if r["bandwidth"] == bw]
            if matching:
                positions.append(x_positions[sorted_bandwidths.index(bw)] + si * bar_width)
                values.append(matching[0]["ssim"])

        if not positions:
            continue

        local_max = max(values)
        if local_max > metric_max:
            metric_max = local_max

        ax.bar(
            positions, values, bar_width,
            label=series, edgecolor="black", linewidth=0.9,
            color=get_game_color(series), hatch=get_hatch(series),
        )

    ax.set_xlabel("Bandwidth (Mbps)", fontsize=22)
    ax.set_ylabel("SSIM", fontsize=22)
    ax.set_xticks(x_positions + bar_width * n_series / 2)
    ax.set_xticklabels([f"{bw:.0f}" for bw in sorted_bandwidths])
    ax.tick_params(axis="both", labelsize=20)

    upper = max(1, metric_max * 1.1) if metric_max > 0 else 1
    ax.set_ylim(0, upper)
    ax.set_axisbelow(True)
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.7, zorder=0)
    ax.legend(fontsize=14, frameon=True, edgecolor="black", ncol=3, loc="lower right", facecolor="white", framealpha=1)

    fig.tight_layout()
    out_path = os.path.join(graph_dir, f"ssim_summary_{safe_games}{output_suffix}.pdf")
    fig.savefig(out_path, dpi=150)
    print(f"Saved SSIM Real vs Synth summary plot to: {out_path}")
    plt.close(fig)


def plot_lpips_real_vs_synth(
    repo_root: str,
    games: List[str],
    bandwidths: List[str],
    labels: List[str],
    real_cache: Dict[tuple, Dict],
    synth_cache: Dict[tuple, Dict],
    output_suffix: str = "_real_vs_synth",
) -> None:
    series_rows = []
    for game in games:
        for bandwidth_base, label in zip(bandwidths, labels):
            bitrate_label = f"{bandwidth_base}_{game}"
            key = (game, bitrate_label)
            target_bw = parse_bandwidth_from_label(bandwidth_base, label)

            if key in real_cache:
                data = real_cache[key]
                bw_value = target_bw if target_bw is not None else data.get("bandwidth", 0)
                series_rows.append({
                    "series": f"{game} Real",
                    "bandwidth": bw_value,
                    "lpips": data.get("avg_lpips", 0),
                })

            if key in synth_cache:
                data = synth_cache[key]
                bw_value = target_bw if target_bw is not None else data.get("bandwidth", 0)
                series_rows.append({
                    "series": f"{game} Synth",
                    "bandwidth": bw_value,
                    "lpips": data.get("avg_lpips", 0),
                })

    if not series_rows:
        print("[WARN] No data for LPIPS summary plot.")
        return

    sorted_bandwidths = sorted(set(r["bandwidth"] for r in series_rows))
    series_labels = sorted(set(r["series"] for r in series_rows))

    x_positions = np.arange(len(sorted_bandwidths))
    n_series = max(len(series_labels), 1)
    bar_width = 0.8 / n_series

    graph_dir = os.path.join(repo_root, "acm_tomm_experiments", "new_graphs")
    os.makedirs(graph_dir, exist_ok=True)
    safe_games = "_".join(games)

    fig, ax = plt.subplots(figsize=(8, 5))

    metric_max = 0.0

    for si, series in enumerate(series_labels):
        rows = [r for r in series_rows if r["series"] == series]
        positions = []
        values = []
        for bw in sorted_bandwidths:
            matching = [r for r in rows if r["bandwidth"] == bw]
            if matching:
                positions.append(x_positions[sorted_bandwidths.index(bw)] + si * bar_width)
                values.append(matching[0]["lpips"])

        if not positions:
            continue

        local_max = max(values)
        if local_max > metric_max:
            metric_max = local_max

        ax.bar(
            positions, values, bar_width,
            label=series, edgecolor="black", linewidth=0.9,
            color=get_game_color(series), hatch=get_hatch(series),
        )

    ax.set_xlabel("Bandwidth (Mbps)", fontsize=22)
    ax.set_ylabel("LPIPS (lower is better)", fontsize=22)
    ax.set_xticks(x_positions + bar_width * n_series / 2)
    ax.set_xticklabels([f"{bw:.0f}" for bw in sorted_bandwidths])
    ax.tick_params(axis="both", labelsize=20)

    upper = min(1.0, metric_max * 1.2) if metric_max > 0 else 0.5
    upper = max(upper, 0.5)
    ax.set_ylim(0, upper)
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.7)
    ax.legend(fontsize=14, frameon=True, edgecolor="black")

    fig.tight_layout()
    out_path = os.path.join(graph_dir, f"lpips_summary_{safe_games}{output_suffix}.pdf")
    fig.savefig(out_path, dpi=150)
    print(f"Saved LPIPS (lower is better) Real vs Synth summary plot to: {out_path}")
    plt.close(fig)


def plot_qvideo_summary_real_vs_synth(
    repo_root: str,
    games: List[str],
    bandwidths: List[str],
    labels: List[str],
    real_cache: Dict[tuple, Dict],
    synth_cache: Dict[tuple, Dict],
    output_suffix: str = "_real_vs_synth",
) -> None:
    """Plot Real vs Synth Video Quality (Q_video) vs Bandwidth across games.

    Q_video is derived from AvgVMAF normalized to [0,1]. Each (game, experiment-
    type) pair (e.g., "Fortnite Real", "Fortnite Synth") is plotted as a
    separate series of bars over bandwidth.
    """
    series_rows = []
    for game in games:
        for bandwidth_base, label in zip(bandwidths, labels):
            bitrate_label = f"{bandwidth_base}_{game}"
            key = (game, bitrate_label)

            target_bw = parse_bandwidth_from_label(bandwidth_base, label)

            if key in real_cache:
                data = real_cache[key]
                bw_value = target_bw if target_bw is not None else data.get("bandwidth", 0)
                vmaf_r = data.get("avg_vmaf", 0.0)
                qvideo_r = max(0.0, min(1.0, float(vmaf_r) / 100.0))
                series_rows.append({
                    "series": f"{game} Real",
                    "bandwidth": bw_value,
                    "qvideo": qvideo_r,
                })

            if key in synth_cache:
                data = synth_cache[key]
                bw_value = target_bw if target_bw is not None else data.get("bandwidth", 0)
                vmaf_s = data.get("avg_vmaf", 0.0)
                qvideo_s = max(0.0, min(1.0, float(vmaf_s) / 100.0))
                series_rows.append({
                    "series": f"{game} Synth",
                    "bandwidth": bw_value,
                    "qvideo": qvideo_s,
                })

    if not series_rows:
        print("[WARN] No data for Q_video Real vs Synth summary plot.")
        return

    sorted_bandwidths = sorted(set(r["bandwidth"] for r in series_rows))
    series_labels = sorted(set(r["series"] for r in series_rows))

    x_positions = np.arange(len(sorted_bandwidths))
    n_series = max(len(series_labels), 1)
    bar_width = 0.8 / n_series

    fig, ax = plt.subplots(figsize=(10, 6))

    for si, series in enumerate(series_labels):
        rows = [r for r in series_rows if r["series"] == series]
        positions = []
        values = []
        for bw in sorted_bandwidths:
            matching = [r for r in rows if r["bandwidth"] == bw]
            if matching:
                positions.append(x_positions[sorted_bandwidths.index(bw)] + si * bar_width)
                values.append(matching[0]["qvideo"])

        if not positions:
            continue

        ax.bar(
            positions,
            values,
            bar_width,
            label=series,
            edgecolor="black",
            linewidth=0.9,
            color=get_game_color(series),
            hatch=get_hatch(series),
        )

    ax.set_xlabel("Bandwidth (Mbps)", fontsize=22)
    ax.set_ylabel(r"Video Quality ($Q_{video}$)", fontsize=22)
    ax.tick_params(axis="both", labelsize=20)
    ax.set_xticks(x_positions + bar_width * n_series / 2)
    ax.set_xticklabels([f"{bw:.0f}" for bw in sorted_bandwidths])
    ax.set_ylim(0.0, 1.0)
    ax.set_axisbelow(True)
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.7, zorder=0)
    ax.legend(fontsize=14, frameon=True, edgecolor="black", ncol=3, loc="lower right", facecolor="white", framealpha=1)

    fig.tight_layout()

    graph_dir = os.path.join(repo_root, "acm_tomm_experiments", "new_graphs")
    os.makedirs(graph_dir, exist_ok=True)
    safe_games = "_".join(games)
    out_path = os.path.join(graph_dir, f"qvideo_summary_{safe_games}{output_suffix}.pdf")
    fig.savefig(out_path, dpi=150)
    print(f"Saved Real vs Synth Q_video summary plot to: {out_path}")
    plt.close(fig)


def plot_delay_and_rt_real_vs_synth(
    repo_root: str,
    game: str,
    bandwidths: List[str],
    labels: List[str],
    real_metrics_cache: Dict[tuple, Dict],
    synth_metrics_cache: Dict[tuple, Dict],
) -> None:
    """Plot downlink video delay and response time (RT) vs bandwidth for Real vs Synth.

    - Downlink video delay is the mean |received_time - send_time| from srv_QoEMetrics.csv.
    - RT is the mean command-to-frame response time from responsetime_CG.csv.

    One figure per game, with Real/Synth curves across bandwidths.
    """
    bw_values: List[float] = []
    delay_real: List[float] = []
    delay_synth: List[float] = []
    rt_real: List[float] = []
    rt_synth: List[float] = []

    for bw_base, label in zip(bandwidths, labels):
        bw_val = parse_bandwidth_from_label(bw_base, label)
        if bw_val is None:
            continue

        bitrate_label = f"{bw_base}_{game}"

        real_root = os.path.join(
            repo_root,
            "acm_tomm_experiments",
            "reference_vs_real",
            game,
            bitrate_label,
        )
        synth_root = os.path.join(
            repo_root,
            "acm_tomm_experiments",
            "reference_vs_synth",
            game,
            bitrate_label,
        )

        real_delay_ms = compute_mean_video_delay_from_qoe_logs(real_root) if os.path.isdir(real_root) else None
        synth_delay_ms = compute_mean_video_delay_from_qoe_logs(synth_root) if os.path.isdir(synth_root) else None

        real_rt_ms = compute_mean_rt_from_logs(real_root) if os.path.isdir(real_root) else None
        synth_rt_ms = compute_mean_rt_from_logs(synth_root) if os.path.isdir(synth_root) else None

        if all(v is None for v in (real_delay_ms, synth_delay_ms, real_rt_ms, synth_rt_ms)):
            continue

        bw_values.append(bw_val)
        delay_real.append(real_delay_ms if real_delay_ms is not None else 0.0)
        delay_synth.append(synth_delay_ms if synth_delay_ms is not None else 0.0)
        rt_real.append(real_rt_ms if real_rt_ms is not None else 0.0)
        rt_synth.append(synth_rt_ms if synth_rt_ms is not None else 0.0)

        print(
            f"{label} ({game}): Delay_real={real_delay_ms if real_delay_ms is not None else float('nan'):.1f} ms, "
            f"Delay_synth={synth_delay_ms if synth_delay_ms is not None else float('nan'):.1f} ms, "
            f"RT_real={real_rt_ms if real_rt_ms is not None else float('nan'):.1f} ms, "
            f"RT_synth={synth_rt_ms if synth_rt_ms is not None else float('nan'):.1f} ms"
        )

    if not bw_values:
        print(f"[WARN] No delay/RT data available for {game}, skipping delay+RT plot.")
        return

    bw = np.array(bw_values, dtype=float)
    d_r = np.array(delay_real, dtype=float)
    d_s = np.array(delay_synth, dtype=float)
    rt_r = np.array(rt_real, dtype=float)
    rt_s = np.array(rt_synth, dtype=float)

    order = np.argsort(bw)
    bw = bw[order]
    d_r = d_r[order]
    d_s = d_s[order]
    rt_r = rt_r[order]
    rt_s = rt_s[order]

    x = np.arange(len(bw))

    delay_real_color = GAME_COLORS["Fortnite"]["real"]
    delay_synth_color = GAME_COLORS["Fortnite"]["synth"]
    rt_real_color = GAME_COLORS["Kombat"]["real"]
    rt_synth_color = GAME_COLORS["Kombat"]["synth"]

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.set_xlabel("Bandwidth (Mbps)", fontsize=24)
    ax.set_ylabel("Delay / Response Time (ms)", fontsize=24)

    line_dr, = ax.plot(
        x, d_r, color=delay_real_color, linestyle="-", marker="v",
        linewidth=2.5, label="Real Video Delay",
    )
    line_ds, = ax.plot(
        x, d_s, color=delay_synth_color, linestyle="-", marker="o",
        linewidth=2.5, label="Synth Video Delay",
    )
    line_rt_r, = ax.plot(
        x, rt_r, color=rt_real_color, linestyle="--", marker="^",
        linewidth=2.5, label="Real RT",
    )
    line_rt_s, = ax.plot(
        x, rt_s, color=rt_synth_color, linestyle="--", marker="s",
        linewidth=2.5, label="Synth RT",
    )

    ax.set_xticks(x)
    ax.set_xticklabels([f"{val:.0f}" for val in bw])
    ax.tick_params(axis="both", labelsize=22)
    ax.set_axisbelow(True)
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.7, zorder=0)

    handles = [line_dr, line_ds, line_rt_r, line_rt_s]
    labels_legend = [h.get_label() for h in handles]
    ax.legend(handles, labels_legend, fontsize=20, frameon=True, edgecolor="black", loc="center right", facecolor="white", framealpha=1)

    fig.tight_layout()

    graph_dir = os.path.join(repo_root, "acm_tomm_experiments", "new_graphs")
    os.makedirs(graph_dir, exist_ok=True)
    safe_game = game.replace(" ", "_")
    safe_bits = "_".join(bandwidths).replace("/", "_")
    out_name = f"delay_rt_bandwidth_summary_{safe_game}_{safe_bits}_real_vs_synth.pdf"
    out_path = os.path.join(graph_dir, out_name)
    fig.savefig(out_path, dpi=150)
    print(f"Saved Delay+RT summary plot to: {out_path}")


def plot_qint_real_vs_synth(
    repo_root: str,
    game: str,
    bandwidths: List[str],
    labels: List[str],
    real_metrics_cache: Dict[tuple, Dict],
    synth_metrics_cache: Dict[tuple, Dict],
    beta: float = 0.5,
) -> None:
    """Plot interactivity quality Q_Int (0-1) vs bandwidth for Real vs Synth.

    Q_Int is computed per experiment from Q_sync and Q_delay as:

        Q_Int = beta * Q_delay + (1 - beta) * Q_sync

    where Q_sync = (Q_Vsmooth + Q_Csmooth)/2 and Q_delay is derived from the
    mean one-way RT per experiment (see compute_mean_rt_from_logs).
    """
    bw_values: List[float] = []
    qint_real: List[float] = []
    qint_synth: List[float] = []

    for bw_base, label in zip(bandwidths, labels):
        bw_val = parse_bandwidth_from_label(bw_base, label)
        if bw_val is None:
            continue

        bitrate_label = f"{bw_base}_{game}"

        real_root = os.path.join(
            repo_root,
            "acm_tomm_experiments",
            "reference_vs_real",
            game,
            bitrate_label,
        )
        synth_root = os.path.join(
            repo_root,
            "acm_tomm_experiments",
            "reference_vs_synth",
            game,
            bitrate_label,
        )

        real_vsmooth = compute_vsmooth_from_qoe_logs(real_root) if os.path.isdir(real_root) else None
        real_csmooth = compute_csmooth_from_qoe_logs(real_root) if os.path.isdir(real_root) else None
        synth_vsmooth = compute_vsmooth_from_qoe_logs(synth_root) if os.path.isdir(synth_root) else None
        synth_csmooth = compute_csmooth_from_qoe_logs(synth_root) if os.path.isdir(synth_root) else None

        real_qsync = None
        synth_qsync = None
        if real_vsmooth is not None and real_csmooth is not None:
            real_qsync = 0.5 * (real_vsmooth + real_csmooth)
        if synth_vsmooth is not None and synth_csmooth is not None:
            synth_qsync = 0.5 * (synth_vsmooth + synth_csmooth)

        real_rt_ms = compute_mean_rt_from_logs(real_root) if os.path.isdir(real_root) else None
        synth_rt_ms = compute_mean_rt_from_logs(synth_root) if os.path.isdir(synth_root) else None

        real_qdelay = compute_qdelay(real_rt_ms) if real_rt_ms is not None else None
        synth_qdelay = compute_qdelay(synth_rt_ms) if synth_rt_ms is not None else None

        real_qint = None
        synth_qint = None
        if real_qsync is not None and real_qdelay is not None:
            real_qint = compute_qint_from_components(real_qsync, real_qdelay, beta)
        if synth_qsync is not None and synth_qdelay is not None:
            synth_qint = compute_qint_from_components(synth_qsync, synth_qdelay, beta)

        if real_qint is None and synth_qint is None:
            continue

        bw_values.append(bw_val)
        qint_real.append(real_qint if real_qint is not None else 0.0)
        qint_synth.append(synth_qint if synth_qint is not None else 0.0)

        if real_rt_ms is not None or synth_rt_ms is not None:
            print(
                f"{label}: Q_Int_real={real_qint if real_qint is not None else float('nan'):.3f}, "
                f"Q_Int_synth={synth_qint if synth_qint is not None else float('nan'):.3f}, "
                f"RT_real_mean={real_rt_ms if real_rt_ms is not None else float('nan'):.1f} ms, "
                f"RT_synth_mean={synth_rt_ms if synth_rt_ms is not None else float('nan'):.1f} ms"
            )

    if not bw_values:
        print(f"[WARN] No Q_Int data available for {game}, skipping interactivity quality plot.")
        return

    bw = np.array(bw_values, dtype=float)
    qint_r = np.array(qint_real, dtype=float)
    qint_s = np.array(qint_synth, dtype=float)

    order = np.argsort(bw)
    bw = bw[order]
    qint_r = qint_r[order]
    qint_s = qint_s[order]

    x = np.arange(len(bw))
    bar_width = 0.35

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.set_xlabel("Bandwidth (Mbps)", fontsize=24)
    ax.set_ylabel(r"Interactivity Quality ($Q_{Int}$, 0-1)", fontsize=24)
    ax.set_ylim(0.0, 1.0)

    real_color = GAME_COLORS.get(game, {}).get("real", "#CCCCCC")
    synth_color = GAME_COLORS.get(game, {}).get("synth", "#666666")

    bars_real = ax.bar(
        x - bar_width / 2, qint_r, width=bar_width,
        color=real_color, edgecolor="black", linewidth=1.0,
        label="Real $Q_{Int}$", hatch=GAME_HATCHES.get(game, ""),
    )
    bars_synth = ax.bar(
        x + bar_width / 2, qint_s, width=bar_width,
        color=synth_color, edgecolor="black", linewidth=1.0,
        label="Synth $Q_{Int}$", hatch=GAME_HATCHES.get(game, ""),
    )

    ax.set_xticks(x)
    ax.set_xticklabels([f"{val:.0f}" for val in bw])
    ax.tick_params(axis="both", labelsize=22)
    ax.set_axisbelow(True)
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.7, zorder=0)

    handles = [bars_real, bars_synth]
    labels_legend = [h.get_label() for h in handles]
    ax.legend(handles, labels_legend, loc="upper right", fontsize=20, frameon=True, edgecolor="black", facecolor="white", framealpha=1)

    fig.tight_layout()

    graph_dir = os.path.join(repo_root, "acm_tomm_experiments", "new_graphs")
    os.makedirs(graph_dir, exist_ok=True)
    safe_game = game.replace(" ", "_")
    safe_bits = "_".join(bandwidths).replace("/", "_")
    out_name = f"qint_bandwidth_summary_{safe_game}_{safe_bits}_real_vs_synth_beta{beta:.2f}.pdf"
    out_path = os.path.join(graph_dir, out_name)
    fig.savefig(out_path, dpi=150)
    print(f"Saved Q_Int summary plot to: {out_path}")


def plot_qoe_real_vs_synth(
    repo_root: str,
    game: str,
    bandwidths: List[str],
    labels: List[str],
    real_metrics_cache: Dict[tuple, Dict],
    synth_metrics_cache: Dict[tuple, Dict],
    delta_vid: float = 0.5,
    delta_int: float = 0.5,
) -> None:
    """Plot overall QoE (0-1) vs bandwidth for Real vs Synth.

    QoE_0-1 = delta_vid * Q_video + delta_Int * Q_Interactivity

    - Q_video is derived from AvgVMAF normalized to [0,1].
    - Q_Interactivity is currently Q_sync = (Q_Vsmooth + Q_Csmooth) / 2.
    """
    w_sum = delta_vid + delta_int
    if w_sum <= 0:
        delta_vid_n = 0.5
        delta_int_n = 0.5
    else:
        delta_vid_n = delta_vid / w_sum
        delta_int_n = delta_int / w_sum

    bw_values = []
    qoe_real = []
    qoe_synth = []
    loss_real = []
    loss_synth = []

    for bw_base, label in zip(bandwidths, labels):
        bw_val = parse_bandwidth_from_label(bw_base, label)
        if bw_val is None:
            continue

        bitrate_label = f"{bw_base}_{game}"
        key = (game, bitrate_label)

        real_loss = None
        synth_loss = None
        real_qvideo = None
        synth_qvideo = None
        if key in real_metrics_cache:
            real_loss = real_metrics_cache[key].get("loss_pct")
            vmaf_r = real_metrics_cache[key].get("avg_vmaf")
            if vmaf_r is not None:
                real_qvideo = max(0.0, min(1.0, float(vmaf_r) / 100.0))
        if key in synth_metrics_cache:
            synth_loss = synth_metrics_cache[key].get("loss_pct")
            vmaf_s = synth_metrics_cache[key].get("avg_vmaf")
            if vmaf_s is not None:
                synth_qvideo = max(0.0, min(1.0, float(vmaf_s) / 100.0))

        real_root = os.path.join(
            repo_root, "acm_tomm_experiments", "reference_vs_real",
            game, bitrate_label,
        )
        synth_root = os.path.join(
            repo_root, "acm_tomm_experiments", "reference_vs_synth",
            game, bitrate_label,
        )

        real_vsmooth = compute_vsmooth_from_qoe_logs(real_root) if os.path.isdir(real_root) else None
        real_csmooth = compute_csmooth_from_qoe_logs(real_root) if os.path.isdir(real_root) else None
        synth_vsmooth = compute_vsmooth_from_qoe_logs(synth_root) if os.path.isdir(synth_root) else None
        synth_csmooth = compute_csmooth_from_qoe_logs(synth_root) if os.path.isdir(synth_root) else None

        real_qsync = None
        synth_qsync = None
        if real_vsmooth is not None and real_csmooth is not None:
            real_qsync = 0.5 * (real_vsmooth + real_csmooth)
        if synth_vsmooth is not None and synth_csmooth is not None:
            synth_qsync = 0.5 * (synth_vsmooth + synth_csmooth)

        real_qoe = None
        synth_qoe = None
        if real_qvideo is not None and real_qsync is not None:
            real_qoe = delta_vid_n * real_qvideo + delta_int_n * real_qsync
        if synth_qvideo is not None and synth_qsync is not None:
            synth_qoe = delta_vid_n * synth_qvideo + delta_int_n * synth_qsync

        if real_qoe is None and synth_qoe is None:
            continue

        bw_values.append(bw_val)
        qoe_real.append(real_qoe if real_qoe is not None else 0.0)
        qoe_synth.append(synth_qoe if synth_qoe is not None else 0.0)
        loss_real.append(real_loss if real_loss is not None else 0.0)
        loss_synth.append(synth_loss if synth_loss is not None else 0.0)

    if not bw_values:
        print(f"[WARN] No QoE data available for {game}, skipping QoE plot.")
        return

    bw = np.array(bw_values, dtype=float)
    qoe_r = np.array(qoe_real, dtype=float)
    qoe_s = np.array(qoe_synth, dtype=float)
    lr = np.array(loss_real, dtype=float)
    ls = np.array(loss_synth, dtype=float)

    order = np.argsort(bw)
    bw = bw[order]
    qoe_r = qoe_r[order]
    qoe_s = qoe_s[order]
    lr = lr[order]
    ls = ls[order]

    x = np.arange(len(bw))
    bar_width = 0.35

    fig, ax1 = plt.subplots(figsize=(10, 6))

    ax1.set_xlabel("Bandwidth (Mbps)", fontsize=24)
    ax1.set_ylabel("Perceived QoE Score (0-1)", fontsize=24)
    ax1.set_ylim(0.0, 1.0)

    real_color = GAME_COLORS.get(game, {}).get("real", "#CCCCCC")
    synth_color = GAME_COLORS.get(game, {}).get("synth", "#666666")

    bars_real = ax1.bar(
        x - bar_width / 2, qoe_r, width=bar_width,
        color=real_color, edgecolor="black", linewidth=1.0,
        label="Real QoE", hatch=GAME_HATCHES.get(game, ""),
    )
    bars_synth = ax1.bar(
        x + bar_width / 2, qoe_s, width=bar_width,
        color=synth_color, edgecolor="black", linewidth=1.0,
        label="Synth QoE", hatch=GAME_HATCHES.get(game, ""),
    )

    ax1.set_xticks(x)
    ax1.set_xticklabels([f"{val:.0f}" for val in bw])
    ax1.tick_params(axis="both", labelsize=22)
    ax1.set_axisbelow(True)
    ax1.grid(True, linestyle="--", linewidth=0.5, alpha=0.7, zorder=0)

    handles = [bars_real, bars_synth]
    labels_legend = [h.get_label() for h in handles]
    ax1.legend(handles, labels_legend, loc="lower right", fontsize=20, framealpha=1, edgecolor="black", facecolor="white")

    fig.tight_layout()

    graph_dir = os.path.join(repo_root, "acm_tomm_experiments", "new_graphs")
    os.makedirs(graph_dir, exist_ok=True)
    safe_game = game.replace(" ", "_")
    safe_bits = "_".join(bandwidths).replace("/", "_")
    out_name = f"qoe_bandwidth_summary_{safe_game}_{safe_bits}_real_vs_synth.pdf"
    out_path = os.path.join(graph_dir, out_name)
    fig.savefig(out_path, dpi=150)
    print(f"Saved QoE/LOSS summary plot to: {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate specific Real vs Synth comparison plots for CGSynth")
    parser.add_argument(
        "--games", nargs="+",
        default=["Fortnite", "Forza", "Kombat"],
        help="Game names (default: Fortnite Forza Kombat)",
    )
    parser.add_argument(
        "--bandwidths", nargs="+",
        default=["2Mbit", "4Mbit", "6Mbit", "8Mbit", "10Mbit"],
        help="Bandwidth labels (default: 2Mbit 4Mbit 6Mbit 8Mbit 10Mbit)",
    )
    parser.add_argument("--labels", nargs="+", default=None,
                        help="Legend labels for each bitrate (defaults to bandwidths)")
    parser.add_argument("--total-frames", type=int, default=120,
                        help="Total number of frames (used only for axis scaling)")

    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.abspath(os.path.join(__file__, "..")))
    labels = args.labels if args.labels else args.bandwidths

    if args.labels and len(args.labels) != len(args.bandwidths):
        print("If provided, --labels must have the same length as --bandwidths")
        sys.exit(1)

    # Load caches
    csv_path_real = os.path.join(repo_root, "acm_tomm_experiments", "processed_data", "vmaf_metrics_real.csv")
    csv_path_synth = os.path.join(repo_root, "acm_tomm_experiments", "processed_data", "vmaf_metrics_synth.csv")

    if not os.path.exists(csv_path_real):
        print(f"[ERROR] Real cache not found: {csv_path_real}")
        sys.exit(1)
    if not os.path.exists(csv_path_synth):
        print(f"[ERROR] Synth cache not found: {csv_path_synth}")
        sys.exit(1)

    print(f"[INFO] Loading real cache from: {csv_path_real}")
    real_cache = load_metrics_cache(csv_path_real)
    print(f"[INFO] Loading synth cache from: {csv_path_synth}")
    synth_cache = load_metrics_cache(csv_path_synth)

    if not real_cache or not synth_cache:
        print("[ERROR] One or both caches are empty. Cannot generate plots.")
        sys.exit(1)

    games = args.games

    # 1. Individual metric plots (VMAF, PSNR, SSIM, LPIPS Real vs Synth)
    print("\n=== Generating VMAF Real vs Synth plot ===")
    plot_vmaf_real_vs_synth(
        repo_root=repo_root, games=games, bandwidths=args.bandwidths,
        labels=labels, real_cache=real_cache, synth_cache=synth_cache,
    )
    print("\n=== Generating PSNR Real vs Synth plot ===")
    plot_psnr_real_vs_synth(
        repo_root=repo_root, games=games, bandwidths=args.bandwidths,
        labels=labels, real_cache=real_cache, synth_cache=synth_cache,
    )
    print("\n=== Generating SSIM Real vs Synth plot ===")
    plot_ssim_real_vs_synth(
        repo_root=repo_root, games=games, bandwidths=args.bandwidths,
        labels=labels, real_cache=real_cache, synth_cache=synth_cache,
    )
    print("\n=== Generating LPIPS Real vs Synth plot ===")
    plot_lpips_real_vs_synth(
        repo_root=repo_root, games=games, bandwidths=args.bandwidths,
        labels=labels, real_cache=real_cache, synth_cache=synth_cache,
    )

    # 2. Video quality vs bandwidth (Q_video) Real vs Synth
    print("\n=== Generating Video Quality (Q_video) vs Bandwidth Real vs Synth plot ===")
    plot_qvideo_summary_real_vs_synth(
        repo_root=repo_root,
        games=games,
        bandwidths=args.bandwidths,
        labels=labels,
        real_cache=real_cache,
        synth_cache=synth_cache,
    )

    # 3. Per-game Delay + RT plots
    print("\n=== Generating Delay and Response Time Real vs Synth plots (per game) ===")
    for game in games:
        plot_delay_and_rt_real_vs_synth(
            repo_root=repo_root,
            game=game,
            bandwidths=args.bandwidths,
            labels=labels,
            real_metrics_cache=real_cache,
            synth_metrics_cache=synth_cache,
        )

    # 4. Per-game Quality of Interactivity (Q_Int) plots
    print("\n=== Generating Quality of Interactivity (Q_Int) Real vs Synth plots (per game) ===")
    for game in games:
        plot_qint_real_vs_synth(
            repo_root=repo_root,
            game=game,
            bandwidths=args.bandwidths,
            labels=labels,
            real_metrics_cache=real_cache,
            synth_metrics_cache=synth_cache,
            beta=0.5,
        )

    # 5. Per-game QoE plots
    print("\n=== Generating QoE Real vs Synth plots (per game) ===")
    for game in games:
        plot_qoe_real_vs_synth(
            repo_root=repo_root,
            game=game,
            bandwidths=args.bandwidths,
            labels=labels,
            real_metrics_cache=real_cache,
            synth_metrics_cache=synth_cache,
        )

    print("\n[INFO] All new_graphs plots generated successfully!")
    output_dir = os.path.join(repo_root, "acm_tomm_experiments", "new_graphs")
    print(f"[INFO] Output saved to: {output_dir}")


if __name__ == "__main__":
    main()
