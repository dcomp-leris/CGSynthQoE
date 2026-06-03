# Speaker Notes — Reunião Alireza / Prof. Kleber

**Este arquivo é só seu. Não mostrar na tela.**
Leia antes e durante a reunião como roteiro.

---

## Antes de começar

Abrir na tela (não mostrar ainda, só ter pronto):
- Este terminal na pasta `CGReplay/`
- `MEETING_PREP.md` aberto no editor
- Wireshark fechado (vai abrir durante a demo)

---

## Bloco 1 — Abertura (5 min)

Mostrar: `MEETING_PREP.md` seção "What was done"

**O que dizer:**

> "I completed three things this week. First, I replaced CGReplay's RTP transport
> with QUIC and confirmed the full interactive loop works — video downstream and
> joystick commands upstream. Second, I captured the traffic in Wireshark to show
> the protocol mechanics. Third — and this answers your question from today —
> I integrated QUIC directly into the main CGReplay scripts, so it is no longer
> a separate prototype. One flag in config.yaml switches the entire transport."

Pausa. Deixar eles lerem o "What was done" por 30 segundos.

---

## Bloco 1b — Integração (2 min, resposta direta ao Alireza)

Mostrar: `MEETING_PREP.md` seção "Integration into CGReplay"

**O que dizer:**

> "To answer your question directly: yes, it is integrated. The main CGReplay scripts —
> cg_server1.py and cg_gamer1.py — now read the QUIC flag from config.yaml.
> When QUIC is True, they delegate to the QUIC sender and receiver.
> When it is False, the original RTP/GStreamer pipeline runs as before.
> The pattern is identical to the SCReAM flag that was already in the code."

Apontar para a tabela no MEETING_PREP.md.

> "So the same topology script, same config, same game data — the only difference
> is one line in config.yaml."

---

## Bloco 2 — Arquitetura (5 min)

Mostrar: seção "Architecture" do MEETING_PREP.md

**O que dizer:**

> "The setup runs inside Mininet. h1 is the cloud gaming server, h2 is the player.
> The server reads PNG frames, compresses to JPEG, stamps a QR code with the frame ID,
> and sends each frame on its own QUIC stream — one stream per frame, unidirectional.
> On the other side, h2 receives the frame, decodes it, reads the QR code, then looks up
> the sync file to find the joystick command for that frame and sends it back on a
> client-initiated control stream."

Apontar para o diagrama enquanto fala.

> "The key point Alireza asked about: this is not only video streaming. The player sends
> commands in response to frames. That is the interactive loop of cloud gaming."

---

## Bloco 3 — Demo ao vivo (15 min)

Mostrar: terminal

**Passo 1 — rodar a topologia:**
```bash
cd /home/hugo/CGSynth/CGReplay
sudo python3 topology/simple_topology.py --protocol quic --bw 10 --delay 10ms --loss 0
```

**O que dizer enquanto roda:**

> "This script builds the Mininet network, starts tcpdump on h2 to capture everything,
> launches the sender on h1 and the receiver on h2, waits for completion, and copies the
> PCAP file."

**O que apontar no output:**

Quando aparecer `[QUIC] Handshake complete`:
> "Handshake done — 1 round trip, TLS 1.3 embedded. No separate TCP handshake."

Quando aparecerem os `[TX]` e `[RX]`:
> "Server sending, player receiving. Each line is one frame."

Quando aparecer `[CMD]`:
> "And here — the player sending joystick commands back. This is the interactive part."

Quando aparecer a sequência fora de ordem (ex: 0114 antes de 0102):
> "Look at the frame order: 114 arrived before 102. In TCP that would be a problem —
> the whole pipe stalls waiting for the missing frame. In QUIC each frame is on its own
> stream, so delivery is completely independent. This is no head-of-line blocking."

Ao final, mostrar os logs:
```bash
# Frame log (separado)
head -10 player/logs/ply_quic_frame.csv

# Combined event log — frames e comandos na mesma linha do tempo
head -20 player/logs/ply_quic_events.csv

# Rate log
head -10 player/logs/ratelog_quic.csv
```

**O que dizer ao mostrar o event log:**

> "This combined log puts video frames and commands on the same timeline.
> Each FRAME row records when the frame arrived, its size, and FPS.
> Each CMD entry in cmd_count shows how many commands were dispatched for that frame.
> This is what we will use for the demo paper figure."

---

## Bloco 4 — Wireshark (15 min)

Mostrar: Wireshark com `player/output.pcap`

```bash
wireshark player/output.pcap
```

**Filtro 1: `quic`**

> "This is the full session — 28 thousand packets, 26 MB, 37 seconds.
> You can see two groups: a short burst at the beginning, then a long stream.
> The burst is the handshake. Everything after is video."

**Filtro 2: `quic.header_form == 1`**

> "These 5 packets are the entire connection setup. Compare that to HTTPS over TCP:
> TCP SYN/SYN-ACK/ACK, then TLS ClientHello, then ServerHello, then certificate, then
> Finished — that is 2 full round trips minimum before any data. QUIC does it in 1 RTT
> because TLS 1.3 is embedded directly inside the QUIC Initial packet."

Expandir o pacote 1 (Initial):
- Apontar **Header Form = 1** → "long header, used only during setup"
- Apontar **Version = 0x00000001** → "QUIC version 1, RFC 9000, published 2021"
- Apontar **DCID / SCID** → "connection IDs — these disappear in the short header"
- Apontar **Crypto Data / ClientHello** → "TLS 1.3 handshake, inside QUIC"

**Filtro 3: `quic.header_form == 0`**

> "28 thousand packets. All the video. The header is much smaller now — no version,
> no connection IDs. Just the spin bit, packet number, and encrypted payload."

Expandir qualquer pacote:
- Apontar **Spin Bit** → "used for passive RTT measurement — no extra packets needed"
- Apontar **Packet Number** → "sequence number for loss detection and recovery"
- Apontar **Protected Payload (KP0)** → "fully encrypted, AEAD cipher. The PCAP
  shows only ciphertext. To read the content you would need the session keys."

---

## Bloco 5 — Pontos técnicos (5 min)

Mostrar: seção "Key properties demonstrated"

Ler a tabela com eles. Para cada linha, uma frase:

- **No HoL blocking** → "Demonstrated live — out-of-order frames in the terminal."
- **1-RTT setup** → "Handshake in 5 packets, 56 ms. Visible in Wireshark."
- **Integrated TLS 1.3** → "No separate handshake. Initial packet contains ClientHello."
- **Always-on encryption** → "No mode where QUIC sends plaintext. Always Protected Payload."
- **Bidirectional interactivity** → "[CMD] lines in the terminal output."

---

## Bloco 6 — Próximos passos (5 min)

Mostrar: seção "Next steps"

**O que dizer:**

> "The prototype validates that QUIC works as a drop-in transport for CGReplay.
> The next phase is to run the full experiment matrix: 3 games, 4 network conditions,
> RTP versus QUIC. Before that I need to replace JPEG with H.264, which is the codec
> CGReplay uses in the RTP path, and add RTT measurement to drive adaptive bitrate.
> Then we can compute SSIM and VMAF to compare video quality between protocols."

---

## Perguntas prováveis — respostas rápidas

**"Is this integrated with CGReplay or is it a separate prototype?"**
> "It is integrated. cg_server1.py and cg_gamer1.py read QUIC from config.yaml.
> Setting QUIC: True makes them delegate to the QUIC scripts. QUIC: False keeps
> the original RTP/GStreamer path. Nothing in the original code was removed."



**"Why one stream per frame instead of one stream for all video?"**
> "One stream per frame gives us independent delivery — a packet loss on frame N
> does not block frame N+1. If we used one stream for all video, QUIC would still
> have to deliver that stream in order, which is effectively TCP behavior."

**"What happens when there is packet loss?"**
> "QUIC handles retransmission internally per stream. A lost packet for frame N is
> retransmitted, but the receiver can still process frames N+1, N+2 while waiting.
> In the test we ran with 0% loss. The next step is to run with 1–5% loss and
> measure the FPS and SSIM impact."

**"Is aioquic production quality?"**
> "No — aioquic is a research and testing library. For a real deployment you would
> use a C implementation like MSQUIC or lsquic. For this research prototype it is
> appropriate because it is easy to instrument and modify."

**"Does the server react to the commands?"**
> "Right now the server logs the commands but does not change behavior — the bitrate
> is static. Adding adaptive bitrate based on the received Ack/Nack rate and RTT is
> step 2 in the next steps."

**"Why JPEG and not H.264?"**
> "JPEG was the fastest path to a working prototype. Each frame is self-contained,
> no codec state to manage. H.264 is the correct codec for the experiment — replacing
> it is the first item in the next steps."

---

## Timing guide

| Bloco | Tempo |
|---|---|
| Abertura | 5 min |
| Arquitetura | 5 min |
| Demo ao vivo | 15 min |
| Wireshark | 15 min |
| Pontos técnicos | 5 min |
| Próximos passos | 5 min |
| Perguntas | 10 min |
| **Total** | **60 min** |
