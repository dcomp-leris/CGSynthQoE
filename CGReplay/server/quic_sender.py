#!/usr/bin/env python3
"""
CGReplay QUIC Sender — server side.

Replaces GStreamer RTP/UDP with QUIC transport.
One QUIC stream per video frame (server-unidirectional).
One long-lived bidirectional stream for player control messages (Ack/Nack/command).

Run from CGReplay/server/:
    source ~/venv/bin/activate
    python3 quic_sender.py
"""

import asyncio
import os
import struct
import time
import sys
import yaml
import cv2
import numpy as np
import qrcode
from aioquic.asyncio.server import serve
from aioquic.quic.configuration import QuicConfiguration
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.events import (
    StreamDataReceived,
    HandshakeCompleted,
    ConnectionTerminated,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CONFIG_PATH = "../config/config.yaml"

with open(CONFIG_PATH) as f:
    config = yaml.safe_load(f)

GAME            = config["Running"]["game"]
STOP_FRAME      = config["Running"]["stop_frm_number"]
FOLDER          = config[GAME]["frames"]
FPS             = config["encoding"]["fps"]
WIDTH           = config["encoding"]["resolution"]["width"]
HEIGHT          = config["encoding"]["resolution"]["height"]
JPEG_QUALITY    = 85
QUIC_HOST       = config["server"]["server_IP"]
QUIC_PORT       = config["protocols"].get("quic_port", 4433)
CERT_FILE       = config["protocols"].get("quic_cert", "../../rtp_stream_creation/server.pem")
KEY_FILE        = config["protocols"].get("quic_key",  "../../rtp_stream_creation/server.key")

LOG_DIR = "./logs"
os.makedirs(LOG_DIR, exist_ok=True)
FRAME_LOG = os.path.join(LOG_DIR, "srv_quic_frame.csv")
EVENT_LOG = os.path.join(LOG_DIR, "srv_quic_events.csv")

with open(FRAME_LOG, "w") as f:
    f.write("frame_id,size_bytes,send_time,fps\n")
with open(EVENT_LOG, "w") as f:
    f.write("timestamp,event,frame_id,size_bytes,fps,ctrl_type,ctrl_count\n")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def embed_qr(frame: np.ndarray, frame_id: int, bitrate: int) -> np.ndarray:
    """Overlay a QR code on the bottom-right corner of the frame."""
    qr = qrcode.QRCode(version=1,
                        error_correction=qrcode.constants.ERROR_CORRECT_L,
                        box_size=10, border=4)
    qr.add_data(f"Frame ID: {frame_id}, bitrate:{bitrate}")
    qr.make(fit=True)
    qr_img = np.array(qr.make_image(fill="black", back_color="white").convert("RGB"))
    qr_size = 160
    qr_img = cv2.resize(qr_img, (qr_size, qr_size))
    x = frame.shape[1] - qr_size - 10
    y = frame.shape[0] - qr_size - 10
    frame[y:y + qr_size, x:x + qr_size] = qr_img
    return frame


def encode_jpeg(frame: np.ndarray) -> bytes:
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    return buf.tobytes()


def list_frames() -> list[str]:
    files = sorted(f for f in os.listdir(FOLDER) if f.endswith(".png"))
    return [os.path.join(FOLDER, f) for f in files]


# ---------------------------------------------------------------------------
# QUIC protocol handler
# ---------------------------------------------------------------------------

class QUICSenderProtocol(QuicConnectionProtocol):
    """
    One instance per client connection.

    Video frames go on server-unidirectional streams (IDs 3, 7, 11 …).
    Control messages (Ack / Nack / command) arrive on a client-initiated stream.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._streaming_task: asyncio.Task | None = None
        self._bitrate = 2000          # kbps (static for prototype)
        self._last_ack_frame = 0
        self._frame_count = 0
        self._ctrl_count = 0
        self._session_start = time.perf_counter()

    def quic_event_received(self, event):
        if isinstance(event, HandshakeCompleted):
            print(f"[QUIC] Handshake complete — starting frame stream (game={GAME})")
            self._streaming_task = asyncio.ensure_future(self._stream_frames())

        elif isinstance(event, StreamDataReceived):
            # Control message from player: "timestamp,cmd,frame_id,type,number,fps,cps"
            try:
                msg = event.data.decode().strip()
                parts = msg.split(",")
                if len(parts) >= 4:
                    msg_type = parts[3]
                    frame_id = int(parts[2])
                    self._last_ack_frame = frame_id
                    self._ctrl_count += 1
                    if msg_type == "command" and len(parts) >= 5:
                        number = parts[4]
                        print(f"[CTRL] frame={frame_id:04d}  type={msg_type}  count={number}")
                        with open(EVENT_LOG, "a") as f:
                            f.write(f"{time.perf_counter():.6f},CTRL,{frame_id},0,0,{msg_type},{number}\n")
                    else:
                        print(f"[CTRL] frame={frame_id:04d}  type={msg_type}")
                        with open(EVENT_LOG, "a") as f:
                            f.write(f"{time.perf_counter():.6f},CTRL,{frame_id},0,0,{msg_type},0\n")
            except Exception:
                pass

        elif isinstance(event, ConnectionTerminated):
            print("[QUIC] Connection terminated")
            if self._streaming_task:
                self._streaming_task.cancel()

    async def _stream_frames(self):
        frames = list_frames()
        previous_time = time.perf_counter()

        for path in frames:
            frame_id = int(os.path.basename(path).split(".")[0])
            if frame_id >= STOP_FRAME:
                break

            # Read + preprocess
            frame = cv2.imread(path)
            if frame is None:
                continue
            frame = cv2.resize(frame, (WIDTH, HEIGHT), interpolation=cv2.INTER_AREA)
            frame = embed_qr(frame, frame_id, self._bitrate)
            payload = encode_jpeg(frame)

            # Each frame on its own server-unidirectional stream
            stream_id = self._quic.get_next_available_stream_id(is_unidirectional=True)

            # Frame header: [4-byte frame_id][4-byte payload_size]
            header = struct.pack("!II", frame_id, len(payload))
            self._quic.send_stream_data(stream_id, header + payload, end_stream=True)
            self.transmit()

            now = time.perf_counter()
            fps = 1.0 / max(now - previous_time, 1e-6)
            previous_time = now

            with open(FRAME_LOG, "a") as f:
                f.write(f"{frame_id},{len(payload)},{now:.6f},{fps:.2f}\n")
            with open(EVENT_LOG, "a") as f:
                f.write(f"{now:.6f},TX,{frame_id},{len(payload)},{fps:.2f},,\n")

            print(f"[TX]  frame={frame_id:04d}  size={len(payload):7d}B  stream={stream_id:3d}  fps={fps:5.1f}")
            self._frame_count += 1

            # Pace to target FPS
            await asyncio.sleep(1.0 / FPS)

        duration = time.perf_counter() - self._session_start
        avg_fps = self._frame_count / max(duration, 1e-6)
        print(f"\n[SUMMARY] frames_sent={self._frame_count}  ctrl_received={self._ctrl_count}"
              f"  avg_fps={avg_fps:.1f}  duration={duration:.1f}s")
        print("[QUIC] All frames sent.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    configuration = QuicConfiguration(is_client=False)
    configuration.load_cert_chain(CERT_FILE, KEY_FILE)
    configuration.alpn_protocols = ["cgquic"]

    print(f"[QUIC] Server listening on {QUIC_HOST}:{QUIC_PORT}")
    print(f"[QUIC] Game={GAME}  FPS={FPS}  stop_frame={STOP_FRAME}")

    await serve(
        host=QUIC_HOST,
        port=QUIC_PORT,
        configuration=configuration,
        create_protocol=QUICSenderProtocol,
    )

    await asyncio.Future()  # run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[QUIC] Server stopped.")
