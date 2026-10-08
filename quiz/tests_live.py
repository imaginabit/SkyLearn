from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from course.models import Course, CourseAllocation, Program
from quiz.models import (
    Choice,
    LiveParticipant,
    LiveSession,
    MCQuestion,
    Quiz,
)


class LiveQuizTests(TestCase):
    def setUp(self):
        self.prof = User.objects.create_user(
            username="prof", password="x", is_lecturer=True, is_superuser=True
        )
        self.ana = User.objects.create_user(
            username="ana", password="x", is_student=True
        )
        self.luis = User.objects.create_user(
            username="luis", password="x", is_student=True
        )
        self.programa = Program.objects.create(title="Seguridad Informatica")
        self.curso = Course.objects.create(
            title="MF0487_3",
            code="MF0487_3",
            program=self.programa,
            level="Master",
            semester="Third",
        )
        self.quiz = Quiz.objects.create(
            course=self.curso, title="Repaso objetiva", category="practice"
        )
        self.q1 = MCQuestion.objects.create(
            content="¿Cuánto es 2+2?", explanation="Cuatro."
        )
        self.q1.quiz.add(self.quiz)
        self.q1_correcta = Choice.objects.create(
            question=self.q1, choice_text="4", correct=True
        )
        Choice.objects.create(question=self.q1, choice_text="5", correct=False)
        self.q2 = MCQuestion.objects.create(
            content="¿De qué color es el cielo?", explanation="Azul."
        )
        self.q2.quiz.add(self.quiz)
        self.q2_correcta = Choice.objects.create(
            question=self.q2, choice_text="Azul", correct=True
        )
        Choice.objects.create(question=self.q2, choice_text="Verde", correct=False)

    def test_flujo_completo(self):
        prof = Client()
        prof.force_login(self.prof)

        # El docente crea la partida
        r = prof.post(
            reverse("live_create", args=[self.curso.slug]),
            {"quiz": self.quiz.id, "cuantas": 0, "time_limit": 20},
        )
        self.assertEqual(r.status_code, 302)
        sesion = LiveSession.objects.get()
        self.assertEqual(sesion.total, 2)
        self.assertTrue(sesion.code)

        # Dos alumnos entran con apodo
        ana = Client()
        ana.force_login(self.ana)
        r = ana.post(reverse("live_join"), {"code": sesion.code, "nickname": "Ana"})
        self.assertEqual(r.status_code, 302)
        luis = Client()
        luis.force_login(self.luis)
        luis.post(reverse("live_join"), {"code": sesion.code, "nickname": "Luis"})
        self.assertEqual(LiveParticipant.objects.count(), 2)

        # Empieza
        prof.post(reverse("live_action", args=[sesion.code]), {"action": "start"})
        estado = ana.get(reverse("live_state", args=[sesion.code])).json()
        self.assertEqual(estado["state"], "question")
        self.assertEqual(len(estado["question"]["choices"]), 2)
        self.assertNotIn("correct_id", estado["question"])

        # Ana acierta, Luis falla
        r = ana.post(
            reverse("live_answer", args=[sesion.code]), {"choice": self.q1_correcta.id}
        )
        self.assertTrue(r.json()["correct"])
        self.assertGreaterEqual(r.json()["points"], 500)
        luis.post(
            reverse("live_action", args=[sesion.code]),
            {"action": "noop"},
        )  # acción desconocida del host: no debe romper
        r = luis.post(
            reverse("live_answer", args=[sesion.code]),
            {"choice": self.q1.choice_set.filter(correct=False).first().id},
        )
        self.assertFalse(r.json()["correct"])
        self.assertEqual(r.json()["points"], 0)

        # No se puede responder dos veces
        r = ana.post(
            reverse("live_answer", args=[sesion.code]), {"choice": self.q1_correcta.id}
        )
        self.assertEqual(r.status_code, 400)

        # Revelar: aparece la correcta y el recuento
        prof.post(reverse("live_action", args=[sesion.code]), {"action": "reveal"})
        estado = ana.get(reverse("live_state", args=[sesion.code])).json()
        self.assertEqual(estado["question"]["correct_id"], self.q1_correcta.id)
        self.assertEqual(estado["question"]["counts"][str(self.q1_correcta.id)], 1)

        # Siguiente: segunda pregunta
        prof.post(reverse("live_action", args=[sesion.code]), {"action": "next"})
        estado = ana.get(reverse("live_state", args=[sesion.code])).json()
        self.assertEqual(estado["index"], 1)
        self.assertEqual(estado["state"], "question")

        # Ranking tras la última
        prof.post(reverse("live_action", args=[sesion.code]), {"action": "ranking"})
        estado = ana.get(reverse("live_state", args=[sesion.code])).json()
        self.assertEqual(estado["state"], "ranking")
        self.assertEqual(estado["ranking"][0]["nickname"], "Ana")

        # El alumno ve su puesto
        self.assertEqual(estado["you"]["rank"], 1)

    def test_no_responder_sin_participar(self):
        prof = Client()
        prof.force_login(self.prof)
        prof.post(
            reverse("live_create", args=[self.curso.slug]),
            {"quiz": self.quiz.id, "cuantas": 0, "time_limit": 20},
        )
        sesion = LiveSession.objects.get()
        prof.post(reverse("live_action", args=[sesion.code]), {"action": "start"})
        ana = Client()
        ana.force_login(self.ana)
        r = ana.post(
            reverse("live_answer", args=[sesion.code]), {"choice": self.q1_correcta.id}
        )
        self.assertEqual(r.status_code, 403)


class LiveMenuTests(TestCase):
    """Los enlaces del menu: el alumno entra a la partida, el docente la crea."""

    def setUp(self):
        self.prof = User.objects.create_user(
            username="prof", password="x", is_lecturer=True
        )
        self.ana = User.objects.create_user(
            username="ana", password="x", is_student=True
        )
        self.programa = Program.objects.create(title="Seguridad Informatica")
        self.curso = Course.objects.create(
            title="MF0487_3-C5",
            code="MF0487_3-C5",
            program=self.programa,
            level="Master",
            semester="Third",
        )
        CourseAllocation.objects.get_or_create(lecturer=self.prof)[0].courses.add(
            self.curso
        )
        self.quiz = Quiz.objects.create(
            course=self.curso, title="Repaso objetiva", category="practice"
        )
        pregunta = MCQuestion.objects.create(content="¿Cuánto es 2+2?")
        pregunta.quiz.add(self.quiz)
        Choice.objects.create(question=pregunta, choice_text="4", correct=True)

    def _asignar(self, lecturer, curso):
        """Asigna el curso al docente: `CourseAllocation` usa una M2M."""
        asignacion, _ = CourseAllocation.objects.get_or_create(lecturer=lecturer)
        asignacion.courses.add(curso)
        return asignacion

    def _otro_curso_con_preguntas(self):
        curso = Course.objects.create(
            title="MF0487_3-C6",
            code="MF0487_3-C6",
            program=self.programa,
            level="Master",
            semester="Third",
        )
        self._asignar(self.prof, curso)
        quiz = Quiz.objects.create(course=curso, title="Repaso 2", category="practice")
        pregunta = MCQuestion.objects.create(content="¿De qué color es el cielo?")
        pregunta.quiz.add(quiz)
        Choice.objects.create(question=pregunta, choice_text="Azul", correct=True)
        return curso

    def _como(self, user):
        """Cliente ya con la sesion iniciada: `force_login` no devuelve nada."""
        cliente = Client()
        cliente.force_login(user)
        return cliente

    def test_alumno_tiene_el_enlace_a_entrar(self):
        html = self._como(self.ana).get("/es/").content.decode()
        self.assertIn(reverse("live_join"), html)

    def test_docente_tiene_el_enlace_a_crear(self):
        html = self._como(self.prof).get("/es/").content.decode()
        self.assertIn(reverse("live_create_pick"), html)

    def test_alumno_no_ve_el_enlace_de_crear(self):
        html = self._como(self.ana).get("/es/").content.decode()
        self.assertNotIn(reverse("live_create_pick"), html)

    def test_un_solo_curso_entra_directo(self):
        r = self._como(self.prof).get(reverse("live_create_pick"))
        self.assertRedirects(
            r,
            reverse("live_create", args=[self.curso.slug]),
            fetch_redirect_response=False,
        )

    def test_con_varios_cursos_pregunta_cual(self):
        otro = self._otro_curso_con_preguntas()
        r = self._como(self.prof).get(reverse("live_create_pick"))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn(reverse("live_create", args=[self.curso.slug]), html)
        self.assertIn(reverse("live_create", args=[otro.slug]), html)

    def test_sin_cuestionarios_avisa(self):
        for quiz in Quiz.objects.all():
            MCQuestion.objects.filter(quiz=quiz).delete()
        r = self._como(self.prof).get(reverse("live_create_pick"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("cuestionarios", r.content.decode())

    def test_el_alumno_no_llega_a_crear(self):
        r = self._como(self.ana).get(reverse("live_create_pick"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, "/")
