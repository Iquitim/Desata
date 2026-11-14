# Spec 036: marca 100% configurável

Status: Proposta · Criada: 2026-11-14

## Contexto

O PRO.DATA nasceu com a identidade do Grupo Protege (spec 011). Ele ainda vai ser apresentado à diretoria e pode não ser
adotado. O projeto deve poder seguir com outra identidade visual e outro nome, **Desata**, sem duplicar o código: um produto só,
gerado com a marca escolhida.

Hoje a marca está espalhada: 63 menções a "Protege" e 179 a "PRO.DATA" em 24 arquivos de código e empacotamento, cores
fixas em `brand.css` e em `make_icon.py`, logotipos em `web/brand` e `packaging/brand`, e o nome no título da janela, no
instalador, no cabeçalho e no logo do dashboard (também no HTML exportado), nos dados de exemplo, no Manual, no guia, no
PDF e no contexto para IA.

## Objetivo

Trocar a marca muda **tudo o que uma pessoa vê** e nada do que um fluxo guarda. A versão Protege gerada pela marca
`protege` fica igual à 0.7.7 publicada.

## Três camadas de nome

| Camada | Exemplos | Regra |
|---|---|---|
| O que as pessoas veem | nome do produto, organização, logo, cores, fontes, instalador, guia, Manual, PDF, releases | Vem da marca. 100% configurável. |
| Onde o programa guarda coisas neste computador | pasta de dados, pasta de instalação, identificador do instalador, serviço no cofre do Windows | Vem da marca, para duas marcas conviverem no mesmo computador. |
| Identificadores técnicos | pacote `prodata`, variáveis `PRODATA_*`, arquivo `.prodata.json`, prefixos `sql:`, `folder:` | Iguais em todas as marcas, para um fluxo salvo numa abrir na outra. |

## Histórias

- Como dono do projeto, quero gerar o programa com a minha marca, com outro nome, sem manter dois códigos.
- Como dono do projeto, quero gerar de novo a versão Protege exatamente como foi apresentada.
- Como quem usa o programa, quero que um fluxo feito numa marca abra na outra.
- Como quem troca de uma marca para outra no mesmo computador, quero levar as minhas fontes e fluxos sem refazer nada.

## Requisitos

### Pacote de marca

| ID | Requisito |
|---|---|
| RF-3601 | Cada marca é uma pasta em `src/prodata/marcas/<id>/` com um arquivo `marca.toml` e os arquivos visuais. O id é curto, minúsculo e sem espaço (`protege`, `neutra`). |
| RF-3602 | `marca.toml` define: nome do produto (`PRO.DATA`, `Desata`), nome curto para arquivos (`PRO.DATA`, `Desata`, sem espaço nem acento), organização (`Grupo Protege`, pode ser vazia), linha de apoio opcional, site opcional, a paleta (RF-3604), fontes do texto e do código, e o texto do rodapé dos dashboards exportados. |
| RF-3603 | Arquivos visuais da marca: logo para fundo claro e para fundo escuro (SVG), ícone do programa (PNG quadrado de 1024 px, de onde saem o `.ico` e o ícone da janela) e, opcionais, as fontes (WOFF2) com a licença delas. Logo que falte usa o nome do produto escrito, em vez de quebrar. |
| RF-3604 | A paleta tem papéis definidos, para o tema claro e o escuro: fundo da barra superior; cor de destaque (botões principais, abas ativas, seleção, foco e realces) com a versão clara dela; texto sobre o destaque; cor da organização no cabeçalho do dashboard; e as 8 cores das séries dos gráficos. A arte do instalador sai da mesma paleta. |
| RF-3607 | Ficam fora da marca, iguais em todas: as cores de situação (ok, aviso, erro) e as cores das famílias de ferramentas no canvas, por clareza e acessibilidade. A marca pode trazer os neutros (fundo, superfície, bordas e texto, os quatro juntos, por tema); os tons intermediários saem deles, e os textos secundários são ajustados até 4,5:1. Sem neutros, valem os do tema. |
| RF-3608 | A marca pode ter uma fonte de títulos (títulos, nome na barra, cabeçalhos do dashboard e do guia), um slogan (tela de abertura) e um gradiente de 2 ou 3 cores para os fundos de identidade (tela de abertura, telas do instalador e capa do guia). O texto branco sobre cada cor do gradiente precisa de 4,5:1. Sem eles, a fonte dos títulos é a do texto e o fundo de identidade é a barra escurecendo, como na 0.7.7. |
| RF-3609 | No tema escuro, os botões de ação usam o botão principal da marca; no claro, o destaque. |
| RF-3605 | O pacote é conferido ao gerar: campo obrigatório faltando, cor inválida, arquivo que não existe, nome curto com caractere inválido, texto sobre o destaque, sobre o botão principal ou sobre a barra superior sem contraste mínimo de 4,5:1 (WCAG AA) param o build com uma mensagem que diz o que corrigir, nos dois temas. Cor de série de gráfico com contraste abaixo de 3:1 com o fundo gera um aviso, sem parar: paletas de gráfico validadas para daltonismo podem ter tons claros de propósito. |
| RF-3606 | Ficam no repositório as marcas `protege`, que reproduz a 0.7.7, `neutra`, sem nome de empresa, com cores e logo genéricos, para testar a troca de ponta a ponta, e `desata`, com o logo e a paleta do dono do projeto (etapa 2). |

### Onde a marca aparece

| ID | Requisito |
|---|---|
| RF-3610 | Programa: título da janela e da página, ícone da janela e da aba, logo, nome e organização na barra superior, tela de abertura, mensagens que citam o nome do produto, cores e fontes. |
| RF-3611 | Dashboard: logo e organização no cabeçalho da tela e do HTML exportado, o item "Logo de <organização>" no menu de inserir imagem e o rodapé. Sem organização, o cabeçalho mostra só o nome do fluxo, e o item de logo usa o nome do produto. |
| RF-3612 | Instalador e executável: nome do programa, editora, versão, ícone, as telas do instalador, a pasta de instalação, o nome dos arquivos gerados (`<nome curto>-<versão>-setup.exe` e `-portable.zip`) e o nome do executável da linha de comando. |
| RF-3613 | Documentação: guia, Manual, PDF (`<nome curto>-Guia-do-Produto.pdf`), prints do guia e contexto para IA usam o nome e a marca escolhidos. O guia escreve o nome do produto por uma marcação, nunca o nome fixo. |
| RF-3614 | Os dados de exemplo que levam o logo usam o logo da marca. |
| RF-3615 | A linha de comando mostra o nome da marca em `--version` e nas mensagens. |

### Convivência e mudança de marca

| ID | Requisito |
|---|---|
| RF-3620 | Cada marca tem a sua pasta de dados (`%LOCALAPPDATA%\<nome curto>`), a sua pasta de instalação, o seu identificador de instalador e o seu serviço no cofre do Windows. Duas marcas instaladas no mesmo computador não se misturam. |
| RF-3621 | O identificador do instalador da marca `protege` continua o mesmo da 0.7.7, para atualizar a instalação existente em vez de criar outra. |
| RF-3622 | Na primeira abertura de uma marca, se a pasta de dados dela estiver vazia e existir a pasta de outra marca conhecida, o programa oferece trazer fontes, fluxos, organização e modelos de lá. Copiar, nunca mover: a pasta antiga fica intacta. Recusar não pergunta de novo. |
| RF-3623 | Na mesma oferta, o programa pergunta se pode copiar também as senhas e tokens do serviço da outra marca no cofre do Windows para o seu. A cópia acontece neste computador e neste usuário do Windows, nada sai da máquina, e só com a confirmação da pessoa. Se ela recusar, ou se uma senha não puder ser lida, a tela lista as conexões que precisam da senha de novo. |
| RF-3624 | Fluxos, modelos (`.modelo`) e arquivos exportados de uma marca abrem na outra sem aviso. |

### Gerar com uma marca

| ID | Requisito |
|---|---|
| RF-3630 | O build recebe a marca: `uv run python packaging/build.py --marca protege`. Sem a opção, usa a marca padrão do repositório, definida num lugar só. |
| RF-3631 | O programa em desenvolvimento escolhe a marca por `PRODATA_MARCA`. O programa instalado tem uma marca só, embutida no build: quem usa não troca a marca. |
| RF-3632 | O gerador de prints, o Manual, o PDF e o contexto para IA recebem a mesma opção `--marca`. |
| RF-3633 | A marca `protege` gera o mesmo programa da 0.7.7: os prints da marca `protege` comparados com os da 0.7.7 não mostram diferença além da versão. |

### Garantias

| ID | Requisito |
|---|---|
| RF-3640 | Um teste falha se "Protege", "Grupo Protege", um logotipo ou uma cor da marca aparecer escrito no código fora de `src/prodata/marcas/`. O nome "PRO.DATA" só aparece nos identificadores técnicos da tabela acima. |
| RF-3641 | Um teste gera a marca `neutra` e confere que nenhum texto visível, título, nome de arquivo ou metadado do executável cita a marca `protege`. |
| RF-3642 | Trocar de marca não muda o formato de nenhum arquivo salvo: os testes de fluxo, modelo e exportação passam com as duas marcas. |

### Guia

| ID | Requisito |
|---|---|
| RF-3650 | O README e `src/prodata/marcas/LEIA-ME.md` explicam como criar uma marca nova, com um exemplo de `marca.toml` e a lista dos arquivos visuais. O guia do produto não trata disso: é assunto de quem mantém o projeto. |

## Etapas

1. **Modularizar.** Tudo passa a ler a marca de `src/prodata/marcas/<id>/`. A marca `protege` gera o mesmo programa da 0.7.7 (RF-3633), e a `neutra` prova a troca de ponta a ponta. Nenhuma mudança visível para quem usa.
2. **Marca Desata.** O pacote `src/prodata/marcas/desata/` com o logo (SVG para fundo claro e escuro, ícone quadrado) e a paleta do dono do projeto, conferido pelo RF-3605.
3. **Padrão e publicação.** A marca padrão do repositório passa a ser decidida pelo dono, e a versão sai com a marca escolhida.

## Fora do escopo

- Renomear o repositório no GitHub ou criar outro. É uma ação no GitHub, feita à parte, com o nome decidido e o OK do dono.
- Trocar os identificadores técnicos (`prodata`, `PRODATA_*`, `.prodata.json`). Se um dia fizer sentido, é uma spec própria, com migração.
- Escolher a marca dentro do programa instalado.
- Desenhar a identidade visual da Desata: o logo e a paleta vêm prontos do dono do projeto e entram como mais uma pasta em `src/prodata/marcas/`.

## Decisões

1. **Nome da marca pessoal:** Desata (nome curto para arquivos: `Desata`).
2. **Senhas na mudança de marca:** copiar com a confirmação da pessoa (RF-3623).
3. **Marca padrão do repositório:** `protege` durante a etapa 1; a troca para `desata` é confirmada pelo dono na etapa 3.
