# Tarefas da spec 047 (versão 0.9.4)

## Marco 1 — Espaço, identidade e biblioteca

- [x] T01 Simulador de sincronização nos testes: atraso, conflito no padrão do OneDrive, trava temporária (base de CA-05, CA-08)
- [x] T02 Identidade: nome de exibição, chave Ed25519 no cofre da marca (identidades separadas por marca), usuário de teste (RF-4704)
- [x] T03 Espaços configurados: criar, entrar, sair, detecção de escrita na pasta (RF-4701, RF-4716)
- [x] T04 Repositório do espaço: listar, abrir, salvar, mover e copiar fluxos; só arquivos do espaço (RF-4703, RF-4705)
- [x] T05 Biblioteca com abas, que só aparecem com algum espaço; garantia do opcional (RF-4702, RF-4703, CA-01)

## Marco 2 — Papéis e assinaturas

- [x] T06 Assinatura e conferência de versões e da versão de trabalho, com motivo legível (RF-4714, RF-4715)
- [x] T07 Lista de membros assinada, contador de versão, pedidos de entrada, papéis (RF-4711..4713)
- [x] T08 Diálogo de membros: convidar, aceitar, mudar papel, aviso de um só administrador, ajuda das camadas (RF-4712, RF-4717, RF-4718)
- [x] T09 Espaço e fluxo protegidos quando algo não confere (RF-4713, RF-4715, CA-03, CA-04)

## Marco 3 — Quem está editando e modo só leitura

- [ ] T10 Marcas de edição: criar, renovar, soltar, expirar com folga para a sincronização (RF-4721, RF-4723)
- [ ] T11 Modo só leitura no store e na interface; Leitor e pasta sem escrita usam o mesmo modo (RF-4722, RF-4716)
- [ ] T12 Quem está editando na biblioteca; diálogo Abrir só para ver / Editar mesmo assim (RF-4721, RF-4724, CA-05)

## Marco 4 — O que mudou, confiança por diferença, conflito

- [ ] T13 Versões com autor na pasta do espaço; faixa "Atualizado por"; Recarregar (RF-4731..4733)
- [ ] T14 Confiança por diferença: partes sensíveis desde a última versão confiada; Conferir e confiar (RF-4741, RF-4742, CA-06)
- [ ] T15 Conflito por base: nada sobrescrito, as duas versões guardadas, aviso (RF-4761, CA-08)
- [ ] T16 Cópias de conflito da sincronização viram versões; arquivo preso: novas tentativas e envio adiado (RF-4762, RF-4763)

## Marco 5 — Versão oficial e agendamentos

- [ ] T17 Publicar como oficial (Publicador), selo na biblioteca (RF-4751)
- [ ] T18 Agendamento de fluxo do espaço roda só a oficial assinada; motivo no histórico (RF-4752, CA-07)
- [ ] T19 Agendamentos visíveis ao time; Assumir este agendamento (RF-4753, CA-07)

## Marco 6 — Conferências e publicação

- [ ] T20 conferir_tela.py com dois servidores (Ana e Bruno); Docker com Syncthing e Samba; roteiro manual OneDrive/SharePoint (CA-02..CA-09)
- [ ] T21 Capítulo Trabalhar em equipe no guia e no Manual, prints das duas marcas (todos, geração completa), README, versão 0.9.4, instaladores, publicar (RF-4771)
