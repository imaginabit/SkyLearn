# AGENTS.md — SkyLearn (fork imaginabit)

Django **4.0.8** monolítico (sin build de frontend, sin framework JS). Fork de
`imaginabit/SkyLearn` para https://curso.imaginabit.com — servidor "Rocinante".
`CONTRIBUTING.md` es boilerplate del upstream: **ignóralo**, el flujo real está en
`DEPLOY.md`.

## Entorno

- **Usa un venv con Python 3.9/3.10.** El `python3` del sistema es 3.14 y Django
  4.0.8 no arranca ahí. La matriz de CI es 3.8–3.10.
- `pip install -r requirements.txt` (= `requirements/local.txt`).
- **`.env` es obligatorio para cualquier comando `manage.py`**: `config/settings.py`
  lee `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` y `EMAIL_FROM_ADDRESS` con
  `decouple.config()` **sin default** → sin `.env` fallan hasta los tests.
  Copia `.env.example` y ajústalo.
- No hay settings de producción separados: un solo `config/settings.py`, todo por env.

## Comandos

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
python manage.py test                       # CI corre exactamente esto
python manage.py compilemessages -l es      .po -> .mo (el .mo de es está versionado a propósito)
python manage.py collectstatic --noinput
```

- **URLs con prefijo de idioma**: todo lo de apps va bajo `/es/...`
  (`i18n_patterns`, `config/urls.py:16`); `/admin/` e `/i18n/` quedan fuera. La app
  `course` se sirve en `/programs/`, no en `/course/`.
- **Tras tocar `static/`, ejecuta `collectstatic`**: en DEBUG `/static/` se sirve
  desde `staticfiles/` (`config/urls.py:33`), no desde `static/`.
- SCSS→CSS lo compila la extensión de VSCode (`static/scss/style.scss` →
  `static/css`). No hay paso de build en el repo.
- **Lint**: no hay script. El CI corre `pylint` (`.pylintrc`, `max-line-length=100`)
  sobre `git ls-files '*.py'` excluyendo `migrations/`, y `black` **sin
  `pyproject.toml`** → 88 columnas por defecto. Formatea con black.
- **Tests reales: solo `accounts/tests/`** (`test_decorators.py`, `test_filters.py`).
  El `tests.py` del resto de apps son stubs vacíos.
- Datos de prueba: `scripts/generate_fake_data.py` (factory_boy) **no tiene CLI**,
  impórtalo desde `manage.py shell`, y necesita `pip install faker` (no está en
  `requirements/`).

## Arquitectura

- Apps y su montaje: `accounts` `/accounts/`, `core` `/`, `course` `/programs/`,
  `result` `/result/`, `search` `/search/`, `quiz` `/quiz/`, `payments` `/payments/`.
- `AUTH_USER_MODEL = "accounts.User"` (swap de User). `Student`, `Parent`,
  `Lecturer`, `DepartmentHead` son modelos **separados** en la misma app.
- **Los roles son flags booleanos** en `User` (`is_student`, `is_lecturer`,
  `is_parent`, `is_dep_head`), no grupos/permisos. El orden de decisión está en
  `User.get_user_role()`; el control de acceso, en `accounts/decorators.py`.
- **modeltranslation** crea columnas reales con sufijo (`Course.title_es`,
  `title_en`, `title_fr`, `title_ru`). Para queries, ordenaciones o
  serializaciones hay que usar el sufijo explícito. Un campo traducible nuevo se
  declara en el `<app>/translation.py` **y** genera migración con las columnas.
  Los 4 idiomas están declarados en `LANGUAGES`; el español es el por defecto
  (`LANGUAGE_CODE`, `MODELTRANSLATION_DEFAULT_LANGUAGE`).
- Formularios: crispy-forms + crispy-bootstrap5. Plantillas en `templates/<app>/`.
  PDFs con `xhtml2pdf` (`templates/pdf/`).
- `course.Upload` = actividad/material del curso; `course.Submission` = entrega del
  alumno (opcionalmente vinculada a un quiz). Entregar es subir un fichero, no
  hacer un quiz.

## Datos vivos y despliegue

- **Los datos solo existen en el servidor** (`/opt/skylearn` en el alias SSH
  `rocinante`). El repo es solo código. `db.sqlite3`, `media/`, `.env` y
  `staticfiles/` están gitignored a propósito: no los commitees.
- `git push origin main` y luego `./deploy.sh` (`--dry-run` primero). El script
  sincroniza por `rsync` **sin `--delete`** y excluye los datos en vivo; en el
  servidor hace `migrate` + `compilemessages` + `collectstatic` + restart de
  `skylearn`.
- `course/migrations/0005` y `0006` son un **par de reversión** (0006 revierte
  0005; mismo cambio de `upload.file`). La BD del servidor ya los aplicó: no los
  borres ni los edites, no los squashees.
- `./backup.sh` descarga BD + `.env` + `media/` a `~/backups/skylearn/` (solo
  local, conserva 7).

## Datos personales (RGPD)

- `python manage.py erase_course_data --curso <codigo>` borra curso, entregas,
  quizzes y (con `--alumnos`) las cuentas sin matrícula en otros cursos. **Simulacro
  por defecto; borrar exige `--confirm`.** No lo ejecutes salvo petición
  explícita, y nunca contra el servidor sin avisar.
- `PRIVACY_VERSION` en `.env` es la versión del texto de privacidad publicado:
  ** súbela cada vez que cambie el texto**, porque cada `ConsentRecord` guardado
  declara con qué versión se consintió.

## Estilo

- Negocio e interfaz en **español** (comentarios, mensajes, textos de plantilla);
  el código upstream untouched sigue en inglés. Commit messages en español.
- Black, 4 espacios, comillas dobles (formateo automático al guardar en VSCode).
- Formato de commits libre, pero descriptivo y en una línea (`fix:`, `deploy:`,
  `Servidor:` como prefijos ya usados).
