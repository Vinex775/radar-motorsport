import requests


def buscar_eventos():

    resposta = requests.get(
        "https://api.github.com"
    )

    dados = resposta.json()

    evento = {
        "nome": "Teste de conexão com a internet",
        "categoria": "Sistema",
        "tipo": "Teste",
        "inicio": None,
        "fim": None,
        "transmissao": {
            "plataforma": "GitHub API",
            "gratuito": True,
            "url": dados["current_user_url"]
        }
    }

    return [evento]