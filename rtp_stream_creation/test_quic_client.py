#!/usr/bin/env python3
"""
Cliente QUIC simples para testar conexão
"""

import asyncio
import ssl
from aioquic.asyncio import connect
from aioquic.quic.configuration import QuicConfiguration

async def test_quic():
    print("🔗 Testando conexão QUIC...")
    
    # Configurar QUIC
    configuration = QuicConfiguration(
        is_client=True,
        alpn_protocols=["h3"]
    )
    configuration.verify_mode = ssl.CERT_NONE  # Aceitar qualquer certificado
    
    try:
        # Conectar
        async with connect(
            "quic.tech",
            4433,
            configuration=configuration
        ) as client:
            print("✅ Conexão QUIC estabelecida com sucesso!")
            print(f"   Servidor: quic.tech:4433")
            
            # Aguardar um pouco para a conexão estabilizar
            await asyncio.sleep(0.5)
            
            print("   Status: Conectado e funcional!")
            
            return True
            
    except Exception as e:
        print(f"❌ Erro na conexão: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_quic())
    if result:
        print("\n🎉 QUIC está funcionando perfeitamente!")
    else:
        print("\n❌ QUIC não funcionou.")
