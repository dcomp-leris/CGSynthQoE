#!/usr/bin/env python3
"""
PCAP Throughput Analyzer
Computes average downstream throughput from PCAP files for cloud gaming sessions.
"""

import os
import sys
import argparse
from typing import Dict, List, Optional

try:
    from scapy.all import rdpcap, UDP, Raw
except ImportError:
    print("[ERROR] scapy not installed. Install with: pip install scapy")
    sys.exit(1)


def parse_rtp_header(payload: bytes) -> Optional[dict]:
    if len(payload) < 12:
        return None

    version = (payload[0] >> 6) & 0x3
    if version != 2:
        return None

    extension = (payload[0] >> 4) & 0x1
    cc = payload[0] & 0x0F
    payload_type = payload[1] & 0x7F

    header_size = 12 + 4 * cc

    if extension and len(payload) >= header_size + 4:
        ext_len = (payload[header_size + 2] << 8) | payload[header_size + 3]
        header_size += 4 + 4 * ext_len

    if len(payload) <= header_size:
        return None

    rtp_payload = payload[header_size:]

    return {
        'payload_type': payload_type,
        'header_size': header_size,
        'payload_size': len(rtp_payload),
        'total_size': len(payload)
    }


def analyze_pcap_throughput(pcap_path: str) -> Dict:
    print(f"[INFO] Reading PCAP: {pcap_path}")

    try:
        packets = rdpcap(pcap_path)
    except Exception as e:
        print(f"[ERROR] Failed to read PCAP: {e}")
        return {}

    if not packets:
        print("[WARN] No packets in PCAP")
        return {}

    first_time = None
    last_time = None
    total_rtp_bytes = 0
    total_udp_bytes = 0
    rtp_count = 0
    udp_count = 0

    for packet in packets:
        if not (UDP in packet and Raw in packet):
            continue

        udp_payload = bytes(packet[Raw])
        udp_len = len(udp_payload)
        total_udp_bytes += udp_len
        udp_count += 1

        pkt_time = float(packet.time)
        if first_time is None:
            first_time = pkt_time
        last_time = pkt_time

        if len(udp_payload) >= 12:
            rtp_info = parse_rtp_header(udp_payload)
            if rtp_info and rtp_info['payload_type'] == 96:
                total_rtp_bytes += rtp_info['payload_size']
                rtp_count += 1

    if first_time is None or last_time is None:
        print("[WARN] No packet timestamps found")
        return {}

    duration = last_time - first_time
    if duration <= 0:
        print("[WARN] Zero session duration")
        return {}

    rtp_throughput_mbps = (total_rtp_bytes * 8) / (duration * 1_000_000)
    udp_throughput_mbps = (total_udp_bytes * 8) / (duration * 1_000_000)

    print(f"  Duration: {duration:.2f}s, RTP pkts: {rtp_count}, "
          f"RTP throughput: {rtp_throughput_mbps:.2f} Mbps, "
          f"UDP throughput: {udp_throughput_mbps:.2f} Mbps")

    return {
        'duration_sec': duration,
        'rtp_packet_count': rtp_count,
        'rtp_payload_bytes': total_rtp_bytes,
        'total_udp_bytes': total_udp_bytes,
        'udp_packet_count': udp_count,
        'rtp_throughput_mbps': rtp_throughput_mbps,
        'udp_throughput_mbps': udp_throughput_mbps,
    }


def analyze_all_real_sessions(repo_root: str) -> List[Dict]:
    real_root = os.path.join(repo_root, "acm_tomm_experiments", "reference_vs_real")

    if not os.path.exists(real_root):
        print(f"[ERROR] Real experiments not found: {real_root}")
        return []

    games = ["Fortnite", "Forza", "Kombat"]
    bandwidths = ["2Mbit", "4Mbit", "6Mbit", "8Mbit", "10Mbit"]

    results = []

    for game in games:
        for bw in bandwidths:
            bitrate_label = f"{bw}_{game}"
            pcap_path = os.path.join(real_root, game, bitrate_label, "output.pcap")

            if not os.path.exists(pcap_path):
                print(f"[WARN] PCAP not found: {pcap_path}")
                continue

            print(f"\n=== {game} @ {bw} ===")
            data = analyze_pcap_throughput(pcap_path)

            if data:
                data['game'] = game
                data['bitrate_label'] = bitrate_label
                data['configured_bw_mbps'] = int(bw.replace("Mbit", ""))
                results.append(data)

    return results


def main():
    parser = argparse.ArgumentParser(description="Analyze PCAP throughput")
    parser.add_argument("--repo-root", default="/home/ariel/git/CGSynth",
                        help="Repository root path")
    parser.add_argument("--output-csv", help="Output CSV file for results")
    parser.add_argument("--pcap", help="Analyze single PCAP file")
    args = parser.parse_args()

    if args.pcap:
        result = analyze_pcap_throughput(args.pcap)
        if result:
            print("\n=== Result ===")
            for k, v in result.items():
                print(f"  {k}: {v}")
        return

    results = analyze_all_real_sessions(args.repo_root)

    if not results:
        print("[ERROR] No results generated")
        sys.exit(1)

    print(f"\n=== Summary ({len(results)} sessions) ===")
    for r in results:
        print(f"  {r['game']:10s} @ {r['configured_bw_mbps']:2d} Mbps: "
              f"RTP={r.get('rtp_throughput_mbps', 0):.2f} "

              f"UDP={r.get('udp_throughput_mbps', 0):.2f}")

    if args.output_csv:
        import csv
        fieldnames = ['game', 'bitrate_label', 'configured_bw_mbps', 'duration_sec',
                      'rtp_packet_count', 'rtp_payload_bytes', 'total_udp_bytes',
                      'udp_packet_count', 'rtp_throughput_mbps', 'udp_throughput_mbps']
        with open(args.output_csv, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in results:
                writer.writerow(r)
        print(f"\n[INFO] Saved to {args.output_csv}")


if __name__ == "__main__":
    main()
