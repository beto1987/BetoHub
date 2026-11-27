<#
Gera o instalador do StarHub: testes -> PyInstaller -> (assinatura) -> Inno Setup.

    powershell -ExecutionPolicy Bypass -File instalador\compilar.ps1
    powershell -ExecutionPolicy Bypass -File instalador\compilar.ps1 -SemTestes

Resultado: build\instalador\StarHub-<versao>-Setup.exe

Assinatura digital (opcional): defina UMA das opcoes antes de rodar.
  - Certificado em arquivo .pfx:
        $env:STARHUB_CERT_PFX   = "C:\caminho\certificado.pfx"
        $env:STARHUB_CERT_SENHA = "senha do pfx"
  - Certificado instalado no Windows (token USB / EV, ou importado), pela impressao digital:
        $env:STARHUB_CERT_THUMBPRINT = "ABCDEF0123..."
  Opcional: $env:STARHUB_TIMESTAMP = "http://timestamp.digicert.com" (padrao)
Sem nenhuma delas, o instalador sai sem assinatura (o Windows mostra o aviso do SmartScreen).
#>
param([switch]$SemTestes)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
$py = Join-Path $raiz ".venv\Scripts\python.exe"

$versao = (& $py -c "import beto_hub; print(beto_hub.__version__)").Trim()
Write-Host "== StarHub $versao" -ForegroundColor Cyan

if (-not $SemTestes) {
    Write-Host "== Testes"
    & $py -m pytest -q tests
    if ($LASTEXITCODE -ne 0) { throw "Os testes falharam: o instalador nao foi gerado." }
}

Write-Host "== PyInstaller"
& $py -m PyInstaller --noconfirm --clean --distpath build\dist --workpath build\work instalador\starhub.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou." }

# ---- ferramentas
$iscc = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 nao encontrado (winget install JRSoftware.InnoSetup)." }

# ---- assinatura (opcional)
$argsCert = $null
if ($env:STARHUB_CERT_PFX) {
    $argsCert = "/f `"$env:STARHUB_CERT_PFX`" /p `"$env:STARHUB_CERT_SENHA`""
} elseif ($env:STARHUB_CERT_THUMBPRINT) {
    $argsCert = "/sha1 $env:STARHUB_CERT_THUMBPRINT"
}
$argsIscc = @("/DAppVersion=$versao")
if ($argsCert) {
    $signtool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" |
        Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
    if (-not $signtool) { throw "signtool.exe nao encontrado (Windows SDK)." }
    $ts = if ($env:STARHUB_TIMESTAMP) { $env:STARHUB_TIMESTAMP } else { "http://timestamp.digicert.com" }
    $assinar = "`"$signtool`" sign /fd sha256 /tr $ts /td sha256 $argsCert"
    Write-Host "== Assinando StarHub.exe"
    cmd /c "$assinar `"build\dist\StarHub\StarHub.exe`""
    if ($LASTEXITCODE -ne 0) { throw "A assinatura do StarHub.exe falhou." }
    $argsIscc += "/DASSINAR"
    $argsIscc += "/Sstarhub=$assinar `$f"
} else {
    Write-Host "== Sem certificado: o instalador sai SEM assinatura digital" -ForegroundColor Yellow
}

Write-Host "== Inno Setup"
& $iscc @argsIscc "instalador\starhub.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup falhou." }

$setup = Join-Path $raiz "build\instalador\StarHub-$versao-Setup.exe"
if ($argsCert) {
    & $signtool verify /pa $setup
}
$hash = (Get-FileHash $setup -Algorithm SHA256).Hash
Write-Host "== Pronto: $setup" -ForegroundColor Green
Write-Host "   SHA-256: $hash"
