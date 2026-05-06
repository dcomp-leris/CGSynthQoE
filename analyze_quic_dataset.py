#!/usr/bin/env python3
"""Analisa dataset QUIC usando Scapy"""

from scapy.all import *
import sys

def analyze_pcap(pcap_file):
    """Analisa PCAP QUIC"""
    print(f"📊 Analisando {pcap_file}...")
    
    try:
        # Ler PCAP com Scapy (suporta .pcap e .pcapng)
        packets = rdpcap(pcap_file)
        
        print(f"✅ {len(packets)} pacotes carregados")
        
        # Filtrar pacotes UDP (QUIC usa UDP)
        udp_packets = [p for p in packets if UDP in p]
        
        print(f"   Pacotes UDP: {len(udp_packets)}")
        
        # Filtrar porta 443 (QUIC padrão)
        quic_packets = [p for p in udp_packets if p[UDP].dport == 443 or p[UDP].sport == 443]
        
        print(f"   Pacotes QUIC (porta 443): {len(quic_packets)}")
        
        if len(quic_packets) < 2:
            print("⚠️  Poucos pacotes QUIC encontrados")
            return
        
        # Calcular métricas
        timestamps = [float(p.time) for p in quic_packets]
        sizes = [len(p) for p in quic_packets]
        
        # IPIs (Inter-Packet Intervals)
        ipis = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
        
        total_bytes = sum(sizes)
        duration = timestamps[-1] - timestamps[0]
        
        # Estimar RTT
        rtt_est = min(ipis) * 2000 if ipis else 0  # ms
        
        # Bitrate
        bitrate = (total_bytes * 8) / (duration * 1_000_000) if duration > 0 else 0
        
        print(f"\n📊 MÉTRICAS:")
        print(f"   Total pacotes QUIC: {len(quic_packets)}")
        print(f"   Total bytes: {total_bytes:,} ({total_bytes/1024:.2f} KB)")
        print(f"   Duração: {duration:.2f}s")
        print(f"   Tamanho médio pacote: {sum(sizes)/len(sizes):.0f} bytes")
        print(f"   IPI médio: {sum(ipis)/len(ipis)*1000:.2f}ms" if ipis else "   IPI: N/A")
        print(f"   RTT estimado: {rtt_est:.2f}ms")
        print(f"   Bitrate: {bitrate:.2f} Mbps")
        
        # Classificar rede
        if rtt_est < 50:
            quality = "EXCELENTE"
        elif rtt_est < 100:
            quality = "BOA"
        elif rtt_est < 200:
            quality = "MÉDIA"
        else:
            quality = "RUIM"
        
        print(f"\n🌐 Qualidade de rede: {quality}")
        
    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 analyze_quic_dataset.py arquivo.pcap")
        sys.exit(1)
    
    analyze_pcap(sys.argv[1])
