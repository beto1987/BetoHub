"""Cliente da API da Star Citizen Wiki (api.star-citizen.wiki), dados extraídos do jogo.

- Pública, sem token. Lista paginada: {"data": [...], "meta": {"last_page": N, ...}}.
- Cada nave vem com ~60 KB (encaixes, imagens, traduções). Guardamos no cache só
  os campos que o Hub usa (ver CAMPOS_NAVE), o que reduz a lista de ~17 MB para ~0,5 MB.
- Validade: 24 h. Se a API falhar e houver cache vencido, devolve o cache com aviso.
- Métodos bloqueiam (rede): chame-os pelos workers, nunca na thread da interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from beto_hub.core.i18n import tr
from ..core.logging_setup import obter_logger
from .api_cache import CacheAPI
from .http_client import ClienteHTTP, ErroHTTP
from .uex_api import ResultadoAPI

log = obter_logger("wiki")

URL_BASE = "https://api.star-citizen.wiki/api/v2"
TTL_NAVES = 24 * 3600
POR_PAGINA = 50     # máximo aceito pela API
MAX_PAGINAS = 40    # trava de segurança (hoje são 7 páginas)

# Campos de cada nave mantidos no cache. Os demais (ports, images, parts...) são descartados.
CAMPOS_NAVE = (
    "uuid", "name", "game_name", "slug", "class_name", "manufacturer", "is_spaceship", "is_vehicle",
    "size", "size_class", "career", "role", "type", "foci", "production_status", "crew",
    "cargo_capacity", "ore_capacity", "health", "shield", "armor", "speed", "agility", "quantum",
    "weaponry", "insurance", "msrp", "uex_prices", "version",
)
_CAMPOS_ESCUDO = ("hp", "regeneration", "regeneration_time", "face_type")
_CAMPOS_PRECO = ("price_buy", "price_rent", "terminal_name", "date_updated")


class ErroWiki(Exception):
    pass


def resumir_nave(d: dict[str, Any]) -> dict[str, Any]:
    """Só os campos de CAMPOS_NAVE, com escudo, armadura e preços enxutos."""
    r = {k: d.get(k) for k in CAMPOS_NAVE}
    if isinstance(r["manufacturer"], dict):
        r["manufacturer"] = {k: r["manufacturer"].get(k) for k in ("name", "code")}
    if isinstance(r["shield"], dict):
        r["shield"] = {k: r["shield"].get(k) for k in _CAMPOS_ESCUDO}
    if isinstance(r["armor"], dict):
        r["armor"] = {"health": r["armor"].get("health")}
    if isinstance(r["uex_prices"], dict):
        r["uex_prices"] = {
            tipo: [{k: p.get(k) for k in _CAMPOS_PRECO} | {"star_system_name": (p.get("starmap_location") or {}).get("star_system_name")}
                   for p in (r["uex_prices"].get(tipo) or []) if isinstance(p, dict)]
            for tipo in ("purchase", "rental")
        }
    return r


@dataclass
class ClienteWiki:
    http: ClienteHTTP
    cache: CacheAPI
    url_base: str = URL_BASE

    def _pagina(self, numero: int) -> tuple[list[dict[str, Any]], int]:
        resposta = self.http.obter_json(
            f"{self.url_base}/vehicles", {"page[size]": POR_PAGINA, "page[number]": numero})
        if not isinstance(resposta, dict) or not isinstance(resposta.get("data"), list):
            raise ErroWiki(tr("Resposta inesperada da API da Star Citizen Wiki."))
        ultima = int((resposta.get("meta") or {}).get("last_page") or numero)
        return resposta["data"], ultima

    def _baixar_naves(self) -> list[dict[str, Any]]:
        naves: list[dict[str, Any]] = []
        numero, ultima = 1, 1
        while numero <= min(ultima, MAX_PAGINAS):
            dados, ultima = self._pagina(numero)
            naves.extend(resumir_nave(d) for d in dados if isinstance(d, dict))
            numero += 1
        if not naves:
            raise ErroWiki(tr("A API da Star Citizen Wiki não devolveu nenhuma nave."))
        return naves

    def naves(self, forcar: bool = False) -> ResultadoAPI:
        """Todas as naves e veículos, com estatísticas do loadout de fábrica."""
        chave = "wiki:vehicles"
        entrada = self.cache.ler(chave)
        if entrada and not forcar and entrada.valida(TTL_NAVES):
            return ResultadoAPI(entrada.dados, entrada.obtido_em, do_cache=True)
        try:
            dados = self._baixar_naves()
        except (ErroWiki, ErroHTTP) as erro:
            if entrada:
                log.warning("Usando cache antigo de %s (%.0f h): %s", chave, entrada.idade_s / 3600, erro)
                return ResultadoAPI(entrada.dados, entrada.obtido_em, do_cache=True, desatualizado=True,
                                    aviso=tr("Star Citizen Wiki indisponível ({erro}). Mostrando dados salvos.", erro=erro))
            raise ErroWiki(str(erro)) from erro
        nova = self.cache.gravar(chave, dados)
        log.info("Wiki: %s atualizado (%d naves)", chave, len(dados))
        return ResultadoAPI(nova.dados, nova.obtido_em)
