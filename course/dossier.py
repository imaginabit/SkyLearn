"""El dossier del alumno: lo suyo y lo publico del curso, en un ZIP.

El docente puede bajar, para cada alumno, un archivo con el material visible
del curso, las entregas de ese alumno y el feedback que se le ha dado a cada
una. El alumno puede bajarse el suyo desde la pestana de entregas.

El archivo solo lleva lo que el alumno puede ver en la web: el material
oculto se queda fuera, y de las entregas solo van las suyas, nunca las de
otros. Los videos no se incluyen como fichero (pesan demasiado): van listados
con su enlace en `videos.md`.

El ZIP es siempre el mismo: las entradas llevan fecha fija y dentro no hay
ninguna marca de tiempo. Asi su SHA-256 no cambia entre descargas y el
alumnado puede comprobar que lo que ha bajado es lo que hay en el curso. Por
eso el archivo se guarda en disco (en `dossier/`, fuera de `media/`) y solo se
rehace cuando cambia el material del curso o la entrega del alumno:
`borra_dossiers` y `borra_dossier` lo invalidan.
"""

import hashlib
import io
import zipfile
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify

from course.models import Submission, Upload, UploadVideo

# Fecha fija de las entradas del ZIP. El formato ZIP guarda la fecha de cada
# entrada, asi que sin esto el hash del archivo cambiaria en cada descarga y
# no serviria para comprobar nada.
CUANDO = (2026, 10, 5, 0, 0, 0)

LEEME = """\
Dossier del curso {curso} ({codigo})
Alumno: {alumno}
Material del curso: {fecha}

Contenido:

  material/presentaciones/  Los mazos de diapositivas del curso.
  material/actividades/     Los enunciados de las actividades: lo que se
                            entrega.
  material/documentacion/   El resto de documentos del curso.
  entregas/                 Las entregas de {nombre_corto}, una carpeta por
                            actividad: el fichero entregado y, junto a el,
                            el feedback.md con la nota y los comentarios
                            del docente para esa entrega.
  feedback.md               Resumen de todo: nota y comentarios de cada
                            actividad, junto a las que quedan sin entregar.
  videos.md                 Los videos publicados del curso con su enlace.
                            No se incluyen como fichero: pesan demasiado.

Dentro de cada pestaña, una carpeta numerada por documento, como en la
pagina del curso. El material oculto del curso no va en el archivo: solo lo
que se puede ver en la web, y lo que es de {nombre_corto}.
"""


def _carpeta(indice, titulo):
    """El nombre de carpeta `NN-titulo`, estable y sin caracteres raros."""
    limpio = slugify(titulo or "")[:60].strip("-")
    return f"{indice:02d}-{limpio or 'sin-titulo'}"


def _escribe(zip_file, carpeta, campo, usados):
    """Anade un fichero de un FileField al ZIP, sin pisar nombres repetidos.

    El fichero va dentro de `carpeta` con su nombre original; si dos ficheros
    de la misma carpeta se llaman igual, el segundo y siguientes llevan un
    contador antes de la extension (`guia_2.pdf`).
    """
    if not campo:
        return
    nombre = campo.name.rsplit("/", 1)[-1]
    base, punto, extension = nombre.rpartition(".")
    ruta = f"{carpeta}/{nombre}"
    numero = 2
    while ruta in usados:
        ruta = f"{carpeta}/{base}_{numero}{punto}{extension}"
        numero += 1
    usados.add(ruta)
    with campo.open("rb") as origen:
        _entrada(zip_file, ruta, origen.read())


def _entrada(zip_file, ruta, datos):
    """Escribe una entrada del ZIP con fecha fija: el archivo es siempre igual."""
    info = zipfile.ZipInfo(ruta, date_time=CUANDO)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    zip_file.writestr(info, datos)


def _lineas_feedback(entrega):
    """Las lineas de nota, fecha y comentarios de una entrega."""
    lineas = []
    if entrega.mark is not None:
        lineas.append(f"- Nota: **{entrega.mark}**")
    else:
        lineas.append("- Nota: sin calificar todavia")
    if entrega.graded_at:
        calificada = timezone.localtime(entrega.graded_at).strftime("%d/%m/%Y")
        lineas.append(f"- Calificada el {calificada}")
    subida = timezone.localtime(entrega.uploaded_at).strftime("%d/%m/%Y %H:%M")
    lineas.append(f"- Entregada el {subida} ({entrega.filename})")
    lineas.append("")
    if entrega.feedback:
        lineas.append("Comentarios del docente:")
        for parrafo in entrega.feedback.strip().splitlines() or [""]:
            lineas.append(f"> {parrafo}".rstrip())
    else:
        lineas.append("El docente todavia no ha escrito comentarios.")
    return lineas


def _feedback_md(curso, alumno, actividades, entregas, fecha):
    """El feedback del docente, actividad a actividad, en Markdown."""
    lineas = [
        f"# Feedback del curso {curso.title} ({curso.code})",
        "",
        f"Alumno: {alumno.get_full_name} ({alumno.username})",
        f"Material del curso: {fecha}",
        "",
    ]
    por_actividad = {e.document_id: e for e in entregas}
    sin_entregar = []
    for actividad in actividades:
        entrega = por_actividad.get(actividad.pk)
        if entrega is None:
            sin_entregar.append(actividad)
            continue
        lineas.append(f"## {actividad.title}")
        lineas.extend(_lineas_feedback(entrega))
        lineas.append("")
    if sin_entregar:
        lineas.append("## Sin entregar")
        lineas.append("")
        for actividad in sin_entregar:
            lineas.append(f"- {actividad.title}")
        lineas.append("")
    return "\n".join(lineas)


def _videos_md(curso, videos):
    """El indice de los videos publicados, con su enlace."""
    lineas = [
        f"# Videos del curso {curso.title} ({curso.code})",
        "",
    ]
    for video in videos:
        if video.url:
            lineas.append(f"- [{video.title}]({video.url})")
        elif video.video:
            lineas.append(f"- {video.title} (fichero: {video.video.name})")
        else:
            lineas.append(f"- {video.title}")
    return "\n".join(lineas) + "\n"


def genera_dossier(curso, alumno):
    """El ZIP del dossier como bytes.

    Material visible del curso + las entregas de `alumno` + el feedback
    recibido. Las entregas van siempre, aunque su actividad este ahora
    oculta: son de el. El material, solo si es visible.

    Dos llamadas seguidas dan exactamente el mismo archivo: sin eso su hash
    no valdría para comprobar la descarga.
    """
    materiales = (
        Upload.objects.filter(course=curso, visible=True)
        .prefetch_related("archivos")
        .order_by("upload_time", "pk")
    )
    entregas = (
        Submission.objects.filter(course=curso, student=alumno)
        .select_related("document")
        .order_by("document__upload_time", "document__pk")
    )
    videos = UploadVideo.objects.filter(course=curso, visible=True).order_by(
        "orden", "pk"
    )
    # El material, repartido por las mismas pestañas del curso: los mazos de
    # diapositivas van a Presentaciones, las actividades (lo que se entrega)
    # a la suya y el resto de documentos a Documentacion.
    presentaciones = []
    actividades = []
    documentacion = []
    for material in materiales:
        if material.es_html:
            presentaciones.append(material)
        elif material.is_activity:
            actividades.append(material)
        else:
            documentacion.append(material)
    # La fecha del material: la de la subida mas reciente. Va dentro del
    # archivo, asi que tiene que salir del contenido y no de la hora del
    # reloj, que haria cambiar el hash en cada descarga.
    fechas = [m.upload_time for m in materiales if m.upload_time]
    fecha = (
        f"el que hay en la plataforma, hasta el "
        f"{timezone.localtime(max(fechas)).strftime('%d/%m/%Y')}"
        if fechas
        else "el que hay en la plataforma"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        usados = set()
        _entrada(
            zip_file,
            "LEEME.txt",
            LEEME.format(
                curso=curso.title,
                codigo=curso.code,
                alumno=f"{alumno.get_full_name} ({alumno.username})",
                nombre_corto=alumno.username,
                fecha=fecha,
            ).encode("utf-8"),
        )
        _entrada(
            zip_file,
            "feedback.md",
            _feedback_md(curso, alumno, actividades, entregas, fecha).encode("utf-8"),
        )
        _entrada(zip_file, "videos.md", _videos_md(curso, videos).encode("utf-8"))

        # Cada pestana numera sus carpetas por su cuenta, igual que las
        # tablas de la pagina del curso.
        for carpeta_pestana, grupo in (
            ("material/presentaciones", presentaciones),
            ("material/actividades", actividades),
            ("material/documentacion", documentacion),
        ):
            for indice, material in enumerate(grupo, start=1):
                carpeta = f"{carpeta_pestana}/{_carpeta(indice, material.title)}"
                _escribe(zip_file, carpeta, material.file, usados)
                for adicional in material.archivos.all().order_by("pk"):
                    _escribe(zip_file, carpeta, adicional.file, usados)

        for indice, entrega in enumerate(entregas, start=1):
            titulo = entrega.document.title if entrega.document else ""
            carpeta = f"entregas/{_carpeta(indice, titulo or 'sin-actividad')}"
            _escribe(zip_file, carpeta, entrega.file, usados)
            # El feedback de esta entrega, junto al fichero entregado
            cabecera = f"# Feedback: {titulo or 'Sin actividad'}"
            _entrada(
                zip_file,
                f"{carpeta}/feedback.md",
                ("\n".join([cabecera, ""] + _lineas_feedback(entrega)) + "\n").encode(
                    "utf-8"
                ),
            )

    return buffer.getvalue()


# --- El archivo en disco -------------------------------------------------
#
# El ZIP se guarda en `media/dossier/`: es el mismo que se baja el alumnado,
# byte a byte, y su hash es el que se publica en la pagina del curso. Se
# rehace solo cuando cambia el material del curso o la entrega del alumno.

def _carpeta_dossiers():
    """Donde se guardan los ZIP.

    Fuera de `media/`: esa carpeta la sirve nginx tal cual, sin sesion, y el
    dossier lleva las entregas del alumno y sus notas. aqui solo llega
    Django, que pide la sesion antes de servirlo.
    """
    return Path(settings.BASE_DIR) / "dossier"


def ruta_dossier(curso, alumno):
    """Donde vive el ZIP de este alumno en este curso."""
    return _carpeta_dossiers() / f"{curso.pk}-{slugify(alumno.username)}.zip"


def dossier_en_disco(curso, alumno):
    """El ZIP del alumno, en disco. Se genera si todavia no existe."""
    ruta = ruta_dossier(curso, alumno)
    if not ruta.exists():
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(genera_dossier(curso, alumno))
    return ruta


def hash_dossier(curso, alumno):
    """El SHA-256 del ZIP del alumno, en hexadecimal."""
    ruta = dossier_en_disco(curso, alumno)
    resumen = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            resumen.update(bloque)
    return resumen.hexdigest()


def borra_dossier(curso, alumno):
    """Invalida el ZIP de un alumno: se rehace en la proxima descarga."""
    ruta_dossier(curso, alumno).unlink(missing_ok=True)


def borra_dossiers(curso):
    """Invalida los ZIP de todos los alumnos del curso."""
    prefijo = f"{curso.pk}-"
    for ruta in _carpeta_dossiers().glob(f"{prefijo}*.zip"):
        ruta.unlink(missing_ok=True)
