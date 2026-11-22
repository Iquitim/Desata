# Constituição do PRO.DATA

Princípios não negociáveis do projeto. Toda spec, plano e PR deve ser compatível
com eles; quando um princípio precisar mudar, altere este arquivo primeiro, em PR
separado, com justificativa.

Versão: 1.8.1 · Ratificada: 2026-10-28 · Emendada: 2026-11-22 (princípio IV: cofre do SO, conectores somente leitura; destinos escolhidos pelo usuário — spec 009; imagens PNG do dashboard — spec 014; arquivos de origem vinculados — spec 017; pasta lida, modelo de Excel e estado das caixas — spec 033; pasta de um espaço da equipe e princípio VIII, colaboração opcional e verificável — spec 047; definições compartilhadas da equipe — spec 048; acesso à internet só pelo catálogo de dados públicos — spec 049)

## I. Spec antes do código (SDD)

Mudanças de comportamento começam em `specs/NNN-nome/`:

1. `spec.md` — o **quê** e o **porquê**: histórias de usuário, requisitos
   funcionais numerados (`RF-xxx`), critérios de aceite verificáveis.
   Sem decisões de implementação.
2. `plan.md` — o **como**: arquitetura, contratos (API, formatos), riscos.
3. `tasks.md` — tarefas pequenas e ordenadas, cada uma ligada a um `RF`.

Correções de bug e refatorações sem mudança de comportamento dispensam spec,
mas não dispensam teste.

## II. Motor desacoplado da interface

- O motor (`prodata.engine`, `prodata.nodes`, `prodata.ingestion`) não importa
  FastAPI nem conhece HTTP. Deve ser utilizável a partir de um script Python.
- A API (`prodata.api`) é uma camada fina: valida entrada, chama serviços,
  serializa saída.
- O frontend fala apenas com a API REST documentada em `/docs`.

## III. Ferramentas são declarativas

Cada ferramenta (nó) declara em um único lugar: metadados, portas, modelo de
configuração Pydantic e função de execução. O formulário do Inspector é gerado
a partir desse modelo — não existe formulário escrito à mão por ferramenta,
exceto widgets especializados reutilizáveis.

## IV. Segurança por padrão

- Nenhum caminho de arquivo vindo do cliente é usado sem ser resolvido e
  confinado ao diretório de dados (`resolve_inside`). Exceção única: destinos
  escolhidos explicitamente pelo usuário — a pasta do Output Data, arquivos de
  fluxo `.prodata.json` e imagens `.png` exportadas do dashboard — desde que o caminho seja absoluto, o diretório já
  exista, a extensão seja fixa e o nome do arquivo seja saneado.
- Arquivos de origem **vinculados** pelo usuário (spec 017) podem ser lidos fora do diretório de
  dados: caminho absoluto, arquivo existente no momento do vínculo, extensão da lista permitida.
  São somente leitura: o PRO.DATA nunca grava, move ou apaga o arquivo vinculado.
- A pasta do Input Folder e o modelo de Excel do Output Data (spec 033) seguem a mesma regra dos arquivos
  vinculados: caminho absoluto escolhido pelo usuário, existente, extensão da lista permitida, somente
  leitura. A abertura protegida mostra os dois a quem recebe o fluxo.
- O que uma caixa guarda entre execuções (modelos de ML, tabelas do Compare Runs) fica na pasta de dados do
  computador, num caminho montado com o ID do fluxo e da caixa. Nunca vai no arquivo do fluxo, e um arquivo
  de modelo só é lido dali, depois de conferido o seu SHA-256.
- A pasta de um **espaço da equipe** (spec 047) é a única outra pasta em que o programa grava por conta
  própria: caminho absoluto escolhido explicitamente pela pessoa, já existente. Ali ele grava só os
  arquivos do espaço, em formatos e nomes fixos e saneados (fluxos, versões, assinaturas, membros, marcas
  de edição, comentários, o estado dos agendamentos e as definições compartilhadas: constantes, conexões,
  consultas e APIs, spec 048). Nunca grava ali dados das fontes, resultados de execução, amostras ou
  segredos: uma conexão ou API da equipe vai sem senha, token ou chave, e cada pessoa guarda o seu segredo
  no cofre do próprio computador.
- O **catálogo de dados públicos** (spec 049) é o único acesso à internet que o programa faz por iniciativa
  própria, e só nestes momentos: com o catálogo aberto (conferir se cada órgão está no ar e ler os metadados),
  quando a pessoa pede **Atualizar o catálogo** e quando um fluxo executa uma fonte do catálogo. Só lê, por
  HTTPS, de uma lista fixa de endereços oficiais embutida no programa; nunca envia dados das fontes, dos
  fluxos ou da pessoa, nem usa conta, token ou chave da pessoa (o identificador público de um link de
  compartilhamento oficial, igual para todos e publicado pelo órgão, não é credencial e pode ficar no código). Arquivos grandes baixados do catálogo vão para uma pasta
  escolhida explicitamente pela pessoa (caminho absoluto, já existente, nomes fixos e saneados), nunca para a
  pasta de um espaço da equipe. Sem catálogo aberto e sem fonte do catálogo, o programa não acessa a rede.
- Uploads têm lista de extensões permitidas e tamanho máximo.
- Segredos (senhas de banco, chaves de API) nunca são salvos em workflows,
  arquivos do projeto ou logs, nem devolvidos pela API. Ficam no cofre do
  sistema operacional (`keyring`) ou em variáveis de ambiente.
- Conectores de banco são somente leitura, salvo spec explícita em contrário.
- CORS restrito às origens configuradas.

## V. Falhas são explícitas

- Nenhum `except Exception: pass`. Erros são registrados em log e devolvidos ao
  usuário com mensagem acionável.
- Um nó com falha marca seus descendentes como `skipped`, nunca os executa com
  entradas faltantes.
- Ciclos no grafo são erro de validação, não comportamento indefinido.

## VI. Honestidade funcional

Recursos simulados são rotulados como tal na interface e na documentação
(ex.: provedor de IA `local-heuristic`). Métricas de modelo são calculadas em
dados de validação, não nos dados de treino.

## VII. Testes e qualidade

- `uv run pytest` e `uv run ruff check` passam antes de qualquer merge (CI).
- Todo requisito funcional do motor tem ao menos um teste automatizado.
- Tipagem estática em todo código Python novo (`mypy` sem erros em `src/`).

## VIII. Colaboração opcional e verificável

O trabalho em equipe acontece numa pasta compartilhada (rede, OneDrive, SharePoint), sem servidor nem nuvem
próprios do programa.

- **Opcional.** Sem um espaço da equipe configurado, a tela, o comportamento e os arquivos gravados são
  idênticos aos do programa usado só no computador. Um teste automatizado garante isso.
- **Identidade por chave pessoal.** Cada pessoa tem um par de chaves (Ed25519) gerado no próprio computador.
  A chave privada fica só no cofre do sistema operacional; nunca vai para a pasta, para um fluxo ou para um log.
- **Tudo o que dá permissão é assinado.** A lista de membros e papéis é assinada por um administrador; cada
  versão salva é assinada por quem salvou; a versão oficial de um fluxo é assinada por quem tem o papel de
  publicar; cada definição compartilhada (constante, conexão, consulta, API) é assinada por quem a salvou.
  Uma mudança feita fora do programa, ou por quem não tinha o papel, não tem assinatura válida.
- **Mudança sensível pede conferência.** Quando um colega muda o que decide onde o fluxo lê ou grava (o
  destino de uma conexão, o endereço de uma API, uma consulta), quem usa confere a mudança antes de executar.
- **O que não confere não executa.** Fluxo, versão ou lista de membros com assinatura ausente ou inválida
  abre em modo protegido, com o motivo, e nada dele executa. Agendamentos executam só a versão oficial com
  assinatura válida.
- **Honestidade sobre o limite.** A permissão que de fato impede gravar é a da própria pasta, definida no
  sistema de arquivos. O programa lê essa permissão e se adapta, mas não promete impedir o que só a pasta
  pode impedir: ele garante detectar e recusar, não bloquear quem tem acesso de escrita.
- **Nada se perde.** Gravações concorrentes e sincronização atrasada nunca sobrescrevem trabalho em silêncio:
  as duas versões ficam guardadas e a pessoa é avisada.
