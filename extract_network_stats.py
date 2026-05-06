#!/usr/bin/env python3
"""
Extrai estatísticas agregadas dos PCAPs VisQUIC
"""

import re
import sys

def parse_report(report_file):
    """Parse do relatório de análise"""
    
    stats = []
    current = {}
    
    with open(report_file, 'r') as f:
        for line in f:
            line = line.strip()
            
            if line.startswith('Arquivo:'):
                if current:
                    stats.append(current)
                current = {'file': line.split('Arquivo:')[1].strip()}
            
            elif 'Total pacotes QUIC:' in line:
                current['packets'] = int(line.split(':')[1].strip())
            
            elif 'Total bytes:' in line:
                match = re.search(r'(\d+,?\d*)\s*\(', line)
                if match:
                    current['bytes'] = int(match.group(1).replace(',', ''))
            
            elif 'Duração:' in line:
                current['duration'] = float(line.split(':')[1].replace('s', '').strip())
            
            elif 'RTT estimado:' in line:
                current['rtt'] = float(line.split(':')[1].replace('ms', '').strip())
            
            elif 'Bitrate:' in line:
                current['bitrate'] = float(line.split(':')[1].replace('Mbps', '').strip())
            
            elif 'Qualidade de rede:' in line:
                current['quality'] = line.split(':')[1].strip()
    
    if current:
        stats.append(current)
    
    return stats

def print_summary(stats):
    """Imprime resumo estatístico"""
    
    print("\n" + "=" * 70)
    print("📊 RESUMO ESTATÍSTICO - DATASET VISQUIC")
    print("=" * 70)
    
    print(f"\n📁 Total de PCAPs analisados: {len(stats)}")
    
    # Estatísticas gerais
    total_packets = sum(s.get('packets', 0) for s in stats)
    total_bytes = sum(s.get('bytes', 0) for s in stats)
    avg_rtt = sum(s.get('rtt', 0) for s in stats) / len(stats) if stats else 0
    avg_bitrate = sum(s.get('bitrate', 0) for s in stats) / len(stats) if stats else 0
    
    print(f"\n📦 Totais:")
    print(f"   Pacotes QUIC: {total_packets:,}")
    print(f"   Bytes totais: {total_bytes:,} ({total_bytes/1024/1024:.2f} MB)")
    
    print(f"\n📈 Médias:")
    print(f"   RTT médio: {avg_rtt:.2f}ms")
    print(f"   Bitrate médio: {avg_bitrate:.2f} Mbps")
    
    # Por qualidade de rede
    print(f"\n🌐 Distribuição por qualidade:")
    qualities = {}
    for s in stats:
        q = s.get('quality', 'DESCONHECIDO')
        qualities[q] = qualities.get(q, 0) + 1
    
    for q in ['EXCELENTE', 'BOA', 'MÉDIA', 'RUIM', 'DESCONHECIDO']:
        if q in qualities:
            count = qualities[q]
            pct = (count / len(stats)) * 100
            print(f"   {q:12s}: {count:3d} PCAPs ({pct:5.1f}%)")
    
    # Top 5 maiores
    print(f"\n📊 Top 5 maiores PCAPs:")
    sorted_stats = sorted(stats, key=lambda x: x.get('bytes', 0), reverse=True)[:5]
    for i, s in enumerate(sorted_stats, 1):
        fname = s.get('file', '').split('/')[-1]
        bytes_val = s.get('bytes', 0)
        print(f"   {i}. {fname[:50]:<50s} {bytes_val/1024:>8.2f} KB")
    
    # Por site
    print(f"\n🌐 Por website:")
    sites = {}
    for s in stats:
        fname = s.get('file', '')
        if 'youtube' in fname:
            site = 'YouTube'
        elif 'semrush' in fname:
            site = 'Semrush'
        elif 'facebook' in fname:
            site = 'Facebook'
        elif 'google' in fname:
            site = 'Google'
        elif 'instagram' in fname:
            site = 'Instagram'
        else:
            site = 'Outros'
        
        sites[site] = sites.get(site, 0) + 1
    
    for site, count in sorted(sites.items(), key=lambda x: x[1], reverse=True):
        print(f"   {site:15s}: {count:3d} PCAPs")
    
    print("=" * 70)

if __name__ == "__main__":
    report_file = 'visquic_analysis_report.txt'
    
    print(f"📖 Lendo relatório: {report_file}...")
    
    try:
        stats = parse_report(report_file)
        print_summary(stats)
        
        # Salvar CSV
        with open('visquic_stats.csv', 'w') as f:
            f.write("file,packets,bytes,duration,rtt,bitrate,quality\n")
            for s in stats:
                f.write(f"{s.get('file','')},{s.get('packets',0)},{s.get('bytes',0)},"
                       f"{s.get('duration',0)},{s.get('rtt',0)},{s.get('bitrate',0)},"
                       f"{s.get('quality','')}\n")
        
        print(f"\n💾 Dados salvos em: visquic_stats.csv")
        
    except FileNotFoundError:
        print(f"❌ Arquivo não encontrado: {report_file}")
        print("   Execute primeiro: ./analyze_all_visquic.sh")
