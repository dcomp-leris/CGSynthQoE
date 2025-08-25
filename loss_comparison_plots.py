#!/usr/bin/env python3
"""
Flexible Quality Metrics Comparison Plots Generator
--------------------------------------------------
This script generates plots comparing video quality metrics across different scenarios.
It supports hierarchical selection of game/experiment/bitrate combinations and automatically
discovers available options at each level.

Usage:
    python loss_comparison_plots.py [--game GAME] [--experiment EXPERIMENT] [--bitrate BITRATE] [--output OUTPUT_PATH] [--metrics METRIC1 METRIC2 ...]
    python loss_comparison_plots.py --interactive  # Interactive mode
    python loss_comparison_plots.py --game Kombat --experiment loss --scenario-group 4Mbit --metrics PSNR SSIM  # Only PSNR and SSIM

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


def discover_games(evaluation_dir):
    """Discover available games in the evaluation directory."""
    games = []
    try:
        for item in os.listdir(evaluation_dir):
            item_path = os.path.join(evaluation_dir, item)
            if os.path.isdir(item_path):
                games.append(item)
        return sorted(games)
    except Exception as e:
        print(f"Error discovering games: {e}")
        return []


def discover_experiments(game_dir):
    """Discover available experiments for a given game."""
    experiments = []
    try:
        for item in os.listdir(game_dir):
            item_path = os.path.join(game_dir, item)
            if os.path.isdir(item_path):
                experiments.append(item)
        return sorted(experiments)
    except Exception as e:
        print(f"Error discovering experiments: {e}")
        return []


def discover_scenario_groups(experiment_dir):
    """Discover available scenario groups for a given experiment."""
    scenario_groups = []
    try:
        for item in os.listdir(experiment_dir):
            item_path = os.path.join(experiment_dir, item)
            if os.path.isdir(item_path):
                # Check if the directory contains subdirectories with detailed_metrics.csv files
                has_scenarios = False
                for subitem in os.listdir(item_path):
                    subitem_path = os.path.join(item_path, subitem)
                    if os.path.isdir(subitem_path):
                        csv_files = [f for f in os.listdir(subitem_path) if f.endswith('_detailed_metrics.csv')]
                        if csv_files:
                            has_scenarios = True
                            break
                if has_scenarios:
                    scenario_groups.append(item)
        return sorted(scenario_groups)
    except Exception as e:
        print(f"Error discovering scenario groups: {e}")
        return []


def interactive_metric_selection():
    """Interactive selection of metrics to plot."""
    available_metrics = ['PSNR', 'SSIM', 'LPIPS', 'VMAF']
    
    print("\nAvailable metrics:")
    for i, metric in enumerate(available_metrics, 1):
        print(f"  {i}. {metric}")
    
    print("\nSelect metrics to plot (e.g., '1 3 4' for PSNR, LPIPS, VMAF):")
    while True:
        try:
            choice = input("Enter metric numbers separated by spaces (or 'all' for all metrics): ").strip()
            if choice.lower() == 'all':
                return available_metrics
            
            indices = [int(x) - 1 for x in choice.split()]
            if all(0 <= idx < len(available_metrics) for idx in indices):
                selected_metrics = [available_metrics[idx] for idx in indices]
                if selected_metrics:
                    return selected_metrics
                else:
                    print("Please select at least one metric.")
            else:
                print("Invalid selection. Please try again.")
        except (ValueError, KeyboardInterrupt):
            print("Invalid input. Please enter numbers separated by spaces.")


def interactive_selection(evaluation_dir):
    """Interactive selection of game, experiment, bitrate, and metrics."""
    # Discover games
    games = discover_games(evaluation_dir)
    if not games:
        print(f"No games found in {evaluation_dir}")
        return None, None, None
    
    print("\nAvailable games:")
    for i, game in enumerate(games, 1):
        print(f"  {i}. {game}")
    
    while True:
        try:
            choice = input(f"\nSelect a game (1-{len(games)}): ").strip()
            game_idx = int(choice) - 1
            if 0 <= game_idx < len(games):
                selected_game = games[game_idx]
                break
            else:
                print("Invalid selection. Please try again.")
        except (ValueError, KeyboardInterrupt):
            print("Invalid input. Please enter a number.")
    
    # Discover experiments for selected game
    game_dir = os.path.join(evaluation_dir, selected_game)
    experiments = discover_experiments(game_dir)
    if not experiments:
        print(f"No experiments found for {selected_game}")
        return None, None, None
    
    print(f"\nAvailable experiments for {selected_game}:")
    for i, experiment in enumerate(experiments, 1):
        print(f"  {i}. {experiment}")
    
    while True:
        try:
            choice = input(f"\nSelect an experiment (1-{len(experiments)}): ").strip()
            exp_idx = int(choice) - 1
            if 0 <= exp_idx < len(experiments):
                selected_experiment = experiments[exp_idx]
                break
            else:
                print("Invalid selection. Please try again.")
        except (ValueError, KeyboardInterrupt):
            print("Invalid input. Please enter a number.")
    
    # Discover scenario groups for selected experiment
    experiment_dir = os.path.join(game_dir, selected_experiment)
    scenario_groups = discover_scenario_groups(experiment_dir)
    if not scenario_groups:
        print(f"No scenario groups found for {selected_game}/{selected_experiment}")
        return None, None, None
    
    print(f"\nAvailable scenario groups for {selected_game}/{selected_experiment}:")
    for i, scenario_group in enumerate(scenario_groups, 1):
        print(f"  {i}. {scenario_group}")
    
    while True:
        try:
            choice = input(f"\nSelect a scenario group (1-{len(scenario_groups)}): ").strip()
            group_idx = int(choice) - 1
            if 0 <= group_idx < len(scenario_groups):
                selected_scenario_group = scenario_groups[group_idx]
                break
            else:
                print("Invalid selection. Please try again.")
        except (ValueError, KeyboardInterrupt):
            print("Invalid input. Please enter a number.")
    
    # Select metrics
    selected_metrics = interactive_metric_selection()
    
    return selected_game, selected_experiment, selected_scenario_group, selected_metrics


def plot_metrics_comparison(experiment_dir, game, experiment, scenario_group, selected_metrics=None, output_path=None):
    """Generate plots comparing metrics across different scenarios within a scenario group."""
    # Automatically discover scenario folders within the scenario group directory
    scenarios = []
    try:
        scenario_group_dir = os.path.join(experiment_dir, scenario_group)
        if not os.path.exists(scenario_group_dir):
            print(f"Scenario group directory not found: {scenario_group_dir}")
            return False
        
        # Get all subdirectories in the scenario_group_dir
        for item in os.listdir(scenario_group_dir):
            item_path = os.path.join(scenario_group_dir, item)
            if os.path.isdir(item_path):
                # Check if the directory contains a detailed_metrics.csv file
                csv_files = [f for f in os.listdir(item_path) if f.endswith('_detailed_metrics.csv')]
                if csv_files:
                    scenarios.append(item)
        
        if not scenarios:
            print(f"No scenario folders found in {scenario_group_dir}")
            return False
        
        print(f"\nGenerating plots for: {game}/{experiment}/{scenario_group}")
        print(f"Found {len(scenarios)} scenario folders: {', '.join(sorted(scenarios))}")
    except Exception as e:
        print(f"Error discovering scenario folders: {e}")
        return False
    
    # Define all available metrics
    all_metrics = {
        'PSNR': ('PSNR', 'PSNR (dB)', 'Higher is better'),
        'SSIM': ('SSIM', 'SSIM', 'Higher is better'),
        'LPIPS': ('LPIPS', 'LPIPS', 'Lower is better'),
        'VMAF': ('VMAF', 'VMAF', 'Higher is better')
    }
    
    # Use selected metrics or default to all
    if selected_metrics is None:
        selected_metrics = ['PSNR', 'SSIM', 'LPIPS', 'VMAF']
    
    # Filter metrics based on selection
    metrics = [all_metrics[metric] for metric in selected_metrics if metric in all_metrics]
    
    if not metrics:
        print("Error: No valid metrics selected")
        return False
    
    print(f"Plotting metrics: {', '.join(selected_metrics)}")
    
    # Load metrics from each scenario
    all_metrics = {}
    for scenario in scenarios:
        scenario_path = os.path.join(scenario_group_dir, scenario)
        csv_files = [f for f in os.listdir(scenario_path) if f.endswith('_detailed_metrics.csv')]
        if csv_files:
            csv_path = os.path.join(scenario_path, csv_files[0])
            metrics_df = load_metrics_from_csv(csv_path)
            if metrics_df is not None:
                all_metrics[scenario] = {
                    'PSNR': metrics_df['PSNR'].values,
                    'SSIM': metrics_df['SSIM'].values,
                    'LPIPS': metrics_df['LPIPS'].values,
                    'VMAF': metrics_df['VMAF'].values
                }
    
    if not all_metrics:
        print("Error: No data could be loaded")
        return False
    
    # Create figure with dynamic subplot layout based on number of metrics
    num_metrics = len(metrics)
    if num_metrics == 1:
        fig, axes = plt.subplots(1, 1, figsize=(7, 5))
        axes = [axes]  # Make it iterable
    elif num_metrics == 2:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        axes = axes.flatten()  # Ensure it's always a flat array
    elif num_metrics == 3:
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        axes = axes.flatten()[:3]  # Use only first 3
    else:  # 4 metrics
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        axes = axes.flatten()
    title = f'Video Quality Metrics Comparison: {game} - {experiment} - {scenario_group}'
    fig.suptitle(title, fontsize=16, fontweight='bold')
    
    # Color palette for different scenarios
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']
    
    # Plot each metric
    for idx, (metric_name, ylabel, description) in enumerate(metrics):
        ax = axes[idx]
        
        ax.set_title(f'{ylabel}\n({description})', fontsize=10, fontweight='bold')
        ax.set_xlabel('Frame Number')
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.3)
        
        for i, (scenario, metrics) in enumerate(all_metrics.items()):
            if metric_name in metrics:
                frames = np.arange(len(metrics[metric_name]))
                values = metrics[metric_name]
                color = colors[i % len(colors)]
                
                # Calculate average for legend
                avg_val = np.mean(values)
                
                # Plot the metric values with average in legend
                ax.plot(frames, values, label=f'{scenario} (avg {avg_val:.3f})', color=color, linewidth=1.5)
        
        # Set y-axis limits based on metric type
        if metric_name == 'SSIM':
            ax.set_ylim(0, 1)
        elif metric_name == 'PSNR':
            ax.set_ylim(bottom=0)
        elif metric_name == 'LPIPS':
            ax.set_ylim(bottom=0)
        elif metric_name == 'VMAF':
            ax.set_ylim(0, 100)
        
        ax.legend(fontsize=8)
    
    # Adjust layout and save
    plt.tight_layout()
    
    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"Quality metrics comparison plots saved to: {output_path}")
    else:
        # Set default output path if not provided
        default_output = os.path.join(scenario_group_dir, f"{game}_{experiment}_{scenario_group}_comparison.png")
        plt.savefig(default_output, dpi=300, bbox_inches='tight')
        print(f"Quality metrics comparison plots saved to: {default_output}")
    
    return True


def main():
    """Main function to parse arguments and generate plots."""
    parser = argparse.ArgumentParser(
        description="Generate plots comparing video quality metrics across different scenarios",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--game", "-g",
        help="Game name (e.g., Kombat, Forza, Fortnite)",
        default=None
    )
    
    parser.add_argument(
        "--experiment", "-e",
        help="Experiment type (e.g., loss, delay)",
        default=None
    )
    
    parser.add_argument('--scenario-group', '-s', type=str, help='Scenario group (e.g., 4Mbit, 2Mbit)')
    parser.add_argument('--metrics', '-m', nargs='+', choices=['PSNR', 'SSIM', 'LPIPS', 'VMAF'], 
                       help='Metrics to plot (default: all metrics)', default=['PSNR', 'SSIM', 'LPIPS', 'VMAF'])
    parser.add_argument('--output', '-o', type=str, help='Output path for the generated plot image')
    parser.add_argument('--interactive', '-i', action='store_true', help='Interactive mode for selecting game/experiment/scenario group/metrics')
    
    args = parser.parse_args()
    
    # Base evaluation directory
    evaluation_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "evaluation")
    
    if not os.path.exists(evaluation_dir):
        print(f"Evaluation directory not found: {evaluation_dir}")
        return
    
    # Interactive mode or command line arguments
    if args.interactive:
        game, experiment, scenario_group, selected_metrics = interactive_selection(evaluation_dir)
        if not all([game, experiment, scenario_group]):
            print("Selection cancelled or invalid.")
            return
    else:
        game = args.game
        experiment = args.experiment
        scenario_group = getattr(args, 'scenario_group', None)
        selected_metrics = args.metrics
        
        if not all([game, experiment, scenario_group]):
            print("Error: game, experiment, and scenario-group must be provided when not using interactive mode.")
            print("Use --help for usage information.")
            return
    
    # Construct the experiment directory path
    experiment_dir = os.path.join(evaluation_dir, game, experiment)
    
    if not os.path.exists(experiment_dir):
        print(f"Experiment directory not found: {experiment_dir}")
        return
    
    print(f"\nGenerating plots for: {game}/{experiment}/{scenario_group}")
    print(f"Selected metrics: {', '.join(selected_metrics)}")
    # Generate plots
    success = plot_metrics_comparison(experiment_dir, game, experiment, scenario_group, selected_metrics, args.output)
    if not success:
        print("Failed to generate plots.")
        return


if __name__ == "__main__":
    main()