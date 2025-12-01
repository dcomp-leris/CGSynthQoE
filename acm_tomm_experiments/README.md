# ACM TOMM Experiments

This folder contains experimental data and results for the ACM TOMM paper, comparing different frame quality scenarios in cloud gaming.

## Experimental Setup

The experiments evaluate frame quality under different network conditions using Mininet topology emulation. Network bandwidth values are configured according to the parameters table in `cgsynth_parameters_table.pdf`.

## Bandwidth settings

The following table summarizes the Mininet bandwidth and encoding parameters used in the experiments (mirroring `cgsynth_parameters_table.pdf`):

| Bandwidth (Mbps) | Min bitrate (kbps) | Max bitrate (kbps) | Starting bitrate (kbps) | jump | rise | decrease | fall | window_min | window_max | ack_freq | fps | GOP | width | height |
|------------------|--------------------|--------------------|--------------------------|------|------|----------|------|------------|------------|---------|-----|-----|-------|--------|
| 2                | 1000               | 2000               | 1400                     | 0.2  | 0.1  | 0.3      | 0.3  | 1          | 6          | 10      | 30  | 3   | 1280  | 720    |
| 4                | 2000               | 4000               | 2800                     | 0.2  | 0.1  | 0.3      | 0.3  | 1          | 6          | 10      | 30  | 3   | 1280  | 720    |
| 6                | 3000               | 6000               | 4200                     | 0.2  | 0.1  | 0.3      | 0.3  | 1          | 6          | 10      | 30  | 3   | 1280  | 720    |
| 8                | 4000               | 8000               | 5600                     | 0.2  | 0.1  | 0.3      | 0.3  | 1          | 6          | 10      | 30  | 3   | 1280  | 720    |
| 10               | 5000               | 10000              | 7000                     | 0.2  | 0.1  | 0.3      | 0.3  | 1          | 6          | 10      | 30  | 3   | 1280  | 720    |

## Folder Structure

### `reference_vs_real/`

This experiment compares:
- **Reference**: High-quality Kaggle frames located at `CGReplay/server` (assumed to be the best possible quality)
- **Real**: Frames that players actually received after being transmitted through the Mininet network using the script `tools/topology_experiment.py`

The "real" frames represent the actual user experience under various network bandwidth conditions, capturing any quality degradation that occurs during network transmission.

### `reference_vs_synth/`

This experiment compares:
- **Reference**: High-quality Kaggle frames (same as above, from `CGReplay/server`)
- **Synth**: Interpolated Kaggle frames generated using RIFE (Real-time Intermediate Flow Estimation) in `frame_gen/interpolation`

#### Synthesis Process
 
1. **RIFE Server Setup**: In the `ECCV2022-RIFE` fork, run `rife_server` used by `frame_gen/interpolation`.
2. **Frame Interpolation**: In `frame_gen/interpolation`, execute `interpolate_frames.py` with `exp 0` argument to generate interpolated Kaggle frames.
3. **Frame Replacement**: Back up the original `CGReplay/server/` Kaggle frames and replace them with the interpolated frames so they act as the original content to be sent to the user.
4. **Network Transmission**: Use `tools/topology_experiment.py` to send these interpolated frames through the same Mininet network setup.

The interpolated frames serve as the "original" content that gets transmitted to users, allowing evaluation of how frame interpolation techniques affect perceived quality under network constraints.

## Key Components

- **`tools/topology_experiment.py`**: Script for emulating network conditions and transmitting frames through Mininet
- **`cgsynth_parameters_table.pdf`**: Contains the bandwidth values used for each network condition in the experiments
- **`graphs/`**: Contains experimental results and performance graphs

## Usage

To reproduce these experiments:

1. Set up the Mininet topology as described in the parameters table `cgsynth_parameters_table.pdf`
2. For `reference_vs_real`: Use original Kaggle frames as reference
3. For `reference_vs_synth`: Follow the synthesis process above to generate and use interpolated frames
4. Run `tools/topology_experiment.py` to simulate network transmission
5. Compare received frames against reference frames to measure quality degradation
