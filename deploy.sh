#!/usr/bin/env bash
#
# Despliega SkyLearn (fork imaginabit) en el servidor Rocinante.
#
# Sincroniza SOLO el codigo. NUNCA toca los datos en vivo del servidor:
#   .env, venv/, db.sqlite3, media/, staticfiles/, __pycache__ ...
# (rsync --delete respeta los --exclude: esos ficheros no se borran ni se
#  sobreescriben aunque no existan en el repo.)
#
# Uso:
#   ./deploy.sh             Despliega desde este clon.
#   ./deploy.sh --dry-run   Muestra lo que haria, sin tocar el servidor.
#
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/"
REMOTE="${SKYLEARN_REMOTE:-rocinante}"
DEST="${SKYLEARN_DEST:-/opt/skylearn}"

DRY=""
if [ "${1:-}" = "--dry-run" ]; then
  DRY="--dry-run"
fi

# Rutas del servidor que se protegen (datos en vivo + especificos del servidor).
EXCLUDES=(
  --exclude='.git/'
  --exclude='.env'
  --exclude='venv/'
  --exclude='db.sqlite3'
  --exclude='db.sqlite3-journal'
  --exclude='media/'
  --exclude='staticfiles/'
  --exclude='__pycache__/'
  --exclude='*.pyc'
  --exclude='*.log'
  --exclude='local_note.txt'
  --exclude='datadump.json'
  --exclude='deploy.sh'
  --exclude='DEPLOY.md'
)

echo ">> Repo:    $SRC"
echo ">> Commit:  $(git -C "$SRC" rev-parse --short HEAD 2>/dev/null || echo '?')"
echo ">> Destino: ${REMOTE}:${DEST} ${DRY:+[dry-run]}"

rsync -az --delete "${EXCLUDES[@]}" -e ssh "$SRC" "${REMOTE}:${DEST}/"

if [ -n "$DRY" ]; then
  echo ">> Dry-run: servidor intacto."
  exit 0
fi

echo ">> Permisos + migraciones + estaticos + reinicio"
ssh "$REMOTE" "set -e
  sudo chown -R www-data:www-data '$DEST'
  cd '$DEST'
  sudo -u www-data ./venv/bin/pip install -q -r requirements/base.txt
  sudo -u www-data ./venv/bin/python manage.py migrate --noinput
  sudo -u www-data ./venv/bin/python manage.py compilemessages -l es >/dev/null 2>&1 || true
  sudo -u www-data ./venv/bin/python manage.py collectstatic --noinput >/dev/null
  sudo systemctl restart skylearn
"
echo ">> OK -> https://curso.imaginabit.com"
