# deploy.ps1 - Despliegue de SkyLearn a produccion desde Windows.
#
# Equivalente a deploy.sh (rsync), pero para un equipo Windows SIN rsync:
# empaqueta el codigo con `git archive` y lo sube con scp, excluyendo los
# datos en vivo.
#
# Se empaqueta el contenido GUARDADO EN GIT (HEAD), no el working tree: en
# Windows core.autocrlf deja los ficheros en CRLF y hay que subirlos con LF,
# como los tendria un clon en Linux. Ademas asi lo desplegado es siempre un
# commit concreto.
#
# NUNCA borra nada del servidor (no hay --delete): solo anade/actualiza.
#
# Uso:
#   .\deploy.ps1 -DryRun    Muestra que se subiria, sin tocar el servidor.
#   .\deploy.ps1            Despliega HEAD (exige el arbol limpio).
#   .\deploy.ps1 -AllowDirty  Idem, aunque haya cambios sin commitear
#                             (se despliega igualmente HEAD, no esos cambios).
#
# Requisitos: git, ssh, scp y tar en el PATH, y acceso SSH al servidor.

[CmdletBinding()]
param(
  [switch]$DryRun,
  [switch]$AllowDirty,
  [string]$Remote = "debian@imaginabit.com",
  [string]$Dest = "/opt/skylearn"
)

$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
$archive = Join-Path $env:TEMP "skylearn-deploy.tar.gz"

# Igual que los --exclude de deploy.sh. Los datos en vivo del servidor
# (.env, db.sqlite3, media/, venv/, staticfiles/) jamas se sobreescriben.
$excludePaths = @(
  ".env", ".server.local.md",
  "db.sqlite3", "db.sqlite3-journal",
  "media", "staticfiles", "venv", ".venv",
  "deploy.sh", "backup.sh", "DEPLOY.md", "deploy.ps1"
)

$branch = (git -C $root rev-parse --abbrev-ref HEAD 2>$null)
$commit = (git -C $root rev-parse --short HEAD 2>$null)
Write-Host ">> Repo:    $root"
Write-Host ">> Rama:    $branch @ $commit"
Write-Host ">> Destino: ${Remote}:${Dest} $(if ($DryRun) { '[dry-run]' })"

$dirty = @(git -C $root status --porcelain)
if ($dirty -and -not $AllowDirty) {
  Write-Host ">> ABORTADO: hay cambios sin commitear y se desplegaria ${commit}:" -ForegroundColor Red
  $dirty | Select-Object -First 10 | ForEach-Object { Write-Host "   $_" }
  Write-Host "   Commitea (y push) o usa -AllowDirty si de verdad quieres desplegar ${commit}." -ForegroundColor Red
  exit 1
}

if (Test-Path $archive) { Remove-Item $archive -Force }

$archiveArgs = @(
  "-C", $root,
  # Hay que forzar LF: en Windows `git archive` tambien convierte a CRLF por
  # core.autocrlf, y el servidor (Linux) espera lo que hay guardado en git.
  "-c", "core.autocrlf=false",
  "-c", "core.eol=lf",
  "archive", "--format=tar.gz", "-o", $archive, "HEAD", "--", "."
)
foreach ($e in $excludePaths) { $archiveArgs += ":(exclude)$e" }
& git @archiveArgs
if ($LASTEXITCODE -ne 0) { throw "git archive ha fallado ($LASTEXITCODE)" }

$items = & tar -tzf $archive
$size = "{0:N1} MB" -f ((Get-Item $archive).Length / 1MB)
Write-Host ">> Paquete: $($items.Count) entradas, $size"

# Comprobacion de fin de linea: si el paquete llevara CRLF, el servidor se
# queda con los ficheros de texto en CRLF (ya paso una vez).
$probe = Join-Path $env:TEMP "skylearn-eol-probe"
Remove-Item -Recurse -Force $probe -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $probe | Out-Null
Push-Location $probe
& tar -xf $archive manage.py
Pop-Location
$bytes = [IO.File]::ReadAllBytes((Join-Path $probe "manage.py"))
Remove-Item -Recurse -Force $probe
if ($bytes -contains 13) {
  Write-Host ">> ABORTADO: el paquete lleva CRLF (manage.py); se subiria mal a Linux." -ForegroundColor Red
  Remove-Item $archive -Force
  exit 1
}

# Comprobaciones: nada de datos en vivo, y presentes las piezas clave.
$forbidden = $items | Where-Object { $_ -match "^(\.env$|\.git/|media/|staticfiles/|venv/|db\.sqlite3|__pycache__)" }
if ($forbidden) {
  Write-Host ">> ABORTADO: el paquete incluiria datos en vivo:" -ForegroundColor Red
  $forbidden | Select-Object -First 10 | ForEach-Object { Write-Host "   $_" }
  Remove-Item $archive -Force
  exit 1
}
$mustExist = @("manage.py", "config/settings.py", "quiz/translation.py", "quiz/fixtures/mf0487_3_repaso.json")
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
  sudo tar -xzf '$remoteTmp' -C '$Dest'
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