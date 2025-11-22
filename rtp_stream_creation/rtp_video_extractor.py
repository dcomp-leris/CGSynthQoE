from pathlib import Path
from scapy.all import *
import argparse
import sys
import subprocess
import tempfile


def extract_rtp_payload(pcap_file, payload_type=96, output_file=None):
    """
    Extract RTP payloads from PCAP file and reconstruct the video stream.
    
    Args:
        pcap_file: Path to the PCAP file
        payload_type: RTP payload type to extract (default: 96 for video)
        output_file: Output video file path (if None, auto-generated)
    
    Returns:
        Path to the extracted video file
    """
    pcap_path = Path(pcap_file)
    
    if not pcap_path.exists():
        raise FileNotFoundError(f"PCAP file not found: {pcap_file}")
    
    print(f"Reading packets from {pcap_file}...")
    packets = rdpcap(str(pcap_path))
    
    print(f"Total packets in PCAP: {len(packets)}")
    
    # Analyze packet types
    payload_types = {}
    udp_count = 0
    rtp_count = 0
    
    for pkt in packets:
        if pkt.haslayer(UDP):
            udp_count += 1
            # Try to parse as RTP
            if pkt.haslayer(Raw):
                raw_data = bytes(pkt[Raw].load)
                if len(raw_data) >= 12:  # Minimum RTP header size
                    # Check if it looks like RTP (version should be 2)
                    version = (raw_data[0] >> 6) & 0x03
                    if version == 2:
                        rtp_count += 1
                        pt = raw_data[1] & 0x7F
                        payload_types[pt] = payload_types.get(pt, 0) + 1
    
    print(f"UDP packets: {udp_count}")
    print(f"Potential RTP packets (version=2): {rtp_count}")
    print(f"Payload types found: {payload_types}")
    
    # Extract RTP packets
    rtp_packets = []
    for pkt in packets:
        if pkt.haslayer(UDP) and pkt.haslayer(Raw):
            raw_data = bytes(pkt[Raw].load)
            if len(raw_data) >= 12:
                version = (raw_data[0] >> 6) & 0x03
                if version == 2:
                    pt = raw_data[1] & 0x7F
                    if pt == payload_type:
                        rtp_packets.append(pkt)
    
    if not rtp_packets:
        if payload_types:
            available_pts = ', '.join(map(str, sorted(payload_types.keys())))
            raise ValueError(f"No RTP packets found with payload type {payload_type}. Available payload types: {available_pts}")
        else:
            raise ValueError(f"No RTP packets found in PCAP file")
    
    print(f"Found {len(rtp_packets)} RTP packets with payload type {payload_type}")
    
    # Parse RTP headers manually and extract payloads
    parsed_packets = []
    for pkt in rtp_packets:
        raw_data = bytes(pkt[Raw].load)
        
        # Parse RTP header
        version = (raw_data[0] >> 6) & 0x03
        padding = (raw_data[0] >> 5) & 0x01
        extension = (raw_data[0] >> 4) & 0x01
        cc = raw_data[0] & 0x0F
        marker = (raw_data[1] >> 7) & 0x01
        pt = raw_data[1] & 0x7F
        sequence = int.from_bytes(raw_data[2:4], 'big')
        timestamp = int.from_bytes(raw_data[4:8], 'big')
        ssrc = int.from_bytes(raw_data[8:12], 'big')
        
        # Skip CSRC identifiers
        header_len = 12 + (cc * 4)
        
        # Skip extension if present
        if extension:
            if len(raw_data) < header_len + 4:
                continue
            ext_len = int.from_bytes(raw_data[header_len+2:header_len+4], 'big') * 4
            header_len += 4 + ext_len
        
        # Extract payload
        if len(raw_data) > header_len:
            payload = raw_data[header_len:]
            parsed_packets.append({
                'sequence': sequence,
                'timestamp': timestamp,
                'marker': marker,
                'payload': payload
            })
    
    if not parsed_packets:
        raise ValueError("No valid RTP payloads could be extracted")
    
    print(f"Parsed {len(parsed_packets)} valid RTP payloads")
    
    # Sort packets by sequence number (handle wraparound)
    parsed_packets.sort(key=lambda p: p['sequence'])
    
    # Reconstruct NAL units from RTP packets
    nal_units = []
    fragment_buffer = []
    expected_seq = None
    
    for i, pkt_data in enumerate(parsed_packets):
        sequence = pkt_data['sequence']
        payload = pkt_data['payload']
        
        # Check for sequence number gaps
        if expected_seq is not None and sequence != expected_seq % 65536:
            print(f"Warning: Sequence gap detected at packet {i} (expected {expected_seq % 65536}, got {sequence})")
        expected_seq = sequence + 1
        
        if not payload:
            continue
        
        # Check if this is a fragmented packet (FU-A)
        first_byte = payload[0]
        nal_type = first_byte & 0x1F
        
        if nal_type == 28:  # FU-A (Fragmentation Unit for H.264)
            if len(payload) < 2:
                continue
            
            fu_header = payload[1]
            start_bit = (fu_header >> 7) & 1
            end_bit = (fu_header >> 6) & 1
            frag_nal_type = fu_header & 0x1F
            
            if start_bit:
                # Start of a new fragmented NAL unit
                nal_header = (first_byte & 0xE0) | frag_nal_type
                fragment_buffer = [bytes([nal_header]) + payload[2:]]
            elif fragment_buffer:
                # Middle or end fragment
                fragment_buffer.append(payload[2:])
            
            if end_bit and fragment_buffer:
                # Complete fragmented NAL unit
                complete_nal = b''.join(fragment_buffer)
                nal_units.append(complete_nal)
                fragment_buffer = []
        else:
            # Single NAL unit packet
            nal_units.append(payload)
    
    if not nal_units:
        raise ValueError("No NAL units could be reconstructed from RTP packets")
    
    print(f"Reconstructed {len(nal_units)} NAL units")
    
    # Detect codec from NAL units
    codec = detect_codec(nal_units)
    print(f"Detected codec: {codec}")
    
    # Write NAL units to a raw bitstream file
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{codec}") as raw_file:
        raw_path = raw_file.name
        
        for nal in nal_units:
            # Write with Annex B start code
            raw_file.write(b'\x00\x00\x00\x01')
            raw_file.write(nal)
    
    print(f"Wrote raw bitstream to {raw_path}")
    
    # Determine output file name
    if output_file is None:
        output_file = pcap_path.stem + "_extracted.mp4"
    
    output_path = Path(output_file)
    
    # Use ffmpeg to convert raw bitstream to video
    try:
        print(f"Converting to video using ffmpeg...")
        
        codec_name = "h264" if codec == "h264" else "hevc"
        
        cmd = [
            "ffmpeg", "-y",
            "-loglevel", "warning",
            "-f", codec_name,
            "-i", raw_path,
            "-c:v", "copy",
            "-f", "mp4",
            str(output_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"FFmpeg stderr: {result.stderr}")
            raise RuntimeError(f"FFmpeg conversion failed with return code {result.returncode}")
        
        print(f"Successfully extracted video to: {output_path}")

        # NEW: extract PNG frames
        extract_frames_from_video(output_path)

        return output_path
        
    except FileNotFoundError:
        raise RuntimeError("ffmpeg is not installed or not in PATH. Please install ffmpeg to convert the video.")
    finally:
        # Clean up temporary file
        if Path(raw_path).exists():
            Path(raw_path).unlink()


def detect_codec(nal_units):
    """
    Detect the codec (H.264 or H.265) from NAL units.
    
    Args:
        nal_units: List of NAL unit byte arrays
    
    Returns:
        'h264' or 'h265'
    """
    for nal in nal_units[:10]:  # Check first 10 NAL units
        if not nal:
            continue
        
        first_byte = nal[0]
        
        # H.264 NAL type is in lower 5 bits
        h264_nal_type = first_byte & 0x1F
        
        # H.264 SPS is type 7
        if h264_nal_type == 7:
            return "h264"
        
        # H.265 NAL type is in bits 1-6 (shifted right by 1)
        h265_nal_type = (first_byte >> 1) & 0x3F
        
        # H.265 SPS is type 33
        if h265_nal_type == 33:
            return "h265"
    
    # Default to H.264 if unable to detect
    print("Warning: Could not definitively detect codec, assuming H.264")
    return "h264"

def extract_frames_from_video(video_path, output_dir="result_frames"):
    """
    Use ffmpeg to extract raw frames as PNG files.
    
    Args:
        video_path: Path to the decoded video file (MP4 or other)
        output_dir: Directory name for PNG frame output
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Extracting frames from {video_path} into {output_dir}/ ...")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        str(out_dir / "frame_%06d.png")
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"FFmpeg error while extracting frames: {result.stderr}")
        raise RuntimeError("Frame extraction failed.")

    print(f"✓ Extracted PNG frames to: {out_dir}")


def main():
    """Main function with argument parsing."""
    parser = argparse.ArgumentParser(
        description="Extract video from RTP packets in a PCAP file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Extract video from PCAP with default settings
  python extract_video.py rtp_stream_h264.pcap
  
  # Specify output file
  python extract_video.py rtp_stream_h264.pcap -o output.mp4
  
  # Specify RTP payload type
  python extract_video.py rtp_stream_h264.pcap -pt 96
        """
    )
    
    parser.add_argument("pcap_file", help="Input PCAP file containing RTP packets")
    parser.add_argument("-o", "--output", help="Output video file (default: <pcap_name>_extracted.mp4)")
    parser.add_argument("-pt", "--payload-type", type=int, default=96,
                       help="RTP payload type to extract (default: 96)")
    
    args = parser.parse_args()
    
    try:
        output_path = extract_rtp_payload(
            args.pcap_file,
            payload_type=args.payload_type,
            output_file=args.output
        )
        print(f"\n✓ Video extraction complete!")
        print(f"  Output: {output_path}")
        
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()