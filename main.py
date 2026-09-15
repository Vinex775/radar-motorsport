from datetime import datetime
from zoneinfo import ZoneInfo

from collectors.calendario_dtm import buscar_eventos as buscar_eventos_dtm

agora = datetime.now(ZoneInfo("America/Sao_Paulo"))

eventos = []

eventos.extend(buscar_eventos_dtm())

# --------------------------------------------------
# CABEÇALHO
# --------------------------------------------------

print("🏁 MOTORSPORT RADAR")
print("-" * 40)
print(f"Agora: {agora.strftime('%d/%m/%Y %H:%M:%S')}")
print()


# --------------------------------------------------
# SEPARAR EVENTOS POR STATUS
# --------------------------------------------------

ao_vivo = []
proximos = []

for evento in eventos:
    inicio = evento["inicio"]
    fim = evento["fim"]

    if fim is not None and inicio <= agora <= fim:
        ao_vivo.append(evento)

    elif agora < inicio:
        proximos.append(evento)

# Ordenar os próximos pelo horário de início
proximos.sort(key=lambda evento: evento["inicio"])


# --------------------------------------------------
# MOSTRAR AO VIVO
# --------------------------------------------------

print("🟢 AO VIVO AGORA")

if not ao_vivo:
    print("   Nenhum evento encontrado no momento.")

else:

    for evento in ao_vivo:

        tempo_restante = evento["fim"] - agora
        minutos = int(tempo_restante.total_seconds() / 60)

        print(f"🟢 {evento['nome']}")
        print(f"   Categoria: {evento['categoria']}")
        print(f"   Tipo: {evento['tipo']}")
        print(f"   Acaba em {minutos} minutos!!")

        transmissao = evento["transmissao"]

        if transmissao["gratuito"]:
            print(f"   📺 {transmissao['plataforma']} — GRÁTIS")

        else:
            print(f"   🔒 {transmissao['plataforma']} — ASSINATURA NECESSÁRIA")

        print()


# --------------------------------------------------
# MOSTRAR PRÓXIMOS
# --------------------------------------------------

print()
print("🟡 PRÓXIMOS EVENTOS")

if not proximos:
    print("   Nenhum próximo evento encontrado.")

else:

    for evento in proximos:

        tempo_restante = evento["inicio"] - agora
        minutos = int(tempo_restante.total_seconds() / 60)

        print(f"🟡 {evento['nome']}")
        print(f"   Categoria: {evento['categoria']}")
        print(f"   Tipo: {evento['tipo']}")
        print(f"   Começa em {minutos} minutos")

        transmissao = evento["transmissao"]

        if transmissao["gratuito"]:
            print(f"   📺 {transmissao['plataforma']} — GRÁTIS")

        else:
            print(f"   🔒 {transmissao['plataforma']} — ASSINATURA NECESSÁRIA")

        print()