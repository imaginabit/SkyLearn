# SkyLearn — clon de desarrollo y despliegue

Clon local del fork **imaginabit/SkyLearn** (customizaciones para
`https://curso.imaginabit.com`). El servidor es **Rocinante**; el despliegue se
hace con [`deploy.sh`](deploy.sh).

## Flujo de trabajo

```bash
cd ~/Proyectos/SkyLearn-Git
# editar...
git add -A && git commit -m "..."
git push origin main        # requiere auth de GitHub (helper 'gh')

./deploy.sh --dry-run       # ver que se va a sincronizar
./deploy.sh                 # desplegar al servidor
```

El push usa el credential helper de `gh` (`gh auth git-credential`), ya
configurado en este clon.

## Qué hace `deploy.sh`

1. Sincroniza el **código** al servidor con `rsync -az --delete`.
2. En el servidor: permisos (`www-data`), `pip install`, `migrate`,
   `compilemessages -l es`, `collectstatic` y `systemctl restart skylearn`.
3. Al terminar: https://curso.imaginabit.com

## Qué NO toca (datos en vivo, protegidos por `--exclude`)

Estos ficheros del servidor **nunca** se sobreescriben ni se borran:

| Ruta | Por qué |
|---|---|
| `.env` | Config del servidor (SECRET_KEY, SMTP…) |
| `db.sqlite3` | Base de datos (alumnado, notas, matrículas…) |
| `media/` | Ficheros subidos (documentos, vídeos) |
| `staticfiles/` | Estáticos generados (se regeneran con `collectstatic`) |
| `venv/` | Entorno Python del servidor |

> `rsync --delete` borra en el servidor lo que ya no exista en el repo, pero
> **respeta los `--exclude`**, así que los anteriores quedan a salvo.

## Requisitos

- Acceso SSH por alias `rocinante` (ver `~/.ssh/config`).
- `rsync` y `ssh` en local.
- `sudo` sin contraseña en el servidor para el usuario de despliegue.

## Reglas

- Los **datos** (base de datos, subidas) viven solo en el servidor; el repo es
  solo código.
- El catálogo de traducción `locale/es/LC_MESSAGES/django.mo` **sí** se versiona
  (para que el castellano funcione sin regenerar en cada despliegue);
  `compilemessages` lo vuelve a generar si procede.
