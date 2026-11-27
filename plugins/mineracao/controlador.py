"""Controlador da Mineração: dono da thread do scanner, do histórico e das opções.

A thread conversa com a interface por um sinal Qt (entregue na thread da
interface). As opções ficam em [modulos.mineracao] no config.toml e o
histórico na tabela mineracao_leituras do banco.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from beto_hub.core.i18n import tr
from beto_hub.core.plugin_base import HubContext
from beto_hub.core.texto import chave_nome

from .logica.identificacao import carregar_assinaturas, identificar
from .logica.importacao import importar
from .logica.quebra import DadosMineracao
from .logica.refino import TabelaRefino
from .leitor import LeitorScan
from .scanner import ThreadScanner

PASTA_DADOS = Path(__file__).resolve().parent / "data"

PADROES: dict[str, Any] = {
    "ativo": True,               # scanner ligado (lembra o último estado)
    "so_com_jogo": True,         # só lê com o Star Citizen em primeiro plano
    "regiao_numero": None,       # {"left","top","width","height"} em pixels físicos
    "regiao_rocha": None,
    "intervalo_ms": 250,
    "escala": 3,
    "limiar": 140,
    "texto_escuro": False,
    "valor_minimo": 1500,
    "valor_maximo": 200000,
    "max_quantidade": 12,
    "tolerancia": 0.004,
    "motor_ocr": "auto",         # auto | windows | tesseract
    "idioma_ocr": "auto",
    "tesseract_cmd": r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    "refinarias_mostradas": 3,
    "leituras_no_overlay": 3,    # última + anteriores
    "loadout": None,
    "importado": False,
}

MIGRACOES = [
    """
    CREATE TABLE mineracao_leituras (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        momento     TEXT NOT NULL,     -- 'AAAA-MM-DD HH:MM:SS' (ou só a hora, se importado)
        valores     TEXT NOT NULL,     -- JSON: [12680]
        resultados  TEXT NOT NULL      -- JSON: [[valor, candidatos], ...]
    );
    """,
]
LIMITE_HISTORICO = 300


class ControladorMineracao(QObject):
    leituraNova = Signal()          # histórico mudou (nova leitura)
    rochaNova = Signal()            # self.rocha mudou
    status = Signal(str, str)       # (texto, papel)
    ativoAlterado = Signal(bool)
    pulso = Signal()                # scan rodando (pisca o indicador)
    opcoesAlteradas = Signal()      # loadout/áreas/ajustes mudaram
    loadoutTrocado = Signal()       # nave trocada de fora (nave ativa da Frota)
    refinoAtualizado = Signal()
    _da_thread = Signal(str, object)

    def __init__(self, ctx: HubContext):
        super().__init__()
        self.ctx = ctx
        self.log = ctx.log
        self.assinaturas = carregar_assinaturas(PASTA_DADOS / "signatures.json")
        self.dados = DadosMineracao(PASTA_DADOS / "mining_data.json")
        self.refino = TabelaRefino.de_arquivo(PASTA_DADOS / "refineries_reserva.json")
        self.rocha: dict[str, Any] | None = None
        self.ultimo_status: tuple[str, str] = (tr("Iniciando…"), "ajuda")

        self._importar_scanner_antigo()
        self.opcoes = self._ler_opcoes()

        self._da_thread.connect(self._ao_receber)
        self.thread = ThreadScanner(dict(self.opcoes), self.assinaturas, self._da_thread.emit)
        self.thread.ativo = bool(self.opcoes["ativo"])
        self.thread.start()

        ctx.eventos.assinar("frota.nave_ativa", self._ao_nave_ativa)

        self.carregar_refino()
        self._timer_refino = QTimer(self, interval=6 * 3600 * 1000)
        self._timer_refino.timeout.connect(self.carregar_refino)
        self._timer_refino.start()

    # ================================================================ opções
    def _ler_opcoes(self) -> dict[str, Any]:
        op = {k: self.ctx.opcao(k, v) for k, v in PADROES.items()}
        op["loadout"] = self.dados.normalizar(op.get("loadout"))
        return op

    def atualizar_opcoes(self, valores: dict[str, Any]) -> None:
        """Salva no config e entrega um dicionário NOVO à thread (troca atômica)."""
        self.ctx.salvar_opcoes(valores)
        self.opcoes = {**self.opcoes, **valores}
        self.thread.opcoes = dict(self.opcoes)
        if "regiao_numero" in valores:
            self.thread.area_mudou()
        if "regiao_rocha" in valores:
            self.thread.rocha_mudou()
        self.opcoesAlteradas.emit()

    def salvar_loadout(self, lo: dict[str, Any]) -> None:
        self.atualizar_opcoes({"loadout": self.dados.normalizar(lo)})
        self.rochaNova.emit()  # recalcula a quebra com a nave nova

    def _ao_nave_ativa(self, dados: dict[str, Any]) -> None:
        """Nave ativa escolhida na Frota: se for de mineração, troca para ela (loadout de fábrica).

        Se a nave já é a mesma, mantém as cabeças e módulos que você configurou.
        """
        chaves = set(dados.get("chaves") or [])
        nave = next((n for n in self.dados.naves if chave_nome(n) in chaves), None)
        if nave is None or nave == self.loadout["ship"]:
            return
        self.log.info("Nave ativa da Frota: mineração passa a usar %s", nave)
        self.salvar_loadout(self.dados.loadout_padrao(nave))
        self.loadoutTrocado.emit()

    @property
    def loadout(self) -> dict[str, Any]:
        return self.opcoes["loadout"]

    # ================================================================ liga/pausa
    @property
    def ativo(self) -> bool:
        return self.thread.ativo

    def definir_ativo(self, ativo: bool) -> None:
        self.thread.ativo = ativo
        self.ctx.salvar_opcoes({"ativo": ativo})
        self.opcoes["ativo"] = ativo
        self.ativoAlterado.emit(ativo)
        self.log.info("Scanner %s", "ligado" if ativo else "pausado")

    def alternar(self) -> None:
        self.definir_ativo(not self.ativo)

    # ================================================================ mensagens da thread
    def _ao_receber(self, tipo: str, dados: Any) -> None:
        if tipo == "resultado":
            self.adicionar_leitura(dados)
        elif tipo == "rocha":
            self.rocha = {"time": time.strftime("%H:%M:%S"), **dados}
            self.rochaNova.emit()
        elif tipo == "status":
            self.ultimo_status = tuple(dados)
            self.status.emit(*dados)
        elif tipo == "pulso":
            self.pulso.emit()

    # ================================================================ histórico
    def adicionar_leitura(self, resultados: list) -> None:
        valores = [v for v, _ in resultados]
        momento = time.strftime("%Y-%m-%d %H:%M:%S")
        ultima = self.ctx.banco.consultar_um("SELECT id, valores FROM mineracao_leituras ORDER BY id DESC LIMIT 1")
        if ultima and json.loads(ultima["valores"]) == valores:
            # mesmo ping de novo: só atualiza a hora
            self.ctx.banco.executar("UPDATE mineracao_leituras SET momento=? WHERE id=?", (momento, ultima["id"]))
        else:
            self.ctx.banco.executar(
                "INSERT INTO mineracao_leituras (momento, valores, resultados) VALUES (?, ?, ?)",
                (momento, json.dumps(valores), json.dumps(resultados, ensure_ascii=False)),
            )
            self.ctx.banco.executar(
                "DELETE FROM mineracao_leituras WHERE id NOT IN "
                "(SELECT id FROM mineracao_leituras ORDER BY id DESC LIMIT ?)", (LIMITE_HISTORICO,))
        self.leituraNova.emit()

    def historico(self, quantas: int = 3) -> list[dict[str, Any]]:
        linhas = self.ctx.banco.consultar(
            "SELECT momento, resultados FROM mineracao_leituras ORDER BY id DESC LIMIT ?", (quantas,))
        saida = []
        for l in linhas:
            try:
                saida.append({"momento": l["momento"], "results": json.loads(l["resultados"])})
            except ValueError:
                continue
        return saida

    def limpar_historico(self) -> None:
        self.ctx.banco.executar("DELETE FROM mineracao_leituras")
        self.rocha = None
        self.leituraNova.emit()
        self.rochaNova.emit()

    def identificar_manual(self, valor: int) -> list:
        candidatos = identificar(valor, self.assinaturas, int(self.opcoes["max_quantidade"]),
                                 float(self.opcoes["tolerancia"]))
        resultados = [(valor, candidatos)]
        self.adicionar_leitura(resultados)
        return resultados

    # ================================================================ testar leitura
    def testar_leitura(self, chave: str) -> dict[str, Any]:
        """Captura a área e lê uma vez, com diagnóstico. Roda numa thread de trabalho."""
        from beto_hub.services.ocr import MotorOCR, preprocessar
        from beto_hub.services.ocr.capture import Capturador

        op = dict(self.opcoes)
        with Capturador() as capt:
            img = capt.capturar(op[chave])
        motor = MotorOCR(op["motor_ocr"], op["idioma_ocr"], op["tesseract_cmd"])
        try:
            leitor = LeitorScan(motor, self.assinaturas, op)
            if chave == "regiao_numero":
                resultados = leitor.ler_numero(img)
                processada = leitor.melhor_imagem or preprocessar(img, op)
                partes = []
                for valor, cands in resultados:
                    if cands:
                        c = cands[0]
                        partes.append(f"{valor} = {c['count']}× {c['sig']['name']}")
                    else:
                        partes.append(f"{valor} = " + tr("desconhecido"))
                resumo = "; ".join(partes) or tr("nenhum número reconhecido")
            else:
                info = leitor.ler_rocha(img)
                processada = preprocessar(img, op)
                resumo = (", ".join(f"{k}={v}" for k, v in info.items())
                          if info else tr("massa e resistência não reconhecidas"))
            return {"bruta": img, "processada": processada, "diagnostico": leitor.diagnostico,
                    "resumo": resumo, "motor": f"{motor.motor} ({motor.idioma or tr('padrão')})"}
        finally:
            motor.fechar()

    # ================================================================ refino (UEX)
    def carregar_refino(self) -> None:
        uex = self.ctx.servico("uex")
        if uex is None:
            return
        self.ctx.workers.executar(uex.refinarias_rendimento, ao_concluir=self._ao_refino,
                                  ao_falhar=lambda e: self.log.warning("Refino da UEX indisponível: %s", e))

    def _ao_refino(self, resultado) -> None:
        tabela = TabelaRefino.de_uex(resultado.dados or [])
        if len(tabela):
            self.refino = tabela
            self.log.info("Refino: %d minérios com dados da UEX", len(tabela))
            self.refinoAtualizado.emit()

    # ================================================================ importação
    def _importar_scanner_antigo(self) -> None:
        if self.ctx.opcao("importado", False):
            return
        try:
            opcoes, historico, origem = importar()
        except Exception:
            self.log.exception("Falha ao importar o Beto Scanner antigo")
            opcoes, historico, origem = {}, [], ""
        self.ctx.salvar_opcoes({**opcoes, "importado": True})
        for h in reversed(historico):  # mais antigo primeiro, para o mais novo ficar por cima
            valores = [r[0] for r in h["results"]]
            self.ctx.banco.executar(
                "INSERT INTO mineracao_leituras (momento, valores, resultados) VALUES (?, ?, ?)",
                (str(h.get("time", "")), json.dumps(valores), json.dumps(h["results"], ensure_ascii=False)))
        if origem:
            self.log.info("Beto Scanner importado de %s (%d opções, %d leituras)", origem, len(opcoes), len(historico))
            self.ctx.notificar(tr("Mineração"), tr("Configurações do Beto Scanner importadas de {origem}.", origem=origem))

    # ================================================================ encerramento
    def parar(self) -> None:
        self.thread.parar()
        self.thread.join(timeout=2)
