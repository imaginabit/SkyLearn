from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Student
from course.models import Course, CourseAllocation, Program
from quiz.models import EssayQuestion, Quiz, Sitting
from result.models import TakenCourse

User = get_user_model()


class QuizDesarrolloTests(TestCase):
    """Contestar una pregunta de desarrollo no puede reventar la vista.

    `QuizTake.form_valid_user` pedia `get_choices()`, que solo existe en
    MCQuestion: al enviar un texto salia un AttributeError y la pantalla se
    quedaba colgada. Ademas, contestarlas las metia en la lista de
    incorrectas, porque `check_if_correct` devuelve False siempre.
    """

    def setUp(self):
        self.program = Program.objects.create(title="Programa de prueba")
        self.curso = Course.objects.create(
            title="Curso con desarrollo",
            code="MIO-2",
            program=self.program,
            level="Bachelor",
            year=1,
            semester="First",
        )
        self.alumno = User.objects.create_user(
            username="tmp-alumno-2", password="password", is_student=True
        )
        self.ficha_alumno = Student.objects.create(
            student=self.alumno, level="Bachelor", program=self.program
        )
        TakenCourse.objects.create(student=self.ficha_alumno, course=self.curso)
        self.pregunta = EssayQuestion.objects.create(content="Explica que es un CAAT")
        self.quiz = Quiz.objects.create(
            course=self.curso,
            title="Repaso desarrollo",
            category="practice",
            single_attempt=False,
            answers_at_end=False,
            exam_paper=True,
        )
        self.quiz.question_set.add(self.pregunta)
        self.url = reverse(
            "quiz_take", kwargs={"slug": self.quiz.slug, "pk": self.curso.pk}
        )
        self.client.force_login(self.alumno)

    def test_contestar_una_pregunta_de_desarrollo_no_falla(self):
        response = self.client.post(
            self.url,
            {"question_id": self.pregunta.id, "answers": "Un auditor de sistemas."},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Un auditor de sistemas.")

    def test_el_texto_queda_guardado_para_corregirlo_a_mano(self):
        self.client.post(
            self.url,
            {"question_id": self.pregunta.id, "answers": "Un auditor de sistemas."},
        )

        sitting = Sitting.objects.get(user=self.alumno, quiz=self.quiz, complete=True)
        self.assertEqual(sitting.get_current_score, 0)
        self.assertEqual(sitting.get_incorrect_questions, [])
        self.assertIn(str(self.pregunta.id), sitting.user_answers)


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


class SittingQuestionListSinComaTests(TestCase):
    """Terminar un cuestionario con `question_list` sin coma final.

    Hay sittings antiguas editadas a mano (al retirar preguntas de un
    cuestionario cargado con fixture) cuyas listas quedaron sin la coma
    final que pone `new_sitting`. `remove_first_question` hacia un split de
    dos partes y reventaba con ValueError (HTTP 500) al contestar la ultima
    pregunta: los alumnos no podian terminar el cuestionario.
    """

    def setUp(self):
        self.program = Program.objects.create(title="Programa de prueba")
        self.curso = Course.objects.create(
            title="Curso sin coma",
            code="MIO-3",
            program=self.program,
            level="Bachelor",
            year=1,
            semester="First",
        )
        self.alumno = User.objects.create_user(
            username="tmp-alumno-3", password="password", is_student=True
        )
        self.ficha_alumno = Student.objects.create(
            student=self.alumno, level="Bachelor", program=self.program
        )
        TakenCourse.objects.create(student=self.ficha_alumno, course=self.curso)
        self.pregunta_1 = EssayQuestion.objects.create(content="Pregunta 1")
        self.pregunta_2 = EssayQuestion.objects.create(content="Pregunta 2")
        self.quiz = Quiz.objects.create(
            course=self.curso,
            title="Repaso sin coma",
            category="practice",
            single_attempt=False,
            answers_at_end=False,
            exam_paper=True,
        )
        self.quiz.question_set.add(self.pregunta_1, self.pregunta_2)
        self.url = reverse(
            "quiz_take", kwargs={"slug": self.quiz.slug, "pk": self.curso.pk}
        )
        self.client.force_login(self.alumno)

    def _sitting_sin_coma(self):
        ids = f"{self.pregunta_1.id},{self.pregunta_2.id}"
        return Sitting.objects.create(
            user=self.alumno,
            quiz=self.quiz,
            course=self.curso,
            question_order=ids,
            question_list=ids,
            incorrect_questions="",
            current_score=0,
            complete=False,
            user_answers="{}",
        )

    def test_contestar_todas_las_preguntas_termina_sin_500(self):
        self._sitting_sin_coma()
        for pregunta in (self.pregunta_1, self.pregunta_2):
            response = self.client.post(
                self.url,
                {"question_id": pregunta.id, "answers": "Respuesta de prueba."},
            )
            self.assertEqual(response.status_code, 200)

        sitting = Sitting.objects.get(user=self.alumno, quiz=self.quiz)
        self.assertTrue(sitting.complete)
        self.assertEqual(sitting.question_list, "")

    def test_una_sola_pregunta_restante_sin_coma_tambien_termina(self):
        sitting = self._sitting_sin_coma()
        # El alumno ya habia contestado la primera: solo queda la segunda y
        # ni siquiera al principio lleva coma.
        sitting.question_list = str(self.pregunta_2.id)
        sitting.user_answers = f'{{"{self.pregunta_1.id}": "a"}}'
        sitting.save()

        response = self.client.post(
            self.url,
            {"question_id": self.pregunta_2.id, "answers": "Respuesta final."},
        )

        self.assertEqual(response.status_code, 200)
        sitting.refresh_from_db()
        self.assertTrue(sitting.complete)
        self.assertEqual(sitting.question_list, "")
