from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Student
from core.models import Semester, Session
from course.models import Course, CourseAllocation, Program
from result.models import TakenCourse

User = get_user_model()


class AddScoreForAuthorizationTests(TestCase):
    """Un docente solo puede poner notas de los cursos que tiene asignados.

    El POST antes cogia los ids del POST sin filtrar, asi que bastaba mandar el
    id de una matricula de otro curso para escribir sus notas.
    """

    def setUp(self):
        self.session = Session.objects.create(
            session="2026-2027", is_current_session=True
        )
        self.semester = Semester.objects.create(
            semester="First", is_current_semester=True, session=self.session
        )
        self.program = Program.objects.create(title="Programa de prueba")
        self.curso_propio = Course.objects.create(
            title="Curso asignado",
            code="MIO-1",
            program=self.program,
            level="Bachelor",
            year=1,
            semester="First",
        )
        self.curso_ajeno = Course.objects.create(
            title="Curso sin asignar",
            code="AJENO-1",
            program=self.program,
            level="Bachelor",
            year=1,
            semester="First",
        )
        lecturer = User.objects.create_user(
            username="tmp-lecturer", password="password", is_lecturer=True
        )
        # el signal renombra la cuenta al crearla: hay que releerla
        self.lecturer = User.objects.get(pk=lecturer.pk)
        asignacion = CourseAllocation.objects.create(lecturer=self.lecturer)
        asignacion.courses.set([self.curso_propio])
        alumno = User.objects.create_user(
            username="tmp-alumno", password="password", is_student=True
        )
        self.student = Student.objects.create(
            student=alumno, level="Bachelor", program=self.program
        )
        self.tc_propio = TakenCourse.objects.create(
            student=self.student, course=self.curso_propio
        )
        self.tc_ajeno = TakenCourse.objects.create(
            student=self.student, course=self.curso_ajeno
        )
        self.url = reverse("add_score_for", kwargs={"id": self.curso_propio.pk})

    def test_no_escribe_notas_de_un_curso_no_asignado(self):
        self.client.force_login(self.lecturer)

        response = self.client.post(
            self.url, {str(self.tc_ajeno.pk): ["1", "2", "3", "4", "5"]}
        )

        self.assertEqual(response.status_code, 302)
        self.tc_ajeno.refresh_from_db()
        self.assertEqual(self.tc_ajeno.assignment, Decimal("0.00"))
        self.assertEqual(self.tc_ajeno.total, Decimal("0.00"))

    def test_escribe_las_notas_de_su_curso(self):
        self.client.force_login(self.lecturer)

        response = self.client.post(
            self.url, {str(self.tc_propio.pk): ["1", "2", "3", "4", "5"]}
        )

        self.assertEqual(response.status_code, 302)
        self.tc_propio.refresh_from_db()
        self.assertEqual(self.tc_propio.assignment, Decimal("1"))
