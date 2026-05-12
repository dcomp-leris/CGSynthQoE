# DEMO: CGSynth: Cloud Gaming Synthesizer

**Note:** This paper will be presented on 2025/09/25 in the Sigcomm'25 conference.

<!--[![Conference](https://img.shields.io/badge/submitted-Netsoft2025-blue)](https://netsoft2025.ieee-netsoft.org/)-->
[![Conference](https://img.shields.io/badge/accepted-Sigcomm'25-blue)](https://conferences.sigcomm.org/sigcomm/2025/accepted-posters-demos/)
[![CGReplay](https://img.shields.io/badge/CGReplay-Repository-green)](https://github.com/dcomp-leris/CGReplay.git)
[![Paper](https://img.shields.io/badge/Paper-Zenodo-red)](https://zenodo.org/records/16968173)
[![Demonstration](https://img.shields.io/badge/Sigcomm2025-Demonstration-blue)](https://conferences.sigcomm.org/sigcomm/2025/papers-posters-demos-info/)
[![ACM](https://img.shields.io/badge/Paper-ACM-red)](https://dl.acm.org/doi/10.1145/3744969.3748445)
[![ACM](https://img.shields.io/badge/Video-CGSynth-blue)](https://drive.google.com/file/d/1LrWFbQx8SufftGh4FA4Pdk6-v_bhxG9B/view?usp=drive_link)


*For more details, please refer to the Wiki page of this repository.*

## Table of Contents
- [Installation](#installation)
  - [Requirements at a Glance](#requirements-at-a-glance)
  - [Submodules](#submodules)
  - [Python Environment Setup](#python-environment-setup)
  - [libzbar (QR/barcode support)](#libzbar-qrbarcode-support)
  - [GStreamer H.264 encoder plugins (x264enc)](#gstreamer-h264-encoder-plugins-x264enc)
  - [OpenCV with GStreamer Support](#opencv-with-gstreamer-support)
  - [Installing FFmpeg with VMAF Support](#installing-ffmpeg-with-vmaf-support)
  - [Quality Metrics Tools Setup](#quality-metrics-tools-setup)
- [Quickstart: End-to-End Workflow](#quickstart-end-to-end-workflow)
- [Architecture](#architecture)
  - [RTP Video Tools](#1-rtp-video-tools)
  - [Frame Extraction and Video Creation](#2-frame-extraction-and-video-creation)
  - [Frame Generation and Degradation Toolkit](#3-frame-generation-and-degradation-toolkit)
  - [Quality Metrics Tools](#4-quality-metrics-tools)
- [Notes](#notes)
- [Troubleshooting](#troubleshooting)
  - [OpenCV + NumPy (cv2 import errors)](#troubleshooting-opencv--numpy-cv2-import-errors)
- [Reproducing Video Quality Analysis Results](#reproducing-video-quality-analysis-results)
- [Practical Usage: ffmpeg with VMAF](#practical-usage-ffmpeg-with-vmaf)

## Installation

### Requirements at a Glance

| Component                 | Python Version                 | Notes                                           |
|--------------------------|---------------------------------|-------------------------------------------------|
| Frame generation & tools | 3.8                             | Uses deadsnakes PPA                             |
| Player / CGReplay        | 3.10 (venv, system-site-packages) | OpenCV + GStreamer + GI (PyGObject via apt)    |
| Quality metrics tools    | 3.12.2                          | See Quality Metrics Tools Setup                 |

### Submodules
This project uses Git submodules. To properly initialize them, run:
```bash
git submodule update --init
```

### Python Environment Setup

- Frame generation and tooling: Python 3.8 recommended
- Player/CGReplay components (with GStreamer OpenCV): see OpenCV section below
- Quality metrics tools: Python 3.12.2 (see Quality Metrics Tools section)

> Tip: Use per-component virtual environments to avoid dependency conflicts.

#### For Frame Generation Component
The frame generation component requires Python 3.8. You can install it using the deadsnakes PPA:

```bash
# Add deadsnakes PPA
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update

# Install Python 3.8 and required packages
sudo apt install python3.8 python3.8-venv python3.8-dev
```

#### For CGReplay Player/Server (GI + GStreamer, Python >= 3.10)
On Ubuntu 22.04, the `gi` module (PyGObject) comes from system packages, not from pip. If these libraries are missing, you may see errors like `ModuleNotFoundError: No module named 'gi'` or build failures mentioning `girepository-2.0`.

1. Install the required system GI / PyGObject packages:

```bash
sudo apt update
sudo apt install -y \
    python3-gi python3-gi-cairo \
    gir1.2-gtk-3.0 gir1.2-gdkpixbuf-2.0 \
    libcairo2-dev libgirepository1.0-dev \
    gobject-introspection
```

2. Create a virtual environment for CGSynth using at least Python 3.10 and enable access to system packages (so `gi` is visible inside the venv):

```bash
python3.10 -m venv --system-site-packages ~/venvs/cgsynth
source ~/venvs/cgsynth/bin/activate
```

3. Install the Python dependencies for CGSynth in that venv:

```bash
pip install -r requirements_cgsynth.txt
```

4. Verify that `gi` and OpenCV can be imported from the venv:

```bash
python -c 'import gi, cv2; print("GI and OpenCV OK")'
```

> Note: In bash, `!` inside double quotes triggers history expansion. Prefer single quotes as above, or escape `!` if you use double quotes.

#### For Quality Metrics Tools
The quality metrics tools require Python 3.12.2. See the Quality Metrics Tools section for setup instructions.

#### GStreamer H.264 encoder plugins (x264enc)
To enable H.264 encoding for GStreamer pipelines used by the CGReplay server/player (e.g., avoid `gst_parse_error: no element "x264enc"`), install the encoder plugins:
```bash
sudo apt update
sudo apt install gstreamer1.0-plugins-ugly gstreamer1.0-plugins-bad gstreamer1.0-libav
```

#### libzbar (QR/barcode support)
To enable QR/barcode reading via OpenCV/pyzbar, install the `libzbar` system libraries (Ubuntu/Debian):
```bash
sudo apt update
sudo apt install libzbar0 libzbar-dev
```

#### OpenCV with GStreamer Support

<details>
  <summary><strong>Show detailed OpenCV build instructions</strong></summary>

The CGReplay player component requires OpenCV built with GStreamer support to properly handle video streams. Pre-built packages from pip typically lack this support, so you'll need to build OpenCV from source:

1. First, install the necessary dependencies:
```bash
sudo apt-get install -y build-essential cmake git pkg-config \
    libgtk-3-dev libavcodec-dev libavformat-dev libswscale-dev \
    libv4l-dev libxvidcore-dev libx264-dev libjpeg-dev \
    libpng-dev libtiff-dev gfortran openexr \
    libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
    python3-dev python3-numpy libatlas-base-dev
```

2. Clone the OpenCV repositories:
```bash
mkdir -p ~/opencv_build && cd ~/opencv_build
git clone https://github.com/opencv/opencv.git
git clone https://github.com/opencv/opencv_contrib.git
```

3. Configure the build with CMake (adjust paths to match your environment):
```bash
mkdir -p ~/opencv_build/build && cd ~/opencv_build/build
cmake -D CMAKE_BUILD_TYPE=RELEASE \
      -D CMAKE_INSTALL_PREFIX=/path/to/your/virtualenv \
      -D INSTALL_PYTHON_EXAMPLES=ON \
      -D INSTALL_C_EXAMPLES=OFF \
      -D OPENCV_ENABLE_NONFREE=ON \
      -D WITH_GSTREAMER=ON \
      -D OPENCV_EXTRA_MODULES_PATH=~/opencv_build/opencv_contrib/modules \
      -D BUILD_EXAMPLES=ON \
      -D PYTHON_EXECUTABLE=/path/to/your/virtualenv/bin/python \
      -D PYTHON_DEFAULT_EXECUTABLE=/path/to/your/virtualenv/bin/python \
      ../opencv
```

4. Build and install (replace `8` with the number of CPU cores you want to use):
```bash
make -j8
make install
```

5. Verify that OpenCV has GStreamer support:
```bash
python -c "import cv2; print(cv2.getBuildInformation())" | grep -i gstreamer
```
   You should see `GStreamer: YES` in the output.

</details>

### Installing FFmpeg with VMAF Support

<details>
  <summary><strong>Show detailed VMAF + FFmpeg build steps</strong></summary>

VMAF (Video Multi-Method Assessment Fusion) is a perceptual video quality metric developed by Netflix. To use VMAF-based quality metrics in this project, you need to build and install both libvmaf and ffmpeg with VMAF support. This section provides step-by-step instructions for Ubuntu 22.04/24.04 (adapt as needed for your system).

#### 1. Install Build Dependencies

```bash
sudo apt update
sudo apt install -y git build-essential pkg-config libtool \
    libssl-dev yasm cmake python3-venv meson ninja-build nasm \
    libass-dev libfreetype6-dev libtheora-dev libvorbis-dev \
    libx264-dev libx265-dev libnuma-dev
```

#### 2. Clone and Build libvmaf

```bash
git clone https://github.com/Netflix/vmaf.git
cd vmaf
make
sudo make install
sudo ldconfig
cd ..
```

#### 3. Clone and Build ffmpeg with VMAF Support

```bash
git clone https://git.ffmpeg.org/ffmpeg.git ffmpeg
cd ffmpeg
./configure --enable-gpl --enable-libx264 --enable-libx265 --enable-libvmaf
make -j$(nproc)
sudo make install
cd ..
```

#### 4. Verify VMAF Support in ffmpeg

You can verify that ffmpeg was built with VMAF support by running:

```bash
ffmpeg -filters | grep vmaf
```

You should see output similar to:

```
.. libvmaf           VV->V      Calculate the VMAF between two video streams.
.. vmafmotion        V->V       Calculate the VMAF Motion score.
```

#### 5. Example Usage

To compute the VMAF score between two videos:

```bash
ffmpeg -i reference.mp4 -i distorted.mp4 -lavfi "[0:v][1:v]libvmaf" -f null -
```

This will print VMAF scores to the console.

**Tip:** For more advanced usage and options, refer to the official [FFmpeg VMAF documentation](https://ffmpeg.org/ffmpeg-filters.html#libvmaf).

</details>

### Quality Metrics Tools Setup

1. Create a Python virtual environment:
```bash
python3.12.2 -m venv /home/user/venv/cgreplay_metrics
source /home/user/venv/cgreplay_metrics/bin/activate
```

2. Install dependencies:
```bash
pip install -r frame_gen/tools/requirements_tools.txt
```

## Quickstart: End-to-End Workflow

Follow these steps to go from PNG frames to PCAP, back to an MP4, extract frames, optionally interpolate (RIFE), and re-create a video.

> Note: For live experiments that generate PCAP traces from the network (rather than offline packetization), install `tshark` and run it with `sudo` to capture the traffic.

1) Generate an RTP PCAP from PNG frames

```bash
# From repository root
python tools/rtp_video_packetizer.py --game [Forza Fortnite Kombat]
# Configure input frame directory, codec, IPs/ports, and output PCAP inside the config.yaml

```

2) Extract a playable MP4 from the RTP PCAP

```bash
python tools/rtp_pcap_to_video_extractor.py --input output_pcap.pcap --output output_video.mp4 --codec h264
```

3) Extract frames from the MP4

```bash
python tools/rtp_frame_extractor.py --video output_video.mp4 --out-dir output_frames/Example --fps 30
```

4) (Optional) Interpolate frames (RIFE or simple blending)

```bash
# See detailed options below and in frame_gen/interpolation/README.md
python frame_gen/interpolation/interpolate_frames.py \
  --method rife \
  --game Example \
  --resolution 1600x900 \
  --exp 1 \
  --generate-video yes \
  --fps 30
```

5) Create a video from any folder of frames

```bash
python tools/create_video_from_frames.py --frames-dir output_frames/Example --output output_videos/Example.mp4 --fps 30
```


Cloud gaming's unique network traffic is challenging to reproduce for research. This demo introduces Cloud Gaming Synthesizer (CGSynth), a platform that generates realistic, configurable synthetic cloud gaming (CG) traffic. CGSynth captures real CG patterns and allows their synthetic reproduction with user-defined flow/packet parameters and deterministic protocol headers. It employs a GRU for accurate, order-preserving timestamp generation and AI-based video interpolation for realistic payloads. Crucially, CGSynth integrates a QoE evaluation module using objective (e.g., SSIM) and subjective metrics (e.g., MOS) to validate synthetic traffic's video quality and responsiveness against real streams.

<img width="1210" height="714" alt="image" src="https://github.com/user-attachments/assets/ddfacb9e-21da-4580-bfc7-fdb38a553b66" />

## Architecture

### 1. RTP Video Tools

A pair of Python scripts for working with video streams over RTP networks. These tools enable you to create packet captures (PCAPs) of H.264/H.265 video streams and extract the original video from such captures.

#### Overview

- **tools/rtp_video_packetizer.py**: Converts a series of PNG images into an H.264/H.265 video stream, creates RTP packets for network transmission, and stores them in a PCAP file.
- **tools/rtp_pcap_to_video_extractor.py**: Extracts H.264/H.265 video from RTP packets in a PCAP file and reconstructs the original video stream.

#### Requirements

- Python 3.6+
- Scapy (`pip install scapy`)
- FFmpeg (must be installed and available in your PATH)
- `tshark` (Wireshark CLI) for capturing live RTP traffic to PCAP when running experiments (typically requires `sudo`)

Additional Python dependencies:
```bash
pip install scapy
```

#### Usage

##### Creating RTP Video Packets (PCAP)

```bash
python tools/rtp_video_packetizer.py
```

This script will:
1. Read PNG frames from the specified directory
2. Encode them to H.264/H.265 using FFmpeg
3. Packetize the encoded video into RTP packets
4. Save the packets as a PCAP file

Configuration options are defined within the script, including:
- Image source directory
- Output PCAP filename
- Network parameters (IP addresses, ports)
- Video codec (H.264 or H.265)

##### Extracting Video from PCAP

```bash
python tools/rtp_pcap_to_video_extractor.py --input input_pcap.pcap --output output.mp4 --codec h264
```

Arguments:
- `--input`: Path to the input PCAP file
- `--output`: Path to the output video file (default: 'output.mp4')
- `--codec`: Video codec ('h264' or 'h265', default: 'h264')

Example:
```bash
python tools/rtp_pcap_to_video_extractor.py --input rtp_stream_h264_fixed.pcap --output extracted_video.mp4 --codec h264
```

### 2. Frame Extraction and Video Creation

- `tools/rtp_frame_extractor.py`: Extract frames from an MP4 video at a specified FPS (default 30). Optionally skip corrupted frames. Saves as zero-padded JPEG files (`frame_000001.jpg`, ...).

Usage:
```bash
python tools/rtp_frame_extractor.py --video path/to/video.mp4 --out-dir output_frames/MyVideo --fps 30 --skip-corrupted yes
```

- `tools/create_video_from_frames.py`: Convert a folder of image frames into an MP4 video using FFmpeg. Automatically detects frame patterns.

Usage:
```bash
python tools/create_video_from_frames.py --frames-dir output_frames/MyVideo --output output_videos/MyVideo.mp4 --fps 30
```

### 3. Frame Generation and Degradation Toolkit

Located in the `frame_gen` directory, this toolkit provides tools for generating and degrading video frames, as well as evaluating their quality. It includes:

#### Frame Generation (Interpolation)
- Methods: simple OpenCV blending and AI-based RIFE interpolation
- Main script: `frame_gen/interpolation/interpolate_frames.py`
- RIFE setup and Docker-based instructions: see `frame_gen/interpolation/README.md`

Common usage:
```bash
# Simple blending
python frame_gen/interpolation/interpolate_frames.py \
  --method blend --game Kombat --resolution 1600x900 --exp 1 --fps 30 --generate-video yes

# RIFE interpolation (ensure RIFE environment/server as per README)
python frame_gen/interpolation/interpolate_frames.py \
  --method rife --game Kombat --resolution 1600x900 --exp 1 --fps 30 --generate-video yes
```

Key arguments:
- `--method`: `blend` or `rife`
- `--game`: Used to auto-locate input frame folders for known datasets
- `--resolution`: e.g., `1600x900`
- `--exp`: Interpolation exponent (number of subdivisions)
- `--fps`: Original FPS for output video generation
- `--generate-video`: `yes`/`no` to render MP4 after interpolation

#### Frame Degradation
- Script: `frame_gen/degradation/frame_degradation_simulator.py`
- Simulates artifacts: compression, macroblock loss, resolution scaling, frame freeze, motion blur, color banding, quantization noise.

Usage:
```bash
python frame_gen/degradation/frame_degradation_simulator.py \
  --input_dir path/to/input_frames \
  --output_dir path/to/output_frames_degraded \
  --severity 0.5 \
  --seed 123 \
  --effect_types all \
  --generate_video yes \
  --fps 30 \
  --codec libx264
```

Important notes:
- `--effect_types` accepts one or more of: `network`, `rendering`, `all`.
- Output frames are saved as `%04d.png` and can be turned into a video automatically if `--generate_video yes`.

#### Quality Assessment
- Comprehensive set of quality metrics tools (see Quality Metrics Tools section)
- Support for both objective and subjective quality evaluation
- Real-time visualization capabilities

For detailed usage instructions, please refer to the documentation in the `frame_gen` directory.

### 4. Quality Metrics Tools

Located in the `frame_gen/tools` directory, these tools help evaluate and analyze video quality metrics, particularly useful for comparing original and processed/interpolated video frames.

#### Setup for Quality Metrics Tools

1. Create a Python virtual environment:
```bash
python3.12.2 -m venv /home/user/venv/cgreplay_metrics
source /home/user/venv/cgreplay_metrics/bin/activate
```

2. Install dependencies:
```bash
pip install -r frame_gen/tools/requirements_tools.txt
```

#### Available Quality Metrics Tools

1. **PSNR and SSIM Analysis** (`frame_gen/tools/psnr_and_ssim.py`)
   - Calculates Peak Signal-to-Noise Ratio (PSNR) and Structural Similarity Index (SSIM)
   - Generates plots showing metrics over time
   - Usage: `python frame_gen/tools/psnr_and_ssim.py`

2. **Real-time Quality Metrics Dashboard** (`frame_gen/tools/real_time_quality_metrics.py`)
   - Streamlit-based dashboard for real-time visualization
   - Calculates PSNR, SSIM, LPIPS, and tLPIPS
   - Usage: `streamlit run frame_gen/tools/real_time_quality_metrics.py`

3. **Mean Opinion Score (MOS) Evaluation** (`frame_gen/tools/mean_opinion_score_video_pairs.py`)
   - Tool for subjective quality evaluations (QoE - Quality of Experience)
   - Randomizes video pair order
   - Collects ratings and comments
   - For more details on the QoE subjective evaluation methodology and results, refer to [cgreplay_demo](https://github.com/arielgoes/cgreplay_demo)
   - Usage: `python frame_gen/tools/mean_opinion_score_video_pairs.py`

4. **Video Utilities** (`frame_gen/tools/video_utils.py`)
   - Collection of utility functions for video processing
   - Includes functions for reading, writing, resizing, and frame rate modification
   - Can be imported as a Python module

5. **Per-frame VMAF Scatterplot** (`tools/vmaf_scatter.py`)
   - Computes per-frame VMAF between reference server frames and received frames for multiple experiments.
   - Reference frames are read from `CGReplay/server/<Game>/`.
   - Distorted/received frames are read from `acm_tomm_experiments/reference_vs_real/<Game>/<BitrateLabel>/received_frames/`.
   - Plots a scatterplot of VMAF vs. frame index for each experiment, with a light connecting line to make trends easier to see.
   - Skips missing frames (frames present in the reference but not in `received_frames`).
   - Saves the resulting plot into `acm_tomm_experiments/graphs/` and also shows it interactively.
   - Example usage:

     ```bash
     cd ~/git/CGSynth

     python3 tools/vmaf_scatter.py \
       --game Fortnite \
       --bitrates \
         2Mbit_Fortnite \
         4Mbit_Fortnite \
         6Mbit_Fortnite \
         8Mbit_Fortnite \
         10Mbit_Fortnite \
       --labels \
         "BW: 2Mbps" \
         "BW: 4Mbps" \
         "BW: 6Mbps" \
         "BW: 8Mbps" \
         "BW: 10Mbps" \
       --total-frames 120
     ```

For detailed usage instructions of each quality metrics tool, please refer to the README.md in the `frame_gen/tools` directory.

## Notes

- Use Python 3.8 for frame generation and general tooling; use Python 3.12.2 for quality metrics tools
- Some tools (like LPIPS) require CUDA-capable GPU for optimal performance
- Make sure your input videos/frames have matching dimensions when comparing them
- The tools are designed to work with common video formats (MP4) and image formats (PNG)
- For Mininet-based client/server experiments (e.g., `tools/topology_experiment.py`), ensure `xterm` is installed so the server and player terminals can open correctly
 - When enabling automatic PCAP capture for Mininet experiments via `CGReplay/config/config.yaml` (`capturing_options.enable_pcap: True`), set `gamer.pcap_file` to the **final PCAP location under `CGReplay/player/`** (e.g., `./logs/my.pcap`). Internally, Mininet captures into `/tmp/<filename>.pcap` due to permission constraints and the experiment script automatically copies that `/tmp` file into the configured `gamer.pcap_file` path after the experiment finishes.
 - Always run `tools/topology_experiment.py` from the `CGReplay/` directory (e.g., `cd CGSynth/CGReplay && sudo python3 ../tools/topology_experiment.py`). Running it from another working directory can cause the `player/` and `server/` folders and relative paths (like `../config/config.yaml`) to be resolved in the wrong place.

## Troubleshooting

- Ensure FFmpeg is properly installed and available in your PATH
- Check that your PNG images are valid and can be encoded by FFmpeg
- For extraction problems, verify that the PCAP contains valid RTP packets with H.264/H.265 payload
- Malformed or incomplete packets in the PCAP file may result in corrupted video output
- For quality metrics tools, ensure you have the correct Python version and all dependencies installed
- For the CGReplay server and player:
  - When a game is specified in `config.yaml` (under `Running:game`), ensure a folder with the same name exists in the `server/` directory (e.g., if game is set to "Kombat", you need a `server/Kombat/` folder)
  - The game folder must contain frames in sequential order
   - Both `player/` and `server/` directories must have a `logs` folder created in them for proper operation

### Troubleshooting OpenCV + NumPy (cv2 import errors)

**Typical symptoms**

- `ImportError: numpy.core.multiarray failed to import`
- `_ARRAY_API not found` when doing `import cv2`
- `cv2` imports fine in system Python but fails inside the venv.

**Root causes**

1. **OpenCV built against NumPy 1.x, but the venv has NumPy 2.x**
   - OpenCV's Python bindings are compiled against NumPy's C API.
   - NumPy 2.x changes the C ABI; OpenCV built with NumPy 1.x cannot load against NumPy 2.x.

2. **OpenCV built against system Python instead of the venv**
   - If the environment is created with tools like `uv` or misconfigured, CMake may detect `/usr/bin/python3.x` instead of the venv interpreter.
   - The resulting `cv2*.so` may be placed in `~/opencv_build/build/lib/python3/...` instead of `venv/lib/python3.x/site-packages/`, so the venv cannot find it.

**Recommended fix**

1. **Create the venv with `python -m venv`**:

```bash
python3 -m venv ~/venvs/cgsynth
source ~/venvs/cgsynth/bin/activate
```

2. **Install a NumPy 1.x version in that venv before building OpenCV**:

```bash
pip install "numpy<2"
```

3. **Configure OpenCV with the venv Python in CMake** and verify that variables such as:

- `PYTHON_EXECUTABLE` point to `.../venvs/cgsynth/bin/python`
- `PYTHON3_PACKAGES_PATH` points to `.../venvs/cgsynth/lib/python3.10/site-packages/`

4. **Ensure `cv2` ends up inside the venv**:

- After `make install`, check for `cv2*.so` under the venv's `site-packages/`.
- If it was installed into `~/opencv_build/build/lib/python3/...`, copy it manually into the venv `site-packages/`.

Once these conditions are met, running `python -c "import cv2; print(cv2.__version__)"` inside the venv should succeed.

## Reproducing Video Quality Analysis Results

To reproduce the video quality analysis results from network experiments, follow these steps in order:

### Step 1: Extract Video Frames from Network Captures

Use the RTP video extractor to extract video frames from PCAP files:

```bash
python tools/rtp_pcap_to_video_extractor.py --input input.pcap --output output.mp4 --codec h264
```

This will extract the video frames from the network capture and save them for analysis.

### Step 2: Generate Quality Metrics CSV Files

Run the video quality analysis tool to compute detailed metrics and generate CSV files:

```bash
python video_quality_plots.py [options]
```

This script will:
- Compare extracted video frames against reference frames
- Calculate quality metrics (PSNR, SSIM, LPIPS, VMAF)
- Generate detailed CSV files with per-frame metrics
- Create individual quality plots

### Step 3: Generate Comparison Plots

Use the loss comparison plotting tool to create comparative analysis plots:

```bash
# Interactive mode (recommended)
python loss_comparison_plots.py --interactive

# Direct command-line usage
python loss_comparison_plots.py --game Kombat --experiment loss --scenario-group 4Mbit
```

This script will:
- Automatically discover available games, experiments, and scenario groups
- Aggregate metrics from multiple detailed CSV files
- Generate 2x2 subplot comparisons showing all scenarios for each metric
- Save plots with descriptive names (e.g., `Kombat_loss_4Mbit_comparison.png`)

The resulting plots will show PSNR, SSIM, LPIPS, and VMAF comparisons across different network conditions (e.g., 4Mbit, 4Mbit_Loss10, 4Mbit_Loss20, 4Mbit_Loss30) with average values displayed in the legend.

### Step 4: Generate Loss0 vs Loss1 Cross-Game Comparison

For specific analysis of Loss0 vs Loss1 scenarios across multiple games, use the dedicated comparison script:

```bash
python loss0_loss1_comparison.py [--output OUTPUT_PATH]
```

This specialized script will:
- Automatically explore the evaluation folder structure
- Extract metrics for Loss0 and Loss1 scenarios across all games (Forza, Fortnite, Kombat) at 4Mbit bitrate
- Generate comprehensive plots with 6 lines showing:
  - 4Mbit_Forza_Loss0 (avg ##)
  - 4Mbit_Forza_Loss1 (avg ##) 
  - 4Mbit_Fortnite_Loss0 (avg ##)
  - 4Mbit_Fortnite_Loss1 (avg ##)
  - 4Mbit_Kombat_Loss0 (avg ##)
  - 4Mbit_Kombat_Loss1 (avg ##)
- Display average values for each metric in the legend
- Use consistent styling with the original loss comparison plots
- Save results as `loss0_loss1_comparison.png`

The script generates 2x2 subplot layout showing PSNR, SSIM, LPIPS, and VMAF metrics with color-coded lines for each game (blue for Forza, orange for Fortnite, green for Kombat) and different line styles for Loss0 (solid) vs Loss1 (dashed).

### Troubleshooting VMAF/FFmpeg Build

- **Missing `nasm` or build tools:**
  - If you see errors about `nasm` not found, install it with:
    ```bash
    sudo apt install nasm
    ```
  - For `meson`, `ninja`, or `python3-venv` errors, install with:
    ```bash
    sudo apt install meson ninja-build python3-venv
    ```

- **libvmaf build fails with missing dependencies:**
  - Make sure all dependencies listed above are installed.
  - If you get errors related to Python or Meson, try recreating the virtual environment:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip install meson ninja
    make clean
    make
    ```

- **libvmaf package not available in your distribution:**
  - Building from source (as shown above) is the recommended approach and ensures you get the latest version.

- **`ninja: error: loading 'build.ninja': No such file or directory`**
  - This means the Meson setup step failed. Try running:
    ```bash
    .venv/bin/meson setup libvmaf/build libvmaf --buildtype release -Denable_float=true
    .venv/bin/meson compile -C libvmaf/build
    sudo .venv/bin/meson install -C libvmaf/build
    ```

- **ffmpeg does not detect libvmaf:**
  - Make sure `sudo ldconfig` was run after installing libvmaf.
  - Ensure `--enable-libvmaf` was passed to `./configure` when building ffmpeg.
  - If you installed ffmpeg before libvmaf, rebuild ffmpeg after installing libvmaf.

- **General advice:**
  - Always check the output of each command for errors.
  - Consult the official documentation for [libvmaf](https://github.com/Netflix/vmaf) and [ffmpeg](https://ffmpeg.org/).

## Practical Usage: ffmpeg with VMAF

VMAF is a video quality metric designed to compare a reference (original) video with a distorted (processed or compressed) video. It does not generate a new video; instead, it outputs a quality score or report.

### Basic Usage: Compare Two Videos

Suppose you have:
- `reference.mp4`: the original, high-quality video
- `distorted.mp4`: the video to evaluate (e.g., after compression)

Run:

```bash
ffmpeg -i reference.mp4 -i distorted.mp4 -lavfi "[0:v][1:v]libvmaf" -f null -
```

This will print VMAF scores to the terminal.

### Save VMAF Results as JSON

To generate a JSON file with detailed VMAF statistics (including per-frame scores and the mean), use:

```bash
ffmpeg -i reference.mp4 -i distorted.mp4 \
  -lavfi "[0:v][1:v]libvmaf=log_path=vmaf.json:log_fmt=json" -f null -
```

This will create a file called `vmaf.json` containing:
- The VMAF score for each frame
- The mean (average) VMAF score and other summary statistics

You can use this JSON file for further analysis or plotting with Python, Excel, or other tools.

### Compare Videos of Different Resolutions

If the videos have different resolutions, scale them to match:

```bash
ffmpeg -i reference.mp4 -i distorted.mp4 \
  -lavfi "[0:v]scale=1920:1080[ref];[1:v]scale=1920:1080[dist];[ref][dist]libvmaf" \
  -f null -
```

### Manually Generate a Video from PNG Frames

If you want to manually generate a video with 30 fps from PNG frames for evaluation, use the following command:

```bash
ffmpeg -framerate 30 -i %04d.png -c:v libx264 -pix_fmt yuv420p output.mp4
```

Make sure to run this command in the correct directory containing your PNG frames, or specify the full path to the frames (e.g., `path/to/frames/%04d.png`). Adjust the frame rate or other parameters if needed for your specific evaluation.

### Tips
- The videos must have the same frame count and be synchronized.
- Use `-an` to ignore audio streams if needed.
- You can add other metrics (e.g., `feature=name=psnr`) to the filter.
- For more options, see:
  - [FFmpeg libvmaf filter documentation](https://ffmpeg.org/ffmpeg-filters.html#libvmaf)
  - [Netflix VMAF GitHub](https://github.com/Netflix/vmaf)
  - The OpenCV in your Python environment must have GStreamer support (see OpenCV with GStreamer Support section)


### Please Cite the paper:

    @inproceedings{10.1145/3744969.3748445,
    author = {Shirmarz, Alireza and de Castro Ariel, Goes and Lopes, Victor Hugo Schneider and Verdi, Fabio and Luizelli, Marcelo and Rothenberg, Christian},
    title = {CGSynth: Cloud Gaming Synthesizer},
    year = {2025},
    isbn = {9798400720260},
    publisher = {Association for Computing Machinery},
    address = {New York, NY, USA},
    url = {https://doi.org/10.1145/3744969.3748445},
    doi = {10.1145/3744969.3748445},
    booktitle = {Proceedings of the ACM SIGCOMM 2025 Posters and Demos},
    pages = {175–177},
    numpages = {3},
    keywords = {AI-based Network Traffic Generation, Cloud Gaming Traffic Synthesis, Quality of Experience (QoE) Evaluation},
    location = {Coimbra, Portugal},
    series = {ACM SIGCOMM Posters and Demos '25}
    }

 ### Contact
 
 **Email:** ashirmarz@ufscar.br

