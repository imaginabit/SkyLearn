from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from course.models import Course, CourseAllocation, Program
from quiz.models import MCQuestion, Quiz, Sitting

User = get_user_model()


class QuizDeleteAuthorizationTests(TestCase):
    """Un cuestionario solo se borra desde el curso que lo tiene asignado.

    La vista cogia el quiz por pk sin mirar el curso, con lo que cualquier
    docente podia borrar el cuestionario de otro curso.
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
        asignacion = CourseAllocation.objects.create(lecturer=self.docente)
        asignacion.courses.set([self.curso])
        self.quiz = Quiz.objects.create(course=self.curso, title="Cuestionario 1")
        self.url = reverse(
            "quiz_delete", kwargs={"slug": self.curso.slug, "pk": self.quiz.pk}
        )

    def _docente(self, tmp):
        user = User.objects.create_user(
            username=tmp, password="password", is_lecturer=True
        )
        # el signal renombra la cuenta al crearla: hay que releerla
        return User.objects.get(pk=user.pk)

    def test_docente_de_otro_curso_no_borra_el_quiz(self):
        self.client.force_login(self.docente_ajeno)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Quiz.objects.filter(pk=self.quiz.pk).exists())

    def test_docente_asignado_borra_el_quiz(self):
        self.client.force_login(self.docente)

        self.assertEqual(self.client.post(self.url).status_code, 302)
        self.assertFalse(Quiz.objects.filter(pk=self.quiz.pk).exists())

    def test_borrar_por_get_no_hace_nada(self):
        # era un enlace <a href>: un GET bastaba para destruir
        self.client.force_login(self.docente)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 405)
        self.assertTrue(Quiz.objects.filter(pk=self.quiz.pk).exists())


class OcultarPreguntasCorregidasTests(TestCase):
    """El check del curso oculta al docente las preguntas ya correctas.

    Al corregir un examen, el docente puede pedir que no se le muestren las
    preguntas cuya respuesta ya esta bien, para quedarse solo con las que le
    falta revisar. El check vive en la pagina del curso.
    """

    def setUp(self):
        self.program = Program.objects.create(title="Programa de prueba")
        self.curso = Course.objects.create(
            title="Curso con examen",
            code="MIO-3",
            program=self.program,
            level="Bachelor",
            year=1,
            semester="First",
        )
        self.docente = User.objects.create_user(
            username="tmp-docente-ojo", password="password", is_lecturer=True
        )
        self.docente = User.objects.get(pk=self.docente.pk)
        self.quiz = Quiz.objects.create(course=self.curso, title="Cuestionario 1")
        self.bien = MCQuestion.objects.create(content="Pregunta ya correcta")
        self.bien.quiz.add(self.quiz)
        self.pendiente = MCQuestion.objects.create(content="Pregunta por revisar")
        self.pendiente.quiz.add(self.quiz)

        alumno = User.objects.create_user(
            username="tmp-alumno-ojo", password="password", is_student=True
        )
        self.sitting = Sitting.objects.new_sitting(alumno, self.quiz, self.curso)
        self.sitting.complete = True
        self.sitting.add_incorrect_question(self.pendiente)

        self.url_correccion = reverse(
            "quiz_marking_detail", kwargs={"pk": self.sitting.pk}
        )
        self.url_check = reverse(
            "course_ocultar_corregidas", kwargs={"slug": self.curso.slug}
        )
        self.url_curso = reverse("course_detail", kwargs={"slug": self.curso.slug})

    def test_sin_el_check_se_ven_las_dos_preguntas(self):
        self.client.force_login(self.docente)

        html = self.client.get(self.url_correccion).content.decode()

        self.assertIn("Pregunta ya correcta", html)
        self.assertIn("Pregunta por revisar", html)

    def test_con_el_check_solo_queda_la_que_hay_que_revisar(self):
        self.docente.ocultar_preguntas_corregidas = True
        self.docente.save()
        self.client.force_login(self.docente)

        html = self.client.get(self.url_correccion).content.decode()

        self.assertNotIn("Pregunta ya correcta", html)
        self.assertIn("Pregunta por revisar", html)
        self.assertIn("Ocultando las preguntas ya corregidas", html)

    def test_el_check_del_curso_se_guarda(self):
        self.client.force_login(self.docente)

        self.client.post(self.url_check, {"ocultar": "on"})
        self.assertTrue(
            User.objects.get(pk=self.docente.pk).ocultar_preguntas_corregidas
        )

        self.client.post(self.url_check, {})
        self.assertFalse(
            User.objects.get(pk=self.docente.pk).ocultar_preguntas_corregidas
        )

    def test_el_check_se_ve_en_la_pagina_del_curso(self):
        self.client.force_login(self.docente)

        html = self.client.get(self.url_curso).content.decode()

        self.assertIn('name="ocultar"', html)
        self.assertIn("Ocultar las preguntas ya corregidas", html)

    def test_el_check_no_lo_cambia_un_alumno(self):
        alumno = User.objects.create_user(
            username="tmp-alumno-check", password="password", is_student=True
        )
        self.client.force_login(alumno)

        response = self.client.post(self.url_check, {"ocultar": "on"})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            User.objects.get(pk=alumno.pk).ocultar_preguntas_corregidas
        )

    def test_el_check_solo_se_cambia_por_post(self):
        self.client.force_login(self.docente)

        self.assertEqual(self.client.get(self.url_check).status_code, 405)
