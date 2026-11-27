"""Traduções da interface: núcleo (beto_hub.core.i18n) e arquivos beto_hub/i18n/<idioma>.json.

`chaves_do_codigo()` acha todos os textos marcados com tr("...") ou N_("...") no código,
os nomes dos módulos (manifest.toml) e os textos das assinaturas de mineração.
Cada idioma precisa traduzir todas, sem chaves sobrando, com os mesmos campos {nome}.
"""

from __future__ import annotations

import ast
import json
import tomllib
from pathlib import Path

import pytest

from beto_hub.core import i18n

RAIZ = Path(__file__).resolve().parents[1]
IDIOMAS_TRADUZIDOS = [c for c in i18n.IDIOMAS if c != i18n.PADRAO]


def chaves_do_codigo() -> set[str]:
    chaves: set[str] = set()
    for arq in [*RAIZ.glob("beto_hub/**/*.py"), *RAIZ.glob("plugins/**/*.py")]:
        for no in ast.walk(ast.parse(arq.read_text(encoding="utf-8"))):
            if (isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id in ("tr", "N_")
                    and no.args and isinstance(no.args[0], ast.Constant) and isinstance(no.args[0].value, str)):
                chaves.add(no.args[0].value)
    for manifesto in RAIZ.glob("plugins/*/manifest.toml"):
        with open(manifesto, "rb") as f:
            chaves.add(tomllib.load(f)["nome"])
    assinaturas = json.loads((RAIZ / "plugins/mineracao/data/signatures.json").read_text(encoding="utf-8"))
    for s in assinaturas["signatures"]:
        for campo in ("rarity", "category", "note"):
            if s.get(campo):
                chaves.add(s[campo])
    return chaves


@pytest.fixture(autouse=True)
def _volta_para_portugues():
    yield
    i18n.definir_idioma("pt-BR")


def test_tr_traduz_formata_e_cai_no_original():
    i18n.definir_idioma("en-US")
    assert i18n.tr("Sair") == "Exit"
    assert i18n.tr("{n} rotas", n=3) == "3 routes"
    assert i18n.tr("Texto que não existe {x}", x=1) == "Texto que não existe 1"
    assert i18n.tr("Atalho mal formado: '{texto}'.", texto="Ctrl++")  # campo com o nome do parâmetro
    assert i18n.N_("Sair") == "Sair"                                   # N_ só marca, não traduz
    assert i18n.definir_idioma("xx") == "pt-BR" and i18n.tr("Sair") == "Sair"


def test_numeros_e_datas_por_idioma():
    esperado = {"pt-BR": "12.345,6", "es": "12.345,6", "it": "12.345,6", "fr": "12 345,6", "en-US": "12,345.6"}
    for codigo, texto in esperado.items():
        i18n.definir_idioma(codigo)
        assert i18n.numero(12345.6, 1) == texto
    assert i18n.numero(None) == "—"
    i18n.definir_idioma("en-US")
    assert i18n.formato_data_qt().startswith("MM/dd")


def test_idioma_do_config(tmp_path):
    arq = tmp_path / "config.toml"
    arq.write_text('[geral]\nidioma = "fr"\n', encoding="utf-8")
    assert i18n.idioma_do_config(arq) == "fr"
    assert i18n.idioma_do_config(tmp_path / "nao_existe.toml") == "pt-BR"


@pytest.mark.parametrize("codigo", IDIOMAS_TRADUZIDOS)
def test_arquivo_de_traducao_completo(codigo):
    arquivo = i18n.PASTA / f"{codigo}.json"
    traducoes = json.loads(arquivo.read_text(encoding="utf-8"))
    chaves = chaves_do_codigo()
    faltando = sorted(chaves - set(traducoes))
    sobrando = sorted(set(traducoes) - chaves)
    vazias = sorted(k for k, v in traducoes.items() if not str(v).strip())
    campos_errados = sorted(k for k, v in traducoes.items()
                            if k in chaves and i18n.campos_do_texto(k) != i18n.campos_do_texto(v))
    assert not faltando, f"{codigo}: {len(faltando)} sem tradução, ex.: {faltando[:5]}"
    assert not sobrando, f"{codigo}: {len(sobrando)} chaves que o código não usa mais, ex.: {sobrando[:5]}"
    assert not vazias, f"{codigo}: traduções vazias: {vazias[:5]}"
    assert not campos_errados, f"{codigo}: campos {{...}} diferentes do original: {campos_errados[:5]}"


def test_idioma_do_instalador_vale_uma_vez(tmp_path):
    programa, config = tmp_path / "programa", tmp_path / "config.toml"
    programa.mkdir()
    assert i18n.escolher_idioma(config, programa) == ("pt-BR", None)          # sem config nem instalador
    (programa / i18n.ARQUIVO_INSTALACAO).write_text("fr\n", encoding="utf-8")
    codigo, pendente = i18n.escolher_idioma(config, programa)
    assert codigo == "fr" and pendente[0] == "fr"                             # instalação nova: vale o instalador
    config.write_text(f'[geral]\nidioma = "it"\nidioma_instalador = "{pendente[1]}"\n', encoding="utf-8")
    assert i18n.escolher_idioma(config, programa) == ("it", None)             # já aplicado: vale o config
    (programa / i18n.ARQUIVO_INSTALACAO).write_text("xx", encoding="utf-8")
    assert i18n.escolher_idioma(config, programa) == ("it", None)             # código inválido: ignora


def test_config_com_bom(tmp_path):
    arq = tmp_path / "config.toml"
    arq.write_text('[geral]\nidioma = "es"\n', encoding="utf-8-sig")   # Bloco de Notas antigo / PowerShell
    assert i18n.idioma_do_config(arq) == "es"
    assert i18n.escolher_idioma(arq, tmp_path)[0] == "es"
