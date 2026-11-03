# Contribuindo com o APEX

Obrigado por ajudar a encontrar mais corridas pelo mundo!

## O que queremos

- Novos calendários oficiais e fontes de transmissão verificáveis.
- Cobertura de karting local, categorias regionais, campeonatos nacionais e modalidades pouco conhecidas.
- Correções de datas, plataformas, acesso e restrições territoriais.
- Melhorias de acessibilidade, usabilidade, testes e documentação.

## Regras para fontes e coletores

1. Prefira páginas oficiais de campeonatos, federações, circuitos e plataformas.
2. Inclua a URL da fonte que sustenta a informação e a data em que ela foi conferida.
3. Informe país/região e temporada sempre que possível.
4. Use `unknown` quando preço ou direito territorial não estiver confirmado.
5. Não marque uma corrida como live só porque o horário da sessão está em andamento.
6. Não copie vídeos, marcas/logos, conteúdo protegido ou dados de login.
7. Não burle paywalls, DRM, geobloqueios ou controles de acesso.
8. Faça requisições com timeout, User-Agent identificável e tratamento de falhas.
9. Não faça um coletor falhar junto com o restante do radar: isole erros por fonte.
10. Não invente horários. Se a fonte divulgar apenas o dia da etapa, deixe a hora vazia.

## Desenvolvimento local

```bash
python -m unittest discover -s tests -v
python main.py
```

O projeto usa a biblioteca padrão do Python. O banco SQLite local não deve ser enviado em pull requests.

## Pull requests

- Explique o problema e a mudança.
- Inclua teste para lógica nova ou corrigida.
- Mantenha o painel em português e a interface responsiva.
- Atualize o README quando adicionar recursos, variáveis de ambiente ou fontes relevantes.
- Não inclua API keys, tokens, cookies, banco local ou arquivos pessoais.
