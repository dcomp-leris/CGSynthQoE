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


def read_commands(game):
    """
    Reads encrypted commands from sync_kombat.txt.
    Returns a dictionary mapping frame ID to a list of encrypted commands.
    """
    base_path = Path(__file__).parent
    if game == "Kombat":
        sync_file = base_path.parent / "CGReplay" / "player" / "syncs" / "sync_kombat.txt"
    elif game == "Fortnite":
        sync_file = base_path.parent / "CGReplay" / "player" / "syncs" / "sync_fortnite.txt"
    elif game == "Forza":
        sync_file = base_path.parent / "CGReplay" / "player" / "syncs" / "sync_forza.txt"
    else:
        exit(f"Unsupported game for commands: {game}")
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

'''
def encode_images_to_video(img_dir, codec=DEFAULT_CODEC, fps=30, target_bitrate="5M"):
    """
    Encodes a sequence of PNG images into a video file, then extracts NAL units.
    FIXED: Uses image2 demuxer with framerate to ensure all frames are encoded.
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

        print(f"Found {len(image_files)} PNG files to encode")

        # FIXED: Use image2 demuxer with pattern matching instead of concat
        # This is much more reliable for image sequences
        
        # Determine the file pattern
        first_file = image_files[0].name
        
        # Check if files are numbered (e.g., 0001.png, 0002.png, etc.)
        import re
        match = re.match(r'^(\D*)(\d+)(\.\w+)$', first_file)
        
        if match:
            prefix, number, extension = match.groups()
            num_digits = len(number)
            pattern = f"{prefix}%0{num_digits}d{extension}"
            input_path = str(img_dir / pattern)
            
            # Use image2 demuxer with framerate
            cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-framerate", str(fps),  # Input framerate
                "-i", input_path,
                "-frames:v", str(len(image_files)),  # CRITICAL: Specify exact frame count
                "-pix_fmt", "yuv420p",
                "-c:v", "libx264" if codec == "h264" else "libx265",
                "-profile:v", "main",
                "-level", "4.1",
                "-preset", "veryfast",
                "-tune", "zerolatency",
                "-b:v", target_bitrate,
                "-maxrate", target_bitrate,
                "-bufsize", "2M",
                "-g", "60",
                "-keyint_min", "60",
                "-sc_threshold", "40",
                "-bf", "0",
                "-refs", "1",
                "-x264opts" if codec == "h264" else "-x265-params", 
                "aud=1",
                "-bsf:v", "h264_mp4toannexb" if codec == "h264" else "hevc_mp4toannexb",
                "-f", "rawvideo", encoded_path
            ]
        else:
            # Fallback: Create numbered symlinks if files don't follow pattern
            temp_dir = tempfile.mkdtemp()
            try:
                for idx, img_file in enumerate(image_files):
                    link_path = Path(temp_dir) / f"frame_{idx:04d}.png"
                    link_path.symlink_to(img_file.absolute())
                
                cmd = [
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-framerate", str(fps),
                    "-i", str(Path(temp_dir) / "frame_%04d.png"),
                    "-frames:v", str(len(image_files)),
                    "-pix_fmt", "yuv420p",
                    "-c:v", "libx264" if codec == "h264" else "libx265",
                    "-profile:v", "main",
                    "-level", "4.1",
                    "-preset", "veryfast",
                    "-tune", "zerolatency",
                    "-b:v", target_bitrate,
                    "-maxrate", target_bitrate,
                    "-bufsize", "2M",
                    "-g", "60",
                    "-keyint_min", "60",
                    "-sc_threshold", "40",
                    "-bf", "0",
                    "-refs", "1",
                    "-x264opts" if codec == "h264" else "-x265-params",
                    "aud=1",
                    "-bsf:v", "h264_mp4toannexb" if codec == "h264" else "hevc_mp4toannexb",
                    "-f", "rawvideo", encoded_path
                ]
            except Exception as e:
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
                raise

        print(f"Encoding {len(image_files)} frames as video stream...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"FFmpeg stderr: {result.stderr}")
            raise subprocess.CalledProcessError(result.returncode, cmd)

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
            start_code_pos = -1
            start_code_len = 0
            
            for code in start_codes:
                pos = data.find(code, i)
                if pos != -1 and (start_code_pos == -1 or pos < start_code_pos):
                    start_code_pos = pos
                    start_code_len = len(code)
            
            if start_code_pos == -1:
                break
                
            next_start_pos = len(data)
            for code in start_codes:
                pos = data.find(code, start_code_pos + start_code_len)
                if pos != -1 and pos < next_start_pos:
                    next_start_pos = pos
            
            nal_start = start_code_pos + start_code_len
            nal_end = next_start_pos
            nal_unit = data[nal_start:nal_end]
            
            if nal_unit:
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
                
                # Collect SPS/PPS separately
                if nal_type in [7, 8]:  # SPS or PPS
                    if nalu not in sps_pps_nalus:
                        sps_pps_nalus.append(nalu)
                    continue
                
                # AUD marks frame boundaries
                if nal_type == 9:  # AUD
                    if current_frame:
                        frames_nalus.append(current_frame)
                        current_frame = []
                    continue
                
                # Slices and SEI
                if nal_type in [1, 5, 6]:
                    current_frame.append(nalu)
                
            else:  # h265
                nal_type = (nalu[0] >> 1) & 0x3F
                print(f"NAL {idx}: type={nal_type}, size={len(nalu)} bytes")
                
                if nal_type in [32, 33, 34]:  # VPS, SPS, PPS
                    if nalu not in sps_pps_nalus:
                        sps_pps_nalus.append(nalu)
                    continue
                
                if nal_type == 35:  # AUD
                    if current_frame:
                        frames_nalus.append(current_frame)
                        current_frame = []
                    continue
                
                if nal_type <= 31:  # Slice
                    current_frame.append(nalu)
        
        # Add the last frame
        if current_frame:
            frames_nalus.append(current_frame)
        
        print(f"Extracted {len(frames_nalus)} frames with {len(sps_pps_nalus)} parameter sets")
        print(f"Expected {len(image_files)} frames")
        
        # Verify frame count
        if len(frames_nalus) != len(image_files):
            print(f"WARNING: Frame count mismatch! Expected {len(image_files)}, got {len(frames_nalus)}")
            print(f"This may indicate an issue with the encoding process.")
        
        return sps_pps_nalus, frames_nalus
    
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"FFmpeg encoding failed: {e}")
    except Exception as e:
        raise RuntimeError(f"Error encoding video: {e}")
    finally:
        if os.path.exists(encoded_path):
            os.remove(encoded_path)           
'''
def encode_images_to_video(img_dir, codec=DEFAULT_CODEC, fps=30, target_bitrate="5M"):
    """
    Encodes a sequence of PNG images into a video file, then extracts NAL units.
    Handles missing frame numbers by creating consecutive temporary links.
    """
    assert codec in ["h264", "h265"], "Codec must be 'h264' or 'h265'"
    suffix = "h264" if codec == "h264" else "hevc"

    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{suffix}") as out_file:
        encoded_path = out_file.name

    temp_dir = None
    
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

        print(f"Found {len(image_files)} PNG files to encode")
        
        # ALWAYS use the symlink approach to handle missing frame numbers
        temp_dir = tempfile.mkdtemp()
        
        print(f"Creating temporary consecutive frame links in {temp_dir}")
        for idx, img_file in enumerate(image_files):
            link_path = Path(temp_dir) / f"frame_{idx:04d}.png"
            # Use copy on Windows if symlink fails
            try:
                link_path.symlink_to(img_file.absolute())
            except OSError:
                # Symlinks may require admin rights on Windows, so copy instead
                import shutil
                shutil.copy2(img_file, link_path)
        
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-framerate", str(fps),
            "-i", str(Path(temp_dir) / "frame_%04d.png"),
            "-frames:v", str(len(image_files)),
            "-pix_fmt", "yuv420p",
            "-c:v", "libx264" if codec == "h264" else "libx265",
            "-profile:v", "main",
            "-level", "4.1",
            "-preset", "veryfast",
            "-tune", "zerolatency",
            "-b:v", target_bitrate,
            "-maxrate", target_bitrate,
            "-bufsize", "2M",
            "-g", "60",
            "-keyint_min", "60",
            "-sc_threshold", "40",
            "-bf", "0",
            "-refs", "1",
            "-x264opts" if codec == "h264" else "-x265-params",
            "aud=1",
            "-bsf:v", "h264_mp4toannexb" if codec == "h264" else "hevc_mp4toannexb",
            "-f", "rawvideo", encoded_path
        ]

        print(f"Encoding {len(image_files)} frames as video stream...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"FFmpeg stderr: {result.stderr}")
            raise subprocess.CalledProcessError(result.returncode, cmd)

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
            start_code_pos = -1
            start_code_len = 0
            
            for code in start_codes:
                pos = data.find(code, i)
                if pos != -1 and (start_code_pos == -1 or pos < start_code_pos):
                    start_code_pos = pos
                    start_code_len = len(code)
            
            if start_code_pos == -1:
                break
                
            next_start_pos = len(data)
            for code in start_codes:
                pos = data.find(code, start_code_pos + start_code_len)
                if pos != -1 and pos < next_start_pos:
                    next_start_pos = pos
            
            nal_start = start_code_pos + start_code_len
            nal_end = next_start_pos
            nal_unit = data[nal_start:nal_end]
            
            if nal_unit:
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
                
                # Collect SPS/PPS separately
                if nal_type in [7, 8]:  # SPS or PPS
                    if nalu not in sps_pps_nalus:
                        sps_pps_nalus.append(nalu)
                    continue
                
                # AUD marks frame boundaries
                if nal_type == 9:  # AUD
                    if current_frame:
                        frames_nalus.append(current_frame)
                        current_frame = []
                    continue
                
                # Slices and SEI
                if nal_type in [1, 5, 6]:
                    current_frame.append(nalu)
                
            else:  # h265
                nal_type = (nalu[0] >> 1) & 0x3F
                print(f"NAL {idx}: type={nal_type}, size={len(nalu)} bytes")
                
                if nal_type in [32, 33, 34]:  # VPS, SPS, PPS
                    if nalu not in sps_pps_nalus:
                        sps_pps_nalus.append(nalu)
                    continue
                
                if nal_type == 35:  # AUD
                    if current_frame:
                        frames_nalus.append(current_frame)
                        current_frame = []
                    continue
                
                if nal_type <= 31:  # Slice
                    current_frame.append(nalu)
        
        # Add the last frame
        if current_frame:
            frames_nalus.append(current_frame)
        
        print(f"Extracted {len(frames_nalus)} frames with {len(sps_pps_nalus)} parameter sets")
        print(f"Expected {len(image_files)} frames")
        
        # Verify frame count
        if len(frames_nalus) != len(image_files):
            print(f"WARNING: Frame count mismatch! Expected {len(image_files)}, got {len(frames_nalus)}")
            print(f"This may indicate an issue with the encoding process.")
        
        return sps_pps_nalus, frames_nalus
    
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"FFmpeg encoding failed: {e}")
    except Exception as e:
        raise RuntimeError(f"Error encoding video: {e}")
    finally:
        # Clean up temporary directory
        if temp_dir and os.path.exists(temp_dir):
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
        if os.path.exists(encoded_path):
            os.remove(encoded_path)
                   

def create_rtp_packets(codec=DEFAULT_CODEC, 
                      server_ip="192.168.0.10", user_ip="192.168.0.20",
                      server_port=5004, user_port=5004,
                      server_mac="00:11:22:33:44:55", user_mac="66:77:88:99:aa:bb",
                      img_dir=None, ipi_file=None, max_payload_size=1200,
                      fps=30, target_bitrate="5M", game="Fortnite", bandwidth_limit="2Mbit"):
    """
    Reads PNG frames, encodes them as a video stream, and writes RTP packets to PCAP.
    FIXED: Now encodes as proper video with P-frames, sends SPS/PPS only once.
    FIXED: RTP timestamps stay constant within frames, PCAP timestamps use IPI values.
    """
    base_path = Path(__file__).parent.resolve()
    
    bdwidth_folder = f"{bandwidth_limit}_{game}"
    
    # Set default paths if not provided
    if img_dir is None:
        img_dir = base_path.parent / "acm_tomm_experiments" / "reference_vs_synth" / game / bdwidth_folder / "received_frames"
    else:
        img_dir = Path(img_dir)
        
    if ipi_file is None:
        ipi_file = base_path.parent / "rtp_stream_creation" / "all_packets.txt"
    else:
        ipi_file = Path(ipi_file)
        
    
    
    output_pcap = base_path.parent / "rtp_stream_creation" / "result_pcaps" / f"{game}_{bandwidth_limit}_rtp_stream.pcap"

    # RTP setup
    ssrc = 12345
    seq = 0
    rtp_timestamp = 0
    timestamp = 0
    packet_time = 0.0  # Track actual packet time for PCAP timestamps
    all_packets = []

    # Read commands
    commands = read_commands(game)

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
        wrpcap(str(output_pcap), all_packets)
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
    
    games = ["Fortnite", "Forza", "Kombat"]
    bandwidths = ["2Mbit", "4Mbit", "6Mbit", "8Mbit", "10Mbit"]
    
    for game in games:
        for bandwidth in bandwidths:
            print(f"Generating RTP stream for {game} at {bandwidth}...")
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
                    target_bitrate=args.bitrate,
                    game=game,
                    bandwidth_limit=bandwidth
                )
                
                if not success:
                    print(f"Failed to generate RTP stream for {game} at {bandwidth}.")
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