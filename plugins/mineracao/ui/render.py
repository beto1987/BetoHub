"""Monta o HTML da leitura (rocha + assinaturas), usado na aba e no overlay.

Mesmo conteúdo do overlay do Beto Scanner, com as cores do HUD de mineração.
"""

from __future__ import annotations

from html import escape
from typing import Any

from beto_hub.core import i18n
from beto_hub.core.i18n import tr
from ..logica.quebra import DadosMineracao
from ..logica.refino import TabelaRefino

COR_RARIDADE = {
    "Lendario": "#ffc247", "Epico": "#c58cff", "Raro": "#5ad8f5", "Incomum": "#7ee0a1",
    "Comum": "#c9ced6", "Gema": "#ff7aa8", "Salvage": "#f4a261",
}
AMBAR, CIANO, TEXTO, APAGADO = "#f2a93b", "#5ad8f5", "#d9dee6", "#7f8a97"
OK, RUIM, ALERTA = "#4fd27f", "#e5484d", "#ff9e5e"


def _n(v: float) -> str:
    return i18n.numero(v)


def _span(texto: str, cor: str, negrito: bool = False, tam: str = "") -> str:
    estilo = f"color:{cor};" + ("font-weight:600;" if negrito else "") + (f"font-size:{tam};" if tam else "")
    return f"<span style='{estilo}'>{texto}</span>"


def _titulo(texto: str, quando: str, novo: bool = True) -> str:
    cor = AMBAR if novo else APAGADO
    return (f"<div style='margin-top:6px;'>{_span('◢ ' + escape(texto), cor, True)}"
            f"{_span('  ·  ' + escape(quando), APAGADO)}</div>")


def _barra(pct: float) -> str:
    n = 22
    cheio = n if pct >= 100 else max(1, round(pct / 100 * n))
    cor = OK if pct <= 85 else (ALERTA if pct <= 100 else RUIM)
    rotulo = "  " + (tr("{pct}% do laser", pct=f"{pct:.0f}") if pct <= 100 else tr("além do laser"))
    return (f"<div style='font-family:Consolas,monospace;'>{_span('█' * cheio, cor)}"
            f"{_span('░' * (n - cheio), '#2a3340')}{_span(rotulo, APAGADO)}</div>")


def html_rocha(rocha: dict[str, Any], dados: DadosMineracao, lo: dict[str, Any]) -> str:
    p: list[str] = [_titulo(tr("ROCHA ANALISADA"), rocha.get("time", ""))]
    linha = f"{_span(tr('MASSA') + ' ', APAGADO)}{_span(_n(rocha['mass']), TEXTO, True)}"
    linha += f"{_span('   RES ', APAGADO)}{_span(f'{rocha['resistance']:g}%', TEXTO, True)}"
    if rocha.get("instability") is not None:
        linha += f"{_span('   INST ', APAGADO)}{_span(f'{rocha['instability']:g}'.replace('.', ','), TEXTO, True)}"
    if rocha.get("difficulty"):
        linha += _span("   " + tr("JOGO: {dificuldade}", dificuldade=rocha["difficulty"]), APAGADO)
    p.append(f"<div>{linha}</div>")
    if rocha.get("res_assumed"):
        p.append(f"<div>{_span(tr('resistência não apareceu na leitura: considerei 0%'), ALERTA)}</div>")

    a = dados.analisar(lo, rocha["mass"], rocha["resistance"], rocha.get("instability"))
    b, jogo = a["base"], rocha.get("difficulty")
    if b["breaks"] and jogo == "IMPOSSIBLE":
        p.append(f"<div>{_span('⚠ ' + tr('O JOGO DIZ IMPOSSÍVEL'), RUIM, True, '12pt')}</div>{_barra(b['throttle'])}")
        p.append(f"<div>{_span(tr('Confira se a cabeça de laser e os módulos são os da sua nave. O jogo tem a palavra final.'), ALERTA)}</div>")
    elif b["breaks"]:
        p.append(f"<div>{_span('✔ ' + tr('QUEBRA'), OK, True, '12pt')}</div>{_barra(b['throttle'])}")
        if b["throttle"] > 85:
            p.append(f"<div>{_span(tr('no limite: pode não quebrar'), ALERTA)}</div>")
    else:
        p.append(f"<div>{_span('✘ ' + tr('NÃO QUEBRA'), RUIM, True, '12pt')}</div>{_barra(b['throttle'])}")
        p.append(f"<div>{_span(tr('precisa {necessario}  ·  você tem {disponivel}', necessario=_n(b['required']), disponivel=_n(b['power'])), APAGADO)}</div>")
        if jogo in ("EASY", "TRIVIAL", "MEDIUM"):
            p.append(f"<div>{_span(tr('O jogo diz {dificuldade}: confira a cabeça de laser e os módulos.', dificuldade=jogo), ALERTA)}</div>")
    p.append(f"<div>{_span(tr('resistência ajustada {valor}%', valor=f'{b['adj_resistance']:.1f}'.replace('.', ',')), APAGADO)}</div>")

    ac = a["active"]
    if ac and not b["breaks"]:
        if ac["breaks"]:
            p.append(f"<div>{_span(tr('ativando os módulos ativos:') + ' ', APAGADO)}{_span('✔ ' + tr('QUEBRA'), OK, True)}"
                     f"{_span(f'  ~{ac['throttle']:.0f}%', APAGADO)}</div>")
        else:
            p.append(f"<div>{_span(tr('nem ativando os módulos ativos'), APAGADO)}</div>")
    if not b["breaks"] and not (ac and ac["breaks"]):
        if a["gadgets"]:
            p.append(f"<div>{_span(tr('GADGET QUE RESOLVE'), AMBAR, True)}</div>")
            for g in a["gadgets"][:3]:
                extra = " + " + tr("módulos ativos") if g["use_active"] else ""
                p.append(f"<div>{_span('&nbsp;&nbsp;▸ ' + escape(g['gadget']) + extra + '   ~' + tr('{pct}% do laser', pct=f'{g['throttle']:.0f}'), CIANO)}</div>")
        else:
            p.append(f"<div>{_span(tr('Nenhum gadget resolve: precisa de mais laser (outra nave junto ou cabeça mais forte).'), ALERTA)}</div>")
    return "".join(p)


def html_leitura(resultados: list, refino: TabelaRefino, quantas_refinarias: int = 3) -> str:
    p: list[str] = []
    for i, (valor, candidatos) in enumerate(resultados):
        if i:
            p.append("<div style='height:4px'></div>")
        p.append(f"<div>{_span(_n(valor), CIANO, True, '15pt')}{_span('  ' + tr('ASSINATURA'), APAGADO)}</div>")
        if not candidatos:
            p.append(f"<div>{_span(tr('Desconhecido: não bate com nenhuma assinatura'), ALERTA)}</div>")
            continue
        for j, c in enumerate(candidatos[:4]):
            s = c["sig"]
            cor = COR_RARIDADE.get(s.get("rarity", ""), TEXTO)
            extra = ""
            if not c.get("exact", True):
                extra += _span("  ~" + tr("aprox"), ALERTA)
            if not c.get("likely", True):
                extra += _span("  " + tr("(grupo grande?)"), ALERTA)
            tags = _span(f"   {escape(tr(str(s.get('rarity', ''))).upper())} · {escape(tr(str(s.get('category', ''))).upper())}", APAGADO)
            if j == 0:
                p.append(f"<div>{_span(f'▸ {c['count']}× ', AMBAR, True)}{_span(escape(s['name']), cor, True, '12pt')}{tags}{extra}</div>")
                sec = s.get("secondary", "-")
                if sec and sec != "-":
                    p.append(f"<div>{_span('&nbsp;&nbsp;&nbsp;+ ' + escape(sec), APAGADO)}</div>")
                if s.get("note"):
                    p.append(f"<div>{_span('&nbsp;&nbsp;&nbsp;' + escape(tr(s['note'])), ALERTA)}</div>")
                if s.get("category") == "Nave":
                    p.append(_html_refino(s["name"], refino, quantas_refinarias))
            else:
                ou = '&nbsp;&nbsp;&nbsp;' + tr('ou') + ' ' + str(c['count']) + '× ' + escape(s['name'])
                p.append(f"<div>{_span(ou, APAGADO)}{tags}{extra}</div>")
        if len(candidatos) > 1:
            p.append(f"<div>{_span('&nbsp;&nbsp;&nbsp;' + tr('mais de uma possibilidade'), APAGADO)}</div>")
    return "".join(p)


def _html_refino(minerio: str, refino: TabelaRefino, quantas: int) -> str:
    melhores = refino.melhores(minerio, quantas)
    if melhores is None:
        return ""
    fonte = "" if refino.fonte == "uex" else " " + tr("(dados antigos)")
    linhas = [f"<div>{_span('&nbsp;&nbsp;&nbsp;' + tr('MELHOR REFINO') + fonte, AMBAR, True)}</div>"]
    if not melhores:
        linhas.append(f"<div>{_span('&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;' + tr('nenhuma estação com bônus'), APAGADO)}</div>")
    for r in melhores:
        linhas.append(f"<div>{_span('&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;▸ ' + escape(r.rotulo), CIANO)}</div>")
    return "".join(linhas)


def html_completo(rocha: dict | None, historico: list[dict[str, Any]], dados: DadosMineracao,
                  lo: dict[str, Any], refino: TabelaRefino, quantas_refinarias: int = 3) -> str:
    """Rocha + leituras (a primeira em destaque, as outras como 'anterior')."""
    partes: list[str] = []
    if rocha:
        partes.append(html_rocha(rocha, dados, lo))
    for k, h in enumerate(historico):
        quando = str(h.get("momento", ""))[-8:]  # só a hora
        partes.append(_titulo(tr("ÚLTIMA LEITURA") if k == 0 else tr("ANTERIOR {n}", n=k), quando, k == 0))
        partes.append(html_leitura(h["results"], refino, quantas_refinarias))
    if not partes:
        return (f"<div>{_span('◢ ' + tr('AGUARDANDO PING'), AMBAR, True)}</div>"
                f"<div>{_span(tr('Dê um ping no jogo: a leitura aparece aqui.'), APAGADO)}</div>")
    return f"<div style='color:{TEXTO};'>{''.join(partes)}</div>"


def texto_nave(lo: dict[str, Any]) -> str:
    cabecas = " + ".join(dict.fromkeys(l["head"] for l in lo.get("lasers", [])))
    return f"◢ {lo.get('ship', '').upper()} · {cabecas.upper()}"
