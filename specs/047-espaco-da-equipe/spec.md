# Spec 047: espaço da equipe — trabalhar junto numa pasta compartilhada, com papéis e assinaturas

Status: Em revisão · Versão 0.9.4 · Criada: 2026-11-21 · Constituição 1.6.0 (princípios IV e VIII)

## Contexto

O Desata hoje é de uma pessoa, num computador. Quem trabalha em equipe troca fluxos por e-mail ou por uma pasta
de rede, sem saber quem está mexendo, o que mudou ou se o arquivo foi alterado por fora. Os concorrentes resolvem
isso com servidor e nuvem próprios (Alteryx Server, KNIME Business Hub, Dataiku), caros e dependentes da TI.

Toda empresa já tem uma pasta compartilhada: pasta de rede, OneDrive ou SharePoint. Esta spec faz da pasta da
equipe o lugar do trabalho em conjunto, sem servidor e sem contas: o **espaço da equipe**.

Três premissas guiam tudo:

- **Opcional.** Quem não configura um espaço não vê nada novo: a tela, o comportamento e os arquivos ficam iguais
  aos de hoje (constituição, princípio VIII).
- **Sincronização não é confiável.** OneDrive e SharePoint sincronizam com atraso, criam cópias de conflito e
  seguram arquivos enquanto enviam. Nada pode depender de a sincronização ser rápida ou de um aviso ser respeitado.
- **Detectar e recusar, não fingir bloquear.** Numa pasta compartilhada, quem tem acesso de escrita pode mexer nos
  arquivos por fora. O que impede de verdade é a permissão da pasta; o programa garante que nada adulterado execute
  sem aparecer, assinando o que dá permissão.

A spec 048 (0.9.5) completa a equipe: fontes e conexões da equipe, comentários nas caixas e o conflito juntado
caixa por caixa.

## Histórias de usuário

- Como analista de uma equipe, quero ver os fluxos do time num lugar só, saber quem está editando cada um e o que
  mudou desde a última vez, sem depender da TI para instalar nada.
- Como quem usa o Desata sozinho, quero continuar exatamente como hoje, sem telas nem avisos de equipe.
- Como coordenador, quero dizer quem só consulta, quem edita e quem pode publicar a versão que alimenta os
  relatórios, e ter certeza de que ninguém contorna isso mexendo nos arquivos.
- Como quem agenda o fechamento das 6h, quero que só rode a versão oficial, e que o time veja onde e quando roda.
- Como quem edita junto com um colega pelo OneDrive, quero nunca perder o que salvei, mesmo que nós dois salvemos
  ao mesmo tempo.

## Requisitos

### Espaço da equipe (opcional)

| ID | Requisito |
|----|-----------|
| RF-4701 | **Arquivo › Espaços da equipe…** permite criar um espaço numa pasta escolhida (pasta de rede, OneDrive ou SharePoint sincronizado) ou entrar num espaço que já existe nela. O espaço tem um nome. Uma pessoa pode estar em mais de um espaço. **Cada espaço pertence à marca que o criou**: apontar a outra marca para a mesma pasta mostra "Este espaço é do Desata" (ou do PRO.DATA) e não entra nele. Um arquivo de fluxo avulso continua abrindo nas duas marcas, em modo protegido, como hoje. |
| RF-4702 | **Sem espaço, nada muda.** Enquanto a pessoa não estiver em nenhum espaço, nenhum item, aba, selo ou aviso de equipe aparece além do próprio menu Espaços da equipe, e nenhum arquivo é gravado fora da pasta de dados. Um teste automatizado compara a tela e os arquivos com os de antes. |
| RF-4703 | **Biblioteca com abas:** com algum espaço, Abrir da biblioteca mostra **Meus fluxos** (como hoje) e uma aba por espaço. Fluxos de Meus fluxos continuam funcionando como hoje. **Salvar no espaço…** e **Mover para o espaço…** levam um fluxo para lá; **Fazer uma cópia em Meus fluxos** traz uma cópia de volta. |
| RF-4704 | **Identidade sem login:** na primeira vez, o programa pergunta o nome de exibição (sugerindo o usuário do Windows). A identidade é o usuário do Windows com uma chave pessoal gerada no computador; a parte secreta fica no cofre do Windows. **Cada marca tem a sua identidade**: quem usa Desata e PRO.DATA no mesmo computador é, para cada uma, uma pessoa separada, com chave e papéis próprios. |
| RF-4705 | **O espaço guarda só o que é do espaço:** fluxos, versões, assinaturas, membros, marcas de edição e estado dos agendamentos. Nunca dados das fontes, resultados de execução, amostras dos dados ou senhas. Os resultados guardados (cache) continuam em cada computador. |

### Papéis e assinaturas

| ID | Requisito |
|----|-----------|
| RF-4711 | **Papéis:** **Leitor** (abre, executa no próprio computador), **Editor** (também salva versões), **Publicador** (também marca a versão oficial) e **Administrador** (também gerencia membros e papéis). Quem cria o espaço é o primeiro administrador. |
| RF-4712 | **Membros:** o administrador convida pelo nome; quem entra no espaço pela primeira vez aparece como **pedido de entrada** até um administrador aceitar e escolher o papel. A tela mostra pessoas e o que cada uma pode fazer; a palavra "chave" não aparece no uso normal. |
| RF-4713 | **Lista de membros assinada:** a lista de membros e papéis só vale com a assinatura de um administrador da própria lista. Uma lista alterada fora do programa, ou assinada por quem não é administrador, é recusada: o espaço abre em modo protegido, com o motivo, até um administrador conferir. |
| RF-4714 | **Versões assinadas:** cada versão salva no espaço é assinada por quem salvou. O programa confere a assinatura e se a pessoa tinha papel de Editor (ou maior) quando salvou. |
| RF-4715 | **O que não confere não executa:** fluxo do espaço sem assinatura válida (alterado fora do programa, salvo por quem não podia ou por alguém fora da lista) abre em modo protegido com o motivo ("Este fluxo foi alterado fora do Desata", "Salvo por alguém sem permissão de edição") e nada dele executa. |
| RF-4716 | **A permissão da pasta manda:** o programa confere se pode gravar na pasta do espaço. Sem permissão de escrita, o espaço abre só para leitura, com um aviso que explica de onde vem a limitação, em vez de dar erro ao salvar. O diálogo do espaço mostra como dar acesso só de leitura na pasta de rede, no OneDrive e no SharePoint. |
| RF-4717 | **Mais de um administrador:** o programa recomenda ter pelo menos dois administradores e avisa quando há só um, porque um espaço sem administrador não aceita mudanças de papéis. Um administrador pode passar o papel a outra pessoa. |
| RF-4718 | **Honestidade:** a ajuda do espaço diz com clareza o que cada camada garante: a pasta impede quem não tem escrita; as assinaturas impedem que algo adulterado execute sem aparecer; quem tem escrita na pasta ainda pode apagar arquivos (o histórico de versões do OneDrive e do SharePoint ajuda a recuperar). |

### Quem está editando

| ID | Requisito |
|----|-----------|
| RF-4721 | Abrir para editar um fluxo do espaço deixa uma **marca de edição** com o nome da pessoa. Quem abrir em seguida vê **"Ana está editando desde 10:32"** e pode **Abrir só para ver** ou **Editar mesmo assim**, que avisa que as duas versões podem divergir. |
| RF-4722 | **Modo só leitura:** um fluxo aberto só para ver mostra os dados e executa normalmente, mas não deixa mudar nada nem salvar, com uma faixa que diz por quê e o botão **Editar** quando a edição ficar livre. O mesmo modo vale para o Leitor e para a pasta sem permissão de escrita. |
| RF-4723 | A marca se renova sozinha enquanto o fluxo está aberto e expira quando a pessoa fecha o fluxo, fecha o programa ou fica sem renovar por tempo suficiente para cobrir o atraso de sincronização. Nunca fica presa para sempre. |
| RF-4724 | Na biblioteca do espaço, cada fluxo mostra quem está editando agora (inicial e nome ao passar o mouse). |

### O que mudou (versões com autor)

| ID | Requisito |
|----|-----------|
| RF-4731 | As versões anteriores (spec 046) de um fluxo do espaço ficam na pasta do espaço, com o **autor**: "Bruno, ontem às 17:10 · 2 caixas novas, 1 alterada". Todos do espaço veem e restauram (quem pode editar). |
| RF-4732 | Ao abrir um fluxo que outra pessoa mudou desde a última vez que você o abriu, uma faixa discreta diz **"Atualizado por Bruno há 20 min · Ver o que mudou"**, que abre a prévia de versões com as caixas novas e alteradas marcadas. |
| RF-4733 | **Recarregar:** com o fluxo aberto, se um colega salvar uma versão nova (chegada pela sincronização), a faixa avisa e oferece **Recarregar**; com mudanças suas ainda não salvas, nada é trocado sem a pessoa pedir. |

### Confiança por diferença

| ID | Requisito |
|----|-----------|
| RF-4741 | Um fluxo do espaço com assinatura válida de um Editor abre liberado. Se, desde a última versão que você executou ou confiou, ele ganhou ou mudou **partes sensíveis** (onde grava arquivos, consultas a banco, APIs, caixa SQL, fórmulas que leem arquivos, subfluxos), o programa mostra **só essas mudanças** e pede **Conferir e confiar** antes de executar. Mudanças comuns (filtros, fórmulas, layout) não pedem nada. |
| RF-4742 | A conferência mostra cada parte sensível nova ou alterada com quem mudou e quando, no mesmo formato da abertura protegida de hoje (spec 028). |

### Versão oficial e agendamentos

| ID | Requisito |
|----|-----------|
| RF-4751 | **Publicar como oficial:** um Publicador marca uma versão como **oficial**, assinada por ele. A biblioteca mostra qual versão é a oficial e quem publicou; a versão de trabalho pode estar à frente dela. |
| RF-4752 | **Agendamento roda só a oficial:** agendar um fluxo do espaço agenda a versão oficial. Na hora de rodar, o programa confere a assinatura do Publicador; sem versão oficial válida, não executa e registra o motivo no histórico e no aviso de falha agendada. |
| RF-4753 | **Agendamentos visíveis para o time:** o espaço mostra os agendamentos de seus fluxos, em que computador e de quem rodam, a próxima e a última execução (ou o erro). **Assumir este agendamento** cria a tarefa no seu computador (quem tem papel de Publicador) e passa a mostrar você como responsável; o agendamento antigo aparece como "substituído" no computador anterior. |

### Nunca perder trabalho

| ID | Requisito |
|----|-----------|
| RF-4761 | **Conflito detectado:** se o fluxo mudou na pasta desde que você o abriu (outra pessoa salvou, mesmo sem a marca de edição ter chegado), o Salvar não sobrescreve: guarda a sua versão como versão do fluxo, mantém a do colega e avisa **"Bruno salvou enquanto você editava: as duas versões estão em Versões anteriores"**, com **Ver as duas**. Juntar caixa por caixa fica para a spec 048. |
| RF-4762 | **Cópias de conflito da sincronização:** cópias criadas pelo OneDrive ou SharePoint (nome do arquivo com o nome do computador, por exemplo) são reconhecidas e oferecidas como versões, em vez de virarem fluxos soltos na biblioteca. |
| RF-4763 | **Arquivo preso pela sincronização:** se a pasta segurar o arquivo na hora de gravar, o programa tenta de novo por alguns segundos e, se não conseguir, guarda a versão no computador e avisa que o envio fica para depois, sem perder nada. |

### Documentação

| ID | Requisito |
|----|-----------|
| RF-4771 | Guia e Manual com um capítulo **Trabalhar em equipe**: criar e entrar num espaço, papéis, quem está editando, o que mudou, versão oficial, agendamentos do time, conflitos e o que cada camada de segurança garante. Esquemas visuais e prints nos dois temas e nas duas marcas, com dois "usuários" de exemplo. README, versão 0.9.4, guias e instaladores nas duas marcas. |

## Fora do escopo (spec 048, versão 0.9.5)

- Fontes, constantes e conexões da equipe (hoje, um colega sem a fonte vê "Faltam neste computador").
- Comentários nas caixas.
- Juntar duas versões em conflito caixa por caixa.
- Recomendações de limpeza a partir do perfil de dados e script de benchmark.

Fora de qualquer versão por enquanto: servidor ou nuvem próprios; edição simultânea em tempo real; Mac e Linux.

## Critérios de aceite

| ID | Critério | Requisitos |
|----|----------|------------|
| CA-01 | Sem nenhum espaço configurado, a tela, os menus (exceto Espaços da equipe) e os arquivos gravados numa sessão típica são iguais aos da 0.9.3. | RF-4702 |
| CA-02 | Ana cria um espaço numa pasta, convida Bruno como Editor e Carla como Leitora; Bruno vê o fluxo da Ana na aba do espaço; Carla abre só para ver e não consegue salvar. | RF-4701, RF-4703, RF-4711, RF-4712, RF-4722 |
| CA-03 | Bruno edita `membros.json` à mão para virar administrador: todos os computadores recusam a lista e o espaço abre protegido. | RF-4713 |
| CA-04 | Alguém troca o arquivo de um fluxo do espaço por fora: ele abre protegido com "alterado fora do Desata" e nada executa; restaurar a última versão assinada volta ao normal. | RF-4714, RF-4715 |
| CA-05 | Ana abre um fluxo para editar; Bruno vê "Ana está editando" e abre só para ver; Ana fecha o programa sem fechar o fluxo e, depois do prazo, a marca expira. | RF-4721..4723 |
| CA-06 | Bruno muda um filtro e salva; Ana abre e vê "Atualizado por Bruno · Ver o que mudou", sem conferência. Bruno troca a pasta de destino do Output; Ana precisa Conferir e confiar só essa mudança antes de executar. | RF-4731, RF-4732, RF-4741, RF-4742 |
| CA-07 | O agendamento de um fluxo do espaço roda a versão oficial; com a oficial adulterada, não roda e o histórico diz por quê; Bruno assume o agendamento da Ana e o espaço mostra Bruno como responsável. | RF-4751..4753 |
| CA-08 | Com o simulador de sincronização atrasando 30 s, Ana e Bruno salvam o mesmo fluxo: nenhum dos dois perde a versão, e quem salvou por último é avisado. Com o arquivo preso por alguns segundos, o Salvar espera e conclui. | RF-4761..4763 |
| CA-09 | Sem permissão de escrita na pasta, o espaço abre só para leitura, com o aviso explicando a pasta. | RF-4716 |
