"""
RTP Video Packetizer - CGReplay Network Simulation Tool

This script creates RTP (Real-time Transport Protocol) packet streams from video frames
for network simulation and testing purposes. It reads PNG frames from the game server,
encodes them to H.264/H.265, packetizes them into RTP packets, and writes them to a PCAP file.

Key Features:
- Reads PNG frames from game-specific directories (Fortnite, Forza, Kombat)
- Encodes frames to H.264/H.265 using FFmpeg with baseline profile for compatibility
- Creates proper RTP packets with fragmentation support for large NAL units
- Includes sync commands from game-specific sync files as separate RTP streams
- Uses timing information from IPI (Inter-Packet Interval) files or defaults to FPS
- Generates realistic network traffic patterns for CGReplay testing
- Configurable via config.yaml for game selection, network parameters, and encoding settings

Usage:
    python rtp_video_packetizer.py                    # Uses H.264 codec and game from config
    python rtp_video_packetizer.py --codec h265       # Uses H.265 codec

Output:
    Creates rtp_stream_{codec}_{game_name}.pcap with RTP packets ready for network analysis

Dependencies:
    - scapy: For packet creation and PCAP writing
    - ffmpeg: For video encoding
    - pyyaml: For configuration loading
"""

from pathlib import Path
from scapy.all import *
import os
import csv
import subprocess
import tempfile
from collections import defaultdict
import random
import itertools
import yaml
import itertools
import argparse
import sys

DEFAULT_CODEC = "h264"
MIN_PAYLOAD_SIZE = 900
MAX_PAYLOAD_SIZE_LIMIT = 1400
rtp_clock_rate = 90000  # Hz


def load_config():
    """Load configuration from config.yaml"""
    config_path = Path(__file__).parent.parent / "config" / "config.yaml"
    try:
        with open(config_path, 'r') as file:
            config = yaml.safe_load(file)
        return config
    except Exception as e:
        print(f"Error loading config.yaml: {e}")
        return None

def read_commands(game_name=None):
    """
    Reads encrypted commands from sync file based on game name.
    Returns a dictionary mapping frame ID to a list of encrypted commands.
    """
    config = load_config()
    if not config:
        print("Warning: Could not load config, using default sync_kombat.txt")
        sync_file = Path(__file__).parent.parent / "player" / "syncs" / "sync_kombat.txt"
    else:
        if game_name is None:
            game_name = config["Running"]["game"]
        
        # Get sync file path from game-specific config
        game_config = config.get(game_name, {})
        sync_file_rel = game_config.get("sync_file", f"./syncs/sync_{game_name.lower()}.txt")
        sync_file = Path(__file__).parent.parent / sync_file_rel.lstrip("./")
    
    commands = defaultdict(list)

    if not sync_file.exists():
        print(f"Warning: {sync_file} does not exist. Continuing without commands.")
        return commands

    print("Reading commands from:", sync_file)
    with sync_file.open('r') as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("ID"):
                continue
            parts = line.split(",")
            try:
                frame_id = int(parts[0])
                encrypted_command = parts[-1]
                commands[frame_id].append(encrypted_command)
                print(f"Frame ID: {frame_id}, Encrypted Command: {encrypted_command}")
            except ValueError:
                print("Invalid line format:", line)

    return commands

def read_commands_from_file(sync_file_path, quiet=False):
    """
    Reads encrypted commands from a specific sync file.
    Returns a dictionary mapping frame ID to a list of encrypted commands.
    """
    commands = defaultdict(list)
    
    if not sync_file_path.exists():
        if not quiet:
            print(f"Warning: {sync_file_path} does not exist. Continuing without commands.")
        return commands

    if not quiet:
        print("Reading commands from:", sync_file_path)
    
    with sync_file_path.open('r') as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("ID"):
                continue
            parts = line.split(",")
            try:
                frame_id = int(parts[0])
                encrypted_command = parts[-1]
                commands[frame_id].append(encrypted_command)
                if not quiet:
                    print(f"Frame ID: {frame_id}, Encrypted Command: {encrypted_command}")
            except ValueError:
                if not quiet:
                    print("Invalid line format:", line)

    return commands

def load_ipi_values(ipi_file):
    """Load IPI values from CSV file or use defaults."""
    ipis = []
    
    if ipi_file is None:
        # Use default IPI values based on FPS from config
        config = load_config()
        if config and "encoding" in config and "fps" in config["encoding"]:
            fps = config["encoding"]["fps"]
            ipi = 1.0 / fps
            print(f"Using default IPI values based on {fps} FPS: {ipi:.4f}s")
            ipis = [ipi] * 1000  # Generate many default values
        else:
            print("Using fallback default IPI values (30 FPS)")
            ipis = [0.033] * 1000  # ~30 fps fallback
        return ipis
    
    try:
        with open(ipi_file, 'r') as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            for row in reader:
                try:
                    # Convert to seconds, don't filter out "Other" packets
                    ipi = float(row[0]) / 100000  # Convert to seconds
                    ipis.append(ipi)
                except Exception as e:
                    print(f"Skipping invalid row: {row} - {e}")
    except Exception as e:
        print(f"Error loading IPI file {ipi_file}: {e}")
        print("Using default IPI values")
        config = load_config()
        if config and "encoding" in config and "fps" in config["encoding"]:
            fps = config["encoding"]["fps"]
            ipi = 1.0 / fps
            ipis = [ipi] * 1000
        else:
            ipis = [0.033] * 1000
    
    if not ipis:
        # Fallback to default values if no valid IPIs found
        print("No valid IPI values found. Using default values.")
        ipis = [0.033] * 1000  # ~30 fps
    
    print(f"Loaded {len(ipis)} IPI values")
    return ipis

def packetize_nalu(nalu, seq, current_timestamp, ssrc, marker, max_payload_size, ipi_cycler):
    """
    RTP packetization of a single NAL unit.
    Returns a list of (packet, new_seq, updated_timestamp) tuples.
    
    FIXED: All fragments of the same NAL unit get the same timestamp,
    only updating timestamps between different NAL units.
    """
    packets = []
    # Get next IPI value only once per NAL unit
    ipi = next(ipi_cycler)
    timestamp = current_timestamp + int(ipi * rtp_clock_rate)
    
    if len(nalu) <= max_payload_size:
        # Single NAL Unit packet
        rtp = RTP(
            version=2, padding=0, extension=0, marker=marker,
            payload_type=96, sequence=seq % 65536,
            timestamp=int(timestamp), sourcesync=ssrc
        ) / Raw(load=nalu)
        packets.append((rtp, seq + 1, timestamp))
    else:
        # Fragmentation Units
        nal_header = nalu[0]
        nal_type = nal_header & 0x1F
        nal_nri = (nal_header >> 5) & 0x03

        offset = 1
        while offset < len(nalu):
            end = min(offset + max_payload_size - 2, len(nalu))
            start_bit = 1 if offset == 1 else 0
            end_bit = 1 if end == len(nalu) else 0
            
            # Only mark the last fragment with the marker bit if the original NAL had it
            current_marker = marker if end_bit else 0

            fu_indicator = (nal_nri << 5) | 28  # FU-A
            fu_header = (start_bit << 7) | (end_bit << 6) | nal_type
            fragment = bytes([fu_indicator, fu_header]) + nalu[offset:end]

            rtp = RTP(
                version=2, padding=0, extension=0, marker=current_marker,
                payload_type=96, sequence=seq % 65536,
                timestamp=int(timestamp), sourcesync=ssrc
            ) / Raw(load=fragment)
            
            packets.append((rtp, seq + 1, timestamp))
            seq += 1
            offset = end
        
        print(f"Fragmented NAL unit into {len(packets)} packets with timestamp: {timestamp}")

    return packets, timestamp


def encode_image_to_nalus(img_path, codec=DEFAULT_CODEC):
    """
    Encodes an image to H.264/H.265 and extracts NAL units.
    FIXED: Improved NAL unit extraction with proper handling of start codes.
    """
    assert codec in ["h264", "h265"], "Codec must be 'h264' or 'h265'"
    suffix = "h264" if codec == "h264" else "hevc"

    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{suffix}") as out_file:
        encoded_path = out_file.name

    try:
        # Use more conservative encoding parameters
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(img_path),
            "-pix_fmt", "yuv420p",
            "-c:v", codec,
            "-profile:v", "baseline",  # Use baseline profile for better compatibility
            "-preset", "slow",         # Better quality, more compatible
            "-x264opts", "keyint=1:min-keyint=1", # Force every frame to be a keyframe
            "-b:v", "1500k",           # Slightly higher bitrate
            "-maxrate", "2500k",
            "-bufsize", "4000k",
            "-f", "rawvideo", encoded_path
        ], check=True)

        with open(encoded_path, "rb") as f:
            data = f.read()

        # Improved NAL unit extraction
        nalus = []
        i = 0
        start_codes = [b'\x00\x00\x00\x01', b'\x00\x00\x01']

        while i < len(data):
            # Find start code
            start_code_pos = -1
            start_code_len = 0
            
            for code in start_codes:
                pos = data.find(code, i)
                if pos != -1 and (start_code_pos == -1 or pos < start_code_pos):
                    start_code_pos = pos
                    start_code_len = len(code)
            
            if start_code_pos == -1:
                break
                
            # Find the start of the next NAL unit
            next_start_pos = len(data)
            for code in start_codes:
                pos = data.find(code, start_code_pos + start_code_len)
                if pos != -1 and pos < next_start_pos:
                    next_start_pos = pos
            
            # Extract the NAL unit without the start code
            nal_start = start_code_pos + start_code_len
            nal_end = next_start_pos
            nal_unit = data[nal_start:nal_end]
            
            if nal_unit:  # Only add if not empty
                nalus.append(nal_unit)
            
            i = start_code_pos + start_code_len
            if i >= next_start_pos:
                i = next_start_pos
        
        # Log the NAL units we found
        for idx, nalu in enumerate(nalus):
            if nalu:
                nal_type = (nalu[0] & 0x1F) if codec == "h264" else ((nalu[0] >> 1) & 0x3F)
                print(f"NAL {idx}: type={nal_type}, size={len(nalu)} bytes")

        return nalus
    finally:
        os.remove(encoded_path)


def create_rtp_packets(
    codec=DEFAULT_CODEC,
    game_name=None,
    output_file=None,
    frames_dir=None,
    ipi_file=None,
    sync_file=None,
    server_ip=None,
    player_ip=None,
    server_port=None,
    player_port=None,
    include_commands=True,
    max_payload_size=1200,
    ssrc=12345,
    start_seq=0,
    start_timestamp=0,
    verbose=False,
    quiet=False
):
    """
    Reads PNG frames, encodes them to NALUs, and writes RTP packets to PCAP.
    Fully configurable with command-line arguments and config.yaml overrides.
    """
    def log(msg, force=False):
        if not quiet and (verbose or force):
            print(msg)
    
    config = load_config()
    if not config:
        log("Error: Could not load configuration")
        return

    base_path = Path(__file__).parent.resolve()
    
    # Determine game name
    if game_name is None:
        game_name = config["Running"]["game"]
    
    # Get game-specific paths
    game_config = config.get(game_name, {})
    
    # Construct paths
    if frames_dir is None:
        frames_path = game_config.get("frames", game_name)
        img_dir = base_path.parent / "server" / frames_path
    else:
        img_dir = Path(frames_dir)
    
    # Determine output file
    if output_file is None:
        output_pcap = f"rtp_stream_{codec}_{game_name.lower()}.pcap"
    else:
        output_pcap = output_file

    # Network configuration with argument overrides
    server_ip = server_ip or config["server"]["server_IP"]
    player_ip = player_ip or config["gamer"]["player_IP"]
    server_port = server_port or config["server"]["server_port"]
    player_port = player_port or config["gamer"]["player_streaming_port"]
    
    # MAC addresses (fallback since not in config)
    server_mac = "00:11:22:33:44:55"
    player_mac = "66:77:88:99:aa:bb"

    # RTP setup
    seq = start_seq
    timestamp = start_timestamp
    all_packets = []

    # Read commands
    if include_commands:
        if sync_file is not None:
            commands = read_commands_from_file(sync_file)
        else:
            commands = read_commands(game_name)
    else:
        commands = defaultdict(list)
        log("Skipping command packets (--no-commands)")

    # Validate paths
    if not img_dir.exists():
        log(f"Error: Image directory {img_dir} does not exist.")
        return
    
    log(f"Using game: {game_name}")
    log(f"Using codec: {codec}")
    log(f"Output file: {output_pcap}")
    log(f"Image directory: {img_dir}")
    log(f"Server: {server_ip}:{server_port} -> Player: {player_ip}:{player_port}")

    # Load IPI values
    ipis = load_ipi_values(ipi_file)
    
    # Create a cyclic iterator for IPIs
    ipi_cycler = itertools.cycle(ipis)

    # Find all PNG files
    image_files = sorted(img_dir.glob("*.png"))
    log(f"Found {len(image_files)} PNG files", force=True)

    if not image_files:
        log("No PNG files found in the specified directory.")
        return

    # Loop through each frame
    for frame_index, img_path in enumerate(image_files, start=1):
        log(f"Processing frame {frame_index}/{len(image_files)}: {img_path.name}, MaxPayload={max_payload_size}")

        # Encode image to NAL units
        nal_units = encode_image_to_nalus(img_path, codec=codec)
        
        # Process each NAL unit for this frame
        for idx, nalu in enumerate(nal_units):
            # Mark only the last NAL unit of the frame
            marker = 1 if idx == len(nal_units) - 1 else 0
            
            # Packetize the NAL unit
            rtp_packets, updated_timestamp = packetize_nalu(
                nalu, seq, timestamp, ssrc, marker, max_payload_size, ipi_cycler
            )
            timestamp = updated_timestamp  # Update timestamp for next NAL unit
            
            # Create network packets
            for rtp, new_seq, _ in rtp_packets:
                ip = IP(src=server_ip, dst=player_ip)
                udp = UDP(sport=server_port, dport=player_port)
                eth = Ether(src=server_mac, dst=player_mac)
                full_packet = eth / ip / udp / rtp
                all_packets.append(full_packet)
                seq = new_seq

        # Process commands for this frame if any
        if frame_index in commands:
            for command in commands[frame_index]:
                # Get next IPI and update timestamp for command packet
                ipi = next(ipi_cycler)
                timestamp += int(ipi * rtp_clock_rate)
                
                # Use a distinct payload type for command RTP packets
                rtp_command = RTP(
                    version=2, padding=0, extension=0, marker=1,
                    payload_type=97, sequence=seq % 65536,
                    timestamp=int(timestamp), sourcesync=ssrc
                ) / Raw(load=command.encode())

                ip = IP(src=player_ip, dst=server_ip)
                udp = UDP(sport=player_port, dport=server_port)
                eth = Ether(src=player_mac, dst=server_mac)
                full_packet = eth / ip / udp / rtp_command
                all_packets.append(full_packet)
                seq += 1
                log(f"Added command for frame {frame_index}: {command} with timestamp {timestamp}")

    # Write packets to PCAP file
    log(f"Writing {len(all_packets)} packets to {output_pcap}", force=True)
    wrpcap(output_pcap, all_packets, nano=True)
    log(f"RTP packet stream generation complete.", force=True)
    
    return output_pcap

def log(message, force=False):
    """Helper function for conditional logging based on quiet flag."""
    if not (quiet and not force):
        print(message)

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="RTP Video Packetizer - Create RTP streams from video frames for CGReplay",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Use H.264 and game from config.yaml
  %(prog)s --codec h265                       # Use H.265 codec
  %(prog)s --game Fortnite --codec h264       # Override game selection
  %(prog)s --output custom.pcap               # Custom output filename
  %(prog)s --frames-dir /path/to/frames       # Custom frames directory
  %(prog)s --ipi-file /path/to/ipi.csv        # Custom IPI timing file
  %(prog)s --server-ip 192.168.1.100          # Custom server IP
  %(prog)s --no-commands                      # Skip command packets
        """
    )
    
    # Basic options
    parser.add_argument(
        "--codec", 
        choices=["h264", "h265"], 
        default=DEFAULT_CODEC,
        help=f"Video codec to use (default: {DEFAULT_CODEC})"
    )
    
    parser.add_argument(
        "--game",
        choices=["Fortnite", "Forza", "Kombat"],
        required=True,
        help="Game to process (Fortnite, Forza, or Kombat)"
    )
    
    parser.add_argument(
        "--output",
        help="Output PCAP filename (default: rtp_stream_{codec}_{game}.pcap)"
    )
    
    # Path options
    parser.add_argument(
        "--frames-dir",
        type=Path,
        help="Directory containing PNG frames (overrides config.yaml)"
    )
    
    parser.add_argument(
        "--ipi-file",
        type=Path,
        help="IPI timing file (CSV format). If not provided, uses defaults"
    )
    
    parser.add_argument(
        "--sync-file",
        type=Path,
        help="Sync commands file (overrides game-specific sync file)"
    )
    
    # Network configuration
    parser.add_argument(
        "--server-ip",
        help="Server IP address (overrides config.yaml)"
    )
    
    parser.add_argument(
        "--player-ip",
        help="Player IP address (overrides config.yaml)"
    )
    
    parser.add_argument(
        "--server-port",
        type=int,
        help="Server port (overrides config.yaml)"
    )
    
    parser.add_argument(
        "--player-port",
        type=int,
        help="Player port (overrides config.yaml)"
    )
    
    # Control options
    parser.add_argument(
        "--no-commands",
        action="store_true",
        help="Skip reading and including sync commands"
    )
    
    parser.add_argument(
        "--max-payload",
        type=int,
        default=1200,
        help="Maximum RTP payload size in bytes (default: 1200)"
    )
    
    parser.add_argument(
        "--ssrc",
        type=int,
        default=12345,
        help="RTP SSRC identifier (default: 12345)"
    )
    
    parser.add_argument(
        "--start-seq",
        type=int,
        default=0,
        help="Starting RTP sequence number (default: 0)"
    )
    
    parser.add_argument(
        "--start-timestamp",
        type=int,
        default=0,
        help="Starting RTP timestamp (default: 0)"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress non-error output"
    )
    
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()
    
    # Set global quiet flag for logging
    global quiet
    quiet = args.quiet
    
    # Call create_rtp_packets with parsed arguments
    try:
        output_file = create_rtp_packets(
            codec=args.codec,
            game_name=args.game,
            output_file=args.output,
            frames_dir=args.frames_dir,
            ipi_file=args.ipi_file,
            sync_file=args.sync_file,
            server_ip=args.server_ip,
            server_port=args.server_port,
            player_ip=args.player_ip,
            player_port=args.player_port,
            include_commands=not args.no_commands,
            quiet=args.quiet,
            verbose=args.verbose
        )
        
        if output_file:
            log(f"Successfully created RTP stream: {output_file}", force=True)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)