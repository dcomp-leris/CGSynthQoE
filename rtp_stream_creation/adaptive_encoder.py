#!/usr/bin/env python3
"""
Adaptive H.264 Encoder
Ajusta parâmetros baseado em RTT medido via QUIC
"""

import subprocess
import tempfile
import os
from pathlib import Path

class AdaptiveH264Encoder:
    """
    Encoder H.264 com parâmetros adaptativos baseados em RTT
    """
    
    def __init__(self):
        self.current_params = None
        self.frame_count = 0
    
    def get_encoder_params(self, rtt_ms):
        """
        Retorna parâmetros ótimos baseado em RTT
        
        Baseado em:
        - Salsify (Fouladi et al., NSDI 2018)
        - Adrenaline (Heo et al., 2024)
        - Análise empírica de cloud gaming
        
        Args:
            rtt_ms: RTT em milissegundos
            
        Returns:
            dict com parâmetros do encoder
        """
        
        if rtt_ms < 50:
            # Rede EXCELENTE - priorizar qualidade
            return {
                'bitrate': '10M',
                'crf': 23,      # Constant Rate Factor (melhor que QP fixo)
                'preset': 'medium',
                'gop': 60,
                'tune': 'zerolatency',
                'profile': 'high',
                'level': '4.0',
                'quality': 'EXCELENTE',
                'max_bitrate': '12M',
                'bufsize': '20M'
            }
        
        elif rtt_ms < 100:
            # Rede BOA - balancear qualidade e velocidade
            return {
                'bitrate': '5M',
                'crf': 28,
                'preset': 'fast',
                'gop': 30,
                'tune': 'zerolatency',
                'profile': 'high',
                'level': '4.0',
                'quality': 'BOA',
                'max_bitrate': '7M',
                'bufsize': '10M'
            }
        
        elif rtt_ms < 200:
            # Rede MÉDIA - priorizar estabilidade
            return {
                'bitrate': '3M',
                'crf': 32,
                'preset': 'faster',
                'gop': 20,
                'tune': 'zerolatency',
                'profile': 'main',
                'level': '3.1',
                'quality': 'MÉDIA',
                'max_bitrate': '4M',
                'bufsize': '6M'
            }
        
        else:
            # Rede RUIM - priorizar robustez
            return {
                'bitrate': '2M',
                'crf': 35,
                'preset': 'ultrafast',
                'gop': 15,       # I-frames mais frequentes
                'tune': 'zerolatency',
                'profile': 'baseline',
                'level': '3.0',
                'quality': 'RUIM',
                'max_bitrate': '2.5M',
                'bufsize': '4M'
            }
    
    def encode_frame(self, frame_path, rtt_ms, output_h264=None):
        """
        Codifica um frame PNG/JPG para H.264 NAL units
        
        Args:
            frame_path: caminho do frame (PNG/JPG)
            rtt_ms: RTT atual em ms
            output_h264: caminho de saída (opcional)
            
        Returns:
            bytes: NAL units H.264 codificados
        """
        
        # Obter parâmetros adaptativos
        params = self.get_encoder_params(rtt_ms)
        
        # Criar arquivo temporário se não especificado
        if output_h264 is None:
            output_h264 = tempfile.mktemp(suffix='.h264')
        
        # Construir comando FFmpeg
        cmd = [
            'ffmpeg',
            '-y',
            '-loglevel', 'error',  # NOVO: silenciar warnings
            '-threads', '2',        # NOVO: usar 2 threads
            '-i', frame_path,
            '-c:v', 'libx264',
            '-b:v', params['bitrate'],
            '-maxrate', params['max_bitrate'],
            '-bufsize', params['bufsize'],
            '-crf', str(params['crf']),
            '-preset', params['preset'],
            '-tune', params['tune'],
            '-profile:v', params['profile'],
            '-level', params['level'],
            '-g', str(params['gop']),
            '-keyint_min', str(params['gop']),
            '-sc_threshold', '0',
            '-pix_fmt', 'yuv420p',
            '-f', 'h264',
            '-an',  # NOVO: sem áudio
            output_h264
        ]
        
        try:
            # Executar FFmpeg
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10
            )
            
            if result.returncode != 0:
                print(f"⚠️  FFmpeg error: {result.stderr.decode()}")
                return None
            
            # Ler NAL units
            with open(output_h264, 'rb') as f:
                nal_data = f.read()
            
            # Limpar arquivo temp
            if output_h264.startswith('/tmp'):
                os.remove(output_h264)
            
            self.frame_count += 1
            self.current_params = params
            
            return nal_data
            
        except subprocess.TimeoutExpired:
            print(f"⚠️  FFmpeg timeout encoding {frame_path}")
            return None
        except Exception as e:
            print(f"⚠️  Encoding error: {e}")
            return None
    
    def get_stats(self):
        """Retorna estatísticas do encoder"""
        return {
            'frames_encoded': self.frame_count,
            'current_params': self.current_params
        }


# Teste standalone
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Uso: python3 adaptive_encoder.py <frame.png> [rtt_ms]")
        sys.exit(1)
    
    frame_path = sys.argv[1]
    rtt_ms = float(sys.argv[2]) if len(sys.argv) > 2 else 50.0
    
    encoder = AdaptiveH264Encoder()
    
    print(f"🎬 Codificando {frame_path} com RTT={rtt_ms}ms...")
    
    nal_data = encoder.encode_frame(frame_path, rtt_ms)
    
    if nal_data:
        params = encoder.get_encoder_params(rtt_ms)
        print(f"✅ Sucesso!")
        print(f"   Tamanho: {len(nal_data):,} bytes")
        print(f"   Qualidade: {params['quality']}")
        print(f"   Params: bitrate={params['bitrate']} crf={params['crf']} gop={params['gop']}")
    else:
        print(f"❌ Falha na codificação")
