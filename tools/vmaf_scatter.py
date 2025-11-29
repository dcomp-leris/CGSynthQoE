#!/usr/bin/env python3

import os
import sys
import argparse
import subprocess
import tempfile
import json
import re
from typing import List, Dict, Optional

import itertools
import numpy as np
import matplotlib.pyplot as plt


def parse_bandwidth_from_label(bitrate_label: str, legend_label: str) -> Optional[float]:
    """Extract numeric bandwidth in Mbps from a bitrate or legend label.

    Looks for the first integer or float in legend_label, falling back to
    bitrate_label if needed. Returns None if parsing fails.
    """
    text = legend_label or bitrate_label
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def make_mp4_from_png(png_path: str, mp4_path: str) -> None:
    """Encode a single PNG frame into a 1-frame H.264 MP4 suitable for libvmaf."""
    cmd = [
        "ffmpeg", "-y",
        "-framerate", "1",
        "-i", png_path,
        "-frames:v", "1",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        mp4_path,
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def compute_vmaf_per_frame(ref_folder: str, dst_folder: str) -> Dict[str, List[float]]:
    """Compute per-frame VMAF between PNG frames in ref_folder and dst_folder.

    Only frames that exist in both folders (by filename) are compared.
    Missing frames in dst_folder are skipped entirely.
    """
    ref_images = sorted([f for f in os.listdir(ref_folder) if f.lower().endswith(".png")])
    dst_images = sorted([f for f in os.listdir(dst_folder) if f.lower().endswith(".png")])

    ref_set = set(ref_images)
    dst_set = set(dst_images)

    common_frames = sorted(ref_set.intersection(dst_set))
    missing_frames = sorted(ref_set - dst_set)

    print("\nComparing:")
    print(f"  REF: {ref_folder}")
    print(f"  DST: {dst_folder}")
    print(f"  Common frames: {len(common_frames)}")
    print(f"  Missing frames (only in reference): {len(missing_frames)}")

    vmaf_scores: List[float] = []
    frame_indices: List[int] = []

    for frame_name in common_frames:
        ref_path = os.path.join(ref_folder, frame_name)
        dst_path = os.path.join(dst_folder, frame_name)

        with tempfile.NamedTemporaryFile(suffix=".mp4") as ref_tmp, \
             tempfile.NamedTemporaryFile(suffix=".mp4") as dst_tmp, \
             tempfile.NamedTemporaryFile(suffix=".json") as json_tmp:

            make_mp4_from_png(ref_path, ref_tmp.name)
            make_mp4_from_png(dst_path, dst_tmp.name)

            cmd = [
                "ffmpeg", "-y",
                "-i", dst_tmp.name,
                "-i", ref_tmp.name,
                "-lavfi", f"libvmaf=log_path={json_tmp.name}:log_fmt=json",
                "-f", "null", "-",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                print(f"[FFmpeg ERROR] Frame {frame_name}")
                print(result.stderr)
                continue

            try:
                with open(json_tmp.name) as f:
                    data = json.load(f)
                score = data["pooled_metrics"]["vmaf"]["mean"]
                vmaf_scores.append(score)
                # assume frame name is like 0001.png or 12.png
                base = os.path.splitext(frame_name)[0]
                try:
                    frame_idx = int(base)
                except ValueError:
                    # Fallback: skip non-numeric names
                    continue
                frame_indices.append(frame_idx)
            except Exception as e:
                print(f"[Parse ERROR] {frame_name}: {e}")

    return {
        "vmaf_scores": vmaf_scores,
        "frame_indices": frame_indices,
        "missing_count": len(missing_frames),
        "ref_count": len(ref_images),
    }


def resolve_paths_for_experiment(repo_root: str, game: str, bitrate_label: str) -> (str, str):
    """Map game + bitrate label to reference and destination folders.

    - Reference frames are under CGReplay/server/<Game>/
    - Received frames are under acm_tomm_experiments/reference_vs_real/<Game>/<bitrate_label>/received_frames/

    Example:
      game = "Fortnite", bitrate_label = "2Mbit_Fortnite" →
        ref: CGReplay/server/Fortnite/
        dst: acm_tomm_experiments/reference_vs_real/Fortnite/2Mbit_Fortnite/received_frames/
    """
    ref_folder = os.path.join(repo_root, "CGReplay", "server", game)
    dst_folder = os.path.join(
        repo_root,
        "acm_tomm_experiments",
        "reference_vs_real",
        game,
        bitrate_label,
        "received_frames",
    )
    return ref_folder, dst_folder


def compare_multiple_destinations(
    repo_root: str,
    game: str,
    bitrate_labels: List[str],
    labels: List[str],
    total_frames: int,
) -> None:
    """Compute and plot per-frame VMAF as a scatterplot for multiple experiments."""
    if len(bitrate_labels) != len(labels):
        print("bitrate_labels and labels must have the same length")
        sys.exit(1)

    all_results = []

    # Aggregated stats for bandwidth summary plot
    bandwidths = []
    avg_vmafs = []
    loss_pcts = []
    summary_labels = []
    summary_markers = []

    for bitrate in bitrate_labels:
        ref_folder, dst_folder = resolve_paths_for_experiment(repo_root, game, bitrate)

        if not os.path.isdir(ref_folder):
            print(f"[ERROR] Reference folder not found: {ref_folder}")
            continue
        if not os.path.isdir(dst_folder):
            print(f"[ERROR] Destination folder not found: {dst_folder}")
            continue

        result = compute_vmaf_per_frame(ref_folder, dst_folder)
        all_results.append((bitrate, result))

    if not all_results:
        print("No valid experiments to plot.")
        return

    plt.figure(figsize=(14, 7))

    # Cycle different marker shapes so each experiment is visually distinct
    markers = ["o", "s", "D", "^", "v", "P", "X", "*"]
    marker_cycle = itertools.cycle(markers)

    for (bitrate, result), label in zip(all_results, labels):
        marker = next(marker_cycle)
        frame_indices = np.array(result["frame_indices"], dtype=int)
        vmaf_scores = np.array(result["vmaf_scores"], dtype=float)

        if frame_indices.size == 0:
            print(f"[WARN] No VMAF scores for {label}, skipping plot.")
            continue

        avg_vmaf = float(np.mean(vmaf_scores))

        # Frame loss statistics
        missing = int(result.get("missing_count", 0))
        ref_count = int(result.get("ref_count", 0)) if result.get("ref_count") is not None else 0
        if ref_count > 0:
            loss_rate = missing / ref_count
            loss_pct = loss_rate * 100.0
            legend_label = f"{label} (avg={avg_vmaf:.2f}, loss={loss_pct:.1f}%)"
            print(f"{label}: avg VMAF={avg_vmaf:.2f}, frame loss={missing}/{ref_count} ({loss_pct:.2f}%)")

            # Store aggregate stats for bandwidth summary plot
            bw_value = parse_bandwidth_from_label(bitrate, label)
            if bw_value is not None:
                bandwidths.append(bw_value)
                avg_vmafs.append(avg_vmaf)
                loss_pcts.append(loss_pct)
                summary_labels.append(label)
                summary_markers.append(marker)
            else:
                print(f"[WARN] Could not parse bandwidth from '{label}' / '{bitrate}', skipping summary point.")
        else:
            loss_rate = None
            legend_label = f"{label} (avg={avg_vmaf:.2f})"
            print(f"{label}: avg VMAF={avg_vmaf:.2f}, frame loss: unavailable (ref_count=0)")

        # Scatter points (per-frame VMAF)
        plt.scatter(
            frame_indices,
            vmaf_scores,
            s=15,
            alpha=0.7,
            marker=marker,
            label=legend_label,
        )

        # Light trend line to help visualizing the tendency
        order = np.argsort(frame_indices)
        plt.plot(
            frame_indices[order],
            vmaf_scores[order],
            linewidth=0.8,
            alpha=0.3,
            linestyle="--",
        )

    plt.xlabel("Frame Number")
    plt.ylabel("VMAF Score")
    plt.title(f"VMAF Scatterplot for {game} Experiments")
    plt.grid(True, alpha=0.3)

    # Place legend above the axes, with limited columns, so it stays inside the figure
    legend_cols = min(len(labels), 3)
    plt.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, 1.18),
        ncol=legend_cols,
        fontsize=9,
    )
    # Leave some space at the top for the legend
    plt.tight_layout(rect=[0, 0, 1, 0.9])

    # Save figure to acm_tomm_experiments/graphs
    graph_dir = os.path.join(repo_root, "acm_tomm_experiments", "graphs")
    try:
        os.makedirs(graph_dir, exist_ok=True)
        # Build a simple filename from game and bitrate labels
        safe_game = game.replace(" ", "_")
        safe_bits = "_".join(bitrate_labels)
        safe_bits = safe_bits.replace("/", "_")
        out_name = f"vmaf_scatter_{safe_game}_{safe_bits}.png"
        out_path = os.path.join(graph_dir, out_name)
        plt.savefig(out_path, dpi=150)
        print(f"Saved VMAF scatter plot to: {out_path}")
    except Exception as e:
        print(f"[WARN] Could not save VMAF plot: {e}")

    plt.close()


def plot_bandwidth_summary(
    repo_root: str,
    game: str,
    bandwidths: List[float],
    avg_vmafs: List[float],
    loss_pcts: List[float],
    labels: List[str],
    markers: List[str],
    bitrate_labels: List[str],
) -> None:
    """Plot average VMAF and frame loss vs bandwidth using twin y-axes.

    X axis: bandwidth (Mbps).
    Left Y axis (blue): average VMAF.
    Right Y axis (red): average frame loss percentage.
    Uses scatter points only (no connecting lines).
    """
    if not bandwidths:
        return

    bw = np.array(bandwidths, dtype=float)
    vmaf = np.array(avg_vmafs, dtype=float)
    loss = np.array(loss_pcts, dtype=float)

    # Remove "BW: " prefix from labels if present
    clean_labels = [l.replace("BW: ", "") for l in labels]

    fig, ax1 = plt.subplots(figsize=(10, 6))
    color_vmaf = "tab:blue"
    color_loss = "tab:red"

    # Average VMAF: blue bars with thick border
    ax1.set_xlabel("Bandwidth (Mbps)")
    ax1.set_ylabel("Average VMAF", color=color_vmaf)
    ax1.set_ylabel("VMAF Score (0-100)", color=color_vmaf)
    ax1.tick_params(axis="y", labelcolor=color_vmaf)

    # VMAF bars: one bar per bandwidth on the left Y-axis with thick border
    bar_width = 0.6
    for bw_val, vmaf_val, label in zip(bw, vmaf, clean_labels):
        ax1.bar(
            bw_val,
            vmaf_val,
            width=bar_width,
            color=color_vmaf,
            alpha=0.8,
            edgecolor="black",
            linewidth=2,
            label=f"{label} VMAF",
        )

    ax2 = ax1.twinx()
    ax2.set_ylabel("Frame Loss Percentage (%)", color=color_loss)
    ax2.tick_params(axis="y", labelcolor=color_loss)

    # Frame loss scatter: red markers at each bandwidth, with connecting dashed line
    ax2.scatter(
        bw,
        loss,
        color=color_loss,
        marker="^",
        s=70,
        label="Frame Loss Percentage",
    )
    ax2.plot(
        bw,
        loss,
        color=color_loss,
        linestyle="--",
        linewidth=1.2,
    )

    ax1.set_title(f"VMAF and Frame Loss vs. Bandwidth for {game}")

    # Combine legends from both axes and place inside the plot area
    handles1, labels1 = ax1.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(
        handles1 + handles2,
        labels1 + labels2,
        loc="upper left",
        fontsize=9,
        framealpha=0.9,
    )

    fig.tight_layout()

    graph_dir = os.path.join(repo_root, "acm_tomm_experiments", "graphs")
    os.makedirs(graph_dir, exist_ok=True)
    safe_game = game.replace(" ", "_")
    safe_bits = "_".join(bitrate_labels)
    safe_bits = safe_bits.replace("/", "_")
    out_name = f"vmaf_bandwidth_summary_{safe_game}_{safe_bits}.png"
    out_path = os.path.join(graph_dir, out_name)
    fig.savefig(out_path, dpi=150)
    print(f"Saved VMAF/bandwidth summary plot to: {out_path}")


def compare_bandwidth_across_games(
    repo_root: str,
    base_game: str,
    extra_games: List[str],
    bitrate_labels: List[str],
    labels: List[str],
) -> None:
    """Build a combined bandwidth summary plot across multiple games.

    Reuses the same bitrate_labels/labels configuration as the base game
    and assumes destination folders are named <prefix>_<Game>, e.g.,
    2Mbit_Fortnite, 2Mbit_Kombat, 2Mbit_Forza.
    """
    games = [base_game] + list(extra_games)

    per_game_stats = []
    all_bandwidths = set()

    for game in games:
        game_bandwidths = []
        game_vmafs = []
        game_losses = []

        for bitrate_label_base, label in zip(bitrate_labels, labels):
            # Map base bitrate label to this game
            if game == base_game:
                bitrate_label = bitrate_label_base
            else:
                suffix = f"_{base_game}"
                if bitrate_label_base.endswith(suffix):
                    prefix = bitrate_label_base[: -len(suffix)]
                else:
                    prefix = bitrate_label_base
                bitrate_label = f"{prefix}_{game}"

            ref_folder, dst_folder = resolve_paths_for_experiment(
                repo_root, game, bitrate_label
            )
            if not os.path.isdir(ref_folder) or not os.path.isdir(dst_folder):
                print(f"[WARN] Skipping {game} @ {bitrate_label}: missing folder(s).")
                continue

            result = compute_vmaf_per_frame(ref_folder, dst_folder)
            vmaf_scores = np.array(result["vmaf_scores"], dtype=float)
            if vmaf_scores.size == 0:
                print(f"[WARN] No VMAF scores for {game} @ {bitrate_label}, skipping.")
                continue

            avg_vmaf = float(np.mean(vmaf_scores))
            missing = int(result.get("missing_count", 0))
            ref_count = int(result.get("ref_count", 0)) if result.get("ref_count") is not None else 0
            loss_pct = (missing / ref_count) * 100.0 if ref_count > 0 else 0.0

            bw_value = parse_bandwidth_from_label(bitrate_label_base, label)
            if bw_value is None:
                print(
                    f"[WARN] Could not parse bandwidth from '{label}' / '{bitrate_label_base}', skipping."
                )
                continue

            game_bandwidths.append(bw_value)
            game_vmafs.append(avg_vmaf)
            game_losses.append(loss_pct)
            all_bandwidths.add(bw_value)

        per_game_stats.append(
            {
                "game": game,
                "bandwidths": np.array(game_bandwidths, dtype=float),
                "avg_vmafs": np.array(game_vmafs, dtype=float),
                "loss_pcts": np.array(game_losses, dtype=float),
            }
        )

    if not all_bandwidths:
        return

    # Build aligned matrices over the union of bandwidths
    all_bw = np.array(sorted(all_bandwidths), dtype=float)
    n_games = len(per_game_stats)
    n_bw = all_bw.size

    vmaf_mat = np.full((n_games, n_bw), np.nan, dtype=float)
    loss_mat = np.full((n_games, n_bw), np.nan, dtype=float)

    for gi, stats in enumerate(per_game_stats):
        bw_vals = stats["bandwidths"]
        for bw_val, v, l in zip(bw_vals, stats["avg_vmafs"], stats["loss_pcts"]):
            idx = np.where(all_bw == bw_val)[0]
            if idx.size == 0:
                continue
            vmaf_mat[gi, idx[0]] = v
            loss_mat[gi, idx[0]] = l

    # Plot combined figure
    fig, ax1 = plt.subplots(figsize=(12, 6))

    color_vmaf = "tab:blue"
    color_loss = "tab:red"

    ax1.set_xlabel("Bandwidth (Mbps)")
    ax1.set_ylabel("VMAF Score (0-100)", color=color_vmaf)
    ax1.tick_params(axis="y", labelcolor=color_vmaf)

    # Grouped blue bars (one per game per bandwidth), differentiated by hatch
    if n_bw > 1:
        step = float(np.min(np.diff(all_bw)))
    else:
        step = 1.0
    group_width = min(0.8 * step, 0.8)
    bar_width = group_width / max(n_games, 1)

    hatches = ["", "//", "xx", "..", "||", "\\\\", "oo", "**"]
    markers = ["o", "s", "D", "^", "v", "P", "X", "*"]

    for gi, stats in enumerate(per_game_stats):
        offset = -group_width / 2 + bar_width / 2 + gi * bar_width
        valid = ~np.isnan(vmaf_mat[gi])
        if not np.any(valid):
            continue
        ax1.bar(
            all_bw[valid] + offset,
            vmaf_mat[gi, valid],
            width=bar_width,
            color=color_vmaf,
            alpha=0.8,
            edgecolor="black",
            linewidth=2,
            hatch=hatches[gi % len(hatches)],
            label=f"{stats['game']} VMAF",
        )

    ax2 = ax1.twinx()
    ax2.set_ylabel("Frame Loss Percentage (%)", color=color_loss)
    ax2.tick_params(axis="y", labelcolor=color_loss)

    # Frame loss: red markers + dashed line per game, with small horizontal offset per game
    for gi, stats in enumerate(per_game_stats):
        valid = ~np.isnan(loss_mat[gi])
        if not np.any(valid):
            continue
        # Small offset to avoid overlapping loss series
        offset = -group_width / 2 + bar_width / 2 + gi * bar_width
        ax2.scatter(
            all_bw[valid] + offset,
            loss_mat[gi, valid],
            color=color_loss,
            marker=markers[gi % len(markers)],
            s=70,
            label=f"{stats['game']} Loss",
        )
        # Connect the offset points with a dashed line
        ax2.plot(
            all_bw[valid] + offset,
            loss_mat[gi, valid],
            color=color_loss,
            linestyle="--",
            linewidth=1.0,
            alpha=0.9,
        )

    ax1.set_title("VMAF and Frame Loss vs. Bandwidth (multiple games)")

    handles1, labels1 = ax1.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(
        handles1 + handles2,
        labels1 + labels2,
        loc="upper left",
        fontsize=9,
        framealpha=0.9,
    )

    fig.tight_layout()

    graph_dir = os.path.join(repo_root, "acm_tomm_experiments", "graphs")
    os.makedirs(graph_dir, exist_ok=True)
    games_slug = "_".join(g.replace(" ", "_") for g in games)
    safe_bits = "_".join(bitrate_labels).replace("/", "_")
    out_name = f"vmaf_bandwidth_summary_multi_{games_slug}_{safe_bits}.png"
    out_path = os.path.join(graph_dir, out_name)
    fig.savefig(out_path, dpi=150)
    print(f"Saved multi-game VMAF/bandwidth summary plot to: {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Per-frame VMAF scatterplot for CGSynth experiments")
    parser.add_argument(
        "--games",
        nargs="+",
        required=True,
        help="One or more game names (e.g., Fortnite Kombat Forza). "
             "If a single game is given, generates per-frame and single-game bandwidth plots. "
             "If multiple games are given, also generates a multi-game grouped bandwidth summary.",
    )
    parser.add_argument(
        "--bitrates",
        nargs="+",
        required=True,
        help="Bitrate experiment labels (folder names) under reference_vs_real/<Game>/, e.g., 2Mbit_Fortnite 4Mbit_Fortnite",
    )
    parser.add_argument(
        "--labels",
        nargs="+",
        required=False,
        help="Legend labels for each bitrate (defaults to the bitrate folder names)",
    )
    parser.add_argument(
        "--total-frames",
        type=int,
        default=120,
        help="Total number of frames in the experiment (used only for axis scaling)",
    )

    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.abspath(os.path.join(__file__, "..")))

    if args.labels and len(args.labels) != len(args.bitrates):
        print("If provided, --labels must have the same length as --bitrates")
        sys.exit(1)

    labels = args.labels if args.labels else args.bitrates

    # Split games list: first game is the base for per-frame and single-game plots
    base_game = args.games[0]
    extra_games = args.games[1:] if len(args.games) > 1 else []

    compare_multiple_destinations(
        repo_root=repo_root,
        game=base_game,
        bitrate_labels=args.bitrates,
        labels=labels,
        total_frames=args.total_frames,
    )

    if extra_games:
        compare_bandwidth_across_games(
            repo_root=repo_root,
            base_game=base_game,
            extra_games=extra_games,
            bitrate_labels=args.bitrates,
            labels=labels,
        )


if __name__ == "__main__":
    main()
