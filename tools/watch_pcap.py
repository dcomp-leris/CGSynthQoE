import os
import subprocess
import pwd

# Folder containing PCAPs
pcap_folder = os.path.abspath("./output_pcaps")

# Get current user
current_user = pwd.getpwuid(os.getuid()).pw_name

# Recursively find all PCAP or PCAPNG files
pcap_files = []
for root, dirs, files in os.walk(pcap_folder):
    for name in files:
        if (name.endswith(".pcap") or name.endswith(".pcapng")) and not name.endswith(".temp.pcap"): 
            pcap_files.append(os.path.join(root, name))

print("pcap_files found: ", pcap_files)
print()

# Process each file
for pcap_file in pcap_files:
    # Convert all pcaps to libpcap format to ensure compatibility with GStreamer
    temp_pcap_file = pcap_file + ".temp.pcap"
    subprocess.run(["editcap", "-F", "libpcap", pcap_file, temp_pcap_file], check=True)

    # Set reasonable permissions (owner read/write only)
    os.chmod(temp_pcap_file, 0o644)

    # Prepare output MP4 path
    output_file = pcap_file.replace(".pcap", ".mp4")

    # Ensure output directory exists with proper permissions
    output_dir = os.path.dirname(output_file)
    os.makedirs(output_dir, exist_ok=True)

    print(f"Processing {pcap_file} -> {output_file} ...")

    # Run GStreamer pipeline
    subprocess.run([
        "gst-launch-1.0", "-e", "-v",
        "filesrc", f"location={temp_pcap_file}",
        "!", "pcapparse",
        "!", "application/x-rtp,encoding-name=H264,payload=96",
        "!", "rtph264depay",
        "!", "h264parse",
        "!", "avdec_h264",
        "!", "videorate",
        "!", "video/x-raw,framerate=30/1",
        "!", "x264enc",
        "!", "h264parse",
        "!", "mp4mux", "presentation-time=true",
        "!", "filesink", f"location={output_file}"
    ], check=True)

    print(f"MP4 saved successfully to {output_file}")

    # Clean up the temporary file
    os.remove(temp_pcap_file)
