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
import csv
import yaml
import pandas as pd
import ast
import cv2
from tqdm import tqdm

# Optional metric dependencies
try:
    from skimage.metrics import structural_similarity as skimage_ssim
    from skimage.metrics import peak_signal_noise_ratio as skimage_psnr
except ImportError:
    skimage_ssim = None
    skimage_psnr = None
    print("[WARN] scikit-image not installed. PSNR/SSIM will be 0.0. Install with: pip install scikit-image")

try:
    import torch
    import lpips as lpips_lib
except ImportError:
    torch = None
    lpips_lib = None
    print("[WARN] torch/lpips not installed. LPIPS will be 0.0. Install with: pip install torch lpips")

# Style constants matched to user preference
COLORS = ['#ffffff', '#d9d9d9', '#9c9c9c', '#2f2f2f']
HATCHES = ['/', '\\', '.', 'x']


def parse_bandwidth_from_logs(bitrate_label: str, dst_folder: str) -> Optional[float]:
    """Extract actual average bitrate from CSV logs in the experiment directory."""
    # Get experiment root directory (parent of received_frames)
    experiment_root = os.path.dirname(dst_folder)
    
    # Try server logs first (logs copy), then player logs
    log_dirs = [
        os.path.join(experiment_root, "logs copy"),
        os.path.join(experiment_root, "logs")
    ]
    
    for log_dir in log_dirs:
        if not os.path.exists(log_dir):
            continue
            
        # Try srv_QoEMetrics.csv first (has per-frame bitrate data)
        qoe_metrics_path = os.path.join(log_dir, "srv_QoEMetrics.csv")
        if os.path.exists(qoe_metrics_path):
            try:
                df = pd.read_csv(qoe_metrics_path)
                if 'bitrate' in df.columns:
                    # Convert Kbps to Mbps and take the mean
                    avg_bitrate_kbps = df['bitrate'].mean()
                    return avg_bitrate_kbps / 1000.0
            except Exception as e:
                print(f"[WARN] Error reading {qoe_metrics_path}: {e}")
                continue
        
        # Fallback to srv_codec_bitrate.csv
        codec_bitrate_path = os.path.join(log_dir, "srv_codec_bitrate.csv")
        if os.path.exists(codec_bitrate_path):
            try:
                df = pd.read_csv(codec_bitrate_path)
                if 'rate_ctl' in df.columns:
                    # Extract bitrate values from rate_ctl column
                    bitrates = []
                    for entry in df['rate_ctl']:
                        if isinstance(entry, str) and entry.startswith('['):
                            try:
                                rate_data = ast.literal_eval(entry)
                                if len(rate_data) >= 3 and isinstance(rate_data[2], (int, float)):
                                    bitrates.append(rate_data[2])
                            except:
                                continue
                    
                    if bitrates:
                        avg_bitrate_kbps = sum(bitrates) / len(bitrates)
                        return avg_bitrate_kbps / 1000.0
            except Exception as e:
                print(f"[WARN] Error reading {codec_bitrate_path}: {e}")
                continue
    
    # Fallback to config.yaml if no CSV data found
    print(f"[WARN] No bitrate data found in logs, falling back to config.yaml")
    return parse_bandwidth_from_config(bitrate_label, experiment_root)


def parse_bandwidth_from_config(bitrate_label: str, experiment_root: str) -> Optional[float]:
    """Extract actual bitrate value from config.yaml in the experiment directory."""
    config_path = os.path.join(experiment_root, "config.yaml")
    
    if not os.path.exists(config_path):
        print(f"[WARN] Config file not found: {config_path}, falling back to folder name parsing")
        return parse_bandwidth_from_label(bitrate_label, bitrate_label)
    
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Extract bitrate from encoding section
        if 'encoding' in config and 'bitrate_max' in config['encoding']:
            bitrate_kbps = config['encoding']['bitrate_max']
            bitrate_mbps = bitrate_kbps / 1000.0  # Convert Kbps to Mbps
            return bitrate_mbps
        else:
            print(f"[WARN] bitrate_max not found in config: {config_path}, falling back to folder name parsing")
            return parse_bandwidth_from_label(bitrate_label, bitrate_label)
            
    except Exception as e:
        print(f"[WARN] Error reading config file {config_path}: {e}, falling back to folder name parsing")
        return parse_bandwidth_from_label(bitrate_label, bitrate_label)


def load_metrics_cache(csv_path: str) -> Dict[tuple, Dict]:
    """Load metrics from CSV into a dict keyed by (game, bitrate_label)."""
    cache = {}
    if not os.path.exists(csv_path):
        return cache
    
    try:
        with open(csv_path, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                game = row["Game"]
                bitrate = row["BitrateLabel"]
                key = (game, bitrate)
                cache[key] = {
                    "avg_vmaf": float(row["AvgVMAF"]),
                    "loss_pct": float(row["LossPct"]),
                    "missing": int(row["MissingFrames"]),
                    "ref_count": int(row["RefCount"]),
                    "bandwidth": float(row["Bandwidth"]) if row["Bandwidth"] else None,
                    "vmaf_scores": json.loads(row["VMAFScores"]),
                    "frame_indices": json.loads(row["FrameIndices"]),
                    # New metrics
                    "avg_psnr": float(row.get("AvgPSNR", 0.0)),
                    "avg_ssim": float(row.get("AvgSSIM", 0.0)),
                    "avg_lpips": float(row.get("AvgLPIPS", 0.0)),
                    "psnr_scores": json.loads(row.get("PSNRScores", "[]")),
                    "ssim_scores": json.loads(row.get("SSIMScores", "[]")),
                    "lpips_scores": json.loads(row.get("LPIPSScores", "[]")),
                }
        print(f"[INFO] Loaded metrics cache from {csv_path} ({len(cache)} entries)")
    except Exception as e:
        print(f"[WARN] Failed to load cache: {e}")
    
    return cache


def save_metrics_cache(csv_path: str, cache: Dict[tuple, Dict]) -> None:
    """Save metrics dict to CSV file."""
    if not cache:
        return
    
    fieldnames = [
        "Game", "BitrateLabel", "Bandwidth", "AvgVMAF", "LossPct", 
        "MissingFrames", "RefCount", "VMAFScores", "FrameIndices",
        "AvgPSNR", "AvgSSIM", "AvgLPIPS", "PSNRScores", "SSIMScores", "LPIPSScores"
    ]
    try:
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for (game, bitrate), data in cache.items():
                writer.writerow({
                    "Game": game,
                    "BitrateLabel": bitrate,
                    "Bandwidth": data["bandwidth"],
                    "AvgVMAF": data["avg_vmaf"],
                    "LossPct": data["loss_pct"],
                    "MissingFrames": data["missing"],
                    "RefCount": data["ref_count"],
                    "VMAFScores": json.dumps(data.get("vmaf_scores", [])),
                    "FrameIndices": json.dumps(data.get("frame_indices", [])),
                    "AvgPSNR": data.get("avg_psnr", 0.0),
                    "AvgSSIM": data.get("avg_ssim", 0.0),
                    "AvgLPIPS": data.get("avg_lpips", 0.0),
                    "PSNRScores": json.dumps(data.get("psnr_scores", [])),
                    "SSIMScores": json.dumps(data.get("ssim_scores", [])),
                    "LPIPSScores": json.dumps(data.get("lpips_scores", [])),
                })
        print(f"[INFO] Saved metrics cache to {csv_path}")
    except Exception as e:
        print(f"[WARN] Failed to save cache: {e}")


def calculate_psnr_ssim_lpips(img1, img2, lpips_fn=None, device='cpu'):
    """Calculate PSNR, SSIM, and LPIPS for a pair of images."""
    res = {'psnr': 0.0, 'ssim': 0.0, 'lpips': 0.0}
    
    # PSNR & SSIM
    if skimage_psnr is not None and skimage_ssim is not None:
        try:
            if len(img1.shape) == 3:
                img1_gray = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
                img2_gray = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
            else:
                img1_gray = img1
                img2_gray = img2
            
            res['psnr'] = skimage_psnr(img1, img2, data_range=255)
            res['ssim'] = skimage_ssim(img1_gray, img2_gray, data_range=255)
        except Exception as e:
            print(f"Error calculating PSNR/SSIM: {e}")

    # LPIPS
    if lpips_fn is not None and torch is not None:
        try:
            # Ensure 3 channels
            if len(img1.shape) == 2 or img1.shape[2] == 1:
                img1_rgb = cv2.cvtColor(img1, cv2.COLOR_GRAY2BGR)
                img2_rgb = cv2.cvtColor(img2, cv2.COLOR_GRAY2BGR)
            else:
                img1_rgb = img1
                img2_rgb = img2
                
            # Convert to tensor with shape (1,3,H,W) in [-1,1]
            img1_t = torch.from_numpy(img1_rgb).permute(2, 0, 1).unsqueeze(0).float().to(device) / 255.0 * 2 - 1
            img2_t = torch.from_numpy(img2_rgb).permute(2, 0, 1).unsqueeze(0).float().to(device) / 255.0 * 2 - 1
            
            with torch.no_grad():
                dist = lpips_fn(img1_t, img2_t)
            res['lpips'] = dist.item()
        except Exception as e:
            print(f"Error calculating LPIPS: {e}")
        
    return res


def collect_vmaf_data(
    repo_root: str,
    game: str,
    base_game: str,
    bandwidths: List[str],
    labels: List[str],
    total_frames: int,
    metrics_cache: Dict[tuple, Dict],
    lpips_model=None,
    device='cpu'
) -> None:
    """Collect VMAF data for all experiments and populate the cache."""
    if len(bandwidths) != len(labels):
        print("bandwidths and labels must have the same length")
        sys.exit(1)

    print(f"[INFO] Collecting data for {game}...")
    
    for bandwidth_base, label in zip(bandwidths, labels):
        # Construct game-specific bandwidth label
        bandwidth = f"{bandwidth_base}_{game}"
        
        ref_folder, dst_folder = resolve_paths_for_experiment(repo_root, game, bandwidth)

        if not os.path.isdir(ref_folder):
            print(f"[ERROR] Reference folder not found: {ref_folder}")
            continue
        if not os.path.isdir(dst_folder):
            print(f"[ERROR] Destination folder not found: {dst_folder}")
            continue

        # Check if already in cache
        cache_key = (game, bandwidth)
        if cache_key in metrics_cache:
            print(f"[INFO] Using cached data for {game} @ {bandwidth}")
            continue

        print(f"[INFO] Computing metrics for {game} @ {bandwidth}...")
        result = compute_metrics_per_frame(ref_folder, dst_folder, lpips_model, device)
        
        # Extract bandwidth from logs
        target_bandwidth = parse_bandwidth_from_label(bandwidth_base, label)
        
        if target_bandwidth is not None:
             actual_bandwidth = target_bandwidth
        else:
             actual_bandwidth = parse_bandwidth_from_logs(bandwidth, dst_folder)
        
        if actual_bandwidth is None:
            print(f"[WARN] Could not extract bandwidth for {game} @ {bandwidth}, skipping.")
            continue
        
        # Store in cache
        vmaf_scores = result["vmaf_scores"]
        psnr_scores = result.get("psnr_scores", [])
        ssim_scores = result.get("ssim_scores", [])
        lpips_scores = result.get("lpips_scores", [])
        
        avg_vmaf = float(np.mean(vmaf_scores)) if vmaf_scores else 0.0
        avg_psnr = float(np.mean(psnr_scores)) if psnr_scores else 0.0
        avg_ssim = float(np.mean(ssim_scores)) if ssim_scores else 0.0
        avg_lpips = float(np.mean(lpips_scores)) if lpips_scores else 0.0
        
        missing = int(result.get("missing_count", 0))
        ref_count = int(result.get("ref_count", 0))
        loss_pct = (missing / ref_count * 100.0) if ref_count > 0 else 0.0
        
        metrics_cache[cache_key] = {
            "avg_vmaf": avg_vmaf,
            "avg_psnr": avg_psnr,
            "avg_ssim": avg_ssim,
            "avg_lpips": avg_lpips,
            "loss_pct": loss_pct,
            "missing": missing,
            "ref_count": ref_count,
            "bandwidth": actual_bandwidth,
            "vmaf_scores": vmaf_scores,
            "psnr_scores": psnr_scores,
            "ssim_scores": ssim_scores,
            "lpips_scores": lpips_scores,
            "frame_indices": result["frame_indices"],
        }
        
        print(f"{label}: VMAF={avg_vmaf:.2f}, PSNR={avg_psnr:.2f}, SSIM={avg_ssim:.3f}, LPIPS={avg_lpips:.3f}, loss={missing}/{ref_count} ({loss_pct:.2f}%)")


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


def compute_metrics_per_frame(ref_folder: str, dst_folder: str, lpips_model=None, device='cpu') -> Dict[str, List[float]]:
    """Compute per-frame VMAF, PSNR, SSIM, LPIPS between PNG frames in ref_folder and dst_folder.

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
    psnr_scores: List[float] = []
    ssim_scores: List[float] = []
    lpips_scores: List[float] = []
    frame_indices: List[int] = []

    for frame_name in tqdm(common_frames, desc="Processing frames"):
        ref_path = os.path.join(ref_folder, frame_name)
        dst_path = os.path.join(dst_folder, frame_name)

        # Read images for PSNR/SSIM/LPIPS
        ref_img = cv2.imread(ref_path)
        dst_img = cv2.imread(dst_path)
        
        if ref_img is None or dst_img is None:
            continue
        
        # Calculate PSNR, SSIM, LPIPS
        metrics = calculate_psnr_ssim_lpips(ref_img, dst_img, lpips_model, device)
        psnr_scores.append(metrics['psnr'])
        ssim_scores.append(metrics['ssim'])
        lpips_scores.append(metrics['lpips'])

        # VMAF calculation via ffmpeg
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
                vmaf_scores.append(0.0)
            else:
                try:
                    with open(json_tmp.name) as f:
                        data = json.load(f)
                    score = data["pooled_metrics"]["vmaf"]["mean"]
                    vmaf_scores.append(score)
                except Exception as e:
                    print(f"[Parse ERROR] {frame_name}: {e}")
                    vmaf_scores.append(0.0)

        # Get frame index
        base = os.path.splitext(frame_name)[0]
        try:
            frame_idx = int(base)
        except ValueError:
            continue
        frame_indices.append(frame_idx)

    return {
        "vmaf_scores": vmaf_scores,
        "psnr_scores": psnr_scores,
        "ssim_scores": ssim_scores,
        "lpips_scores": lpips_scores,
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

    for i, ((bitrate, result), label) in enumerate(zip(all_results, labels)):
        marker = next(marker_cycle)
        color = COLORS[i % len(COLORS)]
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
            s=30,
            alpha=0.9,
            marker=marker,
            label=legend_label,
            facecolor=color,
            edgecolor='black',
            linewidth=0.5,
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
    color_vmaf = COLORS[1]
    color_loss = COLORS[3]

    # Average VMAF: bars with thick border
    ax1.set_xlabel("Bandwidth (Mbps)", fontsize=14)
    ax1.set_ylabel("Average VMAF", color="black", fontsize=14)
    ax1.set_ylabel("VMAF Score (0-100)", color="black", fontsize=14)
    ax1.tick_params(axis="y", labelcolor="black")

    # VMAF bars: one bar per bandwidth on the left Y-axis with thick border
    bar_width = 0.6
    for bw_val, vmaf_val, label in zip(bw, vmaf, clean_labels):
        ax1.bar(
            bw_val,
            vmaf_val,
            width=bar_width,
            color=color_vmaf,
            alpha=1.0,
            edgecolor="black",
            linewidth=1,
            hatch=HATCHES[1],
            label=f"{label} VMAF",
        )

    ax2 = ax1.twinx()
    ax2.set_ylabel("Frame Loss Percentage (%)", color="black", fontsize=14)
    ax2.tick_params(axis="y", labelcolor="black")

    # Frame loss scatter: dark markers at each bandwidth, with connecting dashed line
    ax2.scatter(
        bw,
        loss,
        color=color_loss,
        marker="^",
        s=70,
        label="Frame Loss Percentage",
        zorder=10
    )
    ax2.plot(
        bw,
        loss,
        color=color_loss,
        linestyle="--",
        linewidth=1.2,
        zorder=10
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

    color_vmaf = "black"
    color_loss = COLORS[3]

    ax1.set_xlabel("Bandwidth (Mbps)", fontsize=14)
    ax1.set_ylabel("VMAF Score (0-100)", color="black", fontsize=14)
    ax1.tick_params(axis="y", labelcolor="black")

    # Grouped bars (one per game per bandwidth), differentiated by hatch
    if n_bw > 1:
        step = float(np.min(np.diff(all_bw)))
    else:
        step = 1.0
    group_width = min(0.8 * step, 0.8)
    bar_width = group_width / max(n_games, 1)

    # hatches = ["", "//", "xx", "..", "||", "\\\\", "oo", "**"] # using global HATCHES instead
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
            color=COLORS[gi % len(COLORS)],
            alpha=1.0,
            edgecolor="black",
            linewidth=1,
            hatch=HATCHES[gi % len(HATCHES)],
            label=f"{stats['game']} VMAF",
        )

    ax2 = ax1.twinx()
    ax2.set_ylabel("Frame Loss Percentage (%)", color="black", fontsize=14)
    ax2.tick_params(axis="y", labelcolor="black")

    # Frame loss: dark markers + dashed line per game, with small horizontal offset per game
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
            zorder=10
        )
        # Connect the offset points with a dashed line
        ax2.plot(
            all_bw[valid] + offset,
            loss_mat[gi, valid],
            color=color_loss,
            linestyle="--",
            linewidth=1.0,
            alpha=0.9,
            zorder=10
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


def compare_multiple_destinations_from_cache(
    repo_root: str,
    game: str,
    bandwidths: List[str],
    labels: List[str],
    total_frames: int,
    metrics_cache: Dict[tuple, Dict],
) -> None:
    """Generate per-frame VMAF scatterplot from cached data."""
    if len(bandwidths) != len(labels):
        print("bandwidths and labels must have the same length")
        sys.exit(1)

    all_results = []

    # Aggregated stats for bandwidth summary plot
    bandwidth_values = []
    avg_vmafs = []
    loss_pcts = []
    summary_labels = []
    summary_markers = []

    for i, bandwidth_base in enumerate(bandwidths):
        label = labels[i]
        # Construct game-specific bandwidth label
        bandwidth = f"{bandwidth_base}_{game}"
        key = (game, bandwidth)
        
        if key not in metrics_cache:
            print(f"[WARN] No cached data for {game} @ {bandwidth}, skipping.")
            continue
            
        data = metrics_cache[key]
        vmaf_scores = data["vmaf_scores"]
        frame_indices = data["frame_indices"]
        target_bw = parse_bandwidth_from_label(bandwidth_base, label)
        if target_bw is not None:
            actual_bandwidth = target_bw
        else:
            actual_bandwidth = data["bandwidth"]
        
        if actual_bandwidth is None:
            print(f"[WARN] No bandwidth data for {game} @ {bandwidth}, skipping.")
            continue
            
        # Create result dict for plotting
        result = {
            "vmaf_scores": vmaf_scores,
            "frame_indices": frame_indices,
            "bandwidth": actual_bandwidth,
            "missing_count": data["missing"],
            "ref_count": data["ref_count"],
        }
        all_results.append((bandwidth, result, label))
        
        # Store aggregate stats for bandwidth summary plot
        avg_vmaf = data["avg_vmaf"]
        loss_pct = data["loss_pct"]
        
        bandwidth_values.append(actual_bandwidth)
        avg_vmafs.append(avg_vmaf)
        loss_pcts.append(loss_pct)
        summary_labels.append(label)
        summary_markers.append("o")  # Default marker
        
        print(f"{label}: avg VMAF={avg_vmaf:.2f}, frame loss={data['missing']}/{data['ref_count']} ({loss_pct:.2f}%)")

    if not all_results:
        print("No valid cached data to plot.")
        return

    plt.figure(figsize=(14, 7))

    # Cycle different marker shapes so each experiment is visually distinct
    markers = ["o", "s", "D", "^", "v", "P", "X", "*"]
    marker_cycle = itertools.cycle(markers)

    for i, (bitrate, result, label) in enumerate(all_results):
        marker = next(marker_cycle)
        color = COLORS[i % len(COLORS)]
        frame_indices = np.array(result["frame_indices"], dtype=int)
        vmaf_scores = np.array(result["vmaf_scores"], dtype=float)

        if frame_indices.size == 0:
            print(f"[WARN] No VMAF scores for {label}, skipping plot.")
            continue

        avg_vmaf = float(np.mean(vmaf_scores))

        # Plot scatter points (black and white styling)
        plt.scatter(frame_indices, vmaf_scores, marker=marker, s=40, 
                   facecolor=color, edgecolor='black', linewidth=0.6, alpha=0.9)

        # Fit and plot trend line
        if frame_indices.size > 1:
            coeffs = np.polyfit(frame_indices, vmaf_scores, 1)
            trend_line = np.polyval(coeffs, frame_indices)
            plt.plot(frame_indices, trend_line, color='black', linewidth=1.5, alpha=0.8)

            # Add label at the end of trend line
            last_idx = frame_indices[-1]
            last_vmaf = trend_line[-1]
            plt.text(last_idx, last_vmaf, label, fontsize=10, ha='left', va='bottom',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='black', alpha=0.9))

    plt.xlabel("Frame Number", fontsize=19)
    plt.ylabel("VMAF Score", fontsize=19)
    plt.title(f"Per-Frame VMAF for {game} Experiments", fontsize=16)
    plt.tick_params(axis='both', labelsize=14)
    plt.grid(True, linestyle='--', linewidth=0.7, alpha=0.7)
    plt.xlim(0, total_frames)
    plt.ylim(0, 100)

    plt.tight_layout()

    # Save figure
    graph_dir = os.path.join(repo_root, "acm_tomm_experiments", "graphs")
    try:
        os.makedirs(graph_dir, exist_ok=True)
        safe_game = game.replace(" ", "_")
        safe_bits = "_".join(bandwidths)
        safe_bits = safe_bits.replace("/", "_")
        out_name = f"vmaf_scatter_{safe_game}_{safe_bits}.png"
        out_path = os.path.join(graph_dir, out_name)
        plt.savefig(out_path, dpi=150)
        print(f"Saved VMAF scatter plot to: {out_path}")
    except Exception as e:
        print(f"[ERROR] Failed to save scatter plot: {e}")

    plt.close()

    # Generate bandwidth summary plot
    if bandwidth_values:
        plot_bandwidth_summary(
            repo_root, game, bandwidth_values, avg_vmafs, loss_pcts, summary_labels, summary_markers, bandwidths
        )


def compare_bandwidth_across_games_from_cache(
    repo_root: str,
    base_game: str,
    extra_games: List[str],
    bandwidths: List[str],
    labels: List[str],
    total_frames: int,
    metrics_cache: Dict[tuple, Dict],
) -> None:
    """Build a combined bandwidth summary plot across multiple games from cached data."""
    games = [base_game] + list(extra_games)

    per_game_stats = []
    all_bandwidths = set()

    for game in games:
        game_bandwidths = []
        game_vmafs = []
        game_losses = []

        for bandwidth_base, label in zip(bandwidths, labels):
            # Construct game-specific bandwidth label
            bandwidth = f"{bandwidth_base}_{game}"

            key = (game, bandwidth)
            if key not in metrics_cache:
                print(f"[WARN] No cached data for {game} @ {bandwidth}, skipping.")
                continue
                
            data = metrics_cache[key]
            avg_vmaf = data["avg_vmaf"]
            loss_pct = data["loss_pct"]
            target_bw = parse_bandwidth_from_label(bandwidth_base, label)
            if target_bw is not None:
                bw_value = target_bw
            else:
                bw_value = data["bandwidth"]
            
            if bw_value is None:
                print(f"[WARN] No bandwidth data for {game} @ {bandwidth}, skipping.")
                continue

            game_bandwidths.append(bw_value)
            game_vmafs.append(avg_vmaf)
            game_losses.append(loss_pct)
            all_bandwidths.add(bw_value)

        if game_bandwidths:
            per_game_stats.append((game, game_bandwidths, game_vmafs, game_losses))

    if not per_game_stats:
        print("No valid cached data for multi-game summary plot.")
        return

    # Sort bandwidths for consistent ordering
    sorted_bandwidths = sorted(all_bandwidths)
    x_positions = np.arange(len(sorted_bandwidths))
    bar_width = 0.8 / len(per_game_stats)  # Distribute bars evenly

    plt.figure(figsize=(14, 7))

    for i, (game, game_bws, game_vmafs, game_losses) in enumerate(per_game_stats):
        # Find positions for this game's data
        game_positions = []
        game_vmaf_at_positions = []
        for bw in sorted_bandwidths:
            if bw in game_bws:
                idx = game_bws.index(bw)
                game_positions.append(x_positions[sorted_bandwidths.index(bw)] + i * bar_width)
                game_vmaf_at_positions.append(game_vmafs[idx])

        # Plot bars for this game
        bars = plt.bar(game_positions, game_vmaf_at_positions, bar_width,
                      label=game, edgecolor='black', linewidth=0.9, 
                      color=COLORS[i % len(COLORS)], hatch=HATCHES[i % len(HATCHES)])

        # Add value labels on bars
        for bar, vmaf in zip(bars, game_vmaf_at_positions):
            plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                    f'{vmaf:.1f}', ha='center', va='bottom', fontsize=9)

    plt.xlabel("Bandwidth (Mbps)", fontsize=19)
    plt.ylabel("Average VMAF Score", fontsize=19)
    plt.title(f"VMAF vs Bandwidth Across Games", fontsize=16)
    plt.xticks(x_positions + bar_width * len(per_game_stats) / 2, 
               [f'{bw:.1f}' for bw in sorted_bandwidths], fontsize=14)
    plt.tick_params(axis='both', labelsize=14)
    plt.grid(True, linestyle='--', linewidth=0.7, alpha=0.7)
    plt.legend(fontsize=12)
    plt.ylim(0, 100)

    plt.tight_layout()

    # Save figure
    graph_dir = os.path.join(repo_root, "acm_tomm_experiments", "graphs")
    try:
        os.makedirs(graph_dir, exist_ok=True)
        safe_games = "_".join(games)
        safe_bits = "_".join(bandwidths)
        safe_bits = safe_bits.replace("/", "_")
        out_name = f"vmaf_bandwidth_summary_multi_{safe_games}_{safe_bits}.png"
        out_path = os.path.join(graph_dir, out_name)
        plt.savefig(out_path, dpi=150)
        print(f"Saved multi-game VMAF/bandwidth summary plot to: {out_path}")
    except Exception as e:
        print(f"[ERROR] Failed to save multi-game summary plot: {e}")

    plt.close()


def plot_all_metrics_summary(
    repo_root: str,
    games: List[str],
    bandwidths: List[str],
    labels: List[str],
    metrics_cache: Dict[tuple, Dict],
) -> None:
    """Create a bar plot showing VMAF, PSNR, SSIM, LPIPS for each game/bandwidth."""
    
    # Collect data for all games
    rows = []
    for game in games:
        for bandwidth_base, label in zip(bandwidths, labels):
            bandwidth = f"{bandwidth_base}_{game}"
            key = (game, bandwidth)
            if key not in metrics_cache:
                continue
            data = metrics_cache[key]
            target_bw = parse_bandwidth_from_label(bandwidth_base, label)
            bw_value = target_bw if target_bw is not None else data.get("bandwidth", 0)
            rows.append({
                "game": game,
                "bandwidth": bw_value,
                "label": label,
                "vmaf": data.get("avg_vmaf", 0),
                "psnr": data.get("avg_psnr", 0),
                "ssim": data.get("avg_ssim", 0),
                "lpips": data.get("avg_lpips", 0),
            })
    
    if not rows:
        print("[WARN] No data for all-metrics summary plot.")
        return
    
    # Create 2x2 subplot for each metric
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    metrics_info = [
        ("vmaf", "VMAF Score", (0, 100), axes[0, 0]),
        ("psnr", "PSNR (dB)", (0, 50), axes[0, 1]),
        ("ssim", "SSIM", (0, 1), axes[1, 0]),
        ("lpips", "LPIPS (lower is better)", (0, 0.5), axes[1, 1]),
    ]
    
    sorted_bandwidths = sorted(set(r["bandwidth"] for r in rows))
    x_positions = np.arange(len(sorted_bandwidths))
    bar_width = 0.8 / len(games)
    
    for metric_key, metric_label, ylim, ax in metrics_info:
        for i, game in enumerate(games):
            game_rows = [r for r in rows if r["game"] == game]
            positions = []
            values = []
            for bw in sorted_bandwidths:
                matching = [r for r in game_rows if r["bandwidth"] == bw]
                if matching:
                    positions.append(x_positions[sorted_bandwidths.index(bw)] + i * bar_width)
                    values.append(matching[0][metric_key])
            
            bars = ax.bar(positions, values, bar_width, label=game,
                         edgecolor='black', linewidth=0.9,
                         color=COLORS[i % len(COLORS)], hatch=HATCHES[i % len(HATCHES)])
        
        ax.set_xlabel("Bandwidth (Mbps)", fontsize=12)
        ax.set_ylabel(metric_label, fontsize=12)
        ax.set_title(f"{metric_label} vs Bandwidth", fontsize=14)
        ax.set_xticks(x_positions + bar_width * len(games) / 2)
        ax.set_xticklabels([f'{bw:.0f}' for bw in sorted_bandwidths])
        ax.set_ylim(ylim)
        ax.grid(True, linestyle='--', linewidth=0.5, alpha=0.7)
        ax.legend(fontsize=9)
    
    plt.tight_layout()
    
    # Save figure
    graph_dir = os.path.join(repo_root, "acm_tomm_experiments", "graphs")
    os.makedirs(graph_dir, exist_ok=True)
    safe_games = "_".join(games)
    out_path = os.path.join(graph_dir, f"all_metrics_summary_{safe_games}.png")
    plt.savefig(out_path, dpi=150)
    print(f"Saved all-metrics summary plot to: {out_path}")
    plt.close()


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
        "--bandwidths",
        nargs="+",
        required=True,
        help="Bandwidth values (e.g., 2Mbit 4Mbit 6Mbit). Will be mapped to each game automatically.",
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
    parser.add_argument(
        "--skip-collection",
        action="store_true",
        help="Skip data collection and only generate plots from existing vmaf_metrics.csv",
    )

    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.abspath(os.path.join(__file__, "..")))

    if args.labels and len(args.labels) != len(args.bandwidths):
        print("If provided, --labels must have the same length as --bandwidths")
        sys.exit(1)

    labels = args.labels if args.labels else args.bandwidths

    # Split games list: first game is the base for per-frame and single-game plots
    base_game = args.games[0]
    extra_games = args.games[1:] if len(args.games) > 1 else []

    # Initialize cache and collect data
    csv_path = os.path.join(repo_root, "acm_tomm_experiments", "graphs", "vmaf_metrics.csv")
    
    if args.skip_collection:
        if not os.path.exists(csv_path):
            print(f"[ERROR] No cache file found at {csv_path}. Cannot skip collection.")
            sys.exit(1)
        metrics_cache = load_metrics_cache(csv_path)
        print(f"[INFO] Loaded existing metrics cache from {csv_path}")
    else:
        # Phase 1: Collect VMAF data and populate cache
        print("[INFO] Phase 1: Collecting VMAF data...")
        metrics_cache = {}
        
        # Initialize LPIPS model if available
        lpips_model = None
        device = 'cpu'
        if lpips_lib is not None and torch is not None:
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
            try:
                lpips_model = lpips_lib.LPIPS(net='alex').to(device)
                print(f"[INFO] LPIPS model initialized on {device}")
            except Exception as e:
                print(f"[WARN] Could not initialize LPIPS model: {e}")
                lpips_model = None
        else:
            print("[WARN] LPIPS/torch not available, LPIPS will be 0.0")
        
        # Collect data for base game
        collect_vmaf_data(
            repo_root=repo_root,
            game=base_game,
            base_game=base_game,
            bandwidths=args.bandwidths,
            labels=labels,
            total_frames=args.total_frames,
            metrics_cache=metrics_cache,
            lpips_model=lpips_model,
            device=device,
        )
        
        # Collect data for extra games
        if extra_games:
            for game in extra_games:
                collect_vmaf_data(
                    repo_root=repo_root,
                    game=game,
                    base_game=base_game,
                    bandwidths=args.bandwidths,
                    labels=labels,
                    total_frames=args.total_frames,
                    metrics_cache=metrics_cache,
                    lpips_model=lpips_model,
                    device=device,
                )
        
        # Save the collected data
        save_metrics_cache(csv_path, metrics_cache)
        print(f"[INFO] Data collection complete. Saved {len(metrics_cache)} entries to {csv_path}")

    # Phase 2: Generate all plots from cached data
    print("[INFO] Phase 2: Generating plots from cached data...")
    
    # Generate plots for base game
    compare_multiple_destinations_from_cache(
        repo_root=repo_root,
        game=base_game,
        bandwidths=args.bandwidths,
        labels=labels,
        total_frames=args.total_frames,
        metrics_cache=metrics_cache,
    )
    
    if extra_games:
        compare_bandwidth_across_games_from_cache(
            repo_root=repo_root,
            base_game=base_game,
            extra_games=extra_games,
            bandwidths=args.bandwidths,
            labels=labels,
            total_frames=args.total_frames,
            metrics_cache=metrics_cache,
        )
    
    # Generate all-metrics summary plot (VMAF, PSNR, SSIM, LPIPS)
    all_games = [base_game] + list(extra_games) if extra_games else [base_game]
    plot_all_metrics_summary(
        repo_root=repo_root,
        games=all_games,
        bandwidths=args.bandwidths,
        labels=labels,
        metrics_cache=metrics_cache,
    )
    
    print("[INFO] All plots generated successfully!")


if __name__ == "__main__":
    main()
