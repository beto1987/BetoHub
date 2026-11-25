"""Thread do scanner: captura a tela, lê e manda os resultados para a interface.

Mesmo comportamento do Beto Scanner:
- lê a área do número a cada `intervalo_ms` (padrão 250 ms);
- se a imagem não mudou e a última leitura foi boa, não reprocessa;
- só mostra um resultado depois de lê-lo igual DUAS vezes seguidas;
- o painel da rocha também precisa ser confirmado duas vezes.
Novo no Hub:
- com "só com o jogo em primeiro plano" ligado, não lê nada enquanto outra
  janela estiver ativa (economiza CPU).
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from beto_hub.core.logging_setup import obter_logger
from beto_hub.services.ocr import ErroOCR, MotorOCR
from beto_hub.services.ocr.capture import Capturador, mudou, regiao_valida
from beto_hub.services.ocr.janela import jogo_em_primeiro_plano

from .leitor import LeitorScan

log = obter_logger("plugin.mineracao.scanner")

# Tipos de mensagem enviados para a interface: (tipo, dados)
#   "resultado" -> [(valor, candidatos)]   "rocha" -> dict
#   "status"    -> (texto, papel)          "pulso" -> None (scan ativo)
Saida = Callable[[str, Any], None]


class ThreadScanner(threading.Thread):
    def __init__(self, opcoes: dict[str, Any], assinaturas: list[dict[str, Any]], saida: Saida):
        super().__init__(name="BetoHub-Scanner", daemon=True)
        self.opcoes = opcoes            # o controlador troca o dicionário inteiro quando muda algo
        self.assinaturas = assinaturas
        self.saida = saida
        self.ativo = False              # ligado/pausado (controlado pela interface)
        self._rodando = True
        self._reiniciar = threading.Event()
        self._esqueci_rocha = threading.Event()

    # ------------------------------------------------------------ controle (chamados pela interface)
    def parar(self) -> None:
        self._rodando = False

    def area_mudou(self) -> None:
        self._reiniciar.set()

    def rocha_mudou(self) -> None:
        self._esqueci_rocha.set()

    # ------------------------------------------------------------ laço principal
    def run(self) -> None:
        motor: MotorOCR | None = None
        chave_motor = None
        estado_espera = None
        ultimo_pulso = 0.0
        num = {"img": None, "ok": False, "mostrado": None, "pendente": None, "falhas": 0}
        rocha = {"img": None, "pendente": None, "mostrada": None}

        try:
            capt = Capturador()
        except Exception as e:
            self.saida("status", (f"Captura de tela indisponível: {e}", "erro"))
            log.exception("Falha ao iniciar a captura de tela")
            return

        try:
            while self._rodando:
                op = self.opcoes
                intervalo = max(50, int(op.get("intervalo_ms", 250))) / 1000.0

                if self._reiniciar.is_set():
                    self._reiniciar.clear()
                    num.update(img=None, ok=False, mostrado=None, pendente=None, falhas=0)
                if self._esqueci_rocha.is_set():
                    self._esqueci_rocha.clear()
                    rocha.update(img=None, pendente=None, mostrada=None)

                regiao_n, regiao_r = op.get("regiao_numero"), op.get("regiao_rocha")
                tem_area = regiao_valida(regiao_n) or regiao_valida(regiao_r)

                # ---- estados de espera (pausado, sem área, jogo fora de foco)
                espera = None
                if not self.ativo:
                    espera = ("Scanner pausado", "ajuda")
                elif not tem_area:
                    espera = ("Marque a área do número na aba Mineração", "alerta")
                elif op.get("so_com_jogo", True) and not jogo_em_primeiro_plano():
                    espera = ("Aguardando o Star Citizen em primeiro plano", "ajuda")
                if espera:
                    if espera != estado_espera:
                        self.saida("status", espera)
                        estado_espera = espera
                    time.sleep(0.4)
                    continue
                if estado_espera is not None:
                    self.saida("status", ("Scan ativo", "ok"))
                    estado_espera = None

                # ---- motor de OCR (recria se o usuário trocar motor/idioma)
                chave = (op.get("motor_ocr", "auto"), op.get("idioma_ocr", "auto"), op.get("tesseract_cmd"))
                if motor is None or chave != chave_motor:
                    if motor:
                        motor.fechar()
                    try:
                        motor = MotorOCR(*chave) if chave[2] else MotorOCR(chave[0], chave[1])
                        chave_motor = chave
                        self.saida("status", (f"Scan ativo · OCR {motor.motor}", "ok"))
                    except ErroOCR as e:
                        self.saida("status", (str(e), "erro"))
                        motor = None
                        time.sleep(3)
                        continue
                leitor = LeitorScan(motor, self.assinaturas, op)

                agora = time.monotonic()
                if agora - ultimo_pulso > 1.0:
                    self.saida("pulso", None)
                    ultimo_pulso = agora

                # ---- painel da rocha
                if regiao_valida(regiao_r):
                    try:
                        self._passo_rocha(capt, leitor, regiao_r, rocha)
                    except Exception as e:
                        log.debug("Erro lendo a rocha: %s", e)

                # ---- número do scan
                if regiao_valida(regiao_n):
                    try:
                        self._passo_numero(capt, leitor, regiao_n, num)
                    except Exception as e:
                        log.warning("Erro lendo o número: %s", e)
                        self.saida("status", (f"Erro: {e}", "erro"))
                        time.sleep(1)
                time.sleep(intervalo)
        finally:
            if motor:
                motor.fechar()
            capt.fechar()
            log.info("Thread do scanner encerrada")

    # ------------------------------------------------------------ passos
    def _passo_numero(self, capt: Capturador, leitor: LeitorScan, regiao, st: dict) -> None:
        img = capt.capturar(regiao)
        igual = not mudou(st["img"], img)
        st["img"] = img
        if igual and st["ok"]:
            return  # mesma tela, leitura já boa
        resultados = leitor.ler_numero(img)
        for linha in leitor.diagnostico:
            log.debug(linha)
        st["ok"] = bool(resultados)
        if not resultados:
            st["falhas"] += 1
            if st["falhas"] >= 3:  # número sumiu de verdade
                st["mostrado"], st["pendente"] = None, None
            return
        st["falhas"] = 0
        valores = [v for v, _ in resultados]
        if valores == st["mostrado"]:
            return
        if valores == st["pendente"]:
            st["mostrado"], st["pendente"] = valores, None
            log.info("Leitura confirmada: %s", valores)
            self.saida("resultado", resultados)
        else:
            st["pendente"] = valores  # precisa ler igual 2x seguidas
            st["ok"] = False          # força reler na próxima

    def _passo_rocha(self, capt: Capturador, leitor: LeitorScan, regiao, st: dict) -> None:
        img = capt.capturar(regiao)
        anterior = st["img"]
        st["img"] = img
        if st["pendente"] is None and not mudou(anterior, img):
            return
        info = leitor.ler_rocha(img)
        for linha in leitor.diagnostico:
            log.debug(linha)
        if not info:
            st["pendente"] = None
            return
        chave = (round(info["mass"]), round(info["resistance"], 1))
        if chave == st["mostrada"]:
            return
        if chave == st["pendente"]:  # lido igual duas vezes: confirma
            st["mostrada"], st["pendente"] = chave, None
            log.info("Rocha confirmada: %s", info)
            self.saida("rocha", info)
        else:
            st["pendente"] = chave
