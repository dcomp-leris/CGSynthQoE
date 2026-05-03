#!/usr/bin/env python3
"""
Servidor QUIC com visualização de dados recebidos
"""

import asyncio
from aioquic.asyncio.server import serve
from aioquic.quic.configuration import QuicConfiguration
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.events import StreamDataReceived, HandshakeCompleted

class VideoStreamProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        print("🔗 Nova conexão estabelecida")
    
    def quic_event_received(self, event):
        """Processar eventos QUIC"""
        
        if isinstance(event, HandshakeCompleted):
            print("✅ Handshake QUIC completado")
        
        elif isinstance(event, StreamDataReceived):
            print(f"📥 Dados recebidos!")
            print(f"   Stream ID: {event.stream_id}")
            print(f"   Tamanho: {len(event.data)} bytes")
            print(f"   Dados: {event.data.decode('utf-8', errors='ignore')}")
            
            # Enviar resposta de volta
            self._quic.send_stream_data(
                event.stream_id,
                b"ACK: Dados recebidos com sucesso!",
                end_stream=False
            )
        
        else:
            print(f"📋 Evento: {type(event).__name__}")

async def run_server():
    print("🚀 Iniciando servidor QUIC...")
    print("=" * 50)
    
    # Configurar servidor
    configuration = QuicConfiguration(
        is_client=False,
        alpn_protocols=["h3", "h3-29"]
    )
    
    # Carregar certificado
    configuration.load_cert_chain("server.pem", "server.key")
    
    # Iniciar servidor
    await serve(
        host="127.0.0.1",
        port=4433,
        configuration=configuration,
        create_protocol=VideoStreamProtocol
    )
    
    print(f"✅ Servidor QUIC rodando em 127.0.0.1:4433")
    print("   Aguardando conexões...")
    print("   Pressione Ctrl+C para parar")
    print("=" * 50)
    
    try:
        await asyncio.Future()  # Rodar para sempre
    except KeyboardInterrupt:
        print("\n🛑 Servidor parado")

if __name__ == "__main__":
    asyncio.run(run_server())
