# Relatório de Progresso - 03/05/2026

### Implementações Técnicas
1.  QUIC streaming completo (200 frames)
2.  RTT measurement em tempo real (76.9ms)
3.  Encoder H.264 adaptativo implementado
4.  Compressão de 91.1% validada
5.  Sistema end-to-end funcional

### Métricas Alcançadas
- **Compressão:** 144.58 MB → 12.89 MB (91.1%)
- **RTT:** 76.9ms medido via QUIC
- **Bitrate:** 2.00 Mbps H.264
- **Qualidade:** BOA (crf=28, gop=30)
- **Frames:** 200/200 transmitidos

### Código Desenvolvido
- `adaptive_encoder.py`: 250+ linhas
- `quic_video_packetizer.py`: modificado
- `quic_video_streamer.py`: RTT real
- `quic_server.py`: servidor funcional

##  Próximos Passos

### Curto Prazo (próxima sessão)
1. Instalar Mininet
2. Configurar 4 topologias de rede
3. Rodar primeiro experimento

### Médio Prazo (esta semana)
1. Experimentos com 3 jogos
2. Coleta de PCAPs
3. Primeira análise de dados

### Longo Prazo (este mês)
1. Comparação RTP vs QUIC
2. Métricas SSIM/VMAF/LPIPS
3. Escrita do TCC

## 💡 Insights

### O que funcionou bem
- Abordagem modular (encoder separado)
- FFmpeg para encoding
- aioquic para QUIC
- Metodologia incremental

### Desafios Enfrentados
- FPS baixo no encoding (3.70 FPS)
- PCAP com payloads encrypted
- Configuração inicial do Git

### Soluções Encontradas
- Otimização FFmpeg (-threads, -loglevel)
- Entendimento de QUIC encrypted payloads
- Git configurado corretamente

##  Para o TCC

### Seções Prontas
-  Introdução (parcial)
-  Metodologia (QUIC + Encoder)
-  Experimentos (pendente)
-  Resultados (pendente)

### Figuras/Tabelas Geradas
1. Tabela de parâmetros do encoder
2. Estatísticas de compressão
3. Diagrama de arquitetura

### Dados Coletados
- 1 PCAP completo (Fortnite)
- Logs de transmissão
- Métricas de encoding
