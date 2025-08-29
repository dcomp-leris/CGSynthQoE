#!/usr/bin/env python3
"""
Retransmitted Frames Loss Comparison Script
------------------------------------------
This script compares frames with retransmissions against reference frames.
It handles retransmitted frames (e.g., frame_000002_r95.jpg) by averaging
their quality metrics against the corresponding reference frame.

Usage:
    python aligned_loss_comparison.py [--output OUTPUT_PATH] [--metrics METRIC1 METRIC2 ...]
"""

import os
import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import argparse
from pathlib import Path
from collections import defaultdict
import cv2
from skimage.metrics import structural_similarity as ssim
from skimage.metrics import peak_signal_noise_ratio as psnr
try:
    import lpips
    import torch
    LPIPS_AVAILABLE = True
except ImportError:
    LPIPS_AVAILABLE = False
    print("Warning: LPIPS not available. Install with: pip install lpips torch")

try:
    import vmaf
    VMAF_AVAILABLE = True
except ImportError:
    VMAF_AVAILABLE = False
    print("Warning: VMAF not available. Install with: pip install vmaf")




def parse_frame_filename(filename):
    """Parse frame filename to extract frame number and retransmission info.
    
    Examples:
        frame_000002.jpg -> (2, None)
        frame_000002_r95.jpg -> (2, 95)
    """
    # Pattern for regular frames: frame_XXXXXX.jpg
    regular_pattern = r'frame_(\d+)\.jpg'
    # Pattern for retransmitted frames: frame_XXXXXX_rYY.jpg
    retrans_pattern = r'frame_(\d+)_r(\d+)\.jpg'
    
    retrans_match = re.match(retrans_pattern, filename)
    if retrans_match:
        frame_num = int(retrans_match.group(1))
        retrans_num = int(retrans_match.group(2))
        return frame_num, retrans_num
    
    regular_match = re.match(regular_pattern, filename)
    if regular_match:
        frame_num = int(regular_match.group(1))
        return frame_num, None
    
    return None, None


def load_image(image_path):
    """Load image using OpenCV."""
    img = cv2.imread(image_path)
    if img is not None:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return img


def calculate_psnr(img1, img2):
    """Calculate PSNR between two images."""
    try:
        return psnr(img1, img2, data_range=255)
    except Exception as e:
        print(f"Error calculating PSNR: {e}")
        return 0.0


def calculate_ssim(img1, img2):
    """Calculate SSIM between two images."""
    try:
        # Convert to grayscale for SSIM calculation
        gray1 = cv2.cvtColor(img1, cv2.COLOR_RGB2GRAY) if len(img1.shape) == 3 else img1
        gray2 = cv2.cvtColor(img2, cv2.COLOR_RGB2GRAY) if len(img2.shape) == 3 else img2
        return ssim(gray1, gray2, data_range=255)
    except Exception as e:
        print(f"Error calculating SSIM: {e}")
        return 0.0


def calculate_lpips(img1, img2, lpips_model=None):
    """Calculate LPIPS between two images."""
    if not LPIPS_AVAILABLE or lpips_model is None:
        return 0.0
    
    try:
        # Convert to tensor and normalize
        tensor1 = torch.from_numpy(img1).permute(2, 0, 1).float() / 255.0 * 2.0 - 1.0
        tensor2 = torch.from_numpy(img2).permute(2, 0, 1).float() / 255.0 * 2.0 - 1.0
        tensor1 = tensor1.unsqueeze(0)
        tensor2 = tensor2.unsqueeze(0)
        
        with torch.no_grad():
            distance = lpips_model(tensor1, tensor2)
        return distance.item()
    except Exception as e:
        print(f"Error calculating LPIPS: {e}")
        return 0.0


def calculate_vmaf(img1, img2):
    """Calculate VMAF between two images (simplified version)."""
    # VMAF is complex to implement properly for single frames
    # For now, return a placeholder based on PSNR and SSIM
    psnr_val = calculate_psnr(img1, img2)
    ssim_val = calculate_ssim(img1, img2)
    # Simple approximation: combine PSNR and SSIM
    vmaf_approx = min(100, max(0, (psnr_val * 2 + ssim_val * 50)))
    return vmaf_approx


def organize_frames_by_number(frame_dir):
    """Organize frames by frame number, grouping retransmissions.
    
    Returns:
        dict: {frame_number: [(filename, retrans_num), ...]}
    """
    frames_by_number = defaultdict(list)
    
    if not os.path.exists(frame_dir):
        print(f"Warning: Directory not found: {frame_dir}")
        return frames_by_number
    
    for filename in os.listdir(frame_dir):
        if filename.endswith('.jpg'):
            frame_num, retrans_num = parse_frame_filename(filename)
            if frame_num is not None:
                frames_by_number[frame_num].append((filename, retrans_num))
    
    # Sort retransmissions by retrans_num
    for frame_num in frames_by_number:
        frames_by_number[frame_num].sort(key=lambda x: x[1] if x[1] is not None else -1)
    
    return frames_by_number


def calculate_frame_metrics(loss_frame_path, ref_frame_path, lpips_model=None):
    """Calculate all metrics between two frames."""
    loss_img = load_image(loss_frame_path)
    ref_img = load_image(ref_frame_path)
    
    if loss_img is None or ref_img is None:
        return None
    
    # Resize images to match if needed
    if loss_img.shape != ref_img.shape:
        ref_img = cv2.resize(ref_img, (loss_img.shape[1], loss_img.shape[0]))
    
    metrics = {
        'PSNR': calculate_psnr(ref_img, loss_img),
        'SSIM': calculate_ssim(ref_img, loss_img),
        'LPIPS': calculate_lpips(ref_img, loss_img, lpips_model),
        'VMAF': calculate_vmaf(ref_img, loss_img)
    }
    
    return metrics


def extract_retransmission_metrics(loss_frames_dir, ref_frames_dir):
    """Extract metrics comparing retransmitted frames with reference frames."""
    # Initialize LPIPS model if available
    lpips_model = None
    if LPIPS_AVAILABLE:
        try:
            lpips_model = lpips.LPIPS(net='alex')
            lpips_model.eval()
        except Exception as e:
            print(f"Warning: Could not initialize LPIPS model: {e}")
    
    # Organize frames
    loss_frames = organize_frames_by_number(loss_frames_dir)
    ref_frames = organize_frames_by_number(ref_frames_dir)
    
    print(f"Found {len(loss_frames)} frame numbers in loss directory")
    print(f"Found {len(ref_frames)} frame numbers in reference directory")
    
    all_metrics = []
    
    for frame_num in sorted(loss_frames.keys()):
        if frame_num not in ref_frames:
            print(f"Skipping frame {frame_num:06d}: no reference frame")
            continue
        
        # Get reference frame (should be only one)
        ref_frame_info = ref_frames[frame_num]
        if len(ref_frame_info) != 1:
            print(f"Warning: Expected 1 reference frame for {frame_num:06d}, got {len(ref_frame_info)}")
            continue
        
        ref_filename = ref_frame_info[0][0]
        ref_path = os.path.join(ref_frames_dir, ref_filename)
        
        # Get all loss frames for this frame number (including retransmissions)
        loss_frame_infos = loss_frames[frame_num]
        frame_metrics_list = []
        
        for loss_filename, retrans_num in loss_frame_infos:
            loss_path = os.path.join(loss_frames_dir, loss_filename)
            
            metrics = calculate_frame_metrics(loss_path, ref_path, lpips_model)
            if metrics is not None:
                metrics['Frame'] = frame_num
                metrics['Filename'] = loss_filename
                metrics['Retransmission'] = retrans_num
                frame_metrics_list.append(metrics)
        
        if frame_metrics_list:
            if len(frame_metrics_list) == 1:
                # Single frame (no retransmissions)
                all_metrics.append(frame_metrics_list[0])
            else:
                # Multiple retransmissions - calculate average
                avg_metrics = {
                    'Frame': frame_num,
                    'Filename': f"frame_{frame_num:06d}_avg",
                    'Retransmission': 'avg',
                    'PSNR': np.mean([m['PSNR'] for m in frame_metrics_list]),
                    'SSIM': np.mean([m['SSIM'] for m in frame_metrics_list]),
                    'LPIPS': np.mean([m['LPIPS'] for m in frame_metrics_list]),
                    'VMAF': np.mean([m['VMAF'] for m in frame_metrics_list])
                }
                all_metrics.append(avg_metrics)
                print(f"Frame {frame_num:06d}: averaged {len(frame_metrics_list)} retransmissions")
    
    return pd.DataFrame(all_metrics)


def align_datasets_for_comparison(metrics_dict):
    """Align datasets to only include frames present in both datasets."""
    # For this use case, we only have one dataset (Loss1 vs Reference)
    # So we just return the metrics as-is
    return metrics_dict


def calculate_averages(metrics_dict):
    """Calculate average values for each metric across all scenarios."""
    averages = {}
    
    for scenario, df in metrics_dict.items():
        averages[scenario] = {
            'PSNR': df['PSNR'].mean(),
            'SSIM': df['SSIM'].mean(),
            'LPIPS': df['LPIPS'].mean(),
            'VMAF': df['VMAF'].mean()
        }
    
    return averages


def plot_multi_game_comparison(all_games_metrics, all_games_averages, selected_metrics=None, output_path=None):
    """Generate comparison plots for all games in a single figure."""
    
    # Define all available metrics
    all_metrics = {
        'PSNR': ('PSNR', '(dB)', 'Higher is better'),
        'SSIM': ('SSIM', '', 'Higher is better'),
        'LPIPS': ('LPIPS', '', 'Lower is better'),
        'VMAF': ('VMAF', '', 'Higher is better')
    }
    
    # Use selected metrics or default to all
    if selected_metrics is None:
        selected_metrics = ['PSNR', 'SSIM', 'LPIPS', 'VMAF']
    
    # Filter metrics based on selection
    metrics = []
    metric_units = []
    metric_descriptions = []
    
    for metric in selected_metrics:
        if metric in all_metrics:
            name, unit, desc = all_metrics[metric]
            metrics.append(name)
            metric_units.append(unit)
            metric_descriptions.append(desc)
    
    if not metrics:
        print("Error: No valid metrics selected")
        return
    
    print(f"Plotting multi-game comparison metrics: {', '.join(selected_metrics)}")
    
    # Create dynamic subplot layout
    num_metrics = len(metrics)
    if num_metrics == 1:
        fig, axes = plt.subplots(1, 1, figsize=(12, 8))
        axes = [axes]
    elif num_metrics == 2:
        fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    elif num_metrics == 3:
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        axes = axes.flatten()[:3]
    else:  # 4 metrics
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        axes = axes.flatten()
    
    fig.suptitle('Loss0 vs Loss1 Quality Metrics Comparison - All Games (4Mbit)', 
                 fontsize=16, fontweight='bold')
    
    # Define colors for each game
    game_colors = {
        'Forza': ['#1f77b4', '#aec7e8'],      # Blue shades
        'Fortnite': ['#ff7f0e', '#ffbb78'],   # Orange shades  
        'Kombat': ['#2ca02c', '#98df8a']      # Green shades
    }
    
    for idx, metric in enumerate(metrics):
        ax = axes[idx]
        
        ax.set_title(f'{metric} {metric_units[idx]}\n({metric_descriptions[idx]})', 
                    fontsize=12, fontweight='bold')
        ax.set_xlabel('Frame Number')
        ax.set_ylabel(f'{metric} {metric_units[idx]}')
        ax.grid(True, alpha=0.3)
        
        # Plot each game
        for game_name in ['Forza', 'Fortnite', 'Kombat']:
            if game_name in all_games_metrics:
                game_metrics = all_games_metrics[game_name]
                game_averages = all_games_averages[game_name]
                colors = game_colors[game_name]
                
                for loss_idx, (scenario_key, loss_name) in enumerate([(f'4Mbit_Loss0_{game_name}', 'Loss0'), (f'4Mbit_Loss1_{game_name}', 'Loss1')]):
                    if scenario_key in game_metrics:
                        df = game_metrics[scenario_key]
                        avg_val = game_averages[scenario_key][metric]
                        
                        color = colors[loss_idx]
                        linestyle = '-' if loss_name == 'Loss0' else '--'
                        alpha = 0.7
                        
                        ax.plot(df['Frame'], df[metric], color=color, linestyle=linestyle, 
                               label=f"{game_name} {loss_name} (avg {avg_val:.2f})", 
                               linewidth=1.5, alpha=alpha, marker='o', markersize=3)
        
        # Set appropriate y-axis limits
        if metric == 'PSNR':
            ax.set_ylim(bottom=0)
        elif metric == 'SSIM':
            ax.set_ylim(0, 1)
        elif metric == 'LPIPS':
            ax.set_ylim(bottom=0)
        elif metric == 'VMAF':
            ax.set_ylim(0, 100)
        
        ax.legend(fontsize=8, loc='best')
    
    plt.tight_layout()
    
    # Save the plot
    if output_path is None:
        metrics_str = "_".join(selected_metrics)
        output_path = f"4Mbit_AllGames_loss0_loss1_frames_comparison_{metrics_str}.png"
    
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"\nMulti-game comparison plot saved to: {output_path}")


def plot_intersection_comparison(metrics_dict, averages, game_name, selected_metrics=None, output_path=None):
    """Generate comparison plots for retransmitted frames vs reference."""
    
    # Define all available metrics
    all_metrics = {
        'PSNR': ('PSNR', '(dB)', 'Higher is better'),
        'SSIM': ('SSIM', '', 'Higher is better'),
        'LPIPS': ('LPIPS', '', 'Lower is better'),
        'VMAF': ('VMAF', '', 'Higher is better')
    }
    
    # Use selected metrics or default to all
    if selected_metrics is None:
        selected_metrics = ['PSNR', 'SSIM', 'LPIPS', 'VMAF']
    
    # Filter metrics based on selection
    metrics = []
    metric_units = []
    metric_descriptions = []
    
    for metric in selected_metrics:
        if metric in all_metrics:
            name, unit, desc = all_metrics[metric]
            metrics.append(name)
            metric_units.append(unit)
            metric_descriptions.append(desc)
    
    if not metrics:
        print("Error: No valid metrics selected")
        return
    
    print(f"Plotting retransmission metrics: {', '.join(selected_metrics)}")
    
    # Create dynamic subplot layout
    num_metrics = len(metrics)
    if num_metrics == 1:
        fig, axes = plt.subplots(1, 1, figsize=(12, 8))
        axes = [axes]
    elif num_metrics == 2:
        fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    elif num_metrics == 3:
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        axes = axes.flatten()[:3]
    else:  # 4 metrics
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        axes = axes.flatten()
    
    fig.suptitle(f'0% Loss vs 1% Loss Quality Metrics Comparison (4Mbit - {game_name})', 
                 fontsize=16, fontweight='bold')
    
    for idx, metric in enumerate(metrics):
        ax = axes[idx]
        
        ax.set_title(f'{metric} {metric_units[idx]}\n({metric_descriptions[idx]})', 
                    fontsize=12, fontweight='bold')
        ax.set_xlabel('Frame Number')
        ax.set_ylabel(f'{metric} {metric_units[idx]}')
        ax.grid(True, alpha=0.3)
        
        # Plot Loss0 and Loss1 with different styles
        all_frames = []
        
        # Define colors for games
        game_colors = ['#1f77b4', '#aec7e8']  # Blue shades: darker for Loss0, lighter for Loss1
        
        for loss_idx, (scenario_key, loss_name) in enumerate([(f'4Mbit_Loss0_{game_name}', 'Loss0'), (f'4Mbit_Loss1_{game_name}', 'Loss1')]):
            if scenario_key in metrics_dict:
                df = metrics_dict[scenario_key]
                avg_val = averages[scenario_key][metric]
                
                # Use color schema
                color = game_colors[loss_idx]  # Different colors for Loss0 and Loss1
                linestyle = '-' if loss_name == 'Loss0' else '--'
                alpha = 0.8
                
                ax.plot(df['Frame'], df[metric], color=color, linestyle=linestyle, 
                       label=f"{loss_name} vs Reference (avg {avg_val:.3f})", 
                       linewidth=1.5, alpha=alpha, marker='o', markersize=5)
                
                all_frames.extend(df['Frame'].tolist())
        
        # Set appropriate y-axis limits
        if metric == 'PSNR':
            ax.set_ylim(bottom=0)
        elif metric == 'SSIM':
            ax.set_ylim(0, 1)
        elif metric == 'LPIPS':
            ax.set_ylim(bottom=0)
        elif metric == 'VMAF':
            ax.set_ylim(0, 100)
        
        # Set x-axis to show only actual frame numbers with some padding
        if all_frames:
            frame_numbers = sorted(set(all_frames))
            ax.set_xticks(frame_numbers[::max(1, len(frame_numbers)//10)])  # Show every 10th frame or all if <10
            ax.set_xlim(min(frame_numbers) - 1, max(frame_numbers) + 1)
        
        ax.legend(fontsize=10)
    
    plt.tight_layout()
    
    # Save the plot
    if output_path is None:
        metrics_str = "_".join(selected_metrics)
        output_path = f"4Mbit_{game_name}_loss0_loss1_frames_comparison_{metrics_str}.png"
    
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"\nLoss0 vs Loss1 comparison plot saved to: {output_path}")
    
    # Display summary statistics
    print("\n=== Loss0 vs Loss1 Summary Statistics ===")
    for scenario, avgs in averages.items():
        df = metrics_dict[scenario]
        print(f"\n{scenario} ({len(df)} frames):")
        for metric, avg_val in avgs.items():
            std_val = df[metric].std()
            min_val = df[metric].min()
            max_val = df[metric].max()
            print(f"  {metric}: avg={avg_val:.3f}, std={std_val:.3f}, min={min_val:.3f}, max={max_val:.3f}")


def main():
    """Main function to generate retransmitted frames vs reference comparison plots."""
    parser = argparse.ArgumentParser(description='Generate retransmitted frames vs reference quality metrics comparison')
    parser.add_argument('--game', '-g', type=str, choices=['Forza', 'Fortnite', 'Kombat'], default='Forza',
                        help='Game to analyze (default: Forza)')
    parser.add_argument('--all-games', action='store_true',
                        help='Generate comparison plot for all games in a single figure')
    parser.add_argument('--output', '-o', type=str, default=None,
                        help='Output path for the plot (default: auto-generated based on game)')
    parser.add_argument('--metrics', '-m', nargs='+', choices=['PSNR', 'SSIM', 'LPIPS', 'VMAF'], 
                       help='Metrics to plot (default: all metrics)', default=['PSNR', 'SSIM', 'LPIPS', 'VMAF'])
    parser.add_argument('--loss0-frames', type=str, default=None,
                        help='Path to loss0 frames directory (auto-generated if not specified)')
    parser.add_argument('--loss1-frames', type=str, default=None,
                        help='Path to loss1 frames directory (auto-generated if not specified)')
    parser.add_argument('--ref-frames', type=str, default=None,
                        help='Path to reference frames directory (auto-generated if not specified)')
    
    args = parser.parse_args()
    
    # Set up paths (relative to script directory)
    script_dir = Path(__file__).parent.parent  # Go up one level from tools/
    
    if args.all_games:
        # Process all games for multi-game comparison
        games = ['Forza', 'Fortnite', 'Kombat']
        all_games_metrics = {}
        all_games_averages = {}
        
        print("Processing all games for multi-game comparison...")
        print(f"Selected metrics: {', '.join(args.metrics)}")
        
        for game in games:
            print(f"\n=== Processing {game} ===")
            
            # Set up paths for this game
            loss0_frames_dir = script_dir / f'output_frames/4Mbit_Loss0_{game}/'
            loss1_frames_dir = script_dir / f'output_frames/4Mbit_Loss1_{game}/'
            ref_frames_dir = script_dir / f'output_frames/reference_video_{game}_1600x900_frames/'
            
            print(f"Loss0 frames directory: {loss0_frames_dir}")
            print(f"Loss1 frames directory: {loss1_frames_dir}")
            print(f"Reference frames directory: {ref_frames_dir}")
            
            # Check if directories exist
            if not all([loss0_frames_dir.exists(), loss1_frames_dir.exists(), ref_frames_dir.exists()]):
                print(f"Warning: Some directories not found for {game}, skipping...")
                continue
            
            # Extract metrics for this game
            print(f"Processing {game} Loss0 frames...")
            df_loss0 = extract_retransmission_metrics(str(loss0_frames_dir), str(ref_frames_dir))
            
            print(f"Processing {game} Loss1 frames...")
            df_loss1 = extract_retransmission_metrics(str(loss1_frames_dir), str(ref_frames_dir))
            
            if df_loss0.empty and df_loss1.empty:
                print(f"Warning: No metrics data extracted for {game}!")
                continue
            
            # Create metrics dictionary for this game
            game_metrics = {}
            if not df_loss0.empty:
                game_metrics[f'4Mbit_Loss0_{game}'] = df_loss0
                print(f"Extracted {game} Loss0 metrics for {len(df_loss0)} frames")
            if not df_loss1.empty:
                game_metrics[f'4Mbit_Loss1_{game}'] = df_loss1
                print(f"Extracted {game} Loss1 metrics for {len(df_loss1)} frames")
            
            # Calculate averages for this game
            game_averages = calculate_averages(game_metrics)
            
            # Store in overall dictionaries
            all_games_metrics[game] = game_metrics
            all_games_averages[game] = game_averages
        
        if not all_games_metrics:
            print("Error: No metrics data extracted for any game!")
            return
        
        # Generate multi-game plot
        plot_multi_game_comparison(all_games_metrics, all_games_averages, args.metrics, args.output)
        
        # Display summary statistics for all games
        print("\n=== Multi-Game Summary Statistics ===")
        for game, game_averages in all_games_averages.items():
            print(f"\n{game}:")
            for scenario, avgs in game_averages.items():
                game_metrics = all_games_metrics[game]
                df = game_metrics[scenario]
                print(f"  {scenario} ({len(df)} frames):")
                for metric, avg_val in avgs.items():
                    std_val = df[metric].std()
                    min_val = df[metric].min()
                    max_val = df[metric].max()
                    print(f"    {metric}: avg={avg_val:.3f}, std={std_val:.3f}, min={min_val:.3f}, max={max_val:.3f}")
    
    else:
        # Single game processing (original behavior)
        # Auto-generate paths if not specified
        if args.loss0_frames is None:
            args.loss0_frames = f'output_frames/4Mbit_Loss0_{args.game}/'
        if args.loss1_frames is None:
            args.loss1_frames = f'output_frames/4Mbit_Loss1_{args.game}/'
        if args.ref_frames is None:
            args.ref_frames = f'output_frames/reference_video_{args.game}_1600x900_frames/'
        
        loss0_frames_dir = script_dir / args.loss0_frames
        loss1_frames_dir = script_dir / args.loss1_frames
        ref_frames_dir = script_dir / args.ref_frames
        
        print(f"Loss0 frames directory: {loss0_frames_dir}")
        print(f"Loss1 frames directory: {loss1_frames_dir}")
        print(f"Reference frames directory: {ref_frames_dir}")
        
        if not loss0_frames_dir.exists():
            print(f"Error: Loss0 frames directory not found: {loss0_frames_dir}")
            return
        
        if not loss1_frames_dir.exists():
            print(f"Error: Loss1 frames directory not found: {loss1_frames_dir}")
            return
        
        if not ref_frames_dir.exists():
            print(f"Error: Reference frames directory not found: {ref_frames_dir}")
            return
        
        print("Extracting metrics for Loss0 and Loss1 vs reference...")
        print(f"Selected metrics: {', '.join(args.metrics)}")
        
        # Extract metrics for both Loss0 and Loss1
        print("\nProcessing Loss0 frames...")
        df_loss0 = extract_retransmission_metrics(str(loss0_frames_dir), str(ref_frames_dir))
        
        print("\nProcessing Loss1 frames...")
        df_loss1 = extract_retransmission_metrics(str(loss1_frames_dir), str(ref_frames_dir))
        
        if df_loss0.empty and df_loss1.empty:
            print("Error: No metrics data extracted!")
            return
        
        # Create metrics dictionary
        metrics_dict = {}
        if not df_loss0.empty:
            metrics_dict[f'4Mbit_Loss0_{args.game}'] = df_loss0
            print(f"Extracted Loss0 metrics for {len(df_loss0)} frames")
        if not df_loss1.empty:
            metrics_dict[f'4Mbit_Loss1_{args.game}'] = df_loss1
            print(f"Extracted Loss1 metrics for {len(df_loss1)} frames")
        
        # Calculate averages
        averages = calculate_averages(metrics_dict)
        
        # Generate plots
        plot_intersection_comparison(metrics_dict, averages, args.game, args.metrics, args.output)


if __name__ == "__main__":
    main()
