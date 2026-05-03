# QUIC Adaptive Encoder Development

## Objetivo
Implementar encoder adaptativo baseado em QUIC para substituir RTP no CGSynth.

## Branch
`hugo` - branch de desenvolvimento

## Estrutura do Projeto

### Arquivos Novos (QUIC)
rtp_stream_creation/
├── quic_video_streamer.py        # Cliente QUIC para streaming
├── quic_video_packetizer.py      # Packetizador QUIC (substituto do RTP)
├── quic_server.py                # Servidor QUIC de teste
├── test_quic_client.py           # Teste cliente QUIC público
├── test_quic_client_local.py     # Teste cliente QUIC local
└── ssl_certs/                    # Certificados SSL para QUIC
├── server.pem
└── server.key

### Arquivos Originais (RTP)
rtp_stream_creation/
├── rtp_video_packetizer.py       # Original RTP (manter como referência)
└── rtp_video_extractor.py        # Extrator RTP

## Mudanças Principais

### De RTP para QUIC:
- **Antes:** UDP → RTP → Pacotes
- **Depois:** UDP → QUIC → Streams

### Encoder Adaptativo:
```python
RTT < 50ms   → bitrate=10M, qp=23, gop=60  (EXCELENTE)
RTT < 100ms  → bitrate=5M,  qp=28, gop=30  (BOA)
RTT < 200ms  → bitrate=3M,  qp=32, gop=20  (MÉDIA)
RTT > 200ms  → bitrate=2M,  qp=35, gop=15  (RUIM)
```

## Como Usar

### 1. Iniciar Servidor QUIC
```bash
cd ~/CGSynth/rtp_stream_creation
source ~/venv/bin/activate
python3 quic_server.py
```

### 2. Enviar Frames via QUIC
```bash
python3 quic_video_packetizer.py \
  --frames-dir ~/CGSynth/frames_fortnite \
  --fps 30
```

### 3. Testar Conexão QUIC
```bash
# Teste servidor público
python3 test_quic_client.py

# Teste servidor local
python3 test_quic_client_local.py
```

## Status

- [x] QUIC básico funcionando
- [x] Cliente/Servidor QUIC
- [x] Envio de frames via QUIC
- [x] Medição de RTT (básico)
- [ ] Integração com encoder H.264
- [ ] RTT measurement em produção
- [ ] Geração de PCAP QUIC
- [ ] Testes comparativos RTP vs QUIC
- [ ] Experimentos com 3 jogos

## Próximos Passos

1. Integrar encoder H.264 com ajuste dinâmico
2. Implementar medição de RTT real (não placeholder)
3. Gerar PCAP do tráfego QUIC
4. Rodar experimentos: 3 jogos × 4 redes × 2 encoders
5. Comparar métricas (SSIM, VMAF, LPIPS)

## Dependências Adicionais

```bash
pip install aioquic dpkt
```

## Autores
- Hugo (TCC - Adaptive QUIC Encoder)
- Alireza Shirmarz (CGSynth/CGReplay original)

## Data
Maio 2026
