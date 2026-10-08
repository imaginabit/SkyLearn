from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from course.models import Course, Program
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
