# CGReplay — QUIC Transport Integration

**LERIS/UFSCar · Hugo Guilherme · May 2026**

---

## What was done

Three tasks were completed this week:

1. **QUIC downstream video + command interactivity** — replaced CGReplay's RTP/UDP transport with QUIC. Video frames flow downstream; joystick commands flow upstream. Both channels run over the same QUIC connection.

2. **QUIC mechanism captured in real traffic** — the full handshake and data transfer were captured in a 26 MB PCAP inside a Mininet emulation.

3. **Full integration into CGReplay** — QUIC is now a first-class transport option in the main CGReplay scripts (`cg_server1.py` and `cg_gamer1.py`), selectable via a single config flag.

---

## Architecture

```
h1 · 10.0.0.1                s1               h2 · 10.0.0.2
┌─────────────────┐    OVS switch    ┌─────────────────────┐
│  quic_sender.py │                  │  quic_receiver.py   │
│                 │──── stream N ───►│                     │
│  reads PNG      │  1 QUIC stream   │  decodes JPEG       │
│  embeds QR code │  per frame       │  reads QR code      │
│  encodes JPEG   │  (unidirectional)│  loads sync file    │
│  logs commands  │◄── ctrl stream ──│  sends joystick cmd │
└─────────────────┘                  └─────────────────────┘
```

**Link parameters (configurable):**
```
sudo python3 topology/simple_topology.py --protocol quic --bw 10 --delay 10ms --loss 0
```

---

## Channel design

| Channel | Stream type | Direction | Content |
|---|---|---|---|
| Video | Unidirectional (server) | server → player | JPEG frame + 8-byte header `[frame_id][size]` |
| Control | Unidirectional (client) | player → server | `Ack` / `Nack` / `command` (joystick) |

One QUIC stream per video frame — no head-of-line blocking between frames.

---

## Command interactivity

The player loads `syncs/sync_kombat.txt` (pre-recorded joystick state per frame) and sends the matching command after each frame is received:

```
[RX]  frame=0109  qr=109  size=190678B  fps=5.4
[CMD] frame=0109  commands=1             ← joystick command sent to server

[RX]  frame=0113  qr=113  size=189511B  fps=7.4
[CMD] frame=0113  commands=2             ← 2 commands for this frame
```

---

## Out-of-order delivery (QUIC multiplexing)

Frames arrived in this order during the test run:

```
0109 · 0110 · 0114 · 0102 · 0108 · 0112 · 0104 · 0105 · 0113 · 0111 · 0103 · 0115 · 0116 · 0119
```

Frame 0114 arrived before frame 0102. In TCP, a lost frame 0102 would stall all subsequent frames. In QUIC, each stream is independent — delivery of frame N never waits for frame N-1.

---

## Test results

| Metric | Value |
|---|---|
| Game | Kombat |
| Link | 10 Mbps · 10 ms delay · 0% loss |
| Frames sent / received | 119 / 119 |
| Commands dispatched | confirmed (Ack + joystick) |
| PCAP file size | 26 MB |
| Total packets captured | 28 413 |
| Long-header packets (handshake) | 5 |
| Short-header packets (1-RTT data) | 28 409 |
| Handshake duration | ~56 ms |

---

## Wireshark demo

Open:
```
wireshark player/output.pcap
```

### Step 1 — Full session
Filter: `quic`

Two visual groups: a 5-packet burst at t=0 (connection setup) followed by 28 409 larger packets (video data).

### Step 2 — Long-header packets (connection setup)
Filter: `quic.header_form == 1`  → **5 packets**

| # | Direction | Type | Content |
|---|---|---|---|
| 1 | h2 → h1 | `Initial` | ClientHello (TLS 1.3) |
| 2 | h1 → h2 | `Handshake` | ServerHello + certificate |
| 3 | h1 → h2 | `Handshake` | Finished (server) |
| 4 | h2 → h1 | `Handshake` | Finished (client) |
| 5 | h2 → h1 | `Protected Payload (KP0)` | First 1-RTT message |

Expand packet 1 and point to:
- **Header Form = 1** — long header (connection not yet established)
- **Version = 0x00000001** — QUIC v1, RFC 9000
- **DCID / SCID** — connection IDs (negotiated here, omitted in short header)
- **Crypto Data** — TLS 1.3 ClientHello embedded directly inside QUIC

### Step 3 — Short-header packets (1-RTT video data)
Filter: `quic.header_form == 0`  → **28 409 packets**

Expand any packet and point to:
- **Header Form = 0** — short header (connection established)
- **Spin Bit** — passive RTT measurement, no overhead
- **Packet Number** — incrementing, used for loss detection
- **Protected Payload** — encrypted with session keys from the handshake

---

## Key properties demonstrated

| Property | Evidence |
|---|---|
| No head-of-line blocking | Out-of-order frame delivery visible in terminal log |
| 1-RTT connection setup | Handshake complete in 5 packets, ~56 ms |
| Integrated TLS 1.3 | No separate TCP + TLS handshake — all in QUIC Initial/Handshake packets |
| Always-on encryption | Short-header payload shows only `Protected Payload (KP0)` — no plaintext |
| Bidirectional interactivity | `[CMD]` lines confirm joystick commands sent in response to received frames |

---

## Integration into CGReplay

QUIC is now integrated into the main CGReplay scripts using the same pattern as the existing SCReAM flag. One line in `config/config.yaml` switches the entire transport layer:

```yaml
protocols:
    SCReAM: False
    QUIC: True    # ← set True for QUIC, False for original RTP/GStreamer
```

| `QUIC` value | `cg_server1.py` behaviour | `cg_gamer1.py` behaviour |
|---|---|---|
| `True` | delegates to `quic_sender.py` | delegates to `quic_receiver.py` |
| `False` | GStreamer H.264/RTP pipeline (original) | GStreamer decode pipeline (original) |

No other changes required. The original RTP path is untouched.

---

## Files produced

| File | Purpose |
|---|---|
| `server/quic_sender.py` | QUIC server — reads frames, encodes, streams, logs commands |
| `player/quic_receiver.py` | QUIC client — receives, decodes, sends commands from sync file |
| `topology/simple_topology.py` | Mininet topology + tcpdump automation |
| `config/config.yaml` | `QUIC: True`, `quic_port`, `quic_cert`, `quic_key` |
| `player/output.pcap` | 26 MB PCAP — handshake + 119 frames |
| `player/logs/ply_quic_frame.csv` | Per-frame timestamps, size, FPS |
| `player/logs/ratelog_quic.csv` | Per-frame FPS + CPS (commands per second) |
| `player/logs/ply_quic_events.csv` | Combined screen log — FRAME and CMD events in one timeline |
| `server/logs/srv_quic_frame.csv` | Server-side per-frame TX log |
| `server/logs/srv_quic_events.csv` | Combined server screen log — TX and CTRL events in one timeline |

---

## Screen log — combined event timeline

Both the sender and receiver now write a unified event log that puts video frames and commands on the same timeline. Useful for demo paper figures.

Player side (`player/logs/ply_quic_events.csv`):

```
timestamp,event,frame_id,size_bytes,fps,cmd_count
1717430001.123456,FRAME,1,190678,5.4,1
1717430001.123456,FRAME,2,189511,7.4,2
...
```

Server side (`server/logs/srv_quic_events.csv`):

```
timestamp,event,frame_id,size_bytes,fps,ctrl_type,ctrl_count
1717430001.000000,TX,1,190678,5.4,,
1717430001.350000,CTRL,1,0,0,command,1
...
```

Terminal shows the same events live:

```
[TX]  frame=0001  size= 190678B  stream=  3  fps=  5.4
[RX]  frame=0001  qr=   1  size= 190678B  fps=  5.4
[CMD] frame=0001  commands=1
[CTRL] frame=0001  type=command  count=1
...
[SUMMARY] frames=119  commands=87  avg_fps=7.2  duration=37.1s
```

---

## Next steps

| # | What | Why |
|---|---|---|
| 1 | Replace JPEG with H.264 | Realistic codec — much better compression, closer to production |
| 2 | RTT measurement via Spin Bit | Drive adaptive bitrate from actual measured latency |
| 3 | 24-experiment matrix | 3 games × 4 network conditions × RTP vs QUIC |
| 4 | SSIM / VMAF / LPIPS | Quantify video quality difference between protocols |
