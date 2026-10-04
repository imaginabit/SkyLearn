#!/usr/bin/env bash
#
# Copia de seguridad de SkyLearn: descarga la base de datos y los ficheros
# subidos (media/) del servidor a este equipo, con marca de tiempo.
#
# La BD se copia con la API de backup de SQLite (instantanea consistente aunque
# la app este en marcha), no copiando el fichero a pelo.
#
# Uso:
#   ./backup.sh
#
# Variables opcionales:
#   SKYLEARN_REMOTE       alias ssh del servidor   (por defecto: rocinante)
#   SKYLEARN_DEST         ruta en el servidor      (por defecto: /opt/skylearn)
#   SKYLEARN_BACKUP_DIR   destino local            (por defecto: ~/backups/skylearn)
#   SKYLEARN_BACKUP_KEEP  copias a conservar       (por defecto: 7)
#
set -euo pipefail

REMOTE="${SKYLEARN_REMOTE:-rocinante}"
SRC="${SKYLEARN_DEST:-/opt/skylearn}"
DEST="${SKYLEARN_BACKUP_DIR:-$HOME/backups/skylearn}"
KEEP="${SKYLEARN_BACKUP_KEEP:-7}"
TS="$(date +%Y%m%d-%H%M%S)"
OUT="$DEST/$TS"

mkdir -p "$OUT"

echo ">> Copiando de ${REMOTE}:${SRC}  ->  ${OUT}"

# 1) Instantanea consistente de la base de datos
ssh "$REMOTE" "cd '$SRC' && sudo -u www-data ./venv/bin/python -c 'import sqlite3; s=sqlite3.connect(\"db.sqlite3\"); d=sqlite3.connect(\"/tmp/skylearn-db-$TS.sqlite3\"); s.backup(d); d.close(); s.close()'"
scp -q "$REMOTE:/tmp/skylearn-db-$TS.sqlite3" "$OUT/db.sqlite3"
ssh "$REMOTE" "sudo rm -f /tmp/skylearn-db-$TS.sqlite3"

# 2) Configuracion (.env: SECRET_KEY, SMTP...) — fichero sensible
ssh "$REMOTE" "sudo cat '$SRC/.env'" > "$OUT/env"

# 3) Ficheros subidos
rsync -az -e ssh "$REMOTE:$SRC/media/" "$OUT/media/"

# 4) Retencion: conservar solo las KEEP copias mas recientes
ls -1dt "$DEST"/*/ 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -rf

echo ">> Hecho. Tamano:"
du -sh "$OUT"
