# Star Citizen Beto Hub

App desktop modular de apoio ao Star Citizen (Windows, Python 3.13, PySide6).
Só lê a tela e APIs da comunidade: **não modifica arquivos do jogo nem injeta código**.

> Estado atual: **etapa 5**. Os módulos **Comércio**, **Mineração**, **Refino** e **Log do Capitão**
> estão prontos. Contratos e Frota ainda aparecem como abas "em construção".

## Instalar e rodar

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

## Onde ficam as coisas

| O quê | Onde |
|---|---|
| Configuração editável | `%APPDATA%\BetoHub\config.toml` |
| Banco SQLite | `%LOCALAPPDATA%\BetoHub\hub.db` |
| Logs (rotativos, 5 × 2 MB) | `%LOCALAPPDATA%\BetoHub\logs\betohub.log` |
| Dados de cada módulo | `%LOCALAPPDATA%\BetoHub\modulos\<id>\` |

O `config.toml` tem comentários explicando cada opção. Para editar à mão, feche o Hub antes.
Se o arquivo tiver algum erro, o Hub guarda uma cópia como `config.toml.corrompido-<data>`
e recria o arquivo com os valores padrão.

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

## Log do Capitão

- Aba própria (fora do overlay) para registrar as viagens realizadas e fazer anotações livres.
- Na aba Comércio, selecione uma rota e clique em **Registrar no Log do Capitão** (ou dê dois
  cliques nela). O formulário abre pré-preenchido para você ajustar os valores reais.
- Também recebe as operações de **Refino** (custo do refino, refinado vendido e lucro).
- Mostra um resumo do período (operações, lucro total, lucro médio e melhor operação) e exporta
  para CSV, que abre direto no Excel.

## Estrutura

```
main.py                 ponto de entrada
beto_hub/
  app.py                orquestra a inicialização e o encerramento
  core/                 config, logs, banco, eventos, tarefas, atalhos, plugins
  services/             cliente HTTP, cache da API, cliente UEX e OCR
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
