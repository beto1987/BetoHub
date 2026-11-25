"""Descobre se o Star Citizen é a janela em primeiro plano (Windows).

Só consulta qual janela está ativa e o nome do executável dela
(GetForegroundWindow / QueryFullProcessImageName). Não abre o processo para
leitura de memória e não interage com o jogo.
"""

from __future__ import annotations

import os
import sys

EXECUTAVEIS = {"starcitizen.exe"}
TITULOS = ("star citizen",)

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    _cache: dict[int, bool] = {}  # pid -> é o jogo?

    def _exe_do_pid(pid: int) -> str:
        h = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            tam = wintypes.DWORD(len(buf))
            if _kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(tam)):
                return os.path.basename(buf.value).lower()
            return ""
        finally:
            _kernel32.CloseHandle(h)

    def jogo_em_primeiro_plano() -> bool:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return False
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in _cache:
            return _cache[pid.value]
        eh_jogo = _exe_do_pid(pid.value) in EXECUTAVEIS
        if not eh_jogo:  # plano B: título da janela
            buf = ctypes.create_unicode_buffer(256)
            _user32.GetWindowTextW(hwnd, buf, 256)
            eh_jogo = buf.value.strip().lower() in TITULOS
        if len(_cache) > 200:
            _cache.clear()
        _cache[pid.value] = eh_jogo
        return eh_jogo
else:
    def jogo_em_primeiro_plano() -> bool:  # fora do Windows (desenvolvimento)
        return True
