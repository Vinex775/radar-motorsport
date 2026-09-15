import requests
import re

from collectors.calendario_dtm import buscar_proximo_evento
from zoneinfo import ZoneInfo
from datetime import datetime
from bs4 import BeautifulSoup

URL = "https://www.adac-motorsport.de/en/adac-gt4-germany/news/2026/the-race-weekend-at-the-sachsenring-on-tv-and-via-livestream-2026/"

def interpretar_horario(data, horario):
    horario = horario.replace("–", "-")

    partes = horario.split(" - ")

    data_sem_dia = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", data)
    ano = datetime.now().year

    if len(partes) == 2:
        inicio = datetime.strptime(
            data_sem_dia + f" {ano} " + partes[0],
            "%A, %d %B %Y %H:%M"
        ).replace(tzinfo=ZoneInfo("Europe/Berlin"))

        fim = datetime.strptime(
            data_sem_dia + f" {ano} " + partes[1],
            "%A, %d %B %Y %H:%M"
        ).replace(tzinfo=ZoneInfo("Europe/Berlin"))

    else:
        inicio = datetime.strptime(
            data_sem_dia + f" {ano} " + partes[0],
            "%A, %d %B %Y %H:%M"
        ).replace(tzinfo=ZoneInfo("Europe/Berlin"))

        fim = None

    return inicio, fim

def buscar_eventos():

    evento_dtm = buscar_proximo_evento()

    if evento_dtm is None:
        return []

    slug = evento_dtm["slug"]

    resposta = requests.get(
        "https://api.dtm.com/data",
        params={
            "query": "eventDetails",
            "slug": slug
        }
    )

    dados = resposta.json()
    evento = dados["events"][0]

    eventos = []

    for sessao in evento["timetable"]:

        if sessao["raceSeries"] != "DTM":
            continue

        eventos.append({
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

    return eventos