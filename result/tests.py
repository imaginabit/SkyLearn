from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from accounts.models import Student
from core.models import Semester, Session
from course.models import Course, CourseAllocation, Program
from result.models import TakenCourse

User = get_user_model()


class _NotasEscenario:
    """Un curso con docente asignado y alumnos matriculados, de lo que hay."""

    def _montar(self):
        self.session = Session.objects.create(
            session="2026-2027", is_current_session=True
        )
        self.semester = Semester.objects.create(
            semester="First", is_current_semester=True, session=self.session
        )
        self.program = Program.objects.create(title="Programa de prueba")
        self.curso = Course.objects.create(
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
        self.docente = self._docente("tmp-docente-1")
        self.docente_ajeno = self._docente("tmp-docente-2")
        asignacion = CourseAllocation.objects.create(lecturer=self.docente)
        asignacion.courses.set([self.curso])
        self.tc_propio = TakenCourse.objects.create(
            student=self._alumno("tmp-alumno-1"), course=self.curso
        )
        self.tc_ajeno = TakenCourse.objects.create(
            student=self.tc_propio.student, course=self.curso_ajeno
        )
        self.tc_segundo = TakenCourse.objects.create(
            student=self._alumno("tmp-alumno-2"), course=self.curso
        )
        self.url = reverse("add_score_for", kwargs={"id": self.curso.pk})

    def _docente(self, tmp):
        user = User.objects.create_user(
            username=tmp, password="password", is_lecturer=True
        )
        # el signal renombra la cuenta al crearla: hay que releerla
        return User.objects.get(pk=user.pk)

    def _alumno(self, tmp):
        user = User.objects.create_user(
            username=tmp, password="password", is_student=True
        )
        user = User.objects.get(pk=user.pk)
        return Student.objects.create(
            student=user, level="Bachelor", program=self.program
        )


class AddScoreForAuthorizationTests(_NotasEscenario, TestCase):
    """Un docente solo puede poner notas de los cursos que tiene asignados.

    El POST antes cogia los ids del POST sin filtrar, asi que bastaba mandar el
    id de una matricula de otro curso para escribir sus notas.
    """

    def setUp(self):
        self._montar()

    def test_no_escribe_notas_de_un_curso_no_asignado(self):
        self.client.force_login(self.docente_ajeno)

        response = self.client.post(
            self.url, {str(self.tc_ajeno.pk): ["1", "2", "3", "4", "5"]}
        )

        self.assertEqual(response.status_code, 302)
        self.tc_ajeno.refresh_from_db()
        self.assertEqual(self.tc_ajeno.total, Decimal("0.00"))

    def test_escribe_las_notas_de_su_curso(self):
        self.client.force_login(self.docente)

        response = self.client.post(
            self.url, {str(self.tc_propio.pk): ["1", "2", "3", "4", "5"]}
        )

        self.assertEqual(response.status_code, 302)
        self.tc_propio.refresh_from_db()
        self.assertEqual(self.tc_propio.assignment, Decimal("1"))


class ValidacionDeNotasTests(_NotasEscenario, TestCase):
    """Las notas del POST se validan antes de tocar la base de datos.

    Antes iban en crudo a un DecimalField: un valor no numerico se guardaba y
    hacia que la pagina de notas reventara (500) al leerlos, y no solo para
    quien los introduce.
    """

    def setUp(self):
        self._montar()

    def _post(self, *valores, matricula=None):
        self.client.force_login(self.docente)
        return self.client.post(
            self.url,
            {str((matricula or self.tc_propio).pk): [str(v) for v in valores]},
        )

    def test_guarda_notas_validas(self):
        response = self._post(10, 10, 10, 10, 10)

        self.assertEqual(response.status_code, 302)
        self.tc_propio.refresh_from_db()
        self.assertEqual(self.tc_propio.assignment, Decimal("10"))
        self.assertEqual(self.tc_propio.total, Decimal("50"))

    def test_no_guarda_una_nota_no_numerica(self):
        response = self._post("abc", 10, 10, 10, 10)

        self.assertEqual(response.status_code, 302)
        self.tc_propio.refresh_from_db()
        self.assertEqual(self.tc_propio.total, Decimal("0.00"))

    def test_no_guarda_una_nota_vacia(self):
        response = self._post("", 10, 10, 10, 10)

        self.assertEqual(response.status_code, 302)
        self.tc_propio.refresh_from_db()
        self.assertEqual(self.tc_propio.total, Decimal("0.00"))

    def test_no_guarda_una_nota_negativa(self):
        response = self._post(-5, 10, 10, 10, 10)

        self.assertEqual(response.status_code, 302)
        self.tc_propio.refresh_from_db()
        self.assertEqual(self.tc_propio.total, Decimal("0.00"))

    def test_no_guarda_si_la_suma_pasa_de_100(self):
        # la escala la fija get_grade(): 0 a 100
        response = self._post(30, 30, 30, 30, 30)

        self.assertEqual(response.status_code, 302)
        self.tc_propio.refresh_from_db()
        self.assertEqual(self.tc_propio.total, Decimal("0.00"))

    def test_no_guarda_si_faltan_notas(self):
        response = self._post(10, 10)

        self.assertEqual(response.status_code, 302)
        self.tc_propio.refresh_from_db()
        self.assertEqual(self.tc_propio.total, Decimal("0.00"))

    def test_una_nota_mala_no_deja_guardada_la_buena(self):
        self.client.force_login(self.docente)

        response = self.client.post(
            self.url,
            {
                str(self.tc_propio.pk): ["10", "10", "10", "10", "10"],
                str(self.tc_segundo.pk): ["abc", "0", "0", "0", "0"],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.tc_propio.refresh_from_db()
        self.tc_segundo.refresh_from_db()
        self.assertEqual(self.tc_propio.total, Decimal("0.00"))
        self.assertEqual(self.tc_segundo.total, Decimal("0.00"))


class AlumnoSinFichaTests(TestCase):
    """Un alumno sin fila Student da 404, no 500.

    Puede pasar si el alta quedo a medias: la cuenta existe con is_student pero
    sin la ficha, y estas vistas reventaban con DoesNotExist.
    """

    def setUp(self):
        Session.objects.create(session="2026-2027", is_current_session=True)
        self.user = User.objects.create_user(
            username="tmp-alumno", password="password", is_student=True
        )
        self.user = User.objects.get(pk=self.user.pk)

    def test_las_paginas_de_notas_dan_404(self):
        self.client.force_login(self.user)

        for url in [reverse("grade_results"), reverse("ass_results")]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)


class MatriculaUnicaTests(_NotasEscenario, TestCase):
    """No se puede matricular dos veces en el mismo curso.

    Una matricula repetida cuenta dos veces para los credits y para el GPA, con
    lo que descuadraba el expediente entero.
    """

    def setUp(self):
        self._montar()

    def test_no_admite_doble_matricula(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TakenCourse.objects.create(
                    student=self.tc_propio.student, course=self.curso
                )
