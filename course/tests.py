import os
import tempfile

from django.conf import settings
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
    UploadFile,
    UploadVideo,
)
from result.models import TakenCourse

User = get_user_model()
MEDIA_URL = settings.MEDIA_URL


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


class ArchivosAdicionalesTests(TestCase):
    """Una actividad lleva mas de un fichero: el .docx y el .odt, el enunciado
    aparte, un .zip. El principal sigue siendo `Upload.file`; los demas son
    filas de `UploadFile`, que el alumno tambien ve y puede bajar.

    El servidor no tiene LibreOffice, asi que la conversion no se hace aqui:
    el docente sube los dos formatos y el alumno elige.
    """

    def setUp(self):
        self.program = Program.objects.create(title="Programa de prueba")
        self.curso = Course.objects.create(
            title="Curso con anexos",
            code="MIO-2",
            program=self.program,
            level="Bachelor",
            year=1,
            semester="First",
        )
        self.docente = User.objects.create_user(
            username="tmp-docente-anexos", password="password", is_lecturer=True
        )
        # el signal renombra la cuenta al crearla: hay que releerla
        self.docente = User.objects.get(pk=self.docente.pk)
        asignacion = CourseAllocation.objects.create(lecturer=self.docente)
        asignacion.courses.set([self.curso])
        self.url_subida = reverse("upload_file_view", kwargs={"slug": self.curso.slug})
        self.url_curso = reverse("course_detail", kwargs={"slug": self.curso.slug})

    def _sube(self, titulo="Actividad 1", archivos=None):
        datos = {
            "title": titulo,
            "file": SimpleUploadedFile("guia.docx", b"PK\x03\x04"),
        }
        if archivos:
            datos["archivos"] = [
                SimpleUploadedFile(nombre, b"%PDF-1.4") for nombre in archivos
            ]
        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                self.client.force_login(self.docente)
                response = self.client.post(self.url_subida, datos)
                self.url_curso_html = self.client.get(self.url_curso).content.decode()
        return response

    def test_una_actividad_admite_varios_ficheros(self):
        self._sube(archivos=["actividad.odt", "enunciado.pdf"])

        self.assertEqual(Upload.objects.count(), 1)
        self.assertEqual(
            sorted(u.file.name.rsplit("/", 1)[-1] for u in UploadFile.objects.all()),
            ["actividad.odt", "enunciado.pdf"],
        )

    def test_el_alumno_ve_y_puede_bajar_los_dos_formatos(self):
        self._sube(archivos=["actividad.odt"])

        html = self.url_curso_html

        self.assertIn(f"{MEDIA_URL}course_files/actividad.odt", html)
        self.assertIn(f"{MEDIA_URL}course_files/guia", html)

    def test_editar_suma_ficheros_sin_tocar_el_principal(self):
        self._sube(archivos=[])
        upload = Upload.objects.get()
        url_edicion = reverse(
            "upload_file_edit",
            kwargs={"slug": self.curso.slug, "file_id": upload.pk},
        )
        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                self.client.force_login(self.docente)
                response = self.client.post(
                    url_edicion,
                    {
                        "title": upload.title,
                        "archivos": [SimpleUploadedFile("actividad.odt", b"%PDF-1.4")],
                    },
                )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(upload.file.name.endswith("guia.docx"))
        self.assertEqual(UploadFile.objects.count(), 1)

    def test_borrar_la_actividad_borra_sus_ficheros_del_disco(self):
        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                self.client.force_login(self.docente)
                self.client.post(
                    self.url_subida,
                    {
                        "title": "Actividad con anexos",
                        "file": SimpleUploadedFile("guia.docx", b"PK\x03\x04"),
                        "archivos": [SimpleUploadedFile("actividad.odt", b"%PDF-1.4")],
                    },
                )
                upload = Upload.objects.get()
                principal = upload.file.path
                adicional = upload.archivos.get().file.path
                self.assertTrue(os.path.exists(adicional))

                url_borrado = reverse(
                    "upload_file_delete",
                    kwargs={"slug": self.curso.slug, "file_id": upload.pk},
                )
                self.client.post(url_borrado)

                self.assertFalse(os.path.exists(principal))
                self.assertFalse(os.path.exists(adicional))

    def test_docente_de_otro_curso_no_borra_un_fichero_adicional(self):
        self._sube(archivos=["actividad.odt"])
        upload = Upload.objects.get()
        archivo = upload.archivos.get()
        ajeno = User.objects.create_user(
            username="tmp-docente-ajeno-anexos", password="password", is_lecturer=True
        )
        ajeno = User.objects.get(pk=ajeno.pk)
        url = reverse(
            "upload_archivo_delete",
            kwargs={
                "slug": self.curso.slug,
                "file_id": upload.pk,
                "archivo_id": archivo.pk,
            },
        )

        self.client.force_login(ajeno)
        response = self.client.post(url)

        self.assertEqual(response.status_code, 404)
        self.assertTrue(UploadFile.objects.filter(pk=archivo.pk).exists())


class DeckDownloadTests(TestCase):
    """La presentacion se descarga como adjunto y no se abre en el navegador."""

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
        self.url = reverse("deck_download", kwargs={"slug": self.curso.slug})

    def _deck(self, media):
        Upload.objects.create(
            title="Presentacion del curso",
            course=self.curso,
            file=SimpleUploadedFile("presentacion.html", b"<html>mazo</html>"),
        )

    def test_404_si_el_curso_no_tiene_presentacion(self):
        self.client.force_login(User.objects.create_user(username="tmp-lector", password="password"))

        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_devuelve_el_html_con_disposition_adjunto(self):
        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                self._deck(media)
                self.client.force_login(
                    User.objects.create_user(username="tmp-lector", password="password")
                )

                response = self.client.get(self.url)

                self.assertEqual(response.status_code, 200)
                self.assertIn("attachment", response["Content-Disposition"])
                self.assertIn("presentacion.html", response["Content-Disposition"])
                self.assertEqual(b"".join(response.streaming_content), b"<html>mazo</html>")

    def test_el_embed_y_la_descarga_coinciden_en_el_mismo_fichero(self):
        # hay dos .html en el curso: la vista y la descarga tienen que teachcar
        # el mismo, y no depender del orden en que salga la consulta
        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                segunda = Upload.objects.create(
                    title="Segunda presentacion",
                    course=self.curso,
                    file=SimpleUploadedFile("segunda.html", b"<html>segunda</html>"),
                )
                self._deck(media)
                self.client.force_login(
                    User.objects.create_user(username="tmp-lector", password="password")
                )

                pagina = self.client.get(
                    reverse("course_detail", kwargs={"slug": self.curso.slug})
                ).content.decode()
                descarga = self.client.get(self.url)

                self.assertIn(segunda.file.url, pagina)
                self.assertIn(b"segunda", b"".join(descarga.streaming_content))

    def test_la_pagina_muestra_el_boton_de_descarga(self):
        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                self._deck(media)
                self.client.force_login(
                    User.objects.create_user(username="tmp-lector", password="password")
                )

                html = self.client.get(
                    reverse("course_detail", kwargs={"slug": self.curso.slug})
                ).content.decode()

                self.assertIn(reverse("deck_download", kwargs={"slug": self.curso.slug}), html)
                self.assertIn("Descargar HTML", html)
