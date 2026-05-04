#!/usr/bin/env python3
"""
QUIC Video Packetizer com Encoder H.264 Adaptativo
"""

import asyncio
import os
import glob
import time
from pathlib import Path
from quic_video_streamer import QuicVideoStreamer
from adaptive_encoder import AdaptiveH264Encoder

class QuicVideoPacketizer:
    """Packetiza frames e envia via QUIC com encoding adaptativo"""
    
    def __init__(self, frames_dir, server_host="127.0.0.1", server_port=4433, encode_h264=True):
        self.frames_dir = frames_dir
        self.server_host = server_host
        self.server_port = server_port
        self.streamer = None
        self.encode_h264 = encode_h264
        self.encoder = AdaptiveH264Encoder() if encode_h264 else None
        
        self.stats = {
            'total_frames': 0,
            'total_bytes': 0,
            'total_bytes_encoded': 0,
            'start_time': None,
            'end_time': None
        }
    
    async def initialize(self):
        """Inicializa conexão QUIC"""
        print("🚀 Inicializando QUIC Video Packetizer...")
        print(f"   Frames dir: {self.frames_dir}")
        print(f"   Servidor: {self.server_host}:{self.server_port}")
        print(f"   Encoder H.264: {'✅ Ativo' if self.encode_h264 else '❌ Desativado'}")
        
        self.streamer = QuicVideoStreamer(self.server_host, self.server_port)
        await self.streamer.connect_async()
        
        print("✅ Inicializado!")
    
    def get_frame_files(self):
        """Obtém lista de frames"""
        patterns = ['*.png', '*.jpg', '*.jpeg']
        frame_files = []
        
        for pattern in patterns:
            frame_files.extend(glob.glob(os.path.join(self.frames_dir, pattern)))
        
        frame_files = [f for f in frame_files if ':' not in os.path.basename(f)]
        frame_files.sort()
        return frame_files
    
    async def send_frame_file(self, frame_path, frame_number):
        """Envia um arquivo de frame"""
        
        # Ler tamanho original (raw)
        with open(frame_path, 'rb') as f:
            raw_size = len(f.read())
        
        if self.encode_h264 and self.encoder:
            rtt = self.streamer.get_current_rtt()
            frame_data = self.encoder.encode_frame(frame_path, rtt)
            
            if frame_data is None:
                print(f"⚠️  Falha ao codificar frame {frame_number}")
                return 0
            
            # Somar bytes ANTES e DEPOIS
            self.stats['total_bytes'] += raw_size  # Raw (PNG)
            self.stats['total_bytes_encoded'] += len(frame_data)  # H.264
        else:
            frame_data = None
            with open(frame_path, 'rb') as f:
                frame_data = f.read()
            
            self.stats['total_bytes'] += len(frame_data)
        
        await self.streamer.send_frame(frame_data, frame_number)
        self.stats['total_frames'] += 1
        
        return len(frame_data)
    
    async def packetize_and_send(self, fps=30):
        """Packetiza e envia todos os frames"""
        print(f"\n📹 Iniciando transmissão a {fps} FPS...")
        
        frame_files = self.get_frame_files()
        total_frames = len(frame_files)
        
        if total_frames == 0:
            print(f"❌ Nenhum frame encontrado em {self.frames_dir}")
            return
        
        print(f"   Total de frames: {total_frames}")
        
        frame_interval = 1.0 / fps
        self.stats['start_time'] = time.time()
        
        for i, frame_path in enumerate(frame_files):
            frame_size = await self.send_frame_file(frame_path, i)
            
            if i % 30 == 0:
                params = self.streamer.get_encoder_params()
                rtt = self.streamer.get_current_rtt()
                
                if self.encoder:
                    enc_params = self.encoder.get_encoder_params(rtt)
                    enc_info = f"[H.264: crf={enc_params['crf']} gop={enc_params['gop']}]"
                else:
                    enc_info = "[RAW]"
                
                print(f"Frame {i:4d}/{total_frames} | "
                      f"RTT: {rtt:5.1f}ms | "
                      f"Rede: {params['quality']:8s} | "
                      f"{enc_info}")
            
            await asyncio.sleep(frame_interval)
        
        self.stats['end_time'] = time.time()
        await self.print_statistics()
    
    async def print_statistics(self):
        """Imprime estatísticas"""
        duration = self.stats['end_time'] - self.stats['start_time']
        
        print("\n" + "=" * 70)
        print("📊 ESTATÍSTICAS DA TRANSMISSÃO")
        print("=" * 70)
        print(f"Total de frames enviados: {self.stats['total_frames']}")
        print(f"Total de bytes (raw):     {self.stats['total_bytes']:,} bytes ({self.stats['total_bytes']/1024/1024:.2f} MB)")
        
        if self.encoder and self.stats['total_bytes_encoded'] > 0:
            print(f"Total após H.264:         {self.stats['total_bytes_encoded']:,} bytes ({self.stats['total_bytes_encoded']/1024/1024:.2f} MB)")
            compression = (1 - self.stats['total_bytes_encoded'] / self.stats['total_bytes']) * 100
            print(f"Taxa de compressão:       {compression:.1f}%")
        
        print(f"Duração:                  {duration:.2f} segundos")
        print(f"FPS efetivo:              {self.stats['total_frames']/duration:.2f}")
        
        if self.stats['total_bytes_encoded'] > 0:
            print(f"Bitrate H.264:            {(self.stats['total_bytes_encoded']*8/duration/1_000_000):.2f} Mbps")
        else:
            print(f"Bitrate médio:            {(self.stats['total_bytes']*8/duration/1_000_000):.2f} Mbps")
        
        print("=" * 70)
    
    async def close(self):
        """Fecha conexão"""
        if self.streamer:
            await self.streamer.close()

async def main():
    """Função principal"""
    import argparse
    
    parser = argparse.ArgumentParser(description='QUIC Video Packetizer')
    parser.add_argument('--frames-dir', required=True, help='Diretório com frames')
    parser.add_argument('--server-host', default='127.0.0.1', help='IP do servidor')
    parser.add_argument('--server-port', type=int, default=4433, help='Porta do servidor')
    parser.add_argument('--fps', type=int, default=30, help='Frames por segundo')
    parser.add_argument('--encode-h264', action='store_true', help='Codificar em H.264')
    
    args = parser.parse_args()
    
    packetizer = QuicVideoPacketizer(
        frames_dir=args.frames_dir,
        server_host=args.server_host,
        server_port=args.server_port,
        encode_h264=args.encode_h264
    )
    
    try:
        await packetizer.initialize()
        await packetizer.packetize_and_send(fps=args.fps)
    finally:
        await packetizer.close()

if __name__ == "__main__":
    asyncio.run(main())
