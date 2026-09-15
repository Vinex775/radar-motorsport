import requests
from datetime import datetime, timezone


API = "https://api.dtm.com/data"

def buscar_proximo_evento():
    resposta = requests.get(
        API,
        params={"query": "eventsRacetrack"}
    )

    dados = resposta.json()

    agora = datetime.now(timezone.utc)
    proximos = []

    for evento in dados["events"]:
        if "DTM" not in evento["raceSeries"]:
            continue

        inicio = datetime.fromisoformat(evento["startTime"])
        fim = datetime.fromisoformat(evento["endTime"])

        if fim > agora:
            proximos.append(evento)

    proximos.sort(key=lambda evento: evento["startTime"])

    if not proximos:
        return None

    return proximos[0]


def buscar_sessoes_dtm(slug):
    resposta = requests.get(
        API,
        params={
            "query": "eventDetails",
            "slug": slug
        }
    )

    dados = resposta.json()
    evento = dados["events"][0]

    sessoes = []
    if not evento["timetable"]:
        print("O timetable ainda não foi publicado pela DTM.")
        return []

    for sessao in evento["timetable"]:
        if sessao["raceSeries"] != "DTM":
            continue

        sessoes.append({
            "nome": sessao["headline"],
            "categoria": "DTM",
            "tipo": sessao["label"],
            "inicio": datetime.fromisoformat(sessao["start"]),
            "fim": datetime.fromisoformat(sessao["end"]),
            "transmissao": {
                "plataforma": "A definir",
                "gratuito": False,
                "url": None
            }
        })

    return sessoes

def buscar_eventos():

    evento = buscar_proximo_evento()

    if evento is None:
        return []

    sessoes = buscar_sessoes_dtm(evento["slug"])

    if sessoes:
        return sessoes

    return [{
        "nome": evento["name"],
        "categoria": "DTM",
        "tipo": "Fim de semana",
        "inicio": datetime.fromisoformat(evento["startTime"]),
        "fim": datetime.fromisoformat(evento["endTime"]),
        "transmissao": {
            "plataforma": "A definir",
            "gratuito": False,
            "url": None
        }
    }]

if __name__ == "__main__":
    evento = buscar_proximo_evento()

    if evento:
        print("PRÓXIMO EVENTO DTM")
        print("-------------------")
        print("Local:", evento["name"])
        print("Slug:", evento["slug"])
        print()

        sessoes = buscar_sessoes_dtm(evento["slug"])

        print("SESSÕES DTM")
        print("-------------------")

        for sessao in sessoes:
            print(
                sessao["nome"],
                "-",
                sessao["tipo"],
                "|",
                sessao["inicio"],
                "->",
                sessao["fim"]
            )

