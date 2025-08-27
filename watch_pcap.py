import subprocess
import os

# Step 1: Change permissions
'''
subprocess.run(['sudo', 'chmod', '777', '../player/logs/*.*'])
'''

subprocess.run(['sudo', '-S', 'chmod', '777', '../player/logs/my.pcap'], input=f"{os.getenv('SUDO_PASSWORD')}\n", text=True)
#subprocess.run(['sudo', '-S', 'chmod', '777', 'pcaps/4Mbit_Loss0_Fortnite.pcap'], input=f"sudo_password\n", text=True)

print("(1) Access is done!")

# Step 2: Convert PCAPNG to PCAP
subprocess.run(['editcap', '-F', 'libpcap', 'pcaps/4Mbit_Loss0_Fortnite.pcap', './my_converted.pcap'])
print("(2) Converting happened!")

# Step 3: Run GStreamer pipeline
'''
subprocess.run([
    'gst-launch-1.0', '-v',
    'filesrc', 'location=./my_converted.pcap',
    '!', 'pcapparse',
    '!', 'application/x-rtp,encoding-name=H264,payload=96',
    '!', 'rtph264depay',
    '!', 'avdec_h264',
    '!', 'autovideosink'
])
print("(3) Displaying!")
'''
subprocess.run([
    "gst-launch-1.0", "-e", "-v",
    "filesrc", "location=./my_converted.pcap",
    "!", "pcapparse",
    "!", "application/x-rtp,encoding-name=H264,payload=96",
    "!", "rtph264depay",
    "!", "h264parse",
    "!", "mp4mux",
    "!", "filesink", "location=output.mp4"
])

print("(3) Displaying!")