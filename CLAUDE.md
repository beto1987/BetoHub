# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Star Citizen Beto Hub: a modular Windows desktop helper for Star Citizen (Python 3.13, PySide6). It only reads the screen (OCR) and community APIs (UEX Corp API 2.0 and the Star Citizen Wiki API). It never modifies game files or injects code. Global hotkeys poll `GetAsyncKeyState` every 25 ms and use no keyboard hook. Keep it that way.

The code, identifiers, comments, UI strings and user docs (`LEIA-ME.md`) are in **Brazilian Portuguese**. Follow that convention: `controlador`, `logica`, `aba`, `migracoes`, `publicar`/`assinar` and so on.

## Commands

All commands use the project venv in `.venv` (created by `instalar.bat`).

```powershell
.venv\Scripts\python main.py                                 # run with console logs (same as debug.bat)
.venv\Scripts\python -m pytest -v tests                      # all tests (same as testar.bat)
.venv\Scripts\python -m pytest tests/test_comercio.py        # one file
.venv\Scripts\python -m pytest tests/test_comercio.py -k rota  # one test by name
.venv\Scripts\python -m pip install -r requirements.txt
```

There is no linter or formatter configured. `tests/conftest.py` puts the repo root on `sys.path`, so tests import `beto_hub.*` and `plugins.*` directly.

## User data locations (outside the repo)

- Config: `%APPDATA%\BetoHub\config.toml`. It is edited with `tomlkit`, which preserves comments. Missing defaults are merged in. A broken file is backed up as `config.toml.corrompido-<date>` and recreated.
- SQLite DB: `%LOCALAPPDATA%\BetoHub\hub.db`. Logs: `%LOCALAPPDATA%\BetoHub\logs\betohub.log`. Per-module data: `%LOCALAPPDATA%\BetoHub\modulos\<id>\`.
- `beto_hub/core/paths.py` resolves all of these. It also handles a PyInstaller-frozen build through `sys._MEIPASS`.

## Architecture

**Startup** (`beto_hub/app.py`, `HubApp._montar`): logs, then QApplication with a single-instance lock, then config and theme, then `BancoDados`, `BarramentoEventos` and `GerenciadorTarefas`, then the shared services dict (`"cache"`, `"uex"`, `"wiki"`), then the overlay and tray, then plugins, then the main window, then hotkeys.

**Plugins** (`plugins/<id>/`) are the unit of features. Each one has a `manifest.toml` (`id`, `nome`, `versao`, `ordem`, optional `api_minima`/`modulo`/`classe`) and a `plugin.py` with `class Plugin(BasePlugin)`. The contract lives in `beto_hub/core/plugin_base.py`:
- `migracoes()` returns a list of SQL strings, and a string's position in the list is its schema version. Never edit a published migration. Append new ones at the end. Tables must be prefixed with the plugin id (`comercio_*`, ...).
- Hooks: `setup(ctx)`, `criar_aba` (required), `criar_painel_overlay`, `criar_painel_config` with `aplicar_config`, and `encerrar`.
- `HubContext` (`self.ctx`) is the plugin's only access to the app: `config`, `banco`, `eventos`, `workers`, `log`, `notificar`, `pasta_dados`, `servico(name)`, and `opcao`/`salvar_opcoes` for the plugin's own `[modulos.<id>]` config section.
- `plugin_loader.py` isolates failures. A plugin that raises during import, migration or setup becomes an error tab and the app keeps running. Raise `API_VERSAO` only for incompatible contract changes.
- Plugins never import each other. They talk over the event bus with names like `"<target_plugin>.<action>"`, for example `log_capitao.registrar_viagem`, `log_capitao.registrar_refino`, and `hub.mostrar_aba`, which the app handles.
- `frota.nave_ativa` is a broadcast in the other direction. Frota publishes it when the user picks an active ship, with `{"nome", "uuid", "chaves", "carga_scu", "minerio_scu"}`. `comercio` and `mineracao` subscribe and select the same ship. They match it by comparing `beto_hub.core.texto.chave_nome(<their ship name>)` against `chaves`. Use `chave_nome` whenever names from different sources (UEX, Wiki, local JSON) must be compared.
- Status: `comercio`, `mineracao`, `refino`, `frota` and `log_capitao` are implemented. `contratos` is an "em construção" stub.

**Internal layout of a full plugin** (for example `comercio`, `mineracao`, `refino`):
- `logica/`: pure Python with no Qt, no network and no I/O. Most tests target this layer.
- `controlador.py`: a QObject that fetches data (UEX through `ctx.servico("uex")`), runs heavy work on `ctx.workers`, and emits Qt signals to the UI.
- `ui/`: widgets (`aba.py` for the main tab, `overlay.py` for the overlay panel, plus config and dialogs). `plugin.py` imports them lazily inside the `criar_*` methods.

**Threading rules:**
- Nothing slow runs on the UI thread. `GerenciadorTarefas.executar(fn, *args, ao_concluir=..., ao_falhar=...)` runs work on a QThreadPool and delivers callbacks on the UI thread.
- `BarramentoEventos.publicar` can be called from any thread, and its callbacks always run on the UI thread through a queued Qt signal.
- `BancoDados` uses one SQLite connection (WAL, autocommit) behind an RLock, so it is safe from worker threads. Use `banco.transacao()` for multi-statement writes.
- `plugin_base.py` must not import Qt at module top level, so manifest validation stays testable without a GUI.

**Services** (`beto_hub/services/`):
- `ClienteHTTP` handles rate limiting (100 requests/min) and retries.
- `CacheAPI` is a SQLite-backed cache with TTLs. It uses the `nucleo` migrations.
- `ClienteUEX` provides `precos_todos`, `terminais`, `naves`, `refinarias_rendimento` and `distancias`, with cache and a `forcar` refresh.
- UEX payloads drift (for example, `refineries_audits.method` arrives as a name such as `"dinyx_solventation"`, not an id). Parse defensively, and catch errors in controller callbacks so a tab shows an error instead of hanging on "Carregando…".
- `ClienteWiki.naves()` pages through `api.star-citizen.wiki/api/v2/vehicles`, 50 ships per page (the maximum). Each ship is about 60 KB, so `resumir_nave` keeps only the whitelisted `CAMPOS_NAVE` before caching, about 0.7 MB for all ships. To use a new Wiki field, add it to `CAMPOS_NAVE`. The cache TTL is 24 h, so the new field appears after the next refresh.
- `ocr/` covers screen capture (`mss`), preprocessing (Pillow), the engine and foreground-window detection. The engine uses Windows OCR (`winocr`) and can fall back to Tesseract. Each thread must create its own `MotorOCR`, because winocr runs its own asyncio loop.

**Mining scanner** (`plugins/mineracao/scanner.py`):
- It runs a background thread that reads a screen region about every 250 ms.
- It skips the read when the frame is unchanged, and it only accepts a value after reading the same value twice in a row.
- Static game data (ores, signatures, a fallback refinery list) lives in `plugins/mineracao/data/*.json`.
- `tests/test_scanner_thread.py` drives the scanner with a fake capturer and a fake OCR, so it needs neither Windows nor winocr.

**Frota data** (`plugins/frota/logica/naves.py`): the Wiki list includes display models (`*_Display`), mission variants (`_Boarded`, `_TEMP_`) and repeated names (Best in Show paints). `fichas_de_wiki` filters those out, keeps one entry per identical stat set, and adds a suffix to variants that share a name but differ in stats. The hangar stores the Wiki `uuid` and the ship name as a fallback. All stats describe the stock loadout. Loadout editing is not implemented.

**UI smoke testing**: a running Hub holds a single-instance lock. To exercise the real UI without touching it, point `APPDATA` and `LOCALAPPDATA` at a temp dir, then set `QT_QPA_PLATFORM=offscreen` and `QT_QPA_FONTDIR=C:/Windows/Fonts` (without the font dir, text renders as boxes). Build `HubApp(argv)._montar()`, drive the widgets, and save screenshots with `widget.grab().save(...)`.

**UI** (`beto_hub/ui/`):
- `main_window.py` has one tab per plugin.
- `overlay.py` is a single always-on-top window with one tab per plugin panel, opacity control and a "clique atravessa" (click-through) mode.
- `settings_dialog.py` includes the plugin config panels and hotkey capture.
- The theme is in `theme/scifi.qss`, with the `CORES` palette in `theme/__init__.py`.
