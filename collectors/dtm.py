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

    print("Próximo evento:", evento_dtm["name"])

    resposta = requests.get(URL)

    soup = BeautifulSoup(resposta.text, "html.parser")

    titulo = soup.find(
        string="The race weekend at the Sachsenring on TV and via livestream"
    )

    if titulo is None:
        print("Título não encontrado.")
        return

    # título → h1 → div → div(article)
    artigo = titulo.parent.parent.parent

    texto_artigo = artigo.get_text(
        separator="\n",
        strip=True
    )

    inicio_dtm = texto_artigo.find("DTM")

    inicio_gt4 = texto_artigo.find(
        "ADAC GT4 Germany",
        inicio_dtm + 1
    )

    texto_dtm = texto_artigo[inicio_dtm:inicio_gt4]

    linhas = texto_dtm.split("\n")

    eventos = []
    data_atual = None

    for i, linha in enumerate(linhas):
        if re.match(r"^(Friday|Saturday|Sunday),", linha):
            data_atual = linha

        elif re.match(r"^\d{2}:\d{2}", linha):
            inicio, fim = interpretar_horario(data_atual, linha)

            evento = {
                "nome": linhas[i + 1],
                "data": data_atual,
                "horario": linha,
                "transmissao": linhas[i + 2],
                "inicio": inicio,
                "fim": fim
            }

            eventos.append(evento)

    return eventos