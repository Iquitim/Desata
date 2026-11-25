# Tarefas da spec 049 (0.9.6)

## Marco 1 — Endereços e leitores

- [x] T01 `scripts/conferir_catalogo.py`: verificar de verdade cada endereço do plano, gravar respostas reduzidas em `tests/fixtures/catalogo/`, fechar a lista de destaques (RF-4941) e registrar na spec o que saiu
- [x] T02 `catalog/hosts.py` e `catalog/http.py`: lista fixa, só GET/HEAD por HTTPS, limites, redirecionamento dentro da lista (RF-4981, RF-4982)
- [x] T03 Leitores BCB (SGS com janelas de 10 anos, Olinda: PTAX e Focus) e IBGE (agregados v3 e localidades) (RF-4942, RF-4943)
- [x] T04 Leitores Ipeadata, Tesouro Direto, Siconfi e Comex Stat (RF-4941)
- [x] T04a Feriados: calculados, ANBIMA, tabela dos estados e capitais com as leis, fusão com as edições e conflito de revisão; dias úteis por local e calendário (RF-4944, RF-4946..4948)
- [x] T04b Leitor de OData do Banco Central pelo `$metadata`: entidades, funções com parâmetros tipados, paginação, período (RF-4937, CA-11)
- [x] T04c Portais CKAN verificados: lista fixa com os hosts dos arquivos, sonda, catálogo por portal com grupos e temas no índice, classificação dos recursos (legível, grande, só link) (RF-4936, RF-4939, RF-4940)
- [x] T04d Leitura de arquivos dos portais: detecção da vista Dados, ZIP conferido, limite de 200 MB, formato aceito e conferência das colunas a cada execução (RF-4938, RF-4940, CA-12)
- [x] T04e Correção da vista Dados: zeros à esquerda e códigos longos preservados na leitura de CSV, conferidos no arquivo inteiro, aviso na caixa e paridade com o SQL (RF-4995..4997, CA-13)
- [x] T05 `curated.py` com os destaques e o dicionário de colunas; `index.py` com o catálogo guardado por órgão, Atualizar o catálogo e busca sem acento (RF-4912, RF-4931..4934)
- [x] T06 Teste de nenhum acesso à rede fora de hora (RF-4983, CA-08)

## Marco 2 — Painel do catálogo

- [x] T07 Rotas do catálogo; painel com menu de categorias e Portais, ícones, contagens, cartões com o selo Pronto ou Leitura automática, e busca (RF-4901..4904, RF-4936, RF-4939)
- [x] T08 Detalhe da fonte: informações, colunas, prévia (obrigatória na leitura automática, com troca de separador, codificação e cabeçalho), escolhas e parâmetros do OData, Avançado, Abrir no navegador, Adicionar ao fluxo e à vista Dados (RF-4911..4915, RF-4937, RF-4938, RF-4940)
- [x] T09 Favoritos e recentes (RF-4905)
- [x] T09a Editar feriados…: incluir, corrigir, Não vale mais, Restaurar, origem de cada linha, Manter o meu / Usar o do programa; Compartilhar com a equipe (RF-4945..4948, CA-10)

## Marco 3 — Situação dos órgãos

- [x] T10 `health.py`: sondas, No ar / Lenta / Fora do ar, motivo, "desde", sem conexão, histórico de 30 dias (RF-4921..4924)
- [x] T11 Selos na tela: categorias, cartões, detalhe, Conferir de novo, faixa sem conexão, barra de 30 dias (CA-02, CA-03)

## Marco 4 — Fonte do catálogo no fluxo

- [x] T12 Ferramenta `public_data`: configuração, execução, período relativo, leitura guardada e Exigir dados atuais; formato aceito dos arquivos de portal e Aceitar o novo formato; num fluxo do espaço, Feriados e Dias úteis usam a lista de feriados da equipe (RF-4925, RF-4938, RF-4948, RF-4971, RF-4973, CA-01, CA-12)
- [x] T13 Pasta Dados públicos na vista Dados; aviso Dados novos na vista e na caixa (RF-4935)
- [ ] T14 Metadados de fonte no resultado; dicionário no Perfil; citação no dashboard e no HTML exportado (RF-4912, RF-4963, CA-07)

## Marco 5 — Downloads grandes: CNPJ

- [ ] T15 `download.py`: partes, tamanhos, espaço livre, pasta escolhida e proibida, Range, pausar, continuar, cancelar, novas tentativas, estado para retomar (RF-4951..4953)
- [ ] T16 Conferência e descompactação segura; `cnpj.py` com o leiaute e a fonte de pasta pronta; leiaute que não bate (RF-4954, RF-4955, CA-05)
- [ ] T17 Tela: escolha das partes, barra na vista Dados, Continuar o download ao abrir, mês novo, Baixar aqui para o colega da equipe (RF-4953, RF-4956, RF-4972)

## Marco 6 — Usar com um clique

- [ ] T18 Receitas Corrigir pelo IPCA e Converter pela PTAX (RF-4961)
- [ ] T19 Juntar com municípios do IBGE, com casados e não casados antes de inserir (RF-4962, CA-06)

## Marco 7 — Conferências e publicação

- [ ] T20 conferir_tela (`catalogo`, `cnpj`) e conferir_exe com uma fonte pública (leitura guardada, sem rede no CI)
- [ ] T21 Guia e Manual (capítulo Dados públicos do Brasil, Escopo e limitações), prints das duas marcas, README, `contexto-ia.md`, versão 0.9.6, instaladores, publicar (RF-4991)
