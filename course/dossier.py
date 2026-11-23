"""El dossier del alumno: lo suyo y lo publico del curso, en un ZIP.

El docente puede bajar, para cada alumno, un archivo con el material visible
del curso, las entregas de ese alumno y el feedback que se le ha dado a cada
una. El alumno puede bajarse el suyo desde la pestana de entregas.

El archivo solo lleva lo que el alumno puede ver en la web: el material
oculto se queda fuera, y de las entregas solo van las suyas, nunca las de
otros. Los videos no se incluyen como fichero (pesan demasiado): van listados
con su enlace en `videos.md`.
"""

import io
import zipfile

from django.utils import timezone
from django.utils.text import slugify

from course.models import Submission, Upload, UploadVideo

LEEME = """\
Dossier del curso {curso} ({codigo})
Alumno: {alumno}
Generado el {fecha}

Contenido:

  material/presentaciones/  Los mazos de diapositivas del curso.
  material/actividades/     Los enunciados de las actividades: lo que se
                            entrega.
  material/documentacion/   El resto de documentos del curso.
  entregas/                 Las entregas de {nombre_corto}, una carpeta por
                            actividad.
  feedback.md               La nota y los comentarios del docente para cada
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
        zip_file.writestr(ruta, origen.read())


def _feedback_md(curso, alumno, actividades, entregas):
    """El feedback del docente, actividad a actividad, en Markdown."""
    fecha = timezone.localtime(timezone.now()).strftime("%d/%m/%Y %H:%M")
    lineas = [
        f"# Feedback del curso {curso.title} ({curso.code})",
        "",
        f"Alumno: {alumno.get_full_name} ({alumno.username})",
        f"Generado el {fecha}",
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
        if entrega.mark is not None:
            lineas.append(f"- Nota: **{entrega.mark}**")
        else:
            lineas.append("- Nota: sin calificar todavia")
        if entrega.graded_at:
            calificada = timezone.localtime(entrega.graded_at).strftime("%d/%m/%Y")
            lineas.append(f"- Calificada el {calificada}")
        subida = timezone.localtime(entrega.uploaded_at).strftime("%d/%m/%Y %H:%M")
        lineas.append(f"- Entregada el {subida} ({entrega.filename})")
        if entrega.feedback:
            lineas.append("")
            lineas.append("Comentarios del docente:")
            for parrafo in entrega.feedback.strip().splitlines() or [""]:
                lineas.append(f"> {parrafo}".rstrip())
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

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        usados = set()
        fecha = timezone.localtime(timezone.now()).strftime("%d/%m/%Y %H:%M")
        zip_file.writestr(
            "LEEME.txt",
            LEEME.format(
                curso=curso.title,
                codigo=curso.code,
                alumno=f"{alumno.get_full_name} ({alumno.username})",
                nombre_corto=alumno.username,
                fecha=fecha,
            ),
        )
        zip_file.writestr(
            "feedback.md",
            _feedback_md(curso, alumno, actividades, entregas),
        )
        zip_file.writestr("videos.md", _videos_md(curso, videos))

        # Cada pestaña numera sus carpetas por su cuenta, igual que las
        # tablas de la pagina del curso.
        for carpeta_pestana, grupo in (
            ("material/presentaciones", presentaciones),
            ("material/actividades", actividades),
            ("material/documentacion", documentacion),
        ):
            for indice, material in enumerate(grupo, start=1):
                carpeta = f"{carpeta_pestana}/{_carpeta(indice, material.title)}"
                _escribe(zip_file, carpeta, material.file, usados)
                for adicional in material.archivos.all():
                    _escribe(zip_file, carpeta, adicional.file, usados)

        for indice, entrega in enumerate(entregas, start=1):
            titulo = entrega.document.title if entrega.document else ""
            carpeta = f"entregas/{_carpeta(indice, titulo or 'sin-actividad')}"
            _escribe(zip_file, carpeta, entrega.file, usados)

    return buffer.getvalue()
