"""Tradução da interface. Sem Qt (testável); o idioma vem de [geral] idioma no config.toml.

Uso em qualquer módulo:
    from beto_hub.core.i18n import tr
    QLabel(tr("Atualizar preços"))
    tr("{n} rotas encontradas", n=len(rotas))     # campos nomeados, como str.format

Regras:
- A CHAVE é o próprio texto em português. As traduções ficam em
  beto_hub/i18n/<idioma>.json ({"texto em português": "tradução"}).
- Texto sem tradução aparece em português (nunca quebra a tela).
- Traduza só o que é MOSTRADO. Valores guardados no banco/config (ex.: tipo
  "Transporte" de um contrato) continuam em português e passam por tr() na exibição.
- Mensagens de log (log.info...) não são traduzidas.
- O idioma é lido uma vez, ao importar este módulo, antes de qualquer tela ser criada;
  trocar o idioma vale na próxima vez que o Hub abrir.
"""

from __future__ import annotations

import json
import string
import tomllib
from pathlib import Path
from typing import Any

PADRAO = "pt-BR"
# Código -> nome do idioma no próprio idioma (para a lista nas Configurações)
IDIOMAS = {
    "pt-BR": "Português (Brasil)",
    "en-US": "English (US)",
    "es": "Español",
    "fr": "Français",
    "it": "Italiano",
}
# Arquivo de tradução do próprio Qt (botões padrão, menus de contexto) por idioma
ARQUIVOS_QT = {"pt-BR": "qtbase_pt_BR", "en-US": "qtbase_en", "es": "qtbase_es", "fr": "qtbase_fr", "it": "qtbase_it"}

PASTA = Path(__file__).resolve().parents[1] / "i18n"

_idioma = PADRAO
_traducoes: dict[str, str] = {}


def carregar(codigo: str) -> dict[str, str]:
    """Traduções de um idioma ({} para português ou arquivo ausente/inválido)."""
    if codigo == PADRAO:
        return {}
    try:
        with open(PASTA / f"{codigo}.json", encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in dados.items() if isinstance(v, str) and v}


def definir_idioma(codigo: str | None) -> str:
    """Troca o idioma em uso (código desconhecido -> português). Devolve o código aplicado."""
    global _idioma, _traducoes
    codigo = codigo if codigo in IDIOMAS else PADRAO
    _idioma, _traducoes = codigo, carregar(codigo)
    return codigo


def idioma() -> str:
    return _idioma


def N_(texto: str, /) -> str:
    """Marca um texto para tradução SEM traduzir agora (constantes guardadas em português).

    Ex.: NOMES = {"ativo": N_("Em andamento")}  ...  rotulo = tr(NOMES[status])
    """
    return texto


def tr(texto: str, /, **campos: Any) -> str:
    """Texto no idioma atual. `campos` preenchem {nome} no texto (formato do str.format)."""
    traduzido = _traducoes.get(texto, texto)
    if not campos:
        return traduzido
    try:
        return traduzido.format(**campos)
    except (KeyError, IndexError, ValueError):
        return texto.format(**campos)  # tradução com campo errado: usa o original


# Separadores de milhar e decimal por idioma (o francês usa espaço fino no milhar)
_SEPARADORES = {"pt-BR": (".", ","), "es": (".", ","), "it": (".", ","), "fr": (" ", ","), "en-US": (",", ".")}
# Código do idioma para o QLocale do Qt (campos numéricos e de data)
LOCALES_QT = {"pt-BR": "pt_BR", "en-US": "en_US", "es": "es_ES", "fr": "fr_FR", "it": "it_IT"}


def numero(valor: float | None, casas: int = 0) -> str:
    """Número no padrão do idioma: 12345.6 -> "12.345,6" (pt) / "12,345.6" (en). None -> "—"."""
    if valor is None:
        return "—"
    milhar, decimal = _SEPARADORES.get(_idioma, (".", ","))
    texto = f"{valor:,.{casas}f}"  # formato do Python: "12,345.6"
    return texto.replace(",", "\0").replace(".", decimal).replace("\0", milhar)


def separador_decimal() -> str:
    return _SEPARADORES.get(_idioma, (".", ","))[1]


def data_curta(epoch: float | None) -> str:
    """"25/11 21:30" (dia/mês) ou "11/25 21:30" em inglês dos EUA. None -> "—"."""
    import time
    if not epoch:
        return "—"
    formato = "%m/%d %H:%M" if _idioma == "en-US" else "%d/%m %H:%M"
    return time.strftime(formato, time.localtime(epoch))


def formato_data_qt() -> str:
    """Formato para QDateTimeEdit (dia/mês/ano, ou mês/dia/ano em inglês dos EUA)."""
    return "MM/dd/yyyy HH:mm" if _idioma == "en-US" else "dd/MM/yyyy HH:mm"


def campos_do_texto(texto: str) -> set[str]:
    """Nomes dos campos {nome} de um texto (usado nos testes das traduções)."""
    return {nome for _, nome, _, _ in string.Formatter().parse(texto) if nome}


def idioma_do_config(arquivo: Path) -> str:
    """Lê [geral] idioma do config.toml sem depender do resto do app."""
    try:
        texto = Path(arquivo).read_text(encoding="utf-8-sig")  # aceita BOM
        return str(tomllib.loads(texto).get("geral", {}).get("idioma", PADRAO))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return PADRAO


ARQUIVO_INSTALACAO = "idioma_instalacao.txt"  # gravado pelo instalador na pasta do programa
# Idioma escolhido no instalador que ainda não foi salvo no config: (código, marca). O app salva ao abrir.
PENDENTE_DA_INSTALACAO: tuple[str, str] | None = None


def idioma_da_instalacao(pasta: Path) -> tuple[str, str] | None:
    """(código, marca) do idioma escolhido no instalador; a marca muda a cada (re)instalação."""
    arquivo = pasta / ARQUIVO_INSTALACAO
    try:
        codigo = arquivo.read_text(encoding="utf-8-sig").strip()
        marca = str(int(arquivo.stat().st_mtime))
    except OSError:
        return None
    return (codigo, marca) if codigo in IDIOMAS else None


def escolher_idioma(config: Path, pasta_programa: Path) -> tuple[str, tuple[str, str] | None]:
    """Idioma a usar e, se for o caso, o idioma da instalação que precisa ser salvo no config.

    O instalador vence uma vez (instalação nova ou reinstalação, reconhecida pela marca);
    depois vale o que o jogador escolher nas Configurações.
    """
    try:
        geral = tomllib.loads(Path(config).read_text(encoding="utf-8-sig")).get("geral", {})  # aceita BOM
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        geral = {}
    instalacao = idioma_da_instalacao(pasta_programa)
    if instalacao and str(geral.get("idioma_instalador", "")) != instalacao[1]:
        return instalacao[0], instalacao
    return str(geral.get("idioma", PADRAO)), None


def _iniciar() -> None:
    global PENDENTE_DA_INSTALACAO
    from .paths import arquivo_config, raiz_programa  # import tardio: paths não depende de i18n
    codigo, PENDENTE_DA_INSTALACAO = escolher_idioma(arquivo_config(), raiz_programa())
    definir_idioma(codigo)


_iniciar()
