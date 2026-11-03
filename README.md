# APEX — Motorsport Radar

**Radar open-source para descobrir corridas e transmissões de motorsport no mundo todo.** Do kart regional e campeonatos de clubes até Fórmula 1, endurance, rally, drift, arrancada e corridas de motos.

O APEX é um agregador de descoberta: ele aponta calendários, notícias, canais e páginas oficiais. **Não hospeda vídeos, não retransmite corridas e não contorna paywalls ou bloqueios territoriais.**

## O que há nesta versão

- Painel web local em português, com filtros de eventos e tipo de acesso.
- Calendário DTM via coletor isolado. Uma falha nessa fonte não derruba o restante do radar.
- Varredura ampla por famílias de modalidades: fórmulas, karting, rally/rally raid, GT/endurance, turismo/stock cars, motociclismo, motocross, drag, drift, hillclimb, speedway, ovais e corridas regionais.
- **Busca personalizada no próprio painel:** digite qualquer categoria, campeonato, país, pista ou série obscura; o radar procura notícias e anúncios recentes via Google News RSS e seleciona edições regionais conforme o país/idioma identificado na busca.
- Atalhos para 25 tipos de busca, incluindo karting da Suécia, FIA Karting, campeonatos de clubes e eventos nacionais.
- Busca de lives do YouTube pela API oficial quando `YOUTUBE_API_KEY` está configurada; sem chave, o painel abre a busca pública do YouTube.
- Atalhos de busca no Twitch e na web.
- Diretório de fontes e páginas oficiais de transmissão para várias modalidades.
- Classificação de acesso em **Grátis**, **Assinatura**, **Pay-per-view** e **Não confirmado**.
- Cadastro manual de corridas e transmissões que ainda não tenham coletor.
- Alertas do navegador para sessões cadastradas que começam nos próximos 15 minutos (com a página aberta e permissão concedida).
- Banco SQLite local para guardar eventos, pistas e horário da última varredura.

## Requisitos

- Python 3.10 ou superior.
- Conexão com a internet para consultar fontes e notícias.
- Nenhuma biblioteca externa obrigatória.

## Rodar no Windows

1. Baixe ou extraia o projeto.
2. Entre na pasta `radar-motorsport-complete`.
3. Dê dois cliques em `iniciar_radar.bat`, ou abra o PowerShell nessa pasta e execute:

   ```powershell
   py main.py
   ```

4. Abra <http://127.0.0.1:5000> no navegador.
5. Para encerrar, volte ao terminal e pressione `Ctrl + C`.

Se o comando `py` não existir, tente `python main.py`.

## Rodar no macOS / Linux

```bash
python3 main.py
```

Depois abra <http://127.0.0.1:5000>.

## Usar a busca global

1. Abra a aba **Descobrir transmissões**.
2. Escolha um atalho de modalidade ou digite um termo livre.
3. Acrescente país/região para afunilar a busca, por exemplo `Sweden`, `Sverige`, `Brasil`, `Norway` ou `Finland`.
4. Clique em **Buscar no radar** para consultar notícias e anúncios recentes.
5. Use os atalhos YouTube, Twitch e Web para procurar diretamente nas plataformas.

Exemplos de pesquisas livres:

- `Swedish karting series C`
- `Norwegian club rally livestream`
- `Brazil hillclimb championship`
- `Italian regional Formula 4 live`
- `Finnish ice speedway live stream`
- `South African dirt oval racing`

A busca por notícias é uma ferramenta de descoberta. Uma notícia pode estar desatualizada, tratar de uma etapa passada ou não corresponder a uma transmissão ao vivo naquele instante. Sempre abra a fonte original para conferir data e evento.

## Busca de lives do YouTube (opcional)

Para listar no painel os vídeos que o YouTube Data API identifica como transmissões ativas:

1. Crie uma chave no Google Cloud.
2. Habilite **YouTube Data API v3**.
3. Antes de iniciar o projeto, no PowerShell execute:

   ```powershell
   $env:YOUTUBE_API_KEY = "SUA_CHAVE_AQUI"
   py main.py
   ```

A chave fica em uma variável de ambiente e não é gravada no código ou no banco local. **Nunca publique sua chave no GitHub.** Sem a chave, o botão continua abrindo a busca pública do YouTube.

A API pode confirmar que o YouTube classifica o vídeo como live, mas não confirma necessariamente que ele esteja livre de restrição regional, que seja oficial ou que não exija acesso especial. Por isso o painel mantém o preço como **não confirmado**.

Referência: <https://developers.google.com/youtube/v3/docs/search/list>

## Como o acesso é classificado

- **Grátis:** uma fonte identificada declara explicitamente acesso gratuito para aquela modalidade, evento ou região.
- **Assinatura:** a fonte descreve assinatura ou passe pago.
- **Pay-per-view:** existe indicação explícita de compra individual da corrida/evento.
- **Não confirmado:** preço, país, sessão ou condição de acesso não está claro.

A classificação pertence à combinação de **campeonato + plataforma + região + temporada**, e não à modalidade inteira. Um campeonato pode ser gratuito no YouTube em um país e pago em outro. O catálogo procura explicar essas condições no campo de observação.

## Onde os dados vêm

- `collectors/calendario_dtm.py`: calendário estruturado DTM.
- `collectors/discovery.py`: varredura ampla e busca RSS personalizada.
- `collectors/youtube.py`: consulta opcional à API oficial do YouTube.
- `data/watch_sources.json`: diretório de links e guias oficiais de transmissão.
- `data/search_presets.json`: atalhos de pesquisa por modalidade.
- `radar.py`: coordena coletores e prepara o painel.
- `db.py`: persistência SQLite.
- `app.py`: servidor HTTP local e API.

### Adicionar um campeonato ao catálogo

Para cadastrar uma nova página oficial de transmissão, acrescente um objeto em `data/watch_sources.json` com:

- `id` único;
- `series`, `region`, `platform` e `access` (`free`, `subscription`, `ppv` ou `unknown`);
- `url` para a plataforma ou página de transmissão;
- `official_info` para a referência que sustenta a informação;
- `note` explicando restrições importantes;
- `confidence` e `last_checked`.

Use `unknown` quando não conseguir confirmar preço ou território. Não transforme um link de busca em uma fonte oficial.

Para acrescentar um atalho, edite `data/search_presets.json`. O campo `query` é o texto que será preenchido na busca personalizada.

Para adicionar um calendário automático, crie um coletor separado em `collectors/` e registre sua execução em `radar.refresh_all()`. O coletor deve normalizar eventos e falhar de forma isolada. Não invente horários quando a fonte publicar apenas a data da etapa.

## Privacidade e segurança

- O servidor escuta em `127.0.0.1` por padrão e foi pensado para uso local.
- O banco `data/radar.sqlite3` é local e está ignorado pelo Git.
- `.env`, chaves e arquivos de configuração locais estão ignorados pelo Git.
- Não há autenticação multiusuário nem proteção para exposição pública na internet. Não publique a instância local diretamente em um servidor público sem implementar autenticação, controle de acesso, HTTPS e limites de requisição.
- Não adicione chaves de API, tokens, cookies ou dados pessoais ao repositório.

## Limitações conhecidas

- Não existe uma API pública única com todos os eventos, calendários e direitos de transmissão do planeta.
- O calendário estruturado automático desta versão é DTM. Outros campeonatos aparecem por busca de notícias, diretório oficial, YouTube ou cadastro manual.
- O Google News RSS encontra notícias e anúncios; não verifica o estado do player nem confirma que a corrida está ao vivo.
- Sem `YOUTUBE_API_KEY`, o YouTube abre uma busca pública em vez de devolver resultados estruturados dentro do painel.
- “Janela em andamento” é calculada pelo horário publicado da sessão; não é confirmação de vídeo ao vivo.
- Os direitos de transmissão mudam por país, temporada, evento e sessão. Os links oficiais podem mudar sem aviso.
- O coletor DTM usa uma API pública não documentada e pode precisar de manutenção se o fornecedor alterar o formato.
- Os alertas funcionam com o painel aberto; notificações push com o navegador fechado exigiriam infraestrutura adicional.

## Aviso sobre marcas, conteúdo e direitos

APEX é um projeto comunitário independente e não é afiliado, patrocinado ou endossado pela FIA, FIM, Formula 1, Dorna, NASCAR, IMSA, SRO, NHRA ou qualquer campeonato/plataforma listado. Marcas, nomes e links pertencem aos respectivos titulares. O projeto direciona o usuário a fontes externas e não copia nem distribui transmissões.

## Contribuir

Leia `CONTRIBUTING.md` antes de enviar alterações. Sugestões de novos campeonatos são bem-vindas — especialmente karting local, categorias de base, corridas regionais e séries pouco conhecidas.

## Licença

O código deste projeto está disponível sob a licença MIT. Consulte o arquivo `LICENSE`. Isso não concede direitos sobre marcas, transmissões, vídeos, calendários ou conteúdos de terceiros.

## Fontes oficiais mapeadas

- [FIA Karting — canal oficial](https://www.youtube.com/@fiakartingchampionship9818) · [Calendário 2026](https://www.fiakarting.com/competition-list?year=2026)
- [FIA WEC — onde assistir](https://www.fiawec.com/en/page/ou-regarder-1) · [FIAWEC+](https://plus.fiawec.com/)
- [IMSA TV](https://www.imsa.com/tvlive/) · [cobertura internacional](https://www.imsa.com/internationalcoverage/)
- [DTM — TV / live](https://www.dtm.com/live/live-on-tv)
- [WRC — broadcast guide](https://www.wrc.com/en/misc/broadcast-guide) · [Rally.TV](https://www.rally.tv/en/getting-started)
- [Formula E — ways to watch](https://www.fiaformulae.com/en/ways-to-watch)
- [WorldSBK — onde assistir em 2026](https://www.worldsbk.com/en/news/2026/02/19/where-to-watch-worldsbk-throughout-the-2026-seasonx/989565)
- [GT World / SRO America — guia 2026](https://www.gt-world-challenge-america.com/news/1354/how-to-tune-in-to-sro-america-in-2026)
- [NHRA.tv](https://www.nhra.tv/) · [plano gratuito e pago NHRA 2026](https://www.nhra.com/news/2026/nhra-releases-free-2026-streaming-schedule-nhratv-nhra-youtube-page)
- [SuperMotocross Video Pass](https://smxpass.com/247-live/) · [FAQ oficial Supercross](https://www.supercrosslive.com/faq/)
- [NASCAR — guia internacional](https://www.nascar.com/international/how-to-watch)
- [IndyCar — broadcasters internacionais 2026](https://www.indycar.com/how-to-follow/international/)
- [Supercars — guia de transmissão](https://www.supercars.com/how-to-watch)
- [FIM Speedway — onde assistir em 2026](https://fimspeedway.com/news/fim-speedway-where-to-watch-2026)
- [HillClimb.TV](https://hillclimb.tv/)
- [MotoGP VideoPass](https://www.motogp.com/en/videopass)
