"""Cliente da UEX Corp API 2.0 (dados da comunidade do Star Citizen).

- Respostas no formato {"status": "ok", "http_code": 200, "data": [...], "message": ""}.
- Tudo passa pelo cache (CacheAPI). Validade por recurso:
    preços ............ 30 min (a própria UEX atualiza de hora em hora)
    terminais, naves .. 24 h
    distâncias ........ 12 h
- Se a API falhar e houver cache vencido, devolve o cache com `desatualizado=True`.
- Métodos bloqueiam (rede): chame-os pelos workers, nunca na thread da interface.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

from ..core.logging_setup import obter_logger
from .api_cache import CacheAPI, EntradaCache
from .http_client import ClienteHTTP, ErroHTTP

log = obter_logger("uex")

TTL_PRECOS = 30 * 60
TTL_CADASTROS = 24 * 3600
TTL_DISTANCIAS = 12 * 3600

# Endereços conhecidos da API; o configurado pelo usuário é tentado primeiro.
URLS_CONHECIDAS = ("https://api.uexcorp.uk/2.0", "https://uexcorp.space/api/2.0")


class ErroUEX(Exception):
    pass


@dataclass
class ResultadoAPI:
    dados: Any
    obtido_em: float
    do_cache: bool = False        # veio do cache (válido ou não)
    desatualizado: bool = False   # cache vencido usado porque a API falhou
    aviso: str = ""


@dataclass
class ClienteUEX:
    http: ClienteHTTP
    cache: CacheAPI
    obter_config: Callable[[str, Any], Any]  # ex.: config.obter
    _url_boa: str | None = field(default=None, init=False)

    # ------------------------------------------------------------ infraestrutura
    def _urls(self) -> list[str]:
        configurada = str(self.obter_config("api.uex_url", URLS_CONHECIDAS[0]) or "").rstrip("/")
        ordem = [u for u in (self._url_boa, configurada, *URLS_CONHECIDAS) if u]
        return list(dict.fromkeys(ordem))  # sem repetidos, mantendo a ordem

    def _cabecalhos(self) -> dict[str, str]:
        token = str(self.obter_config("api.uex_token", "") or "").strip()
        return {"Authorization": f"Bearer {token}"} if token else {}

    def _baixar(self, recurso: str, params: dict[str, Any] | None = None) -> Any:
        ultimo: Exception | None = None
        for base in self._urls():
            try:
                resposta = self.http.obter_json(f"{base}/{recurso}", params, self._cabecalhos())
            except ErroHTTP as e:
                ultimo = e
                # 404 / sem conexão neste endereço: tenta o próximo endereço conhecido
                continue
            if not isinstance(resposta, dict):
                raise ErroUEX(f"Resposta inesperada da UEX em {recurso}.")
            status = resposta.get("status")
            if status != "ok":
                msg = resposta.get("message") or status or "erro desconhecido"
                if status == "requests_limit_reached":
                    raise ErroUEX("Limite de requisições da UEX atingido. Tente de novo em 1 minuto.")
                raise ErroUEX(f"UEX recusou {recurso}: {msg}")
            self._url_boa = base
            return resposta.get("data")
        raise ErroUEX(f"Não foi possível falar com a UEX: {ultimo}")

    def _com_cache(self, chave: str, ttl: float, forcar: bool, baixar: Callable[[], Any]) -> ResultadoAPI:
        entrada: EntradaCache | None = self.cache.ler(chave)
        if entrada and not forcar and entrada.valida(ttl):
            return ResultadoAPI(entrada.dados, entrada.obtido_em, do_cache=True)
        try:
            dados = baixar()
        except (ErroUEX, ErroHTTP) as erro:
            if entrada:
                log.warning("Usando cache antigo de %s (%.0f min): %s", chave, entrada.idade_s / 60, erro)
                return ResultadoAPI(entrada.dados, entrada.obtido_em, do_cache=True, desatualizado=True,
                                    aviso=f"UEX indisponível ({erro}). Mostrando dados salvos.")
            raise ErroUEX(str(erro)) from erro
        nova = self.cache.gravar(chave, dados)
        log.info("UEX: %s atualizado (%d itens)", chave, len(dados) if hasattr(dados, "__len__") else 1)
        return ResultadoAPI(nova.dados, nova.obtido_em)

    # ------------------------------------------------------------ recursos
    def precos_todos(self, forcar: bool = False) -> ResultadoAPI:
        return self._com_cache("uex:commodities_prices_all", TTL_PRECOS, forcar,
                               lambda: self._baixar("commodities_prices_all") or [])

    def terminais(self, forcar: bool = False) -> ResultadoAPI:
        return self._com_cache("uex:terminals", TTL_CADASTROS, forcar,
                               lambda: self._baixar("terminals") or [])

    def naves(self, forcar: bool = False) -> ResultadoAPI:
        return self._com_cache("uex:vehicles", TTL_CADASTROS, forcar,
                               lambda: self._baixar("vehicles") or [])

    def refinarias_rendimento(self, forcar: bool = False) -> ResultadoAPI:
        """Bônus de rendimento (%) por refinaria e minério. A UEX atualiza ~1x por mês."""
        return self._com_cache("uex:refineries_yields", TTL_CADASTROS, forcar,
                               lambda: self._baixar("refineries_yields") or [])

    def recurso(self, nome: str, ttl: float = TTL_CADASTROS, forcar: bool = False,
                params: dict[str, Any] | None = None) -> ResultadoAPI:
        """Qualquer recurso GET da UEX que não precisa de filtro (ex.: "refineries_methods")."""
        chave = f"uex:{nome}" + (f":{sorted(params.items())}" if params else "")
        return self._com_cache(chave, ttl, forcar, lambda: self._baixar(nome, params) or [])

    @staticmethod
    def _chave_distancia(a: int, b: int) -> str:
        a, b = sorted((int(a), int(b)))  # distância é simétrica: um registro por par
        return f"uex:dist:{a}:{b}"

    def distancias(self, pares: list[tuple[int, int]], paralelo: int = 4) -> dict[tuple[int, int], float | None]:
        """Distância (Gm) para cada par de terminais. None = desconhecida.

        Usa o cache (12 h) e só baixa o que falta, com algumas requisições em paralelo.
        """
        unicos = {tuple(sorted((int(a), int(b)))) for a, b in pares if a and b and a != b}
        chaves = {par: self._chave_distancia(*par) for par in unicos}
        em_cache = self.cache.ler_varios(list(chaves.values()))

        resultado: dict[tuple[int, int], float | None] = {}
        faltando: list[tuple[int, int]] = []
        for par, chave in chaves.items():
            entrada = em_cache.get(chave)
            if entrada and entrada.valida(TTL_DISTANCIAS):
                resultado[par] = entrada.dados
            else:
                faltando.append(par)

        def baixar(par: tuple[int, int]) -> tuple[tuple[int, int], float | None]:
            try:
                dados = self._baixar("terminals_distances",
                                     {"id_terminal_origin": par[0], "id_terminal_destination": par[1]})
                item = dados[0] if isinstance(dados, list) and dados else dados
                dist = float(item.get("distance")) if isinstance(item, dict) and item.get("distance") is not None else None
            except (ErroUEX, ErroHTTP, ValueError, TypeError) as erro:
                log.debug("Distância %s indisponível: %s", par, erro)
                antiga = em_cache.get(chaves[par])
                return par, (antiga.dados if antiga else None)
            self.cache.gravar(chaves[par], dist)
            return par, dist

        if faltando:
            log.info("Buscando %d distância(s) na UEX", len(faltando))
            with ThreadPoolExecutor(max_workers=max(1, paralelo)) as pool:
                for par, dist in pool.map(baixar, faltando):
                    resultado[par] = dist

        # Devolve nas duas direções, para facilitar a consulta
        completo: dict[tuple[int, int], float | None] = {}
        for (a, b), dist in resultado.items():
            completo[(a, b)] = completo[(b, a)] = dist
        return completo
