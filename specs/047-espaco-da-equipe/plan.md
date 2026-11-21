# Plano da spec 047

Constituição 1.6.0: princípio IV (pasta do espaço) e princípio VIII (colaboração opcional e verificável).

## Marcos (cada um testado e conferido antes do próximo)

1. **Espaço, identidade e biblioteca** (RF-4701..4705) — mais o simulador de sincronização, base de todos os testes.
2. **Papéis e assinaturas** (RF-4711..4718).
3. **Quem está editando e modo só leitura** (RF-4721..4724).
4. **Versões com autor, confiança por diferença, conflito** (RF-4731..4733, RF-4741..4742, RF-4761..4763).
5. **Versão oficial e agendamentos do time** (RF-4751..4753).
6. **Documentação e publicação** (RF-4771).

## Formato da pasta do espaço

Tudo em JSON legível, nomes fixos, sem dados das fontes. Uma pasta de controle `_equipe/`, cujo `espaco.json`
registra a marca dona do espaço: só a mesma marca entra (RF-4701); a outra mostra de quem é o espaço.

```
<pasta escolhida>/
  _equipe/
    espaco.json                     {"formato": 1, "id", "nome", "marca", "criado_em"}
    membros.json                    lista assinada (ver abaixo)
    pedidos/<usuario>.json          pedido de entrada: nome, chave pública, quando
    edicao/<fluxo>.json             marca de edição: usuario, nome, maquina, desde, renovado_em
    versoes/<fluxo>/<ts>-<origem>-<usuario>.json      versão (fluxo sem amostra)
    versoes/<fluxo>/<ts>-<origem>-<usuario>.json.sig  assinatura da versão
    oficiais/<fluxo>.json           {"versao", "assinatura do publicador"}
    agendamentos/<id>.json          estado publicado de um agendamento (sem caminhos locais)
  <fluxo>.prodata.json              versão de trabalho (o que a biblioteca abre)
  <fluxo>.prodata.json.sig          assinatura da versão de trabalho
```

- Os fluxos ficam na raiz da pasta, como arquivos `.prodata.json` comuns: quem abrir a pasta no Explorer reconhece,
  e o "Abrir arquivo" de hoje continua funcionando (abrindo protegido, como qualquer arquivo de fora).
- Gravação atômica (`.tmp` + `os.replace`), com novas tentativas curtas quando a sincronização segura o arquivo
  (RF-4763).
- `resolve_inside` confinado à pasta do espaço para todo caminho montado a partir de ids (fluxo, usuário, versão).

## Identidade e chaves (`prodata/team/identity.py`)

- Ed25519 com a biblioteca `cryptography` (dependência nova, só para assinar e conferir).
- Chave privada no cofre do Windows, no **serviço da própria marca** (o mesmo `vault_service` das senhas de banco,
  com uma chave `equipe:identidade`): Desata e PRO.DATA têm identidades separadas, mesmo no mesmo computador
  (RF-4704). Nunca em arquivo, fluxo ou log.
- Identidade = `{usuario: usuário do Windows, nome: nome de exibição, chave_publica: base64}`; `usuario` validado
  por padrão restrito (letras, dígitos, `._-`).
- Só para testes: `PRODATA_USUARIO` e um cofre em memória permitem dois "usuários" no mesmo computador.

## Assinaturas (`prodata/team/signing.py`)

- O que se assina é o **conteúdo canônico**: JSON com chaves ordenadas e sem `samples` (o mesmo critério da
  impressão digital da abertura protegida), mais o contexto (`espaco`, `fluxo`, `tipo`), para uma assinatura não
  servir em outro espaço ou outro fluxo.
- Arquivo `.sig`: `{"formato": 1, "tipo": "versao|oficial|membros", "autor", "chave_publica", "sha256", "assinatura",
  "quando"}`.
- **Conferência** de uma versão: assinatura válida **e** autor na lista de membros vigente com papel ≥ Editor
  (≥ Publicador para `oficial`). Devolve um motivo legível quando falha (RF-4715).
- **Membros** (`membros.json`): `{"formato", "versao" (contador), "membros": [{usuario, nome, chave_publica, papel}],
  "assinada_por", "assinatura"}`. Válida se assinada por alguém que é administrador **na versão anterior aceita**
  (guardada localmente) ou, na criação, pelo próprio criador. Versão menor que a já aceita = recusada (impede voltar
  a uma lista antiga). Lista recusada → espaço protegido (RF-4713).

## Serviço do espaço (`prodata/team/`)

- `workspaces.py` — espaços configurados neste computador (`storage/espacos.json`: id, nome, caminho), entrar,
  criar, sair; detecção de escrita na pasta (arquivo de teste em `_equipe/`) (RF-4716).
- `repository.py` — fluxos do espaço: listar (com quem está editando e quem salvou por último), ler com conferência,
  salvar (assina, grava versão, grava a de trabalho), detecção de conflito por `base_sha256` (RF-4761), cópias de
  conflito da sincronização (RF-4762: padrões `nome-COMPUTADOR.prodata.json`, `nome (1).prodata.json`,
  `.sync-conflict-`).
- `locks.py` — marca de edição: criar, renovar (a cada 30 s), soltar, expirar (sem renovação há mais de 3 min,
  folga para o atraso de sincronização) (RF-4721..4723).
- `trust_diff.py` — confiança por diferença: compara o `summary()` de `services/trust.py` entre a última versão
  confiada/executada (guardada localmente por fluxo) e a nova; devolve só as partes sensíveis novas ou alteradas,
  com autor e data (RF-4741, RF-4742).
- `versions.py` — histórico dos fluxos do espaço (`SpaceVersions`), no formato do `VersionStore` (spec 046) mais o autor,
  a assinatura e as origens `conflito` e `copia`; fica em
  `_equipe/versoes/`. `local_state.py` guarda neste computador o que cada pessoa viu e conferiu e os envios adiados.
- Agendamentos (spec 044): um agendamento de fluxo do espaço guarda `espaco_id` + `fluxo`; o CLI em
  `--agendamento` carrega a versão **oficial**, confere a assinatura de Publicador e só então executa (RF-4752);
  publica o estado em `_equipe/agendamentos/` (RF-4753). "Assumir" cria a tarefa local e marca o anterior como
  substituído.

## API (`api/routes/team.py`)

`/api/espacos` (listar, criar, entrar, sair), `/api/espacos/{id}/membros` (listar, aceitar pedido, mudar papel,
remover), `/api/espacos/{id}/fluxos` (listar, abrir, salvar com `base_sha256`, mover/copiar), `/edicao`
(marcar, renovar, soltar), `/versoes`, `/oficial` (publicar), `/conferencia` (partes sensíveis a confiar),
`/agendamentos`. Respostas nunca trazem a chave privada; a pública só aparece em membros.

## Tela

- `team_spaces.js` — diálogo Espaços da equipe (criar, entrar, membros, papéis, pedidos, ajuda das camadas).
- Biblioteca com abas por espaço (`main.js`/biblioteca) — **só aparecem com algum espaço** (RF-4702).
- `readonly_mode.js` — modo só leitura: o store recusa `mutate` e a interface desativa edição, com a faixa e o motivo.
- Faixas no topo do canvas: "editando", "atualizado por", "recarregar", "conferir e confiar", "conflito".
- Selo de oficial e de quem edita na biblioteca; Versões anteriores com autor.

## Testes

- **Simulador de sincronização** (`tests/sync_sim.py`): duas pastas espelhadas com atraso configurável, regra de
  conflito do OneDrive (renomeia a cópia local com o nome do computador) e trava temporária de arquivo. Determinístico:
  os cenários de CA-05, CA-08 viram testes no CI.
- Unidade: identidade, assinatura e conferência (inclusive adulteração de membros, versão antiga da lista, assinatura
  de outro espaço), marcas de edição e expiração, confiança por diferença, conflito.
- **Garantia do opcional** (CA-01): sem espaço, o catálogo de menus e os arquivos gravados numa sessão são iguais aos
  de referência.
- Tela: `scripts/conferir_tela.py` ganha a conferência `equipe`, com **dois servidores** (Ana e Bruno, cofres em
  memória) apontando para a mesma pasta.
- Docker (`scripts/sincronizacao/`): Syncthing (duas pastas sincronizadas de verdade) e Samba (pasta de rede), para
  conferir antes de publicar. Roteiro manual de 15 minutos com OneDrive/SharePoint reais.

## Riscos

- **Atraso de sincronização** maior que o prazo da marca de edição: a marca é aviso, não trava; o conflito é
  sempre detectado pelo `base_sha256`, e nada é sobrescrito.
- **Chave perdida** (computador formatado sem o cofre): a pessoa entra de novo como pedido e um administrador aceita;
  por isso a recomendação de dois administradores (RF-4717).
- **Relógios diferentes** entre computadores: a ordem das versões usa o contador da lista e a data só para exibir;
  a expiração da marca usa a data de modificação do arquivo vista localmente.
- **Desempenho em pasta de rede lenta**: listar a biblioteca do espaço lê só `espaco.json`, as marcas e os
  cabeçalhos; os fluxos inteiros só ao abrir.
