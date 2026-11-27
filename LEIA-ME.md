# StarHub

App desktop modular de apoio ao Star Citizen (Windows, Python 3.13, PySide6).
Só lê a tela, o `Game.log` e APIs da comunidade: **não modifica arquivos do jogo nem injeta código**.

> **Versão 1.0.0.** Módulos: **Comércio**, **Mineração**, **Contratos**, **Refino**, **Frota** e
> **Log do Capitão**, em português, inglês, espanhol, francês e italiano.
> Até a 0.x o app se chamava **Beto Hub**: na primeira abertura, o StarHub copia os seus dados
> das pastas `BetoHub` (que ficam como backup).

## Instalar (para jogar)

1. Rode **`StarHub-1.0.0-Setup.exe`**. Não precisa de administrador: instala em
   `%LOCALAPPDATA%\Programs\StarHub` (ou, se você escolher, para todos os usuários).
2. Escolha o idioma do instalador e, numa página própria, o **idioma do aplicativo**.
3. Para desinstalar: Configurações do Windows › Aplicativos › StarHub. Seus dados
   (`%APPDATA%\StarHub` e `%LOCALAPPDATA%\StarHub`) ficam guardados.

Enquanto o instalador não tiver assinatura digital, o Windows pode mostrar **"O Windows
protegeu o computador"** (SmartScreen): clique em **Mais informações › Executar assim mesmo**.

## Rodar pelo código-fonte (para desenvolver)

1. Instale o **Python 3.13** (python.org), marcando "Add python.exe to PATH".
2. Dê dois cliques em **`instalar.bat`**. Ele cria a pasta `.venv` e instala as dependências.
3. Para abrir o Hub, use **`iniciar.bat`** (sem console) ou **`debug.bat`** (com os logs ao vivo).
4. Para rodar os testes automáticos, use **`testar.bat`**.

Instalação manual, se preferir:

```bat
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

## Gerar o instalador

Precisa do **Inno Setup 6** (`winget install JRSoftware.InnoSetup`) e do PyInstaller (já no
`requirements.txt`). Depois:

```bat
powershell -ExecutionPolicy Bypass -File instalador\compilar.ps1
```

O script roda os testes, compila com o PyInstaller (`instalador\starhub.spec`), monta o
instalador (`instalador\starhub.iss`) e mostra o SHA-256. O resultado fica em
`build\instalador\StarHub-<versão>-Setup.exe`. Com um certificado de assinatura de código
configurado (veja o início do `compilar.ps1`), o programa, o instalador e o desinstalador saem
assinados. Ao mudar a versão, atualize `beto_hub/__init__.py` e `instalador/versao_exe.txt`.

## Onde ficam as coisas

| O quê | Onde |
|---|---|
| Configuração editável | `%APPDATA%\StarHub\config.toml` |
| Banco SQLite | `%LOCALAPPDATA%\StarHub\hub.db` |
| Logs (rotativos, 5 × 2 MB) | `%LOCALAPPDATA%\StarHub\logs\starhub.log` |
| Dados de cada módulo | `%LOCALAPPDATA%\StarHub\modulos\<id>\` |

O `config.toml` tem comentários explicando cada opção. Para editar à mão, feche o Hub antes.
Se o arquivo tiver algum erro, o Hub guarda uma cópia como `config.toml.corrompido-<data>`
e recria o arquivo com os valores padrão.

## Idioma

- O Hub está em **português (Brasil)**, **inglês (EUA)**, **espanhol**, **francês** e **italiano**.
  Escolha em **Configurações › Geral › Idioma**; o Hub pergunta se pode reiniciar para aplicar.
- Números e datas seguem o idioma (1.234,5 em português; 1,234.5 e mês/dia em inglês).
- Nomes que vêm do jogo e da UEX (naves, minérios, estações, títulos e objetivos de contratos)
  aparecem como o jogo os mostra, em inglês.

## Overlay e atalho

- O overlay é uma janela única, sempre visível, com uma aba por módulo. Você pode arrastá-lo pela
  barra de título e redimensioná-lo pelo canto inferior direito. Ele lembra a posição e o tamanho.
- Ele aparece por cima do jogo no modo **Janela sem bordas** (*Borderless*).
- Em **Configurações › Overlay** você ajusta a opacidade (com prévia ao vivo) e liga o "clique
  atravessa". Com ele ligado, os cliques passam para o jogo, e para desligar você usa o menu
  o atalho, o menu Exibir, o ícone da bandeja ou as configurações.
- Há dois atalhos globais, os dois **desativados** de fábrica: um para mostrar/esconder o
  overlay e outro para ligar/desligar o "clique atravessa". Quando o clique atravessa está
  ligado, a barra do overlay mostra **⇣ CLIQUE ATRAVESSA** em âmbar.
- Para ligar um atalho, vá em **Configurações › Atalhos**, marque "Ativar atalho global", clique no campo e pressione a combinação desejada. Esc cancela e
  Backspace limpa. A mudança vale assim que você clica em Aplicar, sem reiniciar.
- Os atalhos funcionam **com o jogo em foco**. O Hub consulta o estado das teclas a cada 25 ms
  (`GetAsyncKeyState`). Isso é só leitura: não usa gancho de teclado e não toca no jogo.
- As teclas **também chegam ao jogo**, então escolha uma combinação que não faz nada no
  Star Citizen. Enquanto a tela de Configurações estiver aberta, o atalho fica pausado.

## Comércio

- Os dados vêm da **UEX Corp API 2.0** (preços reportados pela comunidade). Não é preciso ter
  token para consultar preços. Os preços ficam em cache por 30 minutos, os cadastros por 24 h e
  as distâncias por 12 h. Se a UEX cair, o Hub mostra os últimos dados salvos, com um aviso.
- Informe a nave (o SCU é preenchido sozinho, ou você digita), o capital, o sistema e, se
  quiser, o terminal onde está. A quantidade de cada rota é o menor valor entre a carga da
  nave, o que o capital compra e o estoque da origem.
- **Eficiência** = lucro ÷ distância (Gm). Rotas muito curtas contam com uma distância mínima
  (padrão de 1 Gm, que você ajusta em Configurações › Comércio).
- **Risco** (0 a 100) considera o valor da carga, Pyro e outros sistemas, ponto de salto,
  terminais NQA e de jogadores, outposts, distância e idade dos preços. Passe o mouse para ver
  os motivos.
- Você ordena pelo menu "Ordenar por" ou clicando no título de qualquer coluna (clique de novo
  para inverter). O overlay mostra as **5 melhores** conforme o "Ordenar por".
- Limitação: a UEX não informa com segurança quanto o destino ainda aceita comprar.

## Mineração (o Beto Scanner dentro do Hub)

- Lê o **número do scan** (ping) e o **painel da rocha** (massa, resistência, instabilidade) com
  o OCR do Windows e mostra: minério, quantidade, raridade, secundários, **melhor refino**
  (dados da UEX) e se o seu laser **quebra** a rocha, com o gadget que resolve quando não quebra.
- Na primeira abertura, as áreas da tela, os ajustes de OCR, a nave/lasers/módulos e as
  últimas leituras são importados do Beto Scanner antigo (`D:\Claudinho\SCScanner` ou da
  versão instalada). Depois disso, o Beto Scanner separado pode ser desinstalado.
- **Ligar/Pausar** fica na aba e no overlay (o botão do overlay é clicável e não tira o foco do
  jogo). Com "só ler com o Star Citizen em primeiro plano" marcado, o scanner não lê a tela
  enquanto outra janela estiver ativa.
- **Marcar áreas:** "Marcar agora" ou "Em 5 s" (dá tempo de voltar ao jogo e pingar). Aparece
  um print escurecido: arraste o retângulo; Esc cancela.
- **Testar leitura** mostra a imagem capturada, a imagem tratada e o que o OCR leu em cada
  ajuste, para acertar área e limiar.
- Um resultado só aparece depois de ser lido igual duas vezes seguidas (como no Beto Scanner).

## Contratos

- O Hub acompanha seus contratos **sozinho**, lendo o `Game.log` que o Star Citizen grava enquanto
  você joga (só leitura: nada é alterado na pasta do jogo). Em poucos segundos depois de aceitar um
  contrato, ele aparece em **Ativos** com os objetivos, que vão sendo marcados conforme você conclui.
- Quando o contrato termina (concluído, falhou ou abandonado), o Windows avisa com um balão, e ele
  passa para o **Histórico**, com filtros por período, resultado e tipo, e um resumo com a taxa de
  sucesso.
- O log **não mostra a recompensa nem o prazo**: informe a recompensa no painel do contrato. Num
  contrato concluído, **Registrar no Log do Capitão** abre o formulário já preenchido.
- **Importar histórico** lê os logs das suas sessões anteriores (pasta `logbackups` do jogo). Se você
  jogar com o Hub fechado, ele lê essas sessões sozinho quando abrir.
- Contratos que ficam "ativos" por mais de 3 dias sem novidade (o jogo fechou antes do fim, por
  exemplo) passam para **Sem desfecho no log**. Use **Marcar concluído / abandonado** se precisar.
- **Rota de entregas**: junta as entregas pendentes dos contratos de transporte ativos (lidas
  dos objetivos "Deliver … to …") e calcula a ordem com a **menor distância total**, usando as
  distâncias da UEX. Escolha em **Estou em** onde você está e clique em **Calcular melhor rota**.
  - Quando o título diz "from X", a coleta em X entra na rota antes das entregas daquele contrato.
  - Várias entregas no mesmo lugar viram uma parada só.
  - Quando o jogo só informa o sistema ("Pyro System") ou o local não está na UEX, a linha fica
    em âmbar: escolha o local na lista (ele aparece no seu mobiGlas). Desmarque o que não quer
    incluir.
  - O log do jogo não informa os pontos de coleta de cada carga; por isso só entram as coletas
    citadas no título.
- O overlay tem uma aba com a rota calculada e os contratos ativos com seus objetivos.
- A pasta do jogo é detectada sozinha (canal LIVE). Para o PTU ou outra instalação, escolha a pasta
  em **Configurações › Contratos**.

## Refino

- **Novo pedido** (pela aba ou pelo botão no overlay, que abre uma janelinha por cima do jogo):
  escolha a refinaria e os minérios com a quantidade em **cSCU**, como no terminal de refino.
- **Comparação de métodos** com estimativas em **SCU**: quanto sai refinado, custo, tempo,
  valor de venda do refinado (melhor preço na UEX) e lucro previsto. As estimativas vêm de
  pedidos reais enviados à UEX pela comunidade, já com o bônus da refinaria escolhida; a coluna
  "Base" mostra de onde vieram e quantos relatos.
- Ao criar o pedido, confirme o **custo e o tempo mostrados no jogo** (os campos já vêm com a
  estimativa) e, se precisar, a hora em que o refino começou.
- A aba mostra os pedidos com contagem regressiva. Quando um fica pronto, o Windows avisa com
  **balão e som**; se o Hub estava fechado, o aviso aparece ao abrir. Os prontos também
  aparecem no overlay.
- **Retirado / vendido** marca o pedido e abre o Log do Capitão pré-preenchido (tipo Refino).

## Frota

- Estatísticas das naves vindas da **Star Citizen Wiki** (dados extraídos do jogo, com o
  **loadout de fábrica**): DPS do piloto e das torretas, armas, mísseis, escudo, casco, armadura,
  velocidade, quantum, carga, tripulação, seguro e preço no jogo (com onde comprar, via UEX).
  O Hub baixa uma vez por dia e guarda no cache; **Atualizar dados das naves** força na hora.
- **Hangar**: cadastre as naves que você tem, com apelido, origem (comprada no jogo, pledge,
  seguro vitalício…) e notas. Selecionar uma nave mostra a ficha completa ao lado.
- **★ Usar como nave ativa**: o Comércio passa a usar essa nave (e a carga dela) e, se for de
  mineração (Prospector, MOLE, Golem), a Mineração troca para ela com o loadout padrão.
  Naves sem carga (caças, Prospector) não mudam a nave do Comércio.
- **Comparador**: até 4 naves lado a lado (qualquer nave, não só as do hangar), com o melhor
  valor de cada linha em verde. No hangar, selecione várias (Ctrl+clique) e clique em
  **Comparar selecionadas**.
- Ainda não dá para trocar armas e componentes (editar o loadout).

## Log do Capitão

- Aba própria (fora do overlay) para registrar as viagens realizadas e fazer anotações livres.
- Na aba Comércio, selecione uma rota e clique em **Registrar no Log do Capitão** (ou dê dois
  cliques nela). O formulário abre pré-preenchido para você ajustar os valores reais.
- Também recebe as operações de **Refino** (custo do refino, refinado vendido e lucro) e os
  **Contratos** concluídos (recompensa e despesas).
- Mostra um resumo do período (operações, lucro total, lucro médio e melhor operação) e exporta
  para CSV, que abre direto no Excel.

## Estrutura

```
main.py                 ponto de entrada
beto_hub/
  app.py                orquestra a inicialização e o encerramento
  core/                 config, logs, banco, eventos, tarefas, atalhos, plugins
  services/             cliente HTTP, cache da API, clientes UEX e Star Citizen Wiki, OCR
  ui/                   janela principal, overlay, configurações, tema
plugins/<id>/           um módulo por pasta: manifest.toml + plugin.py
tests/                  testes com pytest
```

### Como funciona um módulo

```toml
# plugins/meu_modulo/manifest.toml
id = "meu_modulo"
nome = "Meu Módulo"
versao = "0.1.0"
ordem = 60
```

```python
# plugins/meu_modulo/plugin.py
from beto_hub.core.plugin_base import BasePlugin

class Plugin(BasePlugin):
    def migracoes(self):               # SQL; a posição na lista é a versão
        return ["CREATE TABLE meu_modulo_itens (id INTEGER PRIMARY KEY, nome TEXT)"]

    def criar_aba(self, parent):       # obrigatório
        ...

    def criar_painel_overlay(self):    # opcional
        ...
```

O módulo acessa o resto do app pelo `self.ctx`, que oferece `config`, `banco`, `eventos`,
`workers`, `log`, `notificar` e `servicos`. Um módulo com erro não derruba o Hub: ele aparece
numa aba vermelha com o erro e o caminho do log.
