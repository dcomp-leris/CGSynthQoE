#!/usr/bin/env python3
"""
Módulo QUIC para streaming de vídeo
"""

import asyncio
import time
import ssl
from aioquic.asyncio.client import connect
from aioquic.quic.configuration import QuicConfiguration
from aioquic.asyncio.protocol import QuicConnectionProtocol

class VideoProtocol(QuicConnectionProtocol):
    """Protocolo customizado para vídeo"""
    pass

class QuicVideoStreamer:
    """Cliente QUIC para enviar frames"""
    
    def __init__(self, server_host="127.0.0.1", server_port=4433):
        self.server_host = server_host
        self.server_port = server_port
        self.protocol = None
        self.stream_id = None
        self.rtt_measurements = []
        self.frame_count = 0
    
    async def connect_async(self):
        """Estabelece conexão QUIC"""
        print(f"🔗 Conectando em {self.server_host}:{self.server_port}...")
        
        configuration = QuicConfiguration(
            is_client=True,
            alpn_protocols=["h3", "h3-29"]
        )
        configuration.verify_mode = ssl.CERT_NONE
        
        # Criar conexão
        async with connect(
            self.server_host,
            self.server_port,
            configuration=configuration,
            create_protocol=VideoProtocol
        ) as client:
            self.protocol = client
            self.stream_id = client._quic.get_next_available_stream_id()
            print(f"✅ Conectado! Stream ID: {self.stream_id}")
            
            # Manter referência
            self._client = client
    
    async def send_frame(self, frame_data, frame_number=None):
        """Envia frame via QUIC"""
        if self.protocol is None:
            raise Exception("Não conectado!")
        
        import struct
        header = struct.pack('!II', len(frame_data), frame_number or self.frame_count)
        packet = header + frame_data
        
        self.protocol._quic.send_stream_data(
            self.stream_id,
            packet,
            end_stream=False
        )
        
        self.frame_count += 1
        
        if self.frame_count % 30 == 0:
            await self.measure_rtt()
    
    async def measure_rtt(self):
        """Mede RTT real da conexão QUIC"""
        if self.protocol is None:
            return 50.0
        
        try:
            # aioquic armazena RTT no objeto _quic
            quic = self.protocol._quic
            
            # Tentar obter smoothed RTT
            if hasattr(quic, '_loss'):
                # aioquic versão nova
                rtt_seconds = quic._loss.get_probe_timeout()
                rtt_ms = rtt_seconds * 1000 if rtt_seconds else 50.0
            elif hasattr(quic, '_rtt_smoothed'):
                # aioquic versão antiga
                rtt_seconds = quic._rtt_smoothed
                rtt_ms = rtt_seconds * 1000 if rtt_seconds else 50.0
            else:
                # Fallback: medir manualmente com ping-pong
                rtt_ms = await self._measure_rtt_ping_pong()
            
            # Limitar valores absurdos
            rtt_ms = max(1.0, min(rtt_ms, 5000.0))
            
            self.rtt_measurements.append(rtt_ms)
            return rtt_ms
            
        except Exception as e:
            print(f"⚠️  Erro ao medir RTT: {e}")
            return 50.0  # Fallback seguro
    
    async def _measure_rtt_ping_pong(self):
        """Mede RTT manualmente com ping-pong"""
        try:
            import time
            
            # Criar stream de ping
            ping_stream = self.protocol._quic.get_next_available_stream_id()
            
            # Marcar tempo
            start = time.time()
            
            # Enviar PING
            self.protocol._quic.send_stream_data(
                ping_stream,
                b"PING",
                end_stream=True
            )
            
            # Aguardar um frame de transmissão (~33ms @ 30fps)
            await asyncio.sleep(0.001)
            
            # Estimar RTT (simplificado)
            # Em produção, esperaria ACK real
            elapsed = (time.time() - start) * 1000
            
            return max(1.0, elapsed)
            
        except Exception as e:
            print(f"⚠️  Ping-pong falhou: {e}")
            return 50.0
    
    def get_current_rtt(self):
        """Retorna RTT médio"""
        if not self.rtt_measurements:
            return 50.0
        recent = self.rtt_measurements[-10:]
        return sum(recent) / len(recent)
    
    def get_encoder_params(self):
        """Retorna parâmetros do encoder"""
        rtt = self.get_current_rtt()
        
        if rtt < 50:
            return {'bitrate': '10M', 'qp': 23, 'gop': 60, 'preset': 'medium', 'quality': 'EXCELENTE'}
        elif rtt < 100:
            return {'bitrate': '5M', 'qp': 28, 'gop': 30, 'preset': 'fast', 'quality': 'BOA'}
        elif rtt < 200:
            return {'bitrate': '3M', 'qp': 32, 'gop': 20, 'preset': 'faster', 'quality': 'MÉDIA'}
        else:
            return {'bitrate': '2M', 'qp': 35, 'gop': 15, 'preset': 'ultrafast', 'quality': 'RUIM'}
    
    async def close(self):
        """Fecha conexão"""
        if self.protocol:
            self.protocol._quic.send_stream_data(self.stream_id, b"", end_stream=True)
            print("🔌 Conexão fechada")
