"""Estruturas de dados do Comércio, montadas a partir das respostas da UEX."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _int(v: Any, padrao: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return padrao


def _float(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f


def _txt(v: Any) -> str:
    return "" if v is None else str(v)


@dataclass(frozen=True)
class Terminal:
    id: int
    nome: str
    apelido: str
    sistema: str
    planeta: str
    orbita: str
    eh_estacao: bool
    eh_outpost: bool
    eh_nqa: bool
    eh_jogador: bool
    disponivel: bool

    @property
    def rotulo(self) -> str:
        """Nome curto para tabelas."""
        return self.apelido or self.nome

    @property
    def descricao(self) -> str:
        """Nome completo com localização, para dicas (tooltips)."""
        partes = [p for p in (self.nome, self.orbita or self.planeta, self.sistema) if p]
        return " · ".join(dict.fromkeys(partes))

    @property
    def tipo_local(self) -> str:
        if self.eh_estacao:
            return "estação"
        if self.eh_outpost:
            return "outpost"
        return "superfície"

    @classmethod
    def de_uex(cls, d: dict[str, Any]) -> "Terminal":
        disponivel = d.get("is_available_live", d.get("is_available", 1))
        return cls(
            id=_int(d.get("id")),
            nome=_txt(d.get("fullname") or d.get("name")),
            apelido=_txt(d.get("nickname") or d.get("displayname") or d.get("name")),
            sistema=_txt(d.get("star_system_name")),
            planeta=_txt(d.get("planet_name")),
            orbita=_txt(d.get("orbit_name")),
            eh_estacao=_int(d.get("id_space_station")) > 0,
            eh_outpost=_int(d.get("id_outpost")) > 0,
            eh_nqa=_int(d.get("is_nqa")) == 1,
            eh_jogador=_int(d.get("is_player_owned")) == 1,
            disponivel=_int(disponivel, 1) == 1,
        )


@dataclass(frozen=True)
class Preco:
    id_mercadoria: int
    mercadoria: str
    id_terminal: int
    compra: float | None        # preço que o terminal COBRA (você compra)
    venda: float | None         # preço que o terminal PAGA (você vende)
    estoque_compra: float | None  # SCU disponível para comprar (último reportado ou média)
    atualizado_em: int          # epoch do último reporte

    @classmethod
    def de_uex(cls, d: dict[str, Any]) -> "Preco":
        estoque = _float(d.get("scu_buy")) or _float(d.get("scu_buy_avg"))
        return cls(
            id_mercadoria=_int(d.get("id_commodity")),
            mercadoria=_txt(d.get("commodity_name")),
            id_terminal=_int(d.get("id_terminal")),
            compra=_float(d.get("price_buy")) or None,
            venda=_float(d.get("price_sell")) or None,
            estoque_compra=estoque if estoque and estoque > 0 else None,
            atualizado_em=_int(d.get("date_modified")) or _int(d.get("date_added")),
        )


@dataclass(frozen=True)
class Nave:
    id: int
    nome: str
    fabricante: str
    scu: int

    @property
    def rotulo(self) -> str:
        return f"{self.nome} ({self.scu} SCU)"

    @classmethod
    def de_uex(cls, d: dict[str, Any]) -> "Nave":
        return cls(
            id=_int(d.get("id")),
            nome=_txt(d.get("name_full") or d.get("name")),
            fabricante=_txt(d.get("company_name")),
            scu=int(_float(d.get("scu")) or 0),
        )


@dataclass
class ParametrosBusca:
    scu: int
    capital: float
    sistema: str = ""             # "" = todos os sistemas
    id_origem: int | None = None  # terminal onde você está (None = qualquer)
    entre_sistemas: bool = False  # incluir rotas que mudam de sistema
    ignorar_jogadores: bool = True


@dataclass
class Rota:
    id_mercadoria: int
    mercadoria: str
    origem: Terminal
    destino: Terminal
    preco_compra: float
    preco_venda: float
    scu: int
    limitado_por: str             # "nave", "capital" ou "estoque"
    atualizado_origem: int
    atualizado_destino: int
    distancia: float | None = None   # Gm
    eficiencia: float | None = None  # aUEC de lucro por Gm
    risco: int = 0
    nivel_risco: str = "baixo"
    motivos_risco: list[str] = field(default_factory=list)

    @property
    def investimento(self) -> float:
        return self.scu * self.preco_compra

    @property
    def lucro(self) -> float:
        return self.scu * (self.preco_venda - self.preco_compra)

    @property
    def margem_pct(self) -> float:
        return (self.preco_venda / self.preco_compra - 1) * 100 if self.preco_compra else 0.0

    @property
    def entre_sistemas(self) -> bool:
        return self.origem.sistema != self.destino.sistema

    def para_log(self) -> dict[str, Any]:
        """Dados para pré-preencher uma viagem no Log do Capitão."""
        return {
            "mercadoria": self.mercadoria,
            "origem": self.origem.rotulo,
            "destino": self.destino.rotulo,
            "scu": self.scu,
            "preco_compra": self.preco_compra,
            "preco_venda": self.preco_venda,
        }
