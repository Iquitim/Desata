# Plano da spec 049 (0.9.6)

## Marcos

1. **Endereços e leitores** (RF-4931..4934, 4941..4943, 4981..4983): verificar cada endereço de verdade, escrever
   o leitor de cada órgão e o índice do catálogo guardado.
2. **Painel do catálogo** (RF-4901..4905, 4911..4915): menu, cartões, busca, detalhe, prévia e escolhas.
3. **Situação dos órgãos** (RF-4921..4925): conferência, selos, histórico, faixa sem conexão.
4. **Fonte do catálogo no fluxo** (RF-4925, 4935, 4963, 4971, 4973): caixa Dados públicos, execução, leitura
   guardada, Dados novos, citação.
5. **Downloads grandes: CNPJ** (RF-4951..4956, 4972).
6. **Usar com um clique** (RF-4961, 4962): receitas IPCA e PTAX, junção com municípios.
7. **Documentação e publicação** (RF-4991).

Ao fim de cada marco: testes, conferência na tela, commit e push.

## Primeiro passo: verificar os endereços (T01)

Antes de qualquer código de leitor, `scripts/conferir_catalogo.py` (manual, fora do CI) chama de verdade cada
endereço e grava as respostas de exemplo (reduzidas) em `tests/fixtures/catalogo/`, que os testes usam sem rede.
Candidatos a confirmar:

| Órgão / serviço | Catálogo (metadados) | Dados |
|---|---|---|
| BCB, SGS | portal de dados abertos do BCB (CKAN, `package_search`), conjuntos com o código SGS | `api.bcb.gov.br/dados/serie/bcdata.sgs.{código}/dados?formato=json&dataInicial=&dataFinal=` (até 10 anos) |
| BCB, Olinda | serviços OData (`$metadata`) | PTAX (`CotacaoMoedaPeriodo`), Expectativas (Focus) |
| IBGE, agregados v3 | `servicodados.ibge.gov.br/api/v3/agregados`, `/{agregado}/metadados`, `/{agregado}/periodos` | `/{agregado}/periodos/{p}/variaveis/{v}?localidades=` |
| IBGE, localidades v1 | — | `/api/v1/localidades/regioes`, `/estados`, `/municipios` |
| Ipeadata | `www.ipeadata.gov.br/api/odata4/Metadados` (código, nome, fonte, periodicidade, última atualização, ativa), `/Temas` | `/ValoresSerie(SERCODIGO='…')` |
| Tesouro | portal Tesouro Transparente (CKAN) | CSV de preços e taxas do Tesouro Direto; API do Siconfi |
| Receita | listagem das pastas mensais `AAAA-MM` dos dados abertos do CNPJ | ZIPs por parte, leiaute em PDF |
| MDIC | Comex Stat (API pública) | consultas por período, produto, país e UF |

O que não passar (exige token, só HTTP, instável) sai dos destaques da 0.9.6 e fica registrado na spec. Endereços
alternativos (quando o órgão tem dois hosts) entram na mesma lista.

## Organização no código

```
src/prodata/catalog/
  hosts.py        lista fixa de endereços permitidos (RF-4981), por serviço; endereços alternativos
  http.py         cliente: só GET/HEAD, HTTPS, tamanho máximo, redirecionamento dentro da lista, tempo curto;
                  reaproveita o TLS do sistema e as mensagens de rede do conector de API (connectors/api.py)
  model.py        CatalogEntry (id, órgão, serviço, categoria, nome, resumo, periodicidade, granularidade,
                  unidade, período, última atualização, colunas com dicionário, licença, citação, escolhas)
  curated.py      os destaques: nome simples, ícone, palavras-chave, dicionário, escolhas e o leitor que usam
  readers/        um módulo por órgão: bcb_sgs, bcb_olinda, ibge, ipea, tesouro, siconfi, comex, receita
                  cada um com catalog() (lê o catálogo do órgão), meta(id) e read(id, escolhas) -> DataFrame
  calendar.py     feriados nacionais (fixos e móveis pela Páscoa) e dias úteis por local, sem rede
  holidays/       base_estados_capitais.json (feriado, abrangência, lei, vigência; "revisado em") e a fusão das
                  quatro origens com as edições da pessoa
  index.py        índice guardado: catálogo por órgão com a data da leitura, busca sem acento
  health.py       conferência por serviço, situação, "desde", motivo, histórico de 30 dias
  cache.py        última leitura por consulta (Parquet), com a data e a impressão digital da consulta
  download.py     downloads grandes: lista de partes, Range, pausa/retomada, conferência e descompactação segura
  cnpj.py         leiaute da Receita (nomes, tipos, dicionário) e a fonte de pasta pronta
```

- **Por que leitores próprios e não a fonte de API comum**: as regras de cada órgão (janelas de 10 anos no SGS,
  divisão por localidade no IBGE, paginação do Olinda, marcas de "sem dado") não cabem numa configuração de API sem
  o usuário ver os detalhes. A parte de rede é a mesma (TLS do sistema, mensagens de erro em palavras, novas
  tentativas com espera), reaproveitada de `connectors/api.py`.
- **Onde fica no disco** (pasta de dados do computador, nunca no fluxo nem no espaço):
  ```
  catalogo/indice/<orgao>.json.gz      catálogo do órgão + data da leitura
  catalogo/situacao.json               última conferência por serviço e histórico de 30 dias
  catalogo/leituras/<impressão>.parquet + .json   última leitura de cada consulta (dados + quando)
  catalogo/preferencias.json           favoritos e recentes
  catalogo/downloads/<id>.json         estado dos downloads (pasta escolhida, partes, bytes) para retomar
  ```

## Portais de dados abertos (RF-4936..4940)

- `catalog/portals.py`: a lista fixa de portais verificados (id, órgão, endereço do CKAN, hosts dos arquivos,
  esfera federal/estadual/municipal). Cada portal vira um serviço em `hosts.SERVICES` (sonda: `package_search?rows=0`)
  e os hosts dos arquivos entram em `ALLOWED_HOSTS`. Nada vindo de um portal acrescenta endereço: um recurso apontando
  para fora da lista vira só link.
- `readers/ckan.py`: catálogo do portal (`package_search` paginado, com grupos e temas), detalhe do conjunto
  (`package_show`) e a classificação de cada recurso: legível (formato e host ok), grande (download), só link (motivo).
- `readers/odata.py`: leitor de OData do Olinda pelo `$metadata` (entidades, funções com parâmetros e tipos),
  paginação `$top`/`$skip`, filtro de período quando há coluna de data.
- `readers/files.py`: leitura de arquivo de portal reaproveitando a detecção da vista Dados (separador, codificação,
  cabeçalho, número brasileiro); ZIP conferido (caminhos, tamanho descompactado, só CSV/XLSX/Parquet dentro);
  limite de 200 MB lido direto. O **formato aceito** (colunas e tipos da prévia, opções de leitura) vai na
  configuração da caixa; a execução compara e, se mudou, falha com a diferença em palavras (RF-4938).

## A caixa Dados públicos

- Ferramenta de entrada `public_data`, declarativa (princípio III): `{"fonte": "bcb.sgs/432", "escolhas":
  {"periodo": {"atalho": "ultimos_anos", "anos": 5}, "localidade": …}, "exigir_atual": false}`. O fluxo guarda só
  isso (CA-08); a URL é montada na execução pelo leitor.
- Execução: `read()` do leitor → em sucesso, grava a leitura guardada; em falha de rede ou serviço, usa a leitura
  guardada da mesma impressão de consulta e devolve aviso com a data; sem leitura ou com `exigir_atual`, falha com
  a mensagem do motivo.
- Período relativo ("últimos 5 anos") é resolvido na hora da execução, para o agendamento sempre trazer o recente.
- O resultado leva metadados da fonte (órgão, código, título, licença, data da leitura) para o Perfil, o dicionário
  de colunas e a citação.
- Na vista Dados, a pasta **Dados públicos** guarda referências iguais (sem dados), com situação e prévia.

## Situação

- Uma sonda por serviço (a menor consulta possível: metadados de uma série conhecida, `localidades/regioes`, etc.),
  em paralelo, tempo de 5 s; Lenta acima de 2 s. Conferência com o catálogo aberto, ao Conferir de novo e no
  máximo uma vez a cada 5 minutos por serviço.
- Sem rede: se todas as sondas falham por erro de conexão (não por resposta HTTP), a situação é "não conferido" e a
  faixa "Sem conexão" (RF-4923).
- "Fora do ar desde": a hora da primeira falha da sequência atual, guardada em `situacao.json`.
- Histórico: por serviço, por dia, o pior resultado do dia; 30 dias.
- Dados novos (RF-4935): o catálogo traz a última atualização da fonte; a vista Dados compara com a data da última
  leitura guardada das fontes usadas.

## Feriados editáveis

- Cada feriado do programa tem um identificador estável (`<abrangência>/<slug>`, por exemplo `SP/revolucao-1932`) e
  uma impressão do conteúdo. As edições da pessoa ficam em `catalogo/feriados_meus.json`, como operações sobre a
  base: `incluir`, `corrigir` (id + campos + impressão do original no momento da edição) e `nao_vale_mais` (id +
  data). Nada da tabela embutida é alterado.
- Fusão: calculados + ANBIMA + programa, aplicando as edições por id. Se a impressão atual do feriado do programa
  difere da guardada na edição, a linha ganha a marca "O programa também mudou" (RF-4947) até a pessoa escolher.
  Inclusão do programa com a mesma data e abrangência de uma inclusão da pessoa não duplica.
- Regras de data: fixa (dia/mês), móvel (deslocamento da Páscoa), única (data); vigência inicial e final.
- Na equipe, a lista de edições vira uma definição do tipo `feriados` em `_equipe/definicoes/feriados/<id>.json`,
  assinada, pelo mesmo caminho da spec 048 (`TeamDefinitions` e `Overlay`).
- Testes: Páscoa 2000–2050; fusão com cada operação; conflito de revisão; restaurar; dias úteis por UF e município;
  a tabela embutida conferida nos testes contra uma biblioteca de feriados (só como verificação).

## Download do CNPJ

- Lista de partes: leitura da listagem da pasta mensal mais recente e `HEAD` de cada ZIP (tamanho). Espaço livre
  por `shutil.disk_usage` da pasta escolhida.
- Pasta escolhida pelo diálogo do sistema (como no Output Data): caminho absoluto, existente, não pode estar dentro
  de um espaço da equipe nem da pasta de dados; o programa cria só `CNPJ-AAAA-MM` e grava nomes fixos.
- Download em linha de execução de fundo, um arquivo por vez, gravando em `<parte>.zip.parte` com `Range` para
  retomar; estado em `catalogo/downloads/<id>.json`. A tela acompanha por `GET /api/catalogo/downloads/<id>`.
- Conferência: tamanho igual ao do `HEAD`; `zipfile.testzip()`; cada membro com caminho sem `..` nem absoluto,
  tamanho descompactado total até um limite (proporção máxima sobre o compactado) e gravado com o nome fixo.
- Fonte pronta: fonte de pasta (a mesma do Input Folder) com encoding Latin-1, separador `;`, sem cabeçalho, nomes e
  tipos do leiaute em `cnpj.py`; quantidade de colunas conferida na primeira linha (RF-4955).

## Receitas e junção

- **Corrigir pelo IPCA**: insere `public_data` (IPCA, número-índice mensal), uma fórmula que tira o mês da data,
  o Join pelo mês e a fórmula `valor * indice_referencia / indice_mes`, agrupadas e nomeadas; mês de referência
  padrão: o último disponível.
- **Converter pela PTAX**: `public_data` (PTAX venda), junção pela data com "último dia útil anterior" (usa o
  calendário local), fórmula da divisão; aviso com quantas datas usaram o dia anterior.
- **Municípios**: `public_data` (municípios do IBGE) + uma chave normalizada (sem acento, minúsculas, apóstrofos
  uniformes, + UF) ou o código cortado em 6 dígitos; a janela mostra casados e não casados antes de inserir.
- Todas as caixas inseridas são caixas comuns (Ctrl+Z desfaz a inserção inteira).

## Citação

- O dashboard e o HTML exportado juntam os metadados de fonte dos resultados usados e escrevem o rodapé "Fonte:"
  agrupado por órgão; licença ODbL com a atribuição exigida. Opção no dashboard para esconder.

## Rotas

```
GET  /api/catalogo                       índice (destaques + resumo por órgão + data da leitura)
GET  /api/catalogo/busca?q=&orgao=&periodicidade=
GET  /api/catalogo/fontes/{id}           detalhe (metadados da fonte, ao vivo quando possível)
GET  /api/catalogo/fontes/{id}/previa    últimas linhas (ou a leitura guardada)
POST /api/catalogo/atualizar             atualiza os catálogos dos órgãos (progresso por órgão)
GET  /api/catalogo/situacao              situação por serviço; POST para conferir de novo
POST /api/catalogo/favoritos/{id}        marca e desmarca
POST /api/catalogo/downloads             inicia (fonte, partes, pasta); GET/POST …/{id} acompanhar, pausar, continuar, cancelar
```

## Testes

- Leitores com `httpx.MockTransport` e as respostas de `tests/fixtures/catalogo/` (sem rede no CI).
- SGS: 15 anos viram 2 ou 3 janelas, sem repetir a data de fronteira.
- Situação: lenta, fora do ar, sem rede, "desde", histórico.
- Leitura guardada e `exigir_atual`.
- Download: servidor local simulado com Range, pausa e retomada, ZIP malicioso (zip slip, bomba), espaço insuficiente,
  pasta proibida (espaço da equipe, pasta de dados).
- Hosts: URL fora da lista, HTTP, redirecionamento para fora, POST recusados.
- Sem rede fora de hora (RF-4983): um teste que bloqueia o socket e abre o programa, a vista Dados e executa um fluxo
  comum.
- Receitas: IPCA e PTAX com números conhecidos; junção com municípios com os casos de CA-06.
- Feriados: Páscoa e feriados móveis de 2000 a 2050 conferidos contra uma lista conhecida.
- conferir_tela: `catalogo` (abrir, navegar, buscar, detalhe, adicionar, selo fora do ar simulado), `cnpj`
  (download simulado até a fonte pronta).
