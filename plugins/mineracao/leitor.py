"""Leitura das imagens capturadas: número do scan e painel da rocha.

Portado das funções Scanner._read, _rock_step e _read_row do Beto Scanner,
separado da thread para ser reaproveitado pela ferramenta "Testar leitura".
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from PIL import Image, ImageOps

from beto_hub.services.ocr import MotorOCR, preprocessar, variacoes

from .logica.identificacao import extrair_numeros, identificar
from .logica.quebra import ler_painel_por_posicao, ler_painel_por_texto, para_numero, rotulo

Resultado = list[tuple[int, list[dict[str, Any]]]]  # [(valor, candidatos)]


class LeitorScan:
    def __init__(self, motor: MotorOCR, assinaturas: list[dict[str, Any]], opcoes: dict[str, Any]):
        self.motor = motor
        self.assinaturas = assinaturas
        self.opcoes = opcoes
        self.diagnostico: list[str] = []  # o que cada variação leu (para log e "Testar leitura")
        self.melhor_imagem: Image.Image | None = None

    def _diag(self, texto: str) -> None:
        self.diagnostico.append(texto)

    # ------------------------------------------------------------ número do scan
    def ler_numero(self, img: Image.Image) -> Resultado:
        """Lê com várias variações e vota no número mais lido.

        Candidatos vazios = número lido com consistência que não bate com nenhuma
        assinatura (Desconhecido).
        """
        op = self.opcoes
        minimo, maximo = int(op.get("valor_minimo", 1500)), int(op.get("valor_maximo", 200000))
        maxq = int(op.get("max_quantidade", 12))
        self.diagnostico, self.melhor_imagem = [], None
        votos, desconhecidos, guardados = Counter(), Counter(), {}

        for modo, limiar in variacoes(op):
            proc = preprocessar(img, op, limiar, modo)
            texto = self.motor.ler(proc)
            achados = []
            for v, limpo in extrair_numeros(texto, minimo, maximo):
                c = identificar(v, self.assinaturas, maxq, 0)  # só exato na votação
                if c:
                    votos[v] += 3 if limpo else 1  # leitura limpa vale mais que corrigida
                    guardados[v] = c
                    achados.append(v)
                    if self.melhor_imagem is None:
                        self.melhor_imagem = proc
                else:
                    desconhecidos[v] += 1 if limpo else 0
            self._diag(f"[{modo} {limiar}] {texto.strip()!r} -> {achados}")

        if votos:
            topo = votos.most_common(1)[0][1]
            escolhidos = [v for v, n in votos.most_common() if n == topo]
            self._diag(f"votos {dict(votos)} -> {escolhidos}")
            return [(v, guardados[v]) for v in escolhidos[:2]]
        if desconhecidos:
            v, n = desconhecidos.most_common(1)[0]
            if n >= 3:  # lido várias vezes igual, mas não bate com nada
                self._diag(f"desconhecido {dict(desconhecidos)} -> {v}")
                return [(v, [])]
        return []

    # ------------------------------------------------------------ painel da rocha
    def ler_rocha(self, img: Image.Image) -> dict[str, Any]:
        """Massa, resistência, instabilidade e dificuldade. {} se não conseguir as duas primeiras."""
        op = self.opcoes
        self.diagnostico = []
        t = int(op.get("limiar", 140))
        melhor: dict[str, Any] = {}
        melhores_palavras: list = []
        votos_massa: Counter = Counter()
        dificuldade = None

        def pontos(i: dict) -> int:
            return ("mass" in i) * 2 + ("resistance" in i) * 2 + ("instability" in i)

        for modo, limiar in (("lum", t), ("gray", None), ("max", t), ("lum", t - 35), ("max", t + 35)):
            texto, palavras = self.motor.ler_palavras(preprocessar(img, op, limiar, modo))
            info = ler_painel_por_posicao(palavras) if palavras else {}
            if not ("mass" in info and "resistance" in info):
                for k, v in ler_painel_por_texto(texto).items():
                    info.setdefault(k, v)
            self._diag(f"[rocha {modo} {limiar}] {texto.strip()!r} -> {info}")
            if "mass" in info:
                votos_massa[info["mass"]] += 1
            if info.get("difficulty"):
                dificuldade = info["difficulty"]
            if pontos(info) > pontos(melhor) or (pontos(info) == pontos(melhor) and len(info) > len(melhor)):
                melhor, melhores_palavras = info, palavras

        if melhores_palavras:  # zoom na linha da massa: leitura com zoom vale mais
            for v in self._ler_linha(img, melhores_palavras, "mass"):
                votos_massa[v] += 2
        if dificuldade and not melhor.get("difficulty"):
            melhor["difficulty"] = dificuldade
        if votos_massa:
            melhor["mass"] = votos_massa.most_common(1)[0][0]
            self._diag(f"votos massa {dict(votos_massa)} -> {melhor['mass']}")
        if "mass" in melhor and "resistance" not in melhor:
            res = self._ler_linha(img, melhores_palavras, "resistance")
            if res:
                melhor["resistance"] = Counter(res).most_common(1)[0][0]
            elif any(rotulo(p[0]) == "resistance" for p in melhores_palavras):
                # rótulo RES achado sem valor: no jogo isso acontece com "0%"
                melhor["resistance"] = 0.0
                melhor["res_assumed"] = True
        return melhor if ("mass" in melhor and "resistance" in melhor) else {}

    def _ler_linha(self, img: Image.Image, palavras: list, tipo: str) -> list[float]:
        """Relê só a linha de um rótulo (MASS ou RES) com zoom alto."""
        rot = next((p for p in palavras if rotulo(p[0]) == tipo), None)
        if not rot:
            return []
        s, b = max(1, int(self.opcoes.get("escala", 3))), 20
        _, x, y, w, h = rot
        x0 = max(0, int((x + w - b) / s))
        y0 = max(0, int((y - b) / s - h / s * 0.4))
        y1 = min(img.height, int((y + h - b) / s + h / s * 0.4))
        x1 = min(img.width, x0 + int(img.width * 0.6))
        if x1 - x0 < 4 or y1 - y0 < 4:
            return []
        recorte = img.crop((x0, y0, x1, y1))
        valores: list[float] = []
        for lim in (140, 105, 175):
            g = recorte.convert("L").resize((recorte.width * 6, recorte.height * 6), Image.LANCZOS)
            g = ImageOps.autocontrast(g)
            pb = ImageOps.expand(g.point(lambda p, t=lim: 0 if p > t else 255), border=30, fill=255)
            texto = self.motor.ler(pb)
            self._diag(f"[rocha {tipo} zoom {lim}] {texto.strip()!r}")
            tt = re.sub(r"\s+", "", texto)
            if tipo == "resistance":
                if re.fullmatch(r"[0OoDQ]+(%|96|°|o/o)?", tt):
                    valores.append(0.0)
                    continue
                m = re.search(r"([0-9OoDQ][0-9OoDQ.,]*)%", tt) or re.fullmatch(r"([0-9OoDQ][0-9OoDQ.,]*)", tt)
                if m:
                    v = para_numero(m.group(1), "resistance")
                    if v is not None and 0 <= v <= 100:
                        valores.append(v)
            else:
                m = re.search(r"[0-9OoDQIlSB][0-9OoDQIlSB.,]{2,}", tt)
                if m:
                    v = para_numero(m.group(0), "mass")
                    if v is not None:
                        valores.append(v)
        return valores
