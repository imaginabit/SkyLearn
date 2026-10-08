# deploy.ps1 - Despliegue de SkyLearn a produccion desde Windows.
#
# Equivalente a deploy.sh (rsync), pero para un equipo Windows SIN rsync:
# empaqueta el codigo con tar y lo sube con scp, excluyendo los datos en vivo.
#
# NUNCA borra nada del servidor (no hay --delete): solo anade/actualiza.
#
# Uso:
#   .\deploy.ps1 -DryRun    Muestra que se subiria, sin tocar el servidor.
#   .\deploy.ps1            Despliega de verdad.
#
# Requisitos: ssh/scp/tar en el PATH y acceso SSH al servidor (usuario debian).

[CmdletBinding()]
param(
  [switch]$DryRun,
  [string]$Remote = "debian@imaginabit.com",
  [string]$Dest = "/opt/skylearn"
)

$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
$archive = Join-Path $env:TEMP "skylearn-deploy.tar.gz"

# Igual que los --exclude de deploy.sh. Los datos en vivo del servidor
# (.env, db.sqlite3, media/, venv/, staticfiles/) jamas se sobreescriben.
$excludes = @(
  "./.git", "./.git/*",
  "./.venv", "./.venv/*",
  "./venv", "./venv/*",
  "./.env",
  "./db.sqlite3",
  "./db.sqlite3-journal",
  "./media", "./media/*",
  "./staticfiles", "./staticfiles/*",
  "./__pycache__", "./__pycache__/*",
  "*/__pycache__", "*/__pycache__/*",
  "./*.pyc", "./*.log",
  "./local_note.txt",
  "./datadump.json",
  "./deploy.sh",
  "./backup.sh",
  "./DEPLOY.md",
  "./deploy.ps1",
  "./.server.local.md"
)

$commit = (git -C $root rev-parse --short HEAD 2>$null)
Write-Host ">> Repo:    $root"
Write-Host ">> Rama:    $(git -C $root rev-parse --abbrev-ref HEAD) @ $commit"
Write-Host ">> Destino: ${Remote}:${Dest} $(if ($DryRun) { '[dry-run]' })"

if (Test-Path $archive) { Remove-Item $archive -Force }

$tarArgs = @("-czf", $archive)
foreach ($e in $excludes) { $tarArgs += "--exclude=$e" }
$tarArgs += @("-C", $root, ".")
& tar @tarArgs
if ($LASTEXITCODE -ne 0) { throw "tar ha fallado ($LASTEXITCODE)" }

$items = & tar -tzf $archive
$size = "{0:N1} MB" -f ((Get-Item $archive).Length / 1MB)
Write-Host ">> Paquete: $($items.Count) entradas, $size"

# Comprobaciones: nada de datos en vivo, y presentes las piezas clave.
$forbidden = $items | Where-Object { $_ -match "^(\./)?(\.env$|\.git/|media/|staticfiles/|venv/|db\.sqlite3|__pycache__)" }
if ($forbidden) {
  Write-Host ">> ABORTADO: el paquete incluiria datos en vivo:" -ForegroundColor Red
  $forbidden | Select-Object -First 10 | ForEach-Object { Write-Host "   $_" }
  Remove-Item $archive -Force
  exit 1
}
$mustExist = @("./manage.py", "./config/settings.py", "./quiz/translation.py", "./quiz/fixtures/mf0487_3_repaso.json")
$missing = $mustExist | Where-Object { $items -notcontains $_ }
if ($missing) {
  Write-Host ">> ABORTADO: faltan ficheros en el paquete: $($missing -join ', ')" -ForegroundColor Red
  Remove-Item $archive -Force
  exit 1
}

if ($DryRun) {
  Write-Host ">> Dry-run: servidor intacto. Se subiria el paquete y se reiniciaria skylearn."
  Remove-Item $archive -Force
  exit 0
}

$remoteTmp = "/tmp/skylearn-deploy.tar.gz"
Write-Host ">> Subiendo paquete (scp)..."
& scp $archive "${Remote}:$remoteTmp"
if ($LASTEXITCODE -ne 0) { throw "scp ha fallado ($LASTEXITCODE)" }

Write-Host ">> Desempaquetando + permisos + migraciones + estaticos + reinicio"
& ssh $Remote "set -e
  sudo tar -xzf '$remoteTmp' -C '$Dest' --chown=www-data:www-data
  rm -f '$remoteTmp'
  sudo chown -R www-data:www-data '$Dest'
  cd '$Dest'
  sudo -u www-data ./venv/bin/pip install -q -r requirements/base.txt
  sudo -u www-data ./venv/bin/python manage.py migrate --noinput
  sudo -u www-data ./venv/bin/python manage.py compilemessages -l es >/dev/null 2>&1 || true
  sudo -u www-data ./venv/bin/python manage.py collectstatic --noinput >/dev/null
  sudo systemctl restart skylearn
"
if ($LASTEXITCODE -ne 0) { throw "ssh ha fallado ($LASTEXITCODE)" }

Remove-Item $archive -Force
Write-Host ">> OK -> https://curso.imaginabit.com"