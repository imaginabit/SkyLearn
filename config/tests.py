from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Student
from core.models import Semester, Session
from course.models import Course, CourseAllocation, Program, Upload, UploadVideo
from quiz.models import Quiz

User = get_user_model()


class PaginasConBorradoTests(TestCase):
    """Las paginas con boton de borrar renderizan, y el borrado es un POST.

    El include del borrado por POST solo se ve al renderizar: un `{% url ... as %}`
    mal escrito no lo pilla ningun test de vista, y en produccion sale un 500.
    """

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="admin-smoke", email="admin@example.com", password="password"
        )
        self.session = Session.objects.create(
            session="2026-2027", is_current_session=True
        )
        self.semester = Semester.objects.create(
            semester="First", is_current_semester=True, session=self.session
        )
        self.program = Program.objects.create(title="Programa de prueba")
        self.course = Course.objects.create(
            title="Curso de prueba",
            code="MIO-1",
            program=self.program,
            level="Bachelor",
            year=1,
            semester="First",
        )
        self.asignacion = CourseAllocation.objects.create(lecturer=self.admin)
        self.asignacion.courses.set([self.course])
        Upload.objects.create(title="Apuntes", course=self.course, file="apuntes.pdf")
        UploadVideo.objects.create(
            title="Clase 1", course=self.course, video="clase1.mp4"
        )
        Quiz.objects.create(course=self.course, title="Cuestionario 1")
        alumno = User.objects.create_user(
            username="tmp-alumno", password="password", is_student=True
        )
        Student.objects.create(student=alumno, level="Bachelor", program=self.program)

    def test_las_paginas_de_listado_renderizan(self):
        self.client.force_login(self.admin)
        slug = self.course.slug

        paginas = [
            reverse("home"),
            reverse("session_list"),
            reverse("semester_list"),
            reverse("lecturer_list"),
            reverse("student_list"),
            reverse("programs"),
            reverse("program_detail", kwargs={"pk": self.program.pk}),
            reverse("course_detail", kwargs={"slug": slug}),
            reverse("course_allocation_view"),
            reverse("quiz_index", kwargs={"slug": slug}),
        ]

        for url in paginas:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_el_borrado_aparece_como_form_con_csrf_y_sin_enlace(self):
        self.client.force_login(self.admin)
        url_borrar = reverse("course_deallocate", kwargs={"pk": self.asignacion.pk})

        html = self.client.get(reverse("course_allocation_view")).content.decode()

        self.assertIn('action="%s"' % url_borrar, html)
        self.assertIn('method="POST"', html)
        self.assertIn("csrfmiddlewaretoken", html)
        # lo que faltaba: que un GET (un enlace) bastara para borrar
        self.assertNotIn('href="%s"' % url_borrar, html)
        # y que ademas pregunte antes, que esto no tiene vuelta atras
        self.assertIn("onsubmit", html)
        self.assertIn("confirm(", html)

    def test_el_borrado_de_material_del_curso_pregunta_que_se_borra(self):
        self.client.force_login(self.admin)

        html = self.client.get(
            reverse("course_detail", kwargs={"slug": self.course.slug})
        ).content.decode()

        self.assertIn("confirm(", html)
        self.assertIn("¿Borrar esta actividad", html)
