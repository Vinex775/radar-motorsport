from datetime import datetime
from zoneinfo import ZoneInfo


BRASILIA = ZoneInfo("America/Sao_Paulo")

agora = datetime.now(BRASILIA)

# Evento de teste
nome_evento = "DTM - Treino Livre"

inicio = datetime(
    agora.year,
    agora.month,
    agora.day,
    15,
    0,
    tzinfo=BRASILIA
)

fim = datetime(
    agora.year,
    agora.month,
    agora.day,
    17,
    0,
    tzinfo=BRASILIA
)

print("MOTORSPORT RADAR")
print("-" * 30)

print(f"Agora:{agora.strftime('%d/%m/%Y %H:%M:%S')}")
print()

print(f"Evento:{nome_evento}")
print(f"Início:{inicio.strftime('%H:%M')}")
print(f"Fim:{fim.strftime('%H:%M')}")
print()

if agora < inicio:
    print("🟡 PRÓXIMO EVENTO")

elif inicio <= agora <= fim:
    print("🟢 AO VIVO")

else:
    print("🔴 ENCERRADO")