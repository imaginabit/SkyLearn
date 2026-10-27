import os
import tempfile
from decimal import Decimal

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
    """El alumno se matricula, pero no se da de baja.

    Quitar a alguien de un curso es cosa del administrador, desde el panel: la
    vista `course_drop` y su ruta ya no existen.
    """

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
        # La ruta se compone a mano: el nombre `course_drop` ya no existe.
        self.url = reverse("course_registration").replace("registration", "drop")

    def test_la_ruta_de_baja_no_existe(self):
        self.client.login(username="alumno", password="password")

        for metodo in (self.client.get, self.client.post):
            with self.subTest(metodo=metodo.__name__):
                self.assertEqual(metodo(self.url).status_code, 404)

        self.assertTrue(
            TakenCourse.objects.filter(
                student=self.student, course=self.course
            ).exists()
        )

    def test_la_pagina_no_ofrece_darse_de_baja(self):
        self.client.login(username="alumno", password="password")

        response = self.client.get(reverse("course_registration"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "course/drop/")
        self.assertNotContains(response, 'name="course_ids"')


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
        upload = Upload.objects.get()
        adicional = UploadFile.objects.get()

        self.assertIn(
            reverse(
                "upload_file_download",
                kwargs={"slug": self.curso.slug, "file_id": upload.pk},
            ),
            html,
        )
        self.assertIn(
            reverse(
                "upload_archivo_download",
                kwargs={
                    "slug": self.curso.slug,
                    "file_id": upload.pk,
                    "archivo_id": adicional.pk,
                },
            ),
            html,
        )

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


class FormatosDeEntregaTests(TestCase):
    """Cada actividad decide en que formatos puede entregar el alumno.

    Por defecto, solo PDF; el docente puede marcar tambien ODT, DOCX, ZIP...
    El alumno ve los formatos admitidos al elegir la actividad, y el .odt tiene
    su propio icono y su aviso de LibreOffice: no es el formato pobre.
    """

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
            username="tmp-alumno-formatos", password="password", is_student=True
        )
        self.student = Student.objects.create(
            student=alumno, level="Bachelor", program=self.program
        )
        TakenCourse.objects.create(student=self.student, course=self.curso)
        self.client.force_login(self.student.student)
        self.url_curso = reverse("course_detail", kwargs={"slug": self.curso.slug})

    def _entrega(self, actividad, nombre):
        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                return self.client.post(
                    self.url_curso,
                    {
                        "document": actividad.pk,
                        "file": SimpleUploadedFile(nombre, b"%PDF-1.4"),
                    },
                )

    def _docente(self, username):
        docente = User.objects.create_user(
            username=username, password="password", is_lecturer=True
        )
        # el signal renombra la cuenta al crearla: hay que releerla
        docente = User.objects.get(pk=docente.pk)
        asignacion = CourseAllocation.objects.create(lecturer=docente)
        asignacion.courses.set([self.curso])
        self.client.force_login(docente)
        return docente

    def _sube_actividad(self, titulo, extensiones=None):
        datos = {
            "title": titulo,
            "file": SimpleUploadedFile("guia.docx", b"PK\x03\x04"),
            "is_activity": "on",
        }
        if extensiones:
            datos["extensiones_permitidas"] = extensiones
        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                return self.client.post(
                    reverse("upload_file_view", kwargs={"slug": self.curso.slug}), datos
                )

    def test_por_defecto_la_actividad_solo_admite_pdf(self):
        self.assertEqual(self.actividad.get_extensiones_permitidas(), ["pdf"])
        self.assertEqual(self.actividad.formatos_entrega(), "PDF")

    def test_el_alumno_no_entrega_un_formato_que_la_actividad_no_admite(self):
        response = self._entrega(self.actividad, "trabajo.odt")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Submission.objects.count(), 0)

    def test_el_alumno_entrega_en_los_formatos_admitidos(self):
        self.actividad.extensiones_permitidas = "pdf,odt"
        self.actividad.save()

        response = self._entrega(self.actividad, "trabajo.odt")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Submission.objects.count(), 1)

    def test_el_alumno_ve_los_formatos_de_cada_actividad(self):
        self.actividad.extensiones_permitidas = "pdf,odt"
        self.actividad.save()

        html = self.client.get(self.url_curso).content.decode()

        self.assertIn("Actividad 1 (PDF, ODT)", html)
        self.assertIn("Cada actividad admite unos formatos concretos", html)

    def test_el_formulario_del_docente_ofrece_los_formatos(self):
        self._docente("tmp-docente-widget")

        html = self.client.get(
            reverse("upload_file_view", kwargs={"slug": self.curso.slug})
        ).content.decode()

        for formato in ("PDF", "ODT", "DOCX", "ZIP"):
            self.assertIn(formato, html)

    def test_el_formulario_del_docente_guarda_los_formatos_marcados(self):
        self._docente("tmp-docente-formatos")

        response = self._sube_actividad("Actividad en dos formatos", ["pdf", "odt"])

        self.assertEqual(response.status_code, 302)
        upload = Upload.objects.get(title="Actividad en dos formatos")
        self.assertEqual(upload.extensiones_permitidas, "pdf,odt")

    def test_sin_marcar_ningun_formato_queda_en_pdf(self):
        self._docente("tmp-docente-sin-formatos")

        self._sube_actividad("Actividad sin formatos marcados")

        upload = Upload.objects.get(title="Actividad sin formatos marcados")
        self.assertEqual(upload.extensiones_permitidas, "pdf")

    def test_los_ficheros_odt_tienen_icono_y_aviso_de_libreoffice(self):
        UploadFile.objects.create(upload=self.actividad, file="course_files/guia.odt")

        html = self.client.get(self.url_curso).content.decode()

        self.assertIn("fa-file-lines", html)
        self.assertIn('title="LibreOffice Writer"', html)


class OcultarEntregasCorregidasTests(TestCase):
    """El check del curso esconde al docente las entregas ya corregidas.

    Solo las de las actividades NO evaluables: las evaluables cuentan para la
    nota final y se ven siempre, tenga el check puesto o no.
    """

    def setUp(self):
        self.program = Program.objects.create(title="Programa de prueba")
        self.curso = Course.objects.create(
            title="Curso con entregas",
            code="MIO-3",
            program=self.program,
            level="Bachelor",
            year=1,
            semester="First",
        )
        self.docente = User.objects.create_user(
            username="tmp-docente-ojo", password="password", is_lecturer=True
        )
        # el signal renombra la cuenta al crearla: hay que releerla
        self.docente = User.objects.get(pk=self.docente.pk)
        self.no_evaluable = Upload.objects.create(
            title="Actividad de practica",
            course=self.curso,
            file="actividad.pdf",
            is_activity=True,
            is_evaluable=False,
        )
        self.evaluable = Upload.objects.create(
            title="Actividad evaluable",
            course=self.curso,
            file="actividad.pdf",
            is_activity=True,
            is_evaluable=True,
        )
        alumno_uno = User.objects.create_user(
            username="tmp-alumno-uno", password="password", is_student=True
        )
        alumno_dos = User.objects.create_user(
            username="tmp-alumno-dos", password="password", is_student=True
        )
        self.corregida = Submission.objects.create(
            course=self.curso,
            document=self.no_evaluable,
            student=alumno_uno,
            file="submissions/uno.pdf",
            mark=8,
        )
        self.pendiente = Submission.objects.create(
            course=self.curso,
            document=self.no_evaluable,
            student=alumno_dos,
            file="submissions/dos.pdf",
        )
        self.evaluable_corregida = Submission.objects.create(
            course=self.curso,
            document=self.evaluable,
            student=alumno_uno,
            file="submissions/tres.pdf",
            mark=9,
        )
        self.url_curso = reverse("course_detail", kwargs={"slug": self.curso.slug})
        self.url_check = reverse(
            "course_ocultar_corregidas", kwargs={"slug": self.curso.slug}
        )

    def test_sin_el_check_se_ven_todas_las_entregas(self):
        self.client.force_login(self.docente)

        html = self.client.get(self.url_curso).content.decode()

        for fichero in ("uno.pdf", "dos.pdf", "tres.pdf"):
            self.assertIn(fichero, html)

    def test_con_el_check_se_oculta_la_no_evaluable_corregida(self):
        self.docente.ocultar_entregas_corregidas = True
        self.docente.save()
        self.client.force_login(self.docente)

        html = self.client.get(self.url_curso).content.decode()

        self.assertNotIn("uno.pdf", html)
        self.assertIn("dos.pdf", html)
        # la evaluable ya corregida sigue a la vista: cuenta para la nota final
        self.assertIn("tres.pdf", html)
        self.assertIn("Ver las ya corregidas", html)

    def test_el_check_del_curso_se_guarda(self):
        self.client.force_login(self.docente)

        self.client.post(self.url_check, {"ocultar": "on"})
        self.assertTrue(User.objects.get(pk=self.docente.pk).ocultar_entregas_corregidas)

        self.client.post(self.url_check, {})
        self.assertFalse(
            User.objects.get(pk=self.docente.pk).ocultar_entregas_corregidas
        )

    def test_el_check_se_ve_en_la_pagina_del_curso(self):
        self.client.force_login(self.docente)

        html = self.client.get(self.url_curso).content.decode()

        self.assertIn('name="ocultar"', html)
        self.assertIn("Ocultar las entregas ya corregidas", html)

    def test_cuenta_las_entregas_totales_y_visibles(self):
        """Sin el check, todas las entregas del curso se ven."""
        self.client.force_login(self.docente)

        html = self.client.get(self.url_curso).content.decode()

        self.assertIn("3 de 3 entregas visibles", html)

    def test_cuenta_cuando_hay_ocultas(self):
        self.docente.ocultar_entregas_corregidas = True
        self.docente.save()
        self.client.force_login(self.docente)

        html = self.client.get(self.url_curso).content.decode()

        # se ocultan la no evaluable ya corregida y la evaluable se sigue viendo
        self.assertIn("2 de 3 entregas visibles", html)

    def test_cuenta_calificadas_y_sin_calificar(self):
        """El reparto por estado de corrección va sobre todas las entregas."""
        self.docente.ocultar_entregas_corregidas = True
        self.docente.save()
        self.client.force_login(self.docente)

        html = self.client.get(self.url_curso).content.decode()

        # de las 3 hay 2 corregidas (una no evaluable y la evaluable) y 1 sin nota
        plano = " ".join(html.split())
        self.assertIn("calificadas 2", plano)
        self.assertIn("sin calificar 1", plano)

    def test_ofrece_ver_las_ya_corregidas(self):
        """Con todo oculto hay forma de volver a verlas sin el checkbox."""
        self.docente.ocultar_entregas_corregidas = True
        self.docente.save()
        self.client.force_login(self.docente)

        html = self.client.get(self.url_curso).content.decode()

        self.assertIn("Ver las ya corregidas", html)

    def test_el_check_no_lo_cambia_un_alumno(self):
        alumno = User.objects.create_user(
            username="tmp-alumno-check", password="password", is_student=True
        )
        self.client.force_login(alumno)

        response = self.client.post(self.url_check, {"ocultar": "on"})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            User.objects.get(pk=alumno.pk).ocultar_entregas_corregidas
        )

    def test_el_check_solo_se_cambia_por_post(self):
        self.client.force_login(self.docente)

        self.assertEqual(self.client.get(self.url_check).status_code, 405)


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


class MaterialDownloadTests(TestCase):
    """Cada alumno baja el material con su id en el nombre: E2_ugr-2026-1.odt.

    Es para las actividades evaluables: al devolver el ejercicio se sabe de
    quien es sin mirar el contenido. El prefijo sale del titulo de la actividad.
    """

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
        self.alumno = User.objects.create_user(
            username="tmp-alumno-e2", password="password", is_student=True
        )
        self.alumno = User.objects.get(pk=self.alumno.pk)

    def _url(self, upload):
        return reverse(
            "upload_file_download",
            kwargs={"slug": self.curso.slug, "file_id": upload.pk},
        )

    def _sube(self, titulo="Actividad evaluable E2", nombre="enunciado.odt"):
        """Crea la actividad; el fichero se guarda en MEDIA_ROOT al crearla."""
        return Upload.objects.create(
            title=titulo,
            course=self.curso,
            file=SimpleUploadedFile(nombre, b"contenido"),
            is_activity=True,
            is_evaluable=True,
        )

    def test_el_nombre_lleva_el_codigo_y_el_usuario(self):
        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                upload = self._sube()
                self.client.force_login(self.alumno)

                response = self.client.get(self._url(upload))

                self.assertEqual(response.status_code, 200)
                self.assertIn("attachment", response["Content-Disposition"])
                disposition = response["Content-Disposition"]
                self.assertIn("E2_", disposition)
                self.assertIn(self.alumno.username, disposition)
                self.assertIn(".odt", disposition)
                response.close()

    def test_cada_usuario_baja_con_su_nombre(self):
        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                upload = self._sube()
                otro = User.objects.create_user(
                    username="tmp-alumno-otro", password="password", is_student=True
                )
                otro = User.objects.get(pk=otro.pk)

                self.client.force_login(self.alumno)
                primera = self.client.get(self._url(upload))
                self.assertIn(self.alumno.username, primera["Content-Disposition"])
                primera.close()
                self.client.force_login(otro)
                segunda = self.client.get(self._url(upload))
                self.assertIn(otro.username, segunda["Content-Disposition"])
                segunda.close()

    def test_fichero_adicional_tambien_lleva_el_usuario(self):
        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                upload = self._sube()
                adicional = UploadFile.objects.create(
                    upload=upload,
                    file=SimpleUploadedFile("enunciado.docx", b"contenido docx"),
                )
                self.client.force_login(self.alumno)
                url = reverse(
                    "upload_archivo_download",
                    kwargs={
                        "slug": self.curso.slug,
                        "file_id": upload.pk,
                        "archivo_id": adicional.pk,
                    },
                )

                response = self.client.get(url)

                self.assertEqual(response.status_code, 200)
                self.assertIn("attachment", response["Content-Disposition"])
                self.assertIn("E2_", response["Content-Disposition"])
                self.assertIn(self.alumno.username, response["Content-Disposition"])
                self.assertIn(".docx", response["Content-Disposition"])
                self.assertEqual(b"".join(response.streaming_content), b"contenido docx")
                response.close()

    def test_sin_codigo_usa_el_titulo(self):
        """Una actividad sin E1/E2 se renombra con su titulo en minusculas."""
        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                upload = self._sube(titulo="Practica de cortafuegos")
                self.client.force_login(self.alumno)

                response = self.client.get(self._url(upload))

                self.assertIn("practica-de-cortafuegos", response["Content-Disposition"])
                response.close()

    def test_exige_sesion_iniciada(self):
        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                upload = self._sube()

                self.assertEqual(self.client.get(self._url(upload)).status_code, 302)

    def test_un_fichero_de_otro_curso_da_404(self):
        """Un `file_id` de otro curso no se descarga desde este."""
        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                otro_curso = Course.objects.create(
                    title="Otro curso",
                    code="MIO-9",
                    program=self.program,
                    level="Bachelor",
                    year=1,
                    semester="First",
                )
                upload = Upload.objects.create(
                    title="Actividad evaluable E2",
                    course=otro_curso,
                    file=SimpleUploadedFile("ajeno.odt", b"contenido"),
                    is_activity=True,
                )
                self.client.force_login(self.alumno)

                response = self.client.get(self._url(upload))

                self.assertEqual(response.status_code, 404)


class ProgramActivityProgressTests(TestCase):
    """El seguimiento resume entregas por curso, actividad y alumno."""

    def setUp(self):
        self.program = Program.objects.create(title="Programa con seguimiento")
        self.curso = Course.objects.create(
            title="Clase uno",
            code="MIO-1",
            program=self.program,
            level="Bachelor",
            year=1,
            semester="First",
        )
        self.otro_curso = Course.objects.create(
            title="Clase dos",
            code="MIO-2",
            program=self.program,
            level="Bachelor",
            year=1,
            semester="First",
        )
        self.docente = User.objects.create_user(
            username="seguimiento-docente", password="password", is_lecturer=True
        )
        asignacion = CourseAllocation.objects.create(lecturer=self.docente)
        asignacion.courses.set([self.curso])

        self.alumno = User.objects.create_user(
            username="seguimiento-alumno",
            password="password",
            is_student=True,
            first_name="Ana",
            last_name="Alumna",
        )
        self.alumno_sin_entrega = User.objects.create_user(
            username="seguimiento-sin-entrega",
            password="password",
            is_student=True,
            first_name="Beto",
            last_name="Alumno",
        )
        self.ficha = Student.objects.create(
            student=self.alumno, program=self.program, level="Bachelor"
        )
        self.ficha_sin_entrega = Student.objects.create(
            student=self.alumno_sin_entrega, program=self.program, level="Bachelor"
        )
        TakenCourse.objects.create(student=self.ficha, course=self.curso)
        TakenCourse.objects.create(student=self.ficha_sin_entrega, course=self.curso)
        TakenCourse.objects.create(student=self.ficha, course=self.otro_curso)

        self.actividad_calificada = Upload.objects.create(
            title="Actividad calificada",
            course=self.curso,
            file="actividad-uno.pdf",
            is_activity=True,
            is_evaluable=True,
        )
        self.actividad_pendiente = Upload.objects.create(
            title="Actividad pendiente",
            course=self.curso,
            file="actividad-dos.pdf",
            is_activity=True,
        )
        self.actividad_no_entrega = Upload.objects.create(
            title="Actividad de otra clase",
            course=self.otro_curso,
            file="actividad-otra.pdf",
            is_activity=True,
        )
        self.no_es_actividad = Upload.objects.create(
            title="Material de consulta",
            course=self.curso,
            file="guia.pdf",
            is_activity=False,
        )
        Submission.objects.create(
            course=self.curso,
            document=self.actividad_calificada,
            student=self.alumno,
            file="submissions/calificada.pdf",
            mark=Decimal("8.50"),
        )
        Submission.objects.create(
            course=self.curso,
            document=self.actividad_pendiente,
            student=self.alumno,
            file="submissions/pendiente.pdf",
        )

    def test_muestra_entrega_pendiente_nota_y_media(self):
        self.client.force_login(self.docente)

        html = self.client.get(
            reverse("program_detail", kwargs={"pk": self.program.pk})
        ).content.decode()

        self.assertIn("Seguimiento de actividades", html)
        self.assertIn("Actividad calificada", html)
        self.assertIn("Actividad pendiente", html)
        self.assertIn("8,50/10", html)
        self.assertIn("Entregada · sin calificar", html)
        self.assertIn("Pendiente", html)
        self.assertIn("8,50/10", html)  # media: solo cuenta la nota ya puesta
        self.assertNotIn("Actividad de otra clase", html)  # docente no asignado ahí
        self.assertNotIn("Material de consulta", html)  # no admite entrega

    def test_admin_ve_todos_los_cursos_del_programa(self):
        admin = User.objects.create_superuser(
            username="seguimiento-admin", email="admin@example.com", password="password"
        )
        self.client.force_login(admin)

        html = self.client.get(
            reverse("program_detail", kwargs={"pk": self.program.pk})
        ).content.decode()

        self.assertIn("Actividad de otra clase", html)

    def test_alumno_no_ve_la_tabla_de_seguimiento_del_programa(self):
        self.client.force_login(self.alumno)

        html = self.client.get(
            reverse("program_detail", kwargs={"pk": self.program.pk})
        ).content.decode()

        self.assertNotIn("Seguimiento de actividades", html)
        self.assertNotIn("Actividad calificada", html)


class DocumentoOcultoTests(TestCase):
    """Lo que se sube oculto no existe para el alumnado.

    Ni aparece en la lista del curso, ni se puede elegir en el formulario de
    entrega, ni se descarga por la URL del fichero. El docente lo ve siempre.
    """

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
        self.alumno = User.objects.create_user(
            username="tmp-oculto-alumno", password="password", is_student=True
        )
        self.docente = User.objects.create_user(
            username="tmp-oculto-docente", password="password", is_lecturer=True
        )
        self.student = Student.objects.create(
            student=self.alumno, level="Bachelor", program=self.program
        )
        TakenCourse.objects.create(student=self.student, course=self.curso)
        self.oculta = Upload.objects.create(
            title="Actividad evaluable E2-B",
            course=self.curso,
            file="oculta.pdf",
            is_activity=True,
            is_evaluable=True,
            visible=False,
        )
        self.url = reverse("course_detail", kwargs={"slug": self.curso.slug})

    def _descarga(self, upload):
        return reverse(
            "upload_file_download",
            kwargs={"slug": self.curso.slug, "file_id": upload.pk},
        )

    def test_el_alumno_no_la_ve_en_la_lista(self):
        self.client.force_login(self.alumno)

        html = self.client.get(self.url).content.decode()

        self.assertNotIn(self.oculta.title, html)

    def test_el_alumno_no_puede_entregarla(self):
        self.client.force_login(self.alumno)

        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                self.client.post(
                    self.url,
                    {
                        "document": self.oculta.pk,
                        "file": SimpleUploadedFile("trabajo.pdf", b"%PDF-1.4"),
                    },
                )

        self.assertEqual(Submission.objects.count(), 0)

    def test_el_alumno_no_la_descarga(self):
        self.client.force_login(self.alumno)

        self.assertEqual(self.client.get(self._descarga(self.oculta)).status_code, 404)

    def test_el_docente_si_la_ve_y_la_descarga(self):
        self.client.force_login(self.docente)

        html = self.client.get(self.url).content.decode()
        self.assertIn(self.oculta.title, html)

        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                upload = Upload.objects.create(
                    title="Oculta con fichero",
                    course=self.curso,
                    file=SimpleUploadedFile("oculta.pdf", b"%PDF-1.4"),
                    is_activity=True,
                    visible=False,
                )
                response = self.client.get(self._descarga(upload))

        self.assertEqual(response.status_code, 200)


class MazosDelCursoTests(TestCase):
    """Un curso puede no embeber ningun mazo.

    El curso del temario completo acumula el material de todas las clases:
    embeber solo uno dejaba a los demas escondidos. Con `embeber_mazo` a False
    no se muestra el iframe, pero todos los mazos se pueden abrir en una
    pestana y descargar.
    """

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
        self.lector = User.objects.create_user(
            username="tmp-mazos-lector", password="password"
        )
        self.url = reverse("course_detail", kwargs={"slug": self.curso.slug})

    def _mazo(self, titulo="Presentacion", nombre="presentacion.html"):
        return Upload.objects.create(
            title=titulo,
            course=self.curso,
            file=SimpleUploadedFile(nombre, b"<html>mazo</html>"),
        )

    def _abrir(self, upload):
        return reverse(
            "deck_abrir", kwargs={"slug": self.curso.slug, "file_id": upload.pk}
        )

    def test_por_defecto_el_curso_embebe_el_mazo(self):
        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                self._mazo()
                self.client.force_login(self.lector)

                html = self.client.get(self.url).content.decode()

                self.assertIn("<iframe", html)

    def test_sin_embeber_no_hay_iframe_pero_estan_todos_los_mazos(self):
        self.curso.embeber_mazo = False
        self.curso.save()
        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                primero = self._mazo("Presentacion de la clase 2", "clase2.html")
                segundo = self._mazo("Presentacion de la clase 3", "clase3.html")
                self.client.force_login(self.lector)

                html = self.client.get(self.url).content.decode()

                self.assertNotIn("<iframe", html)
                self.assertIn(self._abrir(primero), html)
                self.assertIn(self._abrir(segundo), html)

    def test_abrir_un_mazo_lo_sirve_en_linea(self):
        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                mazo = self._mazo()
                self.client.force_login(self.lector)

                response = self.client.get(self._abrir(mazo))

                self.assertEqual(response.status_code, 200)
                self.assertIn("inline", response["Content-Disposition"])
                self.assertEqual(b"".join(response.streaming_content), b"<html>mazo</html>")

    def test_abrir_un_documento_que_no_es_mazo_da_404(self):
        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                pdf = Upload.objects.create(
                    title="Una ficha",
                    course=self.curso,
                    file=SimpleUploadedFile("ficha.pdf", b"%PDF-1.4"),
                )
                self.client.force_login(self.lector)

                self.assertEqual(self.client.get(self._abrir(pdf)).status_code, 404)

    def test_el_alumno_no_abre_un_mazo_oculto(self):
        self.alumno = User.objects.create_user(
            username="tmp-mazos-alumno", password="password", is_student=True
        )
        self.docente = User.objects.create_user(
            username="tmp-mazos-docente", password="password", is_lecturer=True
        )
        student = Student.objects.create(
            student=self.alumno, level="Bachelor", program=self.program
        )
        TakenCourse.objects.create(student=student, course=self.curso)
        with tempfile.TemporaryDirectory() as media:
            with self.settings(MEDIA_ROOT=media):
                oculto = self._mazo("Mazo oculto")
                Upload.objects.filter(pk=oculto.pk).update(visible=False)

                self.client.force_login(self.alumno)
                self.assertEqual(self.client.get(self._abrir(oculto)).status_code, 404)

                self.client.force_login(self.docente)
                self.assertEqual(self.client.get(self._abrir(oculto)).status_code, 200)
