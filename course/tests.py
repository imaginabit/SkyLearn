from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Student
from course.models import (
    Course,
    CourseAllocation,
    Program,
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
