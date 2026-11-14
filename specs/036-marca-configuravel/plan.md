# Plano da spec 036

## Pacote de marca

`src/prodata/marcas/<id>/`:

- `marca.toml`: nome, nome curto, organização, apoio, site, rodapé, fontes, `[instalacao]` (identificador do instalador, editora, pasta de dados, serviço no cofre, de onde migrar) e `[cores.claro]` / `[cores.escuro]`.
- `logo-claro.svg` (para fundo claro), `logo-escuro.svg` (para fundo escuro e para a barra superior), `icone.png` (1024 px) e, opcional, `icone-escuro.png` para fundos escuros do instalador.

`prodata/brand.py` lê, completa e confere o pacote:

- **Papéis da paleta**, por tema: barra, borda da barra, texto da barra, texto suave da barra, seleção na barra (fundo e texto), realce da barra, botão principal (fundo, passar o mouse, texto), cor da organização, destaque (fundo, passar o mouse, fraco, texto), foco e as 8 séries de gráfico.
- Só barra e destaque são obrigatórios no tema claro; os outros papéis saem deles (texto pelo contraste, versões claras e escuras por mistura). O tema escuro é opcional: sem ele, a marca usa a paleta escura do tema com a sua barra.
- Conferência: obrigatórios, cores válidas, arquivos presentes, nome curto válido, contraste 4,5:1 de texto sobre barra, destaque e botão (erro) e 3:1 das séries com o fundo (aviso).
- `css()` gera as variáveis `--marca-*`, `--accent*`, `--focus`, `--series-*` e `--font` para os dois temas, com os mesmos seletores do tema (`prefers-color-scheme` e `data-theme`).

Marca ativa: `PRODATA_MARCA`, senão o arquivo `marcas/_ativa.txt` que o build grava no pacote, senão a marca padrão do repositório (`protege`, num lugar só).

## Servidor e tela

- `GET /marca/{arquivo}`: logos, ícone, fontes e `cores.css` da marca ativa, com lista fechada de nomes.
- `index.html` usa marcações (`{{marca.nome}}`, `{{marca.organizacao}}`) que o servidor troca, e leva nome, nome curto, organização e rodapé em `data-marca-*` no `<html>`. `js/brand.js` lê esses atributos.
- `brand.css` deixa de ter cores: só a estrutura, com `var(--marca-*)`. A barra, o botão principal, a aba ativa e o cabeçalho do dashboard usam os papéis da paleta.
- Dashboard (tela e HTML exportado), item "Logo de <organização>" e textos que citam o nome do produto passam a ler de `brand.js`.
- Python: textos visíveis usam `marca().nome`; `desktop.py` usa nome, pasta de dados e título da marca; o cofre usa o serviço da marca.

## Mudança de marca

Na abertura do programa instalado, antes de subir o servidor: se a pasta de dados da marca estiver vazia e existir a pasta de uma marca listada em `migrar_de`, uma janela do Windows pergunta se pode trazer fontes, fluxos, organização e modelos, e outra pergunta pelas senhas. A cópia leva a pasta inteira, menos logs, cache de resultados e dados da janela; a pasta antiga fica intacta. As senhas são copiadas pelas chaves que as configurações copiadas citam (conexões, APIs, Jira e a chave do Mask), de um serviço do cofre para o outro. Um arquivo na pasta nova registra a resposta, para não perguntar de novo.

## Empacotamento

- `build.py --marca <id>`: confere o pacote, gera ícone, telas do instalador e abertura a partir da marca, grava os metadados do `.exe`, passa a marca ao PyInstaller (que leva só aquela pasta de marca e grava `_ativa.txt`) e ao Inno Setup (`/DAppId`, `/DAppName`, `/DPublisher`, `/DShortName`).
- Nomes dos arquivos: `<nome curto>.exe`, `<nome curto>-<versão>-setup.exe`, `-portable.zip`. A linha de comando continua `prodata-cli.exe` (identificador técnico).
- Marca diferente da padrão: o build refaz os prints do Manual com a marca, numa pasta temporária, e os coloca no pacote.

## Documentação

- `guia.html` usa `{{produto}}` e `{{organizacao}}`. `gerar_manual.py`, `gerar_pdf.py`, `gerar_contexto_ia.py` e `gerar_imagens.py` recebem `--marca`.
- `manual.json` guarda as marcações, e a tela troca pelo nome da marca ativa: um Manual serve a todas as marcas.

## Garantias

- Teste de código: nenhum "Protege", logotipo ou cor da Protege fora de `marcas/`; "PRO.DATA" só em identificadores técnicos (strings Python fora de docstrings e strings de JavaScript fora de comentários).
- Teste da marca `neutra`: catálogo, página inicial, `cores.css` e textos não citam a Protege.
- Conferência visual: prints da marca `protege` comparados pixel a pixel com os da 0.7.7.
