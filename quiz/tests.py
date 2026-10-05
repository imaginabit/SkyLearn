from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from course.models import Course, CourseAllocation, Program
from quiz.models import Quiz

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
