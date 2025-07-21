#!/usr/bin/env python3
"""
Loss0 vs Loss1 Metrics Comparison Script
----------------------------------------
This script compares video quality metrics (PSNR, SSIM, LPIPS, VMAF) between Loss0 and Loss1
scenarios across three games (Forza, Fortnite, Kombat) at 4Mbit bitrate.

The script generates plots with 6 lines showing:
- 4Mbit_Forza_Loss0 (avg ##)
- 4Mbit_Forza_Loss1 (avg ##)
- 4Mbit_Fortnite_Loss0 (avg ##)
- 4Mbit_Fortnite_Loss1 (avg ##)
- 4Mbit_Kombat_Loss0 (avg ##)
- 4Mbit_Kombat_Loss1 (avg ##)

Usage:
    python loss0_loss1_comparison.py [--output OUTPUT_PATH]

Author: CGSynth Project
"""

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import argparse
from pathlib import Path


def load_metrics_from_csv(csv_path):
    """Load metrics from a detailed_metrics.csv file."""
    try:
        df = pd.read_csv(csv_path)
        return df
    except Exception as e:
        print(f"Error loading metrics from {csv_path}: {e}")
        return None


def find_detailed_metrics_csv(scenario_dir, game, loss):
    """Find the detailed_metrics.csv file in a scenario directory."""
    expected_filename = f"4Mbit_Loss{loss}_{game}_detailed_metrics.csv"
    csv_path = os.path.join(scenario_dir, expected_filename)
    
    if os.path.exists(csv_path):
        return csv_path
    
    # Fallback: look for any detailed_metrics.csv file
    for file in os.listdir(scenario_dir):
        if file.endswith("_detailed_metrics.csv"):
            return os.path.join(scenario_dir, file)
    
    return None


def extract_game_loss_metrics(evaluation_dir, games, losses):
    """Extract metrics for all game-loss combinations."""
    all_metrics = {}
    
    for game in games:
        for loss in losses:
            scenario_dir = os.path.join(evaluation_dir, game, "loss", "4Mbit", f"4Mbit_Loss{loss}")
            
            if not os.path.exists(scenario_dir):
                print(f"Warning: Directory not found: {scenario_dir}")
                continue
            
            csv_path = find_detailed_metrics_csv(scenario_dir, game, loss)
            if not csv_path:
                print(f"Warning: No detailed_metrics.csv found in {scenario_dir}")
                continue
            
            df = load_metrics_from_csv(csv_path)
            if df is not None:
                key = f"4Mbit_{game}_Loss{loss}"
                all_metrics[key] = df
                print(f"Loaded {len(df)} frames for {key}")
            else:
                print(f"Failed to load metrics for {game} Loss{loss}")
    
    return all_metrics


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


def plot_loss_comparison(metrics_dict, averages, output_path=None):
    """Generate comparison plots for Loss0 vs Loss1 across games."""
    
    # Define colors for each game
    colors = {
        'Forza': ['#1f77b4', '#aec7e8'],      # Blue shades
        'Fortnite': ['#ff7f0e', '#ffbb78'],   # Orange shades  
        'Kombat': ['#2ca02c', '#98df8a']      # Green shades
    }
    
    # Create 2x2 subplot layout with same dimensions as original script
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle('Loss0 vs Loss1 Quality Metrics Comparison (4Mbit)', fontsize=16, fontweight='bold')
    
    metrics = ['PSNR', 'SSIM', 'LPIPS', 'VMAF']
    metric_units = ['(dB)', '', '', '']
    metric_descriptions = ['Higher is better', 'Higher is better', 'Lower is better', 'Higher is better']
    
    for idx, metric in enumerate(metrics):
        ax = axes[idx // 2, idx % 2]
        
        # Set title with description like original script
        ax.set_title(f'{metric} {metric_units[idx]}\n({metric_descriptions[idx]})', fontsize=10, fontweight='bold')
        ax.set_xlabel('Frame Number')
        ax.set_ylabel(f'{metric} {metric_units[idx]}')
        ax.grid(True, alpha=0.3)
        
        # Plot each game's Loss0 and Loss1
        games = ['Forza', 'Fortnite', 'Kombat']
        
        for game_idx, game in enumerate(games):
            for loss_idx, loss in enumerate(['0', '1']):
                scenario_key = f"4Mbit_{game}_Loss{loss}"
                
                if scenario_key in metrics_dict:
                    df = metrics_dict[scenario_key]
                    avg_val = averages[scenario_key][metric]
                    
                    # Plot the metric values over frames
                    color = colors[game][loss_idx]
                    linestyle = '-' if loss == '0' else '--'
                    label = f"{scenario_key} (avg {avg_val:.3f})"
                    
                    ax.plot(df['Frame'], df[metric], color=color, linestyle=linestyle, 
                           label=label, linewidth=1.5, alpha=0.8)
        
        # Adjust y-axis limits for better visualization (same as original)
        if metric == 'PSNR':
            ax.set_ylim(bottom=0)
        elif metric == 'SSIM':
            ax.set_ylim(0, 1)
        elif metric == 'LPIPS':
            ax.set_ylim(bottom=0)
        elif metric == 'VMAF':
            ax.set_ylim(0, 100)
        
        # Use same legend style as original script
        ax.legend(fontsize=8)
    
    # Use tight_layout like original script
    plt.tight_layout()
    
    # Save the plot
    if output_path is None:
        output_path = "loss0_loss1_comparison.png"
    
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Plot saved to: {output_path}")
    
    # Display summary statistics
    print("\n=== Summary Statistics ===")
    for scenario, avgs in averages.items():
        print(f"\n{scenario}:")
        for metric, avg_val in avgs.items():
            print(f"  {metric}: {avg_val:.3f}")
    
    #plt.show()


def main():
    """Main function to generate Loss0 vs Loss1 comparison plots."""
    parser = argparse.ArgumentParser(description='Generate Loss0 vs Loss1 quality metrics comparison plots')
    parser.add_argument('--output', '-o', type=str, default=None,
                        help='Output path for the plot (default: loss0_loss1_comparison.png)')
    
    args = parser.parse_args()
    
    # Set up paths
    script_dir = Path(__file__).parent
    evaluation_dir = script_dir / "evaluation"
    
    if not evaluation_dir.exists():
        print(f"Error: Evaluation directory not found: {evaluation_dir}")
        return
    
    # Define games and losses to compare
    games = ['Forza', 'Fortnite', 'Kombat']
    losses = ['0', '1']
    
    print("Extracting metrics for Loss0 vs Loss1 comparison...")
    print(f"Games: {games}")
    print(f"Losses: {losses}")
    print(f"Bitrate: 4Mbit")
    
    # Extract metrics for all combinations
    metrics_dict = extract_game_loss_metrics(evaluation_dir, games, losses)
    
    if not metrics_dict:
        print("Error: No metrics data found!")
        return
    
    print(f"\nFound data for {len(metrics_dict)} scenarios:")
    for scenario in sorted(metrics_dict.keys()):
        print(f"  - {scenario}")
    
    # Calculate averages
    averages = calculate_averages(metrics_dict)
    
    # Generate plots
    plot_loss_comparison(metrics_dict, averages, args.output)


if __name__ == "__main__":
    main()
