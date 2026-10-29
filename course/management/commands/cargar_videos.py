"""Carga los vídeos de un curso desde un fichero JSON.

Los vídeos del material docente son una lista de enlaces: una clase de
Class4crypt, un documental. Para no teclear uno por uno en el admin, se
guardan en un JSON y se suben de una vez.

El JSON es una lista de objetos:

    [
      {
        "course": "MF0489_3",
        "title": "S2 · Modos de cifrado: ECB y CBC",
        "url": "https://www.youtube.com/watch?v=gtuKuryDFuE",
        "summary": "1:27:17 · corte de 0 a 40 min · Class4crypt c4c8.4a",
        "orden": 20
      }
    ]

Al cargar, un vídeo que ya existe se actualiza (enlace, resumen y orden) pero
**no se toca su casilla de visibilidad**: si el profesorado ya lo ha revelado,
no se vuelve a esconder. Los vídeos nuevos nacen ocultos, salvo que el JSON
diga lo contrario con "visible": true.

Los cursos que no existen se saltan con un aviso, no son un error: los cursos de
sesión se crean cuando se monta la clase.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand

from course.models import Course, UploadVideo


class Command(BaseCommand):
    help = "Carga los vídeos de un curso desde un fichero JSON."

    def add_arguments(self, parser):
        parser.add_argument("fichero", help="Ruta del JSON con los vídeos.")
        parser.add_argument(
            "--ocultar",
            action="store_true",
            help="Deja todos los vídeos ocultos, también los que ya estaban visibles.",
        )

    def handle(self, *args, **options):
        ruta = Path(options["fichero"])
        if not ruta.is_file():
            self.stderr.write(f"no existe el fichero: {ruta}")
            return

        datos = json.loads(ruta.read_text(encoding="utf-8"))
        nuevos = actualizados = saltados = 0

        for item in datos:
            curso = Course.objects.filter(code=item["course"]).first()
            if curso is None:
                self.stdout.write(
                    self.style.WARNING(
                        f"no existe el curso {item['course']}: se salta «{item['title']}»"
                    )
                )
                saltados += 1
                continue

            visibles = [v for v in curso.videos.all() if v.title == item["title"]]
            if visibles:
                video = visibles[0]
                video.url = item.get("url", "")
                video.summary = item.get("summary", "")
                video.orden = item.get("orden", 0)
                if options["ocultar"]:
                    video.visible = False
                video.save()
                actualizados += 1
                continue

            video = UploadVideo(
                course=curso,
                title=item["title"],
                url=item.get("url", ""),
                summary=item.get("summary", ""),
                orden=item.get("orden", 0),
                visible=bool(item.get("visible", False)),
            )
            video.save()
            nuevos += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"{nuevos} nuevos, {actualizados} actualizados, {saltados} saltados"
            )
        )
