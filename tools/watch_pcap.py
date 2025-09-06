import os
import subprocess
import pwd
import argparse
from typing import List

script_dir = os.path.dirname(os.path.abspath(__file__))


def find_pcap_files(pcap_folder: str) -> List[str]:
    pcap_files = []
    for root, dirs, files in os.walk(pcap_folder):
        for name in files:
            if (name.endswith(".pcap") or name.endswith(".pcapng")) and not name.endswith(".temp.pcap"):
                pcap_files.append(os.path.join(root, name))
    return pcap_files


def to_output_mp4_path(pcap_file: str) -> str:
    base, _ = os.path.splitext(pcap_file)
    return base + ".mp4"


def convert_to_libpcap(pcap_file: str) -> str:
    temp_pcap_file = pcap_file + ".temp.pcap"
    subprocess.run(["editcap", "-F", "libpcap", pcap_file, temp_pcap_file], check=True)
    # Set reasonable permissions
    os.chmod(temp_pcap_file, 0o644)
    return temp_pcap_file


def run_gst_pipeline_display(temp_pcap_file: str):
    # Decode and display only
    subprocess.run([
        "gst-launch-1.0", "-v",
        "filesrc", f"location={temp_pcap_file}",
        "!", "pcapparse",
        "!", "application/x-rtp,encoding-name=H264,payload=96",
        "!", "rtph264depay",
        "!", "h264parse",
        "!", "avdec_h264",
        "!", "videoconvert",
        "!", "autovideosink", "sync=false",
    ], check=True)


def run_gst_pipeline_save(temp_pcap_file: str, output_file: str, framerate: int):
    # Decode to raw, normalize framerate, re-encode and save as MP4
    subprocess.run([
        "gst-launch-1.0", "-e", "-v",
        "filesrc", f"location={temp_pcap_file}",
        "!", "pcapparse",
        "!", "application/x-rtp,encoding-name=H264,payload=96",
        "!", "rtph264depay",
        "!", "h264parse",
        "!", "avdec_h264",
        "!", "videorate",
        "!", f"video/x-raw,framerate={framerate}/1",
        "!", "x264enc",
        "!", "h264parse",
        "!", "mp4mux", "presentation-time=true",
        "!", "filesink", f"location={output_file}"
    ], check=True)


def main():
    parser = argparse.ArgumentParser(description="Watch or convert RTP/H264 video embedded in PCAP/PCAPNG files using GStreamer.")
    parser.add_argument(
        "--mode",
        choices=["save", "display"],
        default="save",
        help="Operation mode: 'save' to produce MP4 files (default), or 'display' to show video.",
    )
    parser.add_argument(
        "--framerate",
        type=int,
        default=30,
        help="Target framerate for normalization when saving (default: 30).",
    )
    parser.add_argument(
        "--pcap-folder",
        default=os.path.abspath(os.path.join(script_dir, "..", "output_pcaps")),
        help="Folder to recursively scan for .pcap/.pcapng files (default: ../output_pcaps).",
    )
    args = parser.parse_args()

    # Get current user (kept for parity with previous version; not used directly)
    _current_user = pwd.getpwuid(os.getuid()).pw_name

    pcap_files = find_pcap_files(args.pcap_folder)
    print("pcap_files found:", pcap_files)
    print()

    if not pcap_files:
        print("No PCAP/PCAPNG files found.")
        return

    for pcap_file in pcap_files:
        temp_pcap_file = None
        try:
            temp_pcap_file = convert_to_libpcap(pcap_file)
            output_file = to_output_mp4_path(pcap_file)
            os.makedirs(os.path.dirname(output_file), exist_ok=True)

            print(f"Processing {pcap_file} (mode={args.mode}) ...")

            if args.mode == "display":
                run_gst_pipeline_display(temp_pcap_file)
                print("Display completed.")
            else:  # save
                run_gst_pipeline_save(temp_pcap_file, output_file, args.framerate)
                print(f"MP4 saved successfully to {output_file}")
        finally:
            # Clean up the temporary file
            if temp_pcap_file and os.path.exists(temp_pcap_file):
                try:
                    os.remove(temp_pcap_file)
                except OSError:
                    pass


if __name__ == "__main__":
    main()
