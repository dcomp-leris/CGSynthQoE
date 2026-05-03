#!/usr/bin/env python3
"""
Cliente QUIC que envia dados e recebe resposta
"""

import asyncio
import ssl
from aioquic.asyncio import connect
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import StreamDataReceived

class QuicClient:
    def __init__(self, connection):
        self._connection = connection
        self._received_data = []
    
    def quic_event_received(self, event):
        if isinstance(event, StreamDataReceived):
            print(f"📥 Resposta do servidor: {event.data.decode('utf-8', errors='ignore')}")
            self._received_data.append(event.data)

async def test_local_quic():
    print("🔗 Conectando em servidor QUIC local (127.0.0.1:4433)...")
    
    configuration = QuicConfiguration(
        is_client=True,
        alpn_protocols=["h3", "h3-29"]
    )
    configuration.verify_mode = ssl.CERT_NONE
    
    try:
        async with connect(
            "127.0.0.1",
            4433,
            configuration=configuration
        ) as protocol:
            print("✅ Conectado!")
            
            # Criar stream
            stream_id = protocol._quic.get_next_available_stream_id()
            print(f"📤 Enviando dados no stream {stream_id}...")
            
            # Enviar mensagem de teste
            message = b"Hello from QUIC client! This is a test message."
            protocol._quic.send_stream_data(stream_id, message)
            
            print(f"   Enviados {len(message)} bytes")
            print(f"   Mensagem: {message.decode()}")
            
            # Aguardar resposta
            print("\n⏳ Aguardando resposta do servidor...")
            await asyncio.sleep(2)
            
            return True
            
    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    result = asyncio.run(test_local_quic())
    if result:
        print("\n🎉 Teste completo!")
