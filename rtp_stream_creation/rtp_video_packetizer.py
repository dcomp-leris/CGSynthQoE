from pathlib import Path
from scapy.all import *
import os
import csv
import subprocess
import tempfile
from collections import defaultdict
import random
import itertools
import argparse
import sys
import math

DEFAULT_CODEC = "h264"
MIN_PAYLOAD_SIZE = 900
MAX_PAYLOAD_SIZE_LIMIT = 1400
rtp_clock_rate = 90000  # Hz


def read_commands():
    """
    Reads encrypted commands from sync_kombat.txt.
    Returns a dictionary mapping frame ID to a list of encrypted commands.
    """
    base_path = Path(__file__).parent
    sync_file = base_path.parent / "player" / "syncs" / "sync_kombat.txt"
    commands = defaultdict(list)

    if not sync_file.exists():
        print(f"Warning: {sync_file} does not exist. Continuing without commands.")
        return commands

    try:
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
                except (ValueError, IndexError) as e:
                    print(f"Invalid line format: {line} - {e}")
    except Exception as e:
        print(f"Error reading commands file: {e}")

    return commands


def load_ipi_values(ipi_file):
    """Load IPI values from CSV file."""
    ipis = []
    
    if not ipi_file.exists():
        print(f"Warning: IPI file {ipi_file} does not exist. Using default values.")
        return [0.033] * 100  # ~30 fps default
    
    try:
        with open(ipi_file, 'r') as f:
            reader = csv.reader(f)
            try:
                next(reader)  # Skip header if present
            except StopIteration:
                pass
            
            for row_num, row in enumerate(reader, start=1):
                if not row:  # Skip empty rows
                    continue
                try:
                    # Convert to seconds, don't filter out "Other" packets
                    ipi = float(row[0]) / 100000  # Convert to seconds
                    if ipi > 0:  # Only add positive values
                        ipis.append(ipi)
                except (ValueError, IndexError) as e:
                    print(f"Skipping invalid row {row_num}: {row} - {e}")
    except Exception as e:
        print(f"Error loading IPI file: {e}")
        return [0.033] * 100  # Fallback to default values
    
    if not ipis:
        # Fallback to default values if no valid IPIs found
        print("No valid IPI values found. Using default values.")
        ipis = [0.033] * 100  # ~30 fps
    
    print(f"Loaded {len(ipis)} IPI values")
    return ipis


def packetize_nalu(nalu, seq, rtp_timestamp, ssrc, marker, max_payload_size, ipi_cycler, packet_time):
    """
    RTP packetization of a single NAL unit.
    Returns a list of (packet, new_seq, packet_time) tuples.
    Note: RTP timestamp stays the same for all packets in this NAL (and frame).
    """
    packets = []
    
    if len(nalu) <= max_payload_size:
        # Single NAL Unit packet
        # Get next IPI value for packet spacing
        ipi = next(ipi_cycler)
        packet_time += ipi
        
        rtp = RTP(
            version=2, padding=0, extension=0, marker=marker,
            payload_type=96, sequence=seq % 65536,
            timestamp=int(rtp_timestamp), sourcesync=ssrc
        ) / Raw(load=nalu)
        packets.append((rtp, seq + 1, packet_time))
    else:
        # Fragmentation Units (FU-A for H.264)
        nal_header = nalu[0]
        nal_type = nal_header & 0x1F
        nal_nri = (nal_header >> 5) & 0x03

        # Calculate proper fragment size accounting for FU headers
        max_fragment_payload = max_payload_size - 2  # 2 bytes for FU indicator + FU header
        
        # Calculate number of fragments needed
        num_fragments = math.ceil((len(nalu) - 1) / max_fragment_payload)
        
        offset = 1  # Skip the original NAL header
        fragment_index = 0
        
        while offset < len(nalu):
            # Get next IPI value for each fragment
            ipi = next(ipi_cycler)
            packet_time += ipi
            
            # Calculate fragment end position
            remaining_bytes = len(nalu) - offset
            fragment_size = min(max_fragment_payload, remaining_bytes)
            end = offset + fragment_size
            
            # Set FU flags
            start_bit = 1 if fragment_index == 0 else 0
            end_bit = 1 if end == len(nalu) else 0
            
            # Only mark the last fragment with the marker bit if the original NAL had it
            current_marker = marker if end_bit else 0

            # Create FU-A headers
            fu_indicator = (nal_nri << 5) | 28  # FU-A type (28)
            fu_header = (start_bit << 7) | (end_bit << 6) | nal_type
            fragment = bytes([fu_indicator, fu_header]) + nalu[offset:end]

            rtp = RTP(
                version=2, padding=0, extension=0, marker=current_marker,
                payload_type=96, sequence=seq % 65536,
                timestamp=int(rtp_timestamp), sourcesync=ssrc
            ) / Raw(load=fragment)
            
            packets.append((rtp, seq + 1, packet_time))
            seq += 1
            offset = end
            fragment_index += 1

    return packets, packet_time


def encode_images_to_video(img_dir, codec=DEFAULT_CODEC, fps=30, target_bitrate="5M"):
    """
    Encodes a sequence of PNG images into a video file, then extracts NAL units.
    This creates a proper video stream with P-frames and B-frames, not just I-frames.
    """
    assert codec in ["h264", "h265"], "Codec must be 'h264' or 'h265'"
    suffix = "h264" if codec == "h264" else "hevc"

    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{suffix}") as out_file:
        encoded_path = out_file.name

    try:
        # Check if ffmpeg is available
        try:
            subprocess.run(["ffmpeg", "-version"], 
                         stdout=subprocess.DEVNULL, 
                         stderr=subprocess.DEVNULL, 
                         check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("ffmpeg is not installed or not in PATH")

        # Find all PNG files
        image_files = sorted(img_dir.glob("*.png"))
        if not image_files:
            raise RuntimeError(f"No PNG files found in {img_dir}")

        # Create a temporary file listing all images
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            filelist_path = f.name
            for img in image_files:
                f.write(f"file '{img.absolute()}'\n")
                f.write(f"duration {1/fps}\n")

        try:
            # Build ffmpeg command for video encoding with realistic cloud gaming settings
            cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "concat",
                "-safe", "0",
                "-i", filelist_path,
                "-pix_fmt", "yuv420p",
                "-c:v", "libx264" if codec == "h264" else "libx265",
                "-profile:v", "main",          # Use main profile (more common in CG)
                "-level", "4.1",               # Higher level for better quality
                "-preset", "veryfast",         # Fast encoding like real-time CG
                "-tune", "zerolatency",        # Optimize for low latency
                "-b:v", target_bitrate,        # Target bitrate (realistic for CG)
                "-maxrate", target_bitrate,    # Max bitrate
                "-bufsize", "2M",              # Buffer size for rate control
                "-g", "60",                    # GOP size of 60 frames (2 seconds at 30fps)
                "-keyint_min", "60",           # Minimum GOP size
                "-sc_threshold", "40",         # Scene change detection threshold
                "-bf", "0",                    # No B-frames for lower latency
                "-refs", "1",                  # Single reference frame
                "-bsf:v", "h264_mp4toannexb" if codec == "h264" else "hevc_mp4toannexb",
                "-f", "rawvideo", encoded_path
            ]

            print(f"Encoding {len(image_files)} frames as video stream...")
            subprocess.run(cmd, check=True)

            with open(encoded_path, "rb") as f:
                data = f.read()

            if not data:
                raise RuntimeError(f"No data generated from encoding")

            print(f"Encoded video size: {len(data)} bytes")

            # Extract NAL units from the video stream
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
            
            # Group NAL units by frame
            frames_nalus = []
            current_frame = []
            sps_pps_nalus = []
            
            for idx, nalu in enumerate(nalus):
                if not nalu:
                    continue
                    
                if codec == "h264":
                    nal_type = nalu[0] & 0x1F
                    print(f"NAL {idx}: type={nal_type}, size={len(nalu)} bytes")
                    
                    # Collect SPS/PPS separately (only sent once)
                    if nal_type == 7 or nal_type == 8:  # SPS or PPS
                        if nalu not in sps_pps_nalus:
                            sps_pps_nalus.append(nalu)
                        continue
                    
                    # Check if this is a slice (frame data)
                    if nal_type in [1, 5]:  # Non-IDR slice or IDR slice
                        current_frame.append(nalu)
                        # If it's an IDR (keyframe), it marks end of previous frame
                        if nal_type == 5 and len(current_frame) == 1:
                            if frames_nalus and frames_nalus[-1]:  # Close previous frame
                                pass
                    
                    # AUD (Access Unit Delimiter) or SEI can indicate frame boundary
                    if nal_type == 9 and current_frame:  # AUD
                        frames_nalus.append(current_frame)
                        current_frame = []
                else:  # h265
                    nal_type = (nalu[0] >> 1) & 0x3F
                    print(f"NAL {idx}: type={nal_type}, size={len(nalu)} bytes")
                    
                    if nal_type in [33, 34, 35]:  # SPS, PPS, VPS
                        if nalu not in sps_pps_nalus:
                            sps_pps_nalus.append(nalu)
                        continue
                    
                    if nal_type <= 31:  # Slice
                        current_frame.append(nalu)
                    
                    if nal_type == 35 and current_frame:  # AUD
                        frames_nalus.append(current_frame)
                        current_frame = []
            
            # Add the last frame if any
            if current_frame:
                frames_nalus.append(current_frame)
            
            print(f"Extracted {len(frames_nalus)} frames with {len(sps_pps_nalus)} parameter sets")
            
            return sps_pps_nalus, frames_nalus
        
        finally:
            # Clean up filelist
            if os.path.exists(filelist_path):
                os.remove(filelist_path)
    
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"FFmpeg encoding failed: {e}")
    except Exception as e:
        raise RuntimeError(f"Error encoding video: {e}")
    finally:
        # Clean up temporary file
        if os.path.exists(encoded_path):
            os.remove(encoded_path)


def create_rtp_packets(codec=DEFAULT_CODEC, 
                      server_ip="192.168.0.10", user_ip="192.168.0.20",
                      server_port=5004, user_port=5004,
                      server_mac="00:11:22:33:44:55", user_mac="66:77:88:99:aa:bb",
                      img_dir=None, ipi_file=None, max_payload_size=1200,
                      fps=30, target_bitrate="5M"):
    """
    Reads PNG frames, encodes them as a video stream, and writes RTP packets to PCAP.
    FIXED: Now encodes as proper video with P-frames, sends SPS/PPS only once.
    FIXED: RTP timestamps stay constant within frames, PCAP timestamps use IPI values.
    """
    base_path = Path(__file__).parent.resolve()
    
    # Set default paths if not provided
    if img_dir is None:
        img_dir = base_path.parent / "frame_gen" / "rescaling" / "downscaled_original_frames_from_1920_1080_to_1280_720"
    else:
        img_dir = Path(img_dir)
        
    if ipi_file is None:
        ipi_file = base_path.parent / "rtp_stream_creation" / "all_packets.txt"
    else:
        ipi_file = Path(ipi_file)
    
    output_pcap = f"rtp_stream_{codec}.pcap"

    # RTP setup
    ssrc = 12345
    seq = 0
    rtp_timestamp = 0
    timestamp = 0
    packet_time = 0.0  # Track actual packet time for PCAP timestamps
    all_packets = []

    # Read commands
    commands = read_commands()

    # Validate paths
    if not img_dir.exists():
        print(f"Error: Image directory {img_dir} does not exist.")
        return False

    # Load IPI values
    ipis = load_ipi_values(ipi_file)
    if not ipis:
        return False
    
    # Create a cyclic iterator for IPIs
    ipi_cycler = itertools.cycle(ipis)

    try:
        # Encode all images as a video stream
        sps_pps_nalus, frames_nalus = encode_images_to_video(img_dir, codec, fps, target_bitrate)
        
        if not frames_nalus:
            print("Error: No frames generated from video encoding")
            return False
        
        # Send SPS/PPS once at the beginning
        print(f"Sending {len(sps_pps_nalus)} parameter sets at stream start...")
        for idx, nalu in enumerate(sps_pps_nalus):
            marker = 0  # Parameter sets don't mark frame boundaries
            
            rtp_packets, packet_time = packetize_nalu(
                nalu, seq, rtp_timestamp, ssrc, marker, max_payload_size, ipi_cycler, packet_time
            )
            
            for rtp, new_seq, pkt_time in rtp_packets:
                ip = IP(src=server_ip, dst=user_ip)
                udp = UDP(sport=server_port, dport=user_port)
                eth = Ether(src=server_mac, dst=user_mac)
                full_packet = eth / ip / udp / rtp
                full_packet.time = pkt_time  # Set PCAP timestamp
                all_packets.append(full_packet)
                seq = new_seq
        
        # Process each frame
        for frame_index, frame_nalus in enumerate(frames_nalus, start=1):
            print(f"Processing frame {frame_index}/{len(frames_nalus)}, NALs={len(frame_nalus)}, MaxPayload={max_payload_size} bytes")
            
            if not frame_nalus:
                continue
            
            # Process each NAL unit in this frame
            for idx, nalu in enumerate(frame_nalus):
                # Mark only the last NAL unit of the frame
                marker = 1 if idx == len(frame_nalus) - 1 else 0
                
                # Packetize the NAL unit
                rtp_packets, updated_timestamp = packetize_nalu(
                    nalu, seq, rtp_timestamp, ssrc, marker, max_payload_size, ipi_cycler, timestamp
                )
                timestamp = updated_timestamp
                
                # Create network packets
                for rtp, new_seq, _ in rtp_packets:
                    ip = IP(src=server_ip, dst=user_ip)
                    udp = UDP(sport=server_port, dport=user_port)
                    eth = Ether(src=server_mac, dst=user_mac)
                    full_packet = eth / ip / udp / rtp
                    all_packets.append(full_packet)
                    seq = new_seq

            # Process commands for this frame if any
            if frame_index in commands:
                for command in commands[frame_index]:
                    ipi = next(ipi_cycler)
                    timestamp += int(ipi * rtp_clock_rate)
                    
                    rtp_command = RTP(
                        version=2, padding=0, extension=0, marker=1,
                        payload_type=97, sequence=seq % 65536,
                        timestamp=int(timestamp), sourcesync=ssrc
                    ) / Raw(load=command.encode())

                    ip = IP(src=user_ip, dst=server_ip)
                    udp = UDP(sport=user_port, dport=server_port)
                    eth = Ether(src=user_mac, dst=server_mac)
                    full_packet = eth / ip / udp / rtp_command
                    all_packets.append(full_packet)
                    seq += 1
                    print(f"Added command for frame {frame_index}: {command}")

    except Exception as e:
        print(f"Error during encoding/packetization: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Write packets to PCAP file
    if all_packets:
        print(f"Writing {len(all_packets)} packets to {output_pcap}")
        wrpcap(output_pcap, all_packets)
        print(f"RTP packet stream generation complete. Output: {output_pcap}")
        return True
    else:
        print("No packets were generated.")
        return False


def main():
    """Main function with argument parsing."""
    parser = argparse.ArgumentParser(description="Generate RTP packets from PNG frames")
    parser.add_argument("--codec", default=DEFAULT_CODEC, choices=["h264", "h265"], 
                       help="Codec to use (default: h264)")
    parser.add_argument("--server-ip", default="192.168.0.10", 
                       help="Server (sender) IP address")
    parser.add_argument("--user-ip", default="192.168.0.20", 
                       help="User (receiver) IP address")
    parser.add_argument("--server-port", type=int, default=5004, 
                       help="Server UDP port")
    parser.add_argument("--user-port", type=int, default=5004, 
                       help="User UDP port")
    parser.add_argument("--server-mac", default="00:11:22:33:44:55", 
                       help="Server MAC address")
    parser.add_argument("--user-mac", default="66:77:88:99:aa:bb", 
                       help="User MAC address")
    parser.add_argument("--img-dir", 
                       help="Directory containing PNG frames")
    parser.add_argument("--ipi-file", 
                       help="CSV file containing IPI values")
    parser.add_argument("--max-payload-size", type=int, default=1200,
                       help="Maximum RTP payload size (default: 1200)")
    parser.add_argument("--fps", type=int, default=30,
                       help="Target frames per second (default: 30)")
    parser.add_argument("--bitrate", default="5000k",
                       help="Target bitrate for encoding (default: 5Mbps)")
    
    args = parser.parse_args()
    
    if args.max_payload_size > MAX_PAYLOAD_SIZE_LIMIT:
        print(f"Warning: Maximum payload size {args.max_payload_size} exceeds limit of {MAX_PAYLOAD_SIZE_LIMIT}. Using limit instead.")
        args.max_payload_size = MAX_PAYLOAD_SIZE_LIMIT

    try:
        success = create_rtp_packets(
            codec=args.codec,
            server_ip=args.server_ip,
            user_ip=args.user_ip,
            server_port=args.server_port,
            user_port=args.user_port,
            server_mac=args.server_mac,
            user_mac=args.user_mac,
            img_dir=args.img_dir,
            ipi_file=args.ipi_file,
            max_payload_size=args.max_payload_size,
            fps=args.fps,
            target_bitrate=args.bitrate
        )
        
        if not success:
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()