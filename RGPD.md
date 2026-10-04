# Protección de datos · RGPD y LOPDGDD

Lo que hay montado en SkyLearn para cumplir con el tratamiento de datos del
alumnado. La parte de cara al usuario está en `/es/privacidad/` y `/es/terminos/`;
esto es la parte de dentro.

## Quién es quién

| Papel | Quién |
|---|---|
| **Responsable del tratamiento** | El centro. Se configura en `DATA_CONTROLLER` (`.env`). |
| **Contacto para derechos** | `DATA_PROTECTION_EMAIL` (`.env`). Hoy `admin@imaginabit.com` — **cambiar por un buzón que se lea**. |
| **Encargado** | El proveedor del servidor (Rocinante) y el del correo. |

## Qué datos, para qué y con qué base

- **Datos**: nombre, apellidos, correo, teléfono, dirección, género, nivel,
  programa, y los resultados de actividades y pruebas.
- **Finalidad**: gestionar el curso — alta, acceso, corrección, calificación y
  certificado— y justificar la acción formativa ante la administración.
- **Base jurídica**: consentimiento (art. 6.1.a) y ejecución de la relación
  formativa (art. 6.1.b); obligación legal para la justificación (art. 6.1.c).
- **No** hay publicidad, ni perfiles, ni decisiones automatizadas.

## La prueba del consentimiento

`accounts.ConsentRecord` guarda, por cada alta: la persona, la **versión del
texto** aceptado, la **fecha**, la **IP** y el **navegador**, y quién lo
registró (el propio alumno o el administrador que dio el alta). Es de solo
añadir y en el admin **no se puede editar ni borrar**: si se pudiera tocar, no
valdría como prueba.

Al cambiar el texto de la política hay que **subir `PRIVACY_VERSION`** en el
`.env`. Las pruebas anteriores se quedan con la versión con la que se dieron, que
es justo lo que hay que poder demostrar.

## Plazos de retención

`DATA_RETENTION` (`.env`). Por defecto: hasta la finalización del curso y el
cierre administrativo de la acción formativa, y después solo durante los plazos
que exige la normativa de formación para el empleo.

## Procedimiento de borrado

Al cerrar el curso:

```bash
cd /opt/skylearn
sudo -u www-data ./venv/bin/python manage.py erase_course_data --curso <slug>
```

Eso **no borra nada**: dice lo que borraría. Para ejecutarlo, `--confirm`, y con
`--alumnos` para llevarse también las cuentas:

```bash
sudo -u www-data ./venv/bin/python manage.py erase_course_data \
    --curso <slug> --alumnos --confirm
```

- Borra el curso y arrastra ficheros, vídeos, cuestionarios, intentos y
  matrículas.
- Con `--alumnos`, borra la cuenta de cada alumno del curso: se lleva su
  `Student`, sus `Result`, su `Progress`, sus `Sitting` y sus `ConsentRecord`.
- **Solo borra las cuentas sin matrícula en otro curso.** Si alguien sigue en
  otro curso, su cuenta se conserva; el comando lo dice.
- La copia de `db.sqlite3` y `media/` que se haya hecho antes **también hay que
  borrarla**, o el borrado no sirve de nada.

## Lo que queda por decidir (no es código)

- El buzón real de contacto y quién atiende los derechos.
- Si el responsable es el centro o la entidad que explota la plataforma.
- Confirmar los plazos de conservación con quien lleve la justificación.
