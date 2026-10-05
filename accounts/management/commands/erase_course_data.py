"""Borra los datos personales de un curso al terminar (derecho al olvido).

    python manage.py erase_course_data --curso mf0487_3-auditoria
    python manage.py erase_course_data --curso mf0487_3-auditoria --alumnos --confirm

Sin `--confirm` no borra nada: dice lo que borraría. Borrar es irreversible y
esta orden toca datos de personas, así que el simulacro es el modo por defecto y
no al revés.

Qué borra:

  · El curso, y con él los cuestionarios, los intentos y las matrículas
    (TakenCourse). Los ficheros de `media/` (apuntes, vídeos, entregas de los
    alumnos y las figuras de las preguntas) se borran **antes** de la cascada,
    porque el collector de Django borra filas y no ficheros: si no, se quedan
    en el disco y el borrado no sirve de nada.
  · Con `--alumnos`, las cuentas del alumnado matriculado en ese curso: cada
    User se lleva su Student, sus Result, su Progress, sus Sitting y sus
    ConsentRecord. Solo se borran las cuentas que **no tengan matrícula en otro
    curso**: si alguien sigue en otro curso, su cuenta se queda.

Lo que NO borra: el programa y el historial de matrículas de cursos que no sean
este. El borrado es de un curso, no de la plataforma.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Student, User
from course.models import Course
from result.models import Result
from quiz.models import Progress, Question, Sitting


class Command(BaseCommand):
    help = "Borra un curso y los datos personales asociados (RGPD)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--curso",
            required=True,
            help="slug o código del curso, p. ej. mf0487_3-auditoria",
        )
        parser.add_argument(
            "--alumnos",
            action="store_true",
            help="borrar también las cuentas del alumnado del curso",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="ejecutar de verdad. Sin esto solo dice lo que borraría",
        )

    def handle(self, *args, **opts):
        curso = self._busca_curso(opts["curso"])
        alumnos = self._alumnos(curso)
        borrables, conservados = self._separa(curso, alumnos)

        self.stdout.write(f"Curso: {curso.title} ({curso.slug}) · {curso.code}")
        self.stdout.write(f"  ficheros:      {curso.upload_set.count()}")
        self.stdout.write(f"  vídeos:        {curso.uploadvideo_set.count()}")
        self.stdout.write(f"  cuestionarios: {curso.quiz_set.count()}")
        self.stdout.write(f"  matrículas:    {curso.taken_courses.count()}")
        self.stdout.write(
            f"  alumnado:      {len(alumnos)} " f"({len(borrables)} sin otro curso)"
        )

        if opts["alumnos"]:
            for u in borrables:
                self.stdout.write(f"    se borra: {u.username} · {u.get_full_name}")
            for u in conservados:
                self.stdout.write(
                    f"    se conserva (sigue en otro curso): "
                    f"{u.username} · {u.get_full_name}"
                )

        if not opts["confirm"]:
            self.stdout.write(
                self.style.WARNING(
                    "\nSimulacro: no se ha borrado nada. "
                    "Añade --confirm para ejecutarlo de verdad."
                )
            )
            return

        with transaction.atomic():
            # el curso arrastra filas por las claves foráneas (cuestionarios,
            # intentos, matrículas, asignaciones), pero los ficheros de media/
            # hay que borrarlos a mano: eso es lo que hace _borra_ficheros
            titulo = curso.title
            ficheros = self._borra_ficheros(curso)
            curso.delete()
            n = 0
            if opts["alumnos"]:
                for u in borrables:
                    u.delete()  # arrastra Student, Result, Progress,
                    # Sitting y ConsentRecord
                    n += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Borrado «{titulo}»"
                + (f" y {n} cuenta(s) de alumnado." if opts["alumnos"] else ".")
                + f" Ficheros eliminados de media/: {ficheros}."
            )
        )

    def _busca_curso(self, clave):
        curso = (
            Course.objects.filter(slug=clave).first()
            or Course.objects.filter(code=clave).first()
        )
        if curso is None:
            raise CommandError(f"No hay ningún curso con slug o código «{clave}».")
        return curso

    def _alumnos(self, curso):
        ids = curso.taken_courses.values_list("student_id", flat=True)
        return list(User.objects.filter(student__id__in=ids).distinct())

    def _separa(self, curso, alumnos):
        """Parte el alumnado en el que se puede borrar y el que no.

        Solo se borra la cuenta de quien no está matriculado en ningún otro
        curso: borrarla dejaría a esa persona fuera de un curso que sigue vivo.

        Se mira lo que queda *fuera* de este curso, y no todas las matrículas:
        como esto corre antes de borrarlo, contar todas daba 1 a quien solo
        estaba aquí, y `--alumnos` no borraba a nadie.
        """
        borrables, conservados = [], []
        for u in alumnos:
            if not hasattr(u, "student"):
                continue
            en_otros = u.student.takencourse_set.exclude(course=curso).exists()
            (borrables if not en_otros else conservados).append(u)
        return borrables, conservados

    def _borra_ficheros(self, curso):
        """Borra de media/ lo que cuelga del curso, antes de la cascada.

        El collector de Django borra filas, no ficheros: no llama a
        `Upload.delete()` en una cascada, y `Submission` ni siquiera lo tiene.
        Para un derecho al olvido, dejar el PDF de un alumno en media/ es
        justo lo que no puede pasar.

        Devuelve cuántos ficheros se han borrado.
        """
        borrados = 0
        for upload in curso.upload_set.all():
            if upload.file:
                upload.file.delete(save=False)
                borrados += 1
        for video in curso.uploadvideo_set.all():
            if video.video:
                video.video.delete(save=False)
                borrados += 1
        for entrega in curso.submissions.all():
            if entrega.file:
                entrega.file.delete(save=False)
                borrados += 1
        # las preguntas de los cuestionarios del curso. Como `Question.quiz` es
        # ManyToMany, borrar el cuestionario deja la pregunta en la base; solo
        # se van las que no usa ningun otro curso, que las demas siguen vivas.
        for pregunta in Question.objects.filter(quiz__course=curso).distinct():
            if pregunta.quiz.exclude(course=curso).exists():
                continue
            if pregunta.figure:
                pregunta.figure.delete(save=False)
                borrados += 1
            pregunta.delete()
        return borrados
