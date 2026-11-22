# Simular a pasta do espaço da equipe (spec 047)

O espaço da equipe é uma pasta comum: rede (Samba ou Windows), OneDrive ou SharePoint sincronizado. Esta pasta tem três
formas de conferir o comportamento com dois computadores, da mais rápida à mais real.

| Forma | O que exercita | Como |
|-------|----------------|------|
| Simulador nos testes | atraso, conflito, arquivo preso (determinístico) | `uv run pytest tests/test_sync_sim.py tests/test_team_versions.py` |
| Docker + Syncthing | sincronização de verdade entre duas cópias, com conflito | `uv run python scripts/sincronizacao/simular.py` |
| OneDrive / SharePoint | o cliente da Microsoft, com contas reais | roteiro manual abaixo |

## Docker + Syncthing (automático)

Pré-requisito: Docker Desktop aberto.

```powershell
uv run python scripts/sincronizacao/simular.py            # sobe, confere e derruba tudo
uv run python scripts/sincronizacao/simular.py --manter   # deixa os Syncthing de pé
```

O script sobe dois Syncthing (`noteana` e `notebruno`, em `pastas/ana` e `pastas/bruno`), pareia os dois, abre dois
servidores do programa (Ana na porta 8796, Bruno na 8797) e confere:

1. Ana cria o espaço e salva um fluxo; a pasta chega ao Bruno;
2. Bruno pede para entrar; Ana aceita como Editor; a lista assinada chega e o Bruno vira Editor;
3. com o Syncthing do Bruno pausado, os dois salvam o mesmo fluxo; ao retomar, a cópia de conflito
   (`*.sync-conflict-*`) vira versão nos dois computadores, e nenhuma das duas versões se perde;
4. com a sincronização atrasada, os dois comentam ao mesmo tempo: os comentários chegam aos dois lados e não
   aparece cópia de conflito (cada comentário é um arquivo próprio); a constante que a Ana compartilha chega ao
   Bruno, assinada por ela.

Com `--manter`, a interface de cada Syncthing fica em http://127.0.0.1:8384 (Ana) e http://127.0.0.1:8385 (Bruno).
Para limpar depois: `docker compose down -v` nesta pasta.

## Samba (pasta de rede)

```powershell
docker compose --profile samba up -d samba
```

Compartilha `pastas/samba` como `//127.0.0.1/espaco` na porta **1445** (usuário `equipe`, senha `somente-teste`, só
para teste). O Windows não monta compartilhamento fora da porta 445; monte de um Linux, do WSL ou de uma VM:

```bash
sudo mount -t cifs //127.0.0.1/espaco /mnt/espaco -o port=1445,username=equipe,password=somente-teste,uid=$(id -u)
```

Na pasta de rede não há cópias locais: todos gravam no mesmo arquivo. O que vale conferir é a marca de quem está
editando, o modo só leitura e o aviso de conflito pela base (Ana e Bruno com o mesmo fluxo aberto; o segundo a salvar
é avisado e as duas versões ficam em Versões anteriores).

## OneDrive e SharePoint (manual)

Precisa de dois computadores (ou duas contas do Windows) com o mesmo programa instalado e uma pasta compartilhada.

1. **Preparar.** No SharePoint (ou OneDrive), crie uma pasta e compartilhe com a outra pessoa com permissão de editar.
   Nos dois computadores, use *Sincronizar* (ou *Adicionar atalho a Meus arquivos*) para a pasta aparecer no
   Explorador de Arquivos.
2. **Criar e entrar.** Ana: Arquivo › Espaços da equipe › Criar espaço, apontando para a pasta. Bruno: Entrar num
   espaço, na mesma pasta (o caminho local pode ser diferente). Ana aceita o pedido em Membros.
   *Esperado:* o Bruno passa de "Pedido enviado" ao papel escolhido assim que a lista chega.
3. **Quem está editando.** Ana abre um fluxo do espaço. Bruno abre o mesmo fluxo.
   *Esperado:* "Ana está editando desde…"; Abrir só para ver; nada muda no fluxo do Bruno.
4. **Atualizado por.** Ana muda um filtro e salva; Bruno fecha e abre o fluxo.
   *Esperado:* "Atualizado por Ana · Ver o que mudou", sem pedir conferência.
5. **Parte sensível.** Ana troca a pasta de destino de um Output e salva; Bruno abre.
   *Esperado:* a faixa pede Conferir e confiar só para essa caixa.
6. **Conflito.** Pause a sincronização do OneDrive no computador do Bruno (ícone da nuvem › Pausar). Os dois salvam o
   mesmo fluxo. Retome.
   *Esperado:* o OneDrive cria `fluxo-NOMEDOCOMPUTADOR.prodata.json`; ao abrir a biblioteca do espaço, a cópia some
   da pasta e aparece em Versões anteriores ("Cópia da sincronização"). Nada se perde.
7. **Arquivo preso.** Salve um fluxo grande logo depois de outra pessoa salvar (o OneDrive segura o arquivo enquanto
   envia). *Esperado:* o Salvar espera alguns segundos; se não der, "Salvo neste computador; o envio para o espaço
   fica para depois", e o envio acontece sozinho em seguida.
8. **Versão oficial e agendamento.** Um Publicador usa Publicar como oficial; agende o fluxo (Arquivo › Agendar).
   No outro computador, Espaços da equipe › Agendamentos mostra o agendamento; um Publicador pode Assumir.
   *Esperado:* o computador anterior mostra "Assumido por…" e deixa de rodar.

Anote, para cada passo, o tempo que a sincronização levou: é o número que interessa para a orientação da TI.
