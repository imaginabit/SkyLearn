# SkyLearn — clon de desarrollo y despliegue

Clon local del fork **imaginabit/SkyLearn** (customizaciones para
`https://curso.imaginabit.com`). El servidor es **Rocinante**; el despliegue se
hace con [`deploy.sh`](deploy.sh).

## Flujo de trabajo

```bash
cd ~/Proyectos/SkyLearn-Git
# editar...
git add -A && git commit -m "..."
git push origin develop     # la rama desplegada es develop, no main

./deploy.sh --dry-run       # ver que se va a sincronizar
./deploy.sh                 # desplegar al servidor
```

El push usa el credential helper de `gh` (`gh auth git-credential`), ya
configurado en este clon.

## Qué hace `deploy.sh`

1. Sincroniza el **código** al servidor con `rsync -az` (con `sudo` remoto
   para poder escribir en `/opt/skylearn`, propiedad de `www-data`).
2. En el servidor: permisos (`www-data`), `pip install`, `migrate`,
   `compilemessages -l es`, `collectstatic` y `systemctl restart skylearn`.
3. Al terminar: https://curso.imaginabit.com

## Despliegue desde Windows

En un equipo Windows **sin `rsync` ni `bash`** se usa [`deploy.ps1`](deploy.ps1),
que hace lo mismo con `tar` + `scp` (paquete temporal en `/tmp` del servidor,
extracción con `sudo tar` y `chown -R` a `www-data`) y luego los mismos pasos
remotos:

```powershell
.\deploy.ps1 -DryRun        # empaqueta y comprueba, sin tocar el servidor
.\deploy.ps1                # desplegar
```

Mismos `--exclude` que `deploy.sh` y, además, comprobaciones que abortan si el
paquete incluyera datos en vivo (`media/`, `db.sqlite3`, `.env`…) o si el
paquete llevara CRLF. Requiere `ssh`, `scp` y `tar` (los tres vienen con
Windows 10+).

> Ojo con los finales de línea: `git archive` en Windows convierte a CRLF por
> `core.autocrlf`, así que `deploy.ps1` lo llama con `core.autocrlf=false` y
> `core.eol=lf` para subir exactamente lo que hay guardado en git (LF), como un
> clon en Linux. Empaqueta **HEAD**, no el working tree: si hay cambios sin
> commitear, aborta (`-AllowDirty` lo salta, desplegando igualmente HEAD).

## Qué NO toca (datos en vivo, protegidos por `--exclude`)

Estos ficheros del servidor **nunca** se sobreescriben ni se borran:

| Ruta | Por qué |
|---|---|
| `.env` | Config del servidor (SECRET_KEY, SMTP…) |
| `db.sqlite3` | Base de datos (alumnado, notas, matrículas…) |
| `media/` | Ficheros subidos (documentos, vídeos) |
| `staticfiles/` | Estáticos generados (se regeneran con `collectstatic`) |
| `venv/` | Entorno Python del servidor |

> El despliegue **no usa `--delete`**: nunca borra ficheros del servidor. Solo
> añade/actualiza. Los `--exclude` evitan además tocar los datos en vivo.

## Copia de seguridad

`backup.sh` descarga a este equipo la base de datos y los ficheros subidos:

```bash
./backup.sh
```

- Deja cada copia en `~/backups/skylearn/<fecha-hora>/` (BD, `.env` y `media/`).
- La BD se copia con la API de backup de SQLite (consistente con la app en marcha).
- Conserva las 7 últimas copias (`SKYLEARN_BACKUP_KEEP`).
- El servidor **no** guarda copias; están solo en local.

Cron sugerido (diario a las 3:00):

```
0 3 * * *  /home/fer/Proyectos/SkyLearn-Git/backup.sh >> /home/fer/backups/skylearn.log 2>&1
```

## Requisitos

- Acceso SSH al servidor: alias `rocinante` (equipo Linux) o
  `debian@imaginabit.com` (Windows).
- En Linux: `rsync` y `ssh`. En Windows: `ssh`, `scp` y `tar` (`deploy.ps1`).
- `sudo` sin contraseña en el servidor para el usuario de despliegue.

## Reglas

- Los **datos** (base de datos, subidas) viven solo en el servidor; el repo es
  solo código.
- El catálogo de traducción `locale/es/LC_MESSAGES/django.mo` **sí** se versiona
  (para que el castellano funcione sin regenerar en cada despliegue);
  `compilemessages` lo vuelve a generar si procede.
