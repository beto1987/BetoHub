"""Cliente HTTP simples (biblioteca padrão), com limite de requisições e retentativas.

Sem Qt: roda dentro das threads de trabalho e pode ser testado isoladamente.
"""

from __future__ import annotations

import json
import random
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from typing import Any

from .. import __version__
from ..core.logging_setup import obter_logger

log = obter_logger("http")


class ErroHTTP(Exception):
    """Erro de rede ou de servidor, com mensagem amigável em português."""

    def __init__(self, mensagem: str, codigo: int | None = None, temporario: bool = True):
        super().__init__(mensagem)
        self.codigo = codigo
        self.temporario = temporario  # vale a pena tentar de novo / usar cache


class LimitadorTaxa:
    """Janela deslizante: no máximo `maximo` requisições a cada `janela_s` segundos.

    A UEX aceita 120/min; usamos 100 para ter folga (outras ferramentas suas
    podem estar usando a mesma conexão/token).
    """

    def __init__(self, maximo: int = 100, janela_s: float = 60.0):
        self.maximo, self.janela_s = maximo, janela_s
        self._momentos: deque[float] = deque()
        self._trava = threading.Lock()

    def aguardar_vez(self) -> None:
        while True:
            with self._trava:
                agora = time.monotonic()
                while self._momentos and agora - self._momentos[0] > self.janela_s:
                    self._momentos.popleft()
                if len(self._momentos) < self.maximo:
                    self._momentos.append(agora)
                    return
                espera = self.janela_s - (agora - self._momentos[0]) + 0.05
            log.debug("Limite de requisições atingido; aguardando %.1f s", espera)
            time.sleep(espera)


class ClienteHTTP:
    def __init__(self, limitador: LimitadorTaxa | None = None, timeout: float = 20.0, tentativas: int = 3):
        self.limitador = limitador or LimitadorTaxa()
        self.timeout = timeout
        self.tentativas = tentativas

    def obter_json(self, url: str, params: dict[str, Any] | None = None,
                   cabecalhos: dict[str, str] | None = None) -> Any:
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        cab = {"User-Agent": f"StarCitizenBetoHub/{__version__}", "Accept": "application/json"}
        cab.update(cabecalhos or {})

        ultimo_erro: ErroHTTP | None = None
        for tentativa in range(1, self.tentativas + 1):
            self.limitador.aguardar_vez()
            try:
                inicio = time.monotonic()
                req = urllib.request.Request(url, headers=cab)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    corpo = resp.read()
                log.debug("GET %s -> %d bytes em %.2f s", url, len(corpo), time.monotonic() - inicio)
                return json.loads(corpo.decode("utf-8"))
            except urllib.error.HTTPError as e:
                temporario = e.code in (429, 500, 502, 503, 504)
                ultimo_erro = ErroHTTP(f"Servidor respondeu {e.code} ({e.reason}).", e.code, temporario)
                if not temporario:
                    break
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                motivo = getattr(e, "reason", e)
                ultimo_erro = ErroHTTP(f"Sem conexão com o servidor ({motivo}).")
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                ultimo_erro = ErroHTTP(f"Resposta inválida do servidor ({e}).", temporario=False)
                break

            if tentativa < self.tentativas:
                pausa = (2 ** (tentativa - 1)) + random.uniform(0, 0.5)  # 1s, 2s (+ variação)
                log.warning("Falha em %s: %s — nova tentativa em %.1f s", url, ultimo_erro, pausa)
                time.sleep(pausa)

        assert ultimo_erro is not None
        log.error("Falha definitiva em %s: %s", url, ultimo_erro)
        raise ultimo_erro
