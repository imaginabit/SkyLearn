import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from accounts.models import Student
from core.models import Semester, Session
from course.models import (
    Course,
    CourseAllocation,
    Program,
    Submission,
    Upload,
    UploadVideo,
)
from result.models import TakenCourse

User = get_user_model()


class CourseDropTests(TestCase):
    """Desapuntar es un POST: antes un GET devolvia None y Django petaba."""

    def setUp(self):
        self.program = Program.objects.create(title="Programa de prueba")
        self.course = Course.objects.create(
            title="Curso de prueba",
            code="TEST-1",
            program=self.program,
            level="Bachelor",
            year=1,
            semester="First",
        )
        self.user = get_user_model().objects.create_user(
            username="alumno", email="alumno@example.com", password="password"
        )
        self.user.is_student = True
        self.user.save()
        self.student = Student.objects.create(
            student=self.user, level="Bachelor", program=self.program
        )
        self.enrollment = TakenCourse.objects.create(
            student=self.student, course=self.course
        )
        self.url = reverse("course_drop")

    def test_get_is_rejected(self):
        self.client.login(username="alumno", password="password")

        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_post_drops_the_enrollment(self):
        self.client.login(username="alumno", password="password")

        response = self.client.post(self.url, {"course_ids": [self.course.pk]})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            TakenCourse.objects.filter(
                student=self.student, course=self.course
            ).exists()
        )


class MaterialDeCursoAuthorizationTests(TestCase):
    """El material de un curso solo lo toca quien lo tiene asignado.

    Estas vistas cogian el fichero o el video por pk/slug sin mirar el curso,
    con lo que cualquier docente podia editar o borrar el material de otro.
    """

    def setUp(self):
        self.program = Program.objects.create(title="Programa de prueba")
        self.curso = Course.objects.create(
            title="Curso asignado",
            code="MIO-1",
            program=self.program,
            level="Bachelor",
            year=1,
            semester="First",
        )
        self.docente = self._docente("tmp-docente-1")
        self.docente_ajeno = self._docente("tmp-docente-2")
        self.admin = User.objects.create_superuser(
            username="admin-test", email="admin@example.com", password="password"
        )
        asignacion = CourseAllocation.objects.create(lecturer=self.docente)
        asignacion.courses.set([self.curso])
        self.fichero = Upload.objects.create(
            title="Apuntes", course=self.curso, file="apuntes.pdf"
        )
        self.video = UploadVideo.objects.create(
            title="Clase 1", course=self.curso, video="clase1.mp4"
        )
        self.url_fichero = reverse(
            "upload_file_delete",
            kwargs={"slug": self.curso.slug, "file_id": self.fichero.pk},
        )
        self.url_video = reverse(
            "upload_video_delete",
            kwargs={"slug": self.curso.slug, "video_slug": self.video.slug},
        )

    def _docente(self, tmp):
        user = User.objects.create_user(
            username=tmp, password="password", is_lecturer=True
        )
        # el signal renombra la cuenta al crearla: hay que releerla
        return User.objects.get(pk=user.pk)

    def test_docente_de_otro_curso_no_borra_el_fichero(self):
        self.client.force_login(self.docente_ajeno)

        response = self.client.post(self.url_fichero)

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Upload.objects.filter(pk=self.fichero.pk).exists())

    def test_docente_de_otro_curso_no_borra_el_video(self):
        self.client.force_login(self.docente_ajeno)

        response = self.client.post(self.url_video)

        self.assertEqual(response.status_code, 404)
        self.assertTrue(UploadVideo.objects.filter(pk=self.video.pk).exists())

    def test_docente_asignado_borra_el_fichero(self):
        self.client.force_login(self.docente)

        self.assertEqual(self.client.post(self.url_fichero).status_code, 302)
        self.assertFalse(Upload.objects.filter(pk=self.fichero.pk).exists())

    def test_superusuario_sigue_pudiendo_borrar(self):
        self.client.force_login(self.admin)

        self.assertEqual(self.client.post(self.url_video).status_code, 302)
        self.assertFalse(UploadVideo.objects.filter(pk=self.video.pk).exists())

    def test_borrar_por_get_no_hace_nada(self):
        # era un enlace <a href>: un GET bastaba para destruir
        self.client.force_login(self.docente)

        response = self.client.get(self.url_fichero)

        self.assertEqual(response.status_code, 405)
        self.assertTrue(Upload.objects.filter(pk=self.fichero.pk).exists())


class MatriculaTests(TestCase):
    """Solo se puede matricular en los cursos que le tocan.

    El POST cogia los ids del POST tal cual (`Course.objects.get(pk=ids[s])`),
    con lo que servia mandar cualquier curso del mundo y crear la matricula a
    mano, y `create` permitia repetirla.
    """

    def setUp(self):
        Session.objects.create(session="2026-2027", is_current_session=True)
        self.semester = Semester.objects.create(
            semester="First", is_current_semester=True, session=Session.objects.first()
        )
        self.program = Program.objects.create(title="Programa propio")
        self.program_ajeno = Program.objects.create(title="Programa ajeno")
        self.curso = self._curso("MIO-1", self.program)
        self.curso_ajeno = self._curso("AJENO-1", self.program_ajeno)
        self.curso_ajeno_nivel = self._curso("AJENO-2", self.program, level="Master")
        alumno = User.objects.create_user(
            username="tmp-alumno", password="password", is_student=True
        )
        self.student = Student.objects.create(
            student=alumno, level="Bachelor", program=self.program
        )
        self.url = reverse("course_registration")

    def _curso(self, code, program, level="Bachelor"):
        return Course.objects.create(
            title="Curso %s" % code,
            code=code,
            program=program,
            level=level,
            year=1,
            semester="First",
        )

    def test_se_matricula_en_un_curso_de_su_programa_y_nivel(self):
        self.client.force_login(self.student.student)

        response = self.client.post(self.url, {str(self.curso.pk): "1"})

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            TakenCourse.objects.filter(student=self.student, course=self.curso).exists()
        )

    def test_no_se_matricula_en_un_curso_de_otro_programa(self):
        self.client.force_login(self.student.student)

        response = self.client.post(self.url, {str(self.curso_ajeno.pk): "1"})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            TakenCourse.objects.filter(
                student=self.student, course=self.curso_ajeno
            ).exists()
        )

    def test_no_se_matricula_en_un_curso_de_otro_nivel(self):
        self.client.force_login(self.student.student)

        self.client.post(self.url, {str(self.curso_ajeno_nivel.pk): "1"})

        self.assertFalse(
            TakenCourse.objects.filter(
                student=self.student, course=self.curso_ajeno_nivel
            ).exists()
        )

    def test_no_repite_la_misma_matricula(self):
        self.client.force_login(self.student.student)

        self.client.post(self.url, {str(self.curso.pk): "1"})
        self.client.post(self.url, {str(self.curso.pk): "1"})

        self.assertEqual(TakenCourse.objects.filter(student=self.student).count(), 1)


class EntregaTests(TestCase):
    """Solo se entrega si hay matricula en el curso."""

    def setUp(self):
        self.program = Program.objects.create(title="Programa de prueba")
        self.curso = Course.objects.create(
            title="Curso de prueba",
            code="MIO-1",
            program=self.program,
            level="Bachelor",
            year=1,
            semester="First",
        )
        self.actividad = Upload.objects.create(
            title="Actividad 1",
            course=self.curso,
            file="actividad.pdf",
            is_activity=True,
        )
        alumno = User.objects.create_user(
            username="tmp-alumno", password="password", is_student=True
        )
        self.student = Student.objects.create(
            student=alumno, level="Bachelor", program=self.program
        )
        self.url = reverse("course_detail", kwargs={"slug": self.curso.slug})

    def _entrega(self):
        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                return self.client.post(
                    self.url,
                    {
                        "document": self.actividad.pk,
                        "file": SimpleUploadedFile("trabajo.pdf", b"%PDF-1.4"),
                    },
                )

    def test_entrega_con_matricula(self):
        TakenCourse.objects.create(student=self.student, course=self.curso)
        self.client.force_login(self.student.student)

        response = self._entrega()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Submission.objects.count(), 1)

    def test_no_entrega_sin_matricula(self):
        self.client.force_login(self.student.student)

        response = self._entrega()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Submission.objects.count(), 0)

    def test_no_muestra_el_formulario_sin_matricula(self):
        self.client.force_login(self.student.student)

        html = self.client.get(self.url).content.decode()

        self.assertNotIn("Enviar mi entrega", html)
