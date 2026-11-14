# Marcas (spec 036)

Cada pasta aqui é uma marca: o mesmo programa, com outro nome, outras cores e outro logo. A marca muda tudo o que uma
pessoa vê e nada do que um fluxo guarda: um fluxo feito numa marca abre em qualquer outra.

## Como gerar com uma marca

```
uv run python packaging/build.py --marca neutra
PRODATA_MARCA=neutra uv run prodata          # em desenvolvimento
uv run python docs/guia/gerar_pdf.py --marca neutra
```

Sem `--marca`, vale a marca padrão do repositório (`DEFAULT` em `src/prodata/brand.py`).

## Criar uma marca nova

1. Crie `src/prodata/marcas/<id>/` (id curto, minúsculo, sem espaço).
2. Coloque os arquivos visuais:
   - `logo-claro.svg`: logo para fundo claro (dashboard, ícone da aba do navegador).
   - `logo-escuro.svg`: logo para fundo escuro (barra superior, tema escuro, capa do guia).
   - `icone.png`: ícone quadrado de 1024 px, de onde saem o `.ico`, o ícone da janela e as telas do instalador.
   - `icone-escuro.png` (opcional): versão do ícone para fundos da cor da barra.
   - `fontes/*.woff2` (opcional): só se a fonte não for Open Sans, Inter ou JetBrains Mono, que já vêm com o programa.
3. Escreva o `marca.toml`:

```toml
nome = "Desata"                 # como aparece na tela
nome_curto = "Desata"           # para arquivos: Desata-0.8.0-setup.exe (sem espaço nem acento)
organizacao = ""                # vazio: a linha da organização some
fonte_texto = "Inter"
fonte_codigo = "JetBrains Mono"

[instalacao]
app_id = "GERE-UM-GUID-NOVO"     # identifica o instalador no Windows: um por marca, nunca reaproveitado
pasta_dados = "Desata"           # %LOCALAPPDATA%\Desata
cofre = "DESATA"                 # serviço no cofre do Windows
# Na primeira abertura, oferece trazer os dados (e as senhas) de outra marca instalada no computador.
migrar_de = [{ pasta = "PRO.DATA", cofre = "PRODATA", nome = "PRO.DATA" }]

[cores.claro]
barra = "#1f2937"               # obrigatória: fundo da barra superior
destaque = "#2a63d6"            # obrigatória: botões, abas ativas, seleção e foco
organizacao = "#0b6e64"         # opcional: borda da barra, botão principal e detalhes
# series = ["#...", ...]        # opcional: 8 cores dos gráficos

# fundo/superficie/bordas/texto: opcionais, os quatro juntos; sem eles, valem os neutros do tema

# [cores.escuro]                # opcional: sem ela, vale a barra escura do tema
```

Opcionais, no topo do `marca.toml`:

```toml
fonte_titulos = "Manrope"       # títulos, nome na barra, cabeçalhos; arquivos manrope-*.woff2 em fontes/
slogan = "Desate a complexidade. Conecte possibilidades."   # tela de abertura
gradiente = ["#003F46", "#007E7D"]  # tela de abertura, instalador e capa do guia (texto branco precisa de 4,5:1)
```

Os papéis que você não informar saem da barra e do destaque: o texto pelo contraste, as versões claras e escuras por
mistura. A lista completa de papéis está em `Palette` (`src/prodata/brand.py`) e o exemplo completo em
`protege/marca.toml`.

## O que o build confere

- Os arquivos visuais existem e as cores estão no formato `#rrggbb`.
- Texto sobre a barra, sobre o destaque e sobre o botão principal com contraste de 4,5:1 nos dois temas (para o build).
- Cores dos gráficos com contraste de 3:1 com o fundo (só avisa).

Para testar a troca de ponta a ponta, use a marca `neutra`. A marca `protege` reproduz a versão 0.7.7, e a `desata` é o exemplo completo de identidade: neutros, fonte de títulos, slogan e gradiente.
