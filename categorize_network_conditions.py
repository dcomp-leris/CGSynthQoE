#!/usr/bin/env python3
"""
Categoriza condições de rede dos PCAPs VisQUIC
"""

import sys

def categorize_from_report(report_file):
    """Lê relatório e categoriza redes"""
    
    categories = {
        'EXCELENTE': [],
        'BOA': [],
        'MÉDIA': [],
        'RUIM': []
    }
    
    with open(report_file, 'r') as f:
        current_file = None
        
        for line in f:
            if line.startswith('Arquivo:'):
                current_file = line.split('Arquivo:')[1].strip()
            
            if 'RTT estimado:' in line:
                rtt = float(line.split(':')[1].replace('ms', '').strip())
                
                if rtt < 50:
                    cat = 'EXCELENTE'
                elif rtt < 100:
                    cat = 'BOA'
                elif rtt < 200:
                    cat = 'MÉDIA'
                else:
                    cat = 'RUIM'
                
                if current_file:
                    categories[cat].append({
                        'file': current_file,
                        'rtt': rtt
                    })
    
    # Imprimir resultado
    print("=" * 70)
    print("📊 CATEGORIZAÇÃO DE CONDIÇÕES DE REDE")
    print("=" * 70)
    
    for cat, files in categories.items():
        print(f"\n🌐 {cat} (RTT {'<50' if cat=='EXCELENTE' else '<100' if cat=='BOA' else '<200' if cat=='MÉDIA' else '>200'}ms):")
        print(f"   Total: {len(files)} PCAPs")
        
        if files:
            print(f"   RTT médio: {sum(f['rtt'] for f in files)/len(files):.2f}ms")
            print(f"   Exemplos:")
            for f in files[:3]:
                basename = f['file'].split('/')[-1]
                print(f"     - {basename} (RTT: {f['rtt']:.2f}ms)")

if __name__ == "__main__":
    categorize_from_report('visquic_analysis_report.txt')
