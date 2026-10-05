import os
import tempfile
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase

from accounts.models import Student
from course.models import Course, Program, Submission, Upload
from quiz.models import MCQuestion, Quiz
from result.models import TakenCourse

User = get_user_model()


class EraseCourseDataTests(TestCase):
    """Derecho al olvido: si la orden dice que borra, no queda nada.

    Dos cosas no se veian mirando el codigo:
      · `_separa` contaba todas las matriculas, y como corre antes de borrar el
        curso, daba 1 a quien solo estaba ahi: `--alumnos` no borraba a nadie.
      · la cascada de Django borra filas, no ficheros, asi que los PDFs de los
        alumnos se quedaban en media/.
    """

    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.settings_override = self.settings(MEDIA_ROOT=self.media)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        self.program = Program.objects.create(title="Programa de prueba")
        self.curso = Course.objects.create(
            title="Curso a borrar",
            code="MF0487_3",
            program=self.program,
            level="Bachelor",
            year=1,
            semester="First",
        )
        self.otro_curso = Course.objects.create(
            title="Curso que sigue",
            code="OTRO-1",
            program=self.program,
            level="Bachelor",
            year=1,
            semester="First",
        )
        Upload.objects.create(
            title="Apuntes",
            course=self.curso,
            file=SimpleUploadedFile("apuntes.pdf", b"%PDF-1.4 apuntes"),
        )
        Upload.objects.create(
            title="Otra actividad",
            course=self.curso,
            file=SimpleUploadedFile("actividad.pdf", b"%PDF-1.4 actividad"),
            is_activity=True,
        )
        pregunta = MCQuestion.objects.create(content="Pregunta con figura")
        pregunta.figure = SimpleUploadedFile("figura.png", b"\x89PNG figura")
        pregunta.save()
        quiz = Quiz.objects.create(course=self.curso, title="Cuestionario")
        pregunta.quiz.add(quiz)

        # solo en el curso que se borra: su cuenta si se puede ir
        self.solo_aqui = self._alumno("tmp-solo", self.curso)
        # tambien en otro curso: su cuenta se queda
        self.en_dos = self._alumno("tmp-dos", self.curso)
        self.en_dos.takencourse_set.create(course=self.otro_curso)

        Submission.objects.create(
            course=self.curso,
            student=self.solo_aqui.student,
            document=Upload.objects.get(title="Otra actividad"),
            file=SimpleUploadedFile("trabajo.pdf", b"%PDF-1.4 trabajo"),
        )

    def _alumno(self, tmp, curso):
        user = User.objects.create_user(
            username=tmp, password="password", is_student=True
        )
        user = User.objects.get(pk=user.pk)  # el signal renombra la cuenta
        student = Student.objects.create(
            student=user, level="Bachelor", program=self.program
        )
        TakenCourse.objects.create(student=student, course=curso)
        return student

    def _ficheros(self):
        encontrados = []
        for raiz, _, ficheros in os.walk(self.media):
            for nombre in ficheros:
                encontrados.append(os.path.join(raiz, nombre))
        return encontrados

    def test_el_simulacro_no_borra_nada(self):
        salida = StringIO()
        call_command("erase_course_data", "--curso", self.curso.slug, stdout=salida)

        self.assertIn("Simulacro", salida.getvalue())
        self.assertTrue(Course.objects.filter(pk=self.curso.pk).exists())
        self.assertTrue(
            User.objects.filter(username=self.solo_aqui.student.username).exists()
        )
        self.assertEqual(len(self._ficheros()), 4)

    def test_borra_el_curso_y_sus_ficheros_de_media(self):
        call_command(
            "erase_course_data",
            "--curso",
            self.curso.slug,
            "--confirm",
            stdout=StringIO(),
        )

        self.assertFalse(Course.objects.filter(pk=self.curso.pk).exists())
        self.assertFalse(
            MCQuestion.objects.filter(content="Pregunta con figura").exists()
        )
        # apuntes + actividad + trabajo + figura: ninguno puede quedarse
        self.assertEqual(self._ficheros(), [])

    def test_alumnos_borra_a_quien_solo_estaba_en_este_curso(self):
        call_command(
            "erase_course_data",
            "--curso",
            self.curso.slug,
            "--alumnos",
            "--confirm",
            stdout=StringIO(),
        )

        # el bug: este se conservaba siempre y no se borraba nunca
        self.assertFalse(
            User.objects.filter(username=self.solo_aqui.student.username).exists()
        )
        # este sigue en otro curso: su cuenta y su matricula se quedan
        self.assertTrue(
            User.objects.filter(username=self.en_dos.student.username).exists()
        )
        self.assertTrue(
            TakenCourse.objects.filter(
                student=self.en_dos, course=self.otro_curso
            ).exists()
        )
        # y de este curso no queda matricula de nadie
        self.assertFalse(TakenCourse.objects.filter(course=self.curso).exists())
