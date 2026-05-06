#!/bin/bash
# Analisa todos os PCAPs do VisQUIC

echo "📊 Analisando dataset VisQUIC completo..."
echo ""

cd ~/CGSynth

OUTPUT="visquic_analysis_report.txt"
echo "Relatório de Análise VisQUIC" > $OUTPUT
echo "Data: $(date)" >> $OUTPUT
echo "======================================" >> $OUTPUT
echo "" >> $OUTPUT

count=0
total=$(wc -l < visquic_files.txt)

while read pcap; do
  count=$((count+1))
  echo "[$count/$total] Analisando: $(basename $pcap)"
  
  echo "================================" >> $OUTPUT
  echo "Arquivo: $pcap" >> $OUTPUT
  echo "================================" >> $OUTPUT
  python3 analyze_quic_dataset.py "$pcap" >> $OUTPUT 2>&1
  echo "" >> $OUTPUT
  
done < visquic_files.txt

echo ""
echo "✅ Análise completa!"
echo "📄 Relatório salvo em: $OUTPUT"
echo ""
echo "📊 Resumo:"
echo "   Total de PCAPs analisados: $count"
