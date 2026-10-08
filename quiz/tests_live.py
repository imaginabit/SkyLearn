from datetime import timedelta

from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Student, User
from course.models import Course, CourseAllocation, Program
from quiz.models import (
    Choice,
    LiveParticipant,
    LiveSession,
    MCQuestion,
    Quiz,
)
from quiz.views import SEGUNDOS_VISTA
from result.models import TakenCourse


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
        # Para entrar a una partida hay que estar matriculado en su curso
        for alumno in (self.ana, self.luis):
            ficha = Student.objects.create(
                student=alumno, level="Master", program=self.programa
            )
            TakenCourse.objects.create(student=ficha, course=self.curso)

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


class LiveAccesoTests(TestCase):
    """Solo entra quien está matriculado, y `last_seen` no se escribe cada vez.

    El código son seis caracteres: sin mirar la matrícula, cualquier cuenta con
    sesión iniciada que lo acertara se colaba en el juego. Y como el estado se
    consulta cada 1,2 s, refrescar `last_seen` en cada consulta eran unas doce
    escrituras por segundo con 15 alumnos sobre un SQLite.
    """

    def setUp(self):
        self.prof = User.objects.create_user(
            username="prof", password="x", is_lecturer=True
        )
        self.matriculado = User.objects.create_user(
            username="ana", password="x", is_student=True
        )
        self.ajeno = User.objects.create_user(
            username="forastero", password="x", is_student=True
        )
        self.programa = Program.objects.create(title="Seguridad Informatica")
        self.curso = Course.objects.create(
            title="MF0487_3-C5",
            code="MF0487_3-C5",
            program=self.programa,
            level="Master",
            semester="Third",
        )
        asignacion = CourseAllocation.objects.get_or_create(lecturer=self.prof)[0]
        asignacion.courses.add(self.curso)
        self.quiz = Quiz.objects.create(
            course=self.curso, title="Repaso objetiva", category="practice"
        )
        self.pregunta = MCQuestion.objects.create(content="¿Cuánto es 2+2?")
        self.pregunta.quiz.add(self.quiz)
        Choice.objects.create(
            question=self.pregunta, choice_text="4", correct=True
        )
        ficha = Student.objects.create(
            student=self.matriculado, level="Master", program=self.programa
        )
        TakenCourse.objects.create(student=ficha, course=self.curso)
        self.sesion = self._partida()

    def _partida(self):
        cliente = Client()
        cliente.force_login(self.prof)
        cliente.post(
            reverse("live_create", args=[self.curso.slug]),
            {"quiz": self.quiz.id, "cuantas": 0, "time_limit": 20},
        )
        sesion = LiveSession.objects.get()
        cliente.post(reverse("live_action", args=[sesion.code]), {"action": "start"})
        return sesion

    def _como(self, user):
        cliente = Client()
        cliente.force_login(user)
        return cliente

    def test_el_matriculado_entra(self):
        r = self._como(self.matriculado).post(
            reverse("live_join"), {"code": self.sesion.code, "nickname": "Ana"}
        )

        self.assertEqual(r.status_code, 302)
        self.assertEqual(LiveParticipant.objects.count(), 1)

    def test_quien_no_esta_matriculado_no_entra(self):
        r = self._como(self.ajeno).post(
            reverse("live_join"), {"code": self.sesion.code, "nickname": "Colado"}
        )

        self.assertEqual(r.status_code, 200)
        self.assertIn("No estás matriculado", r.content.decode())
        self.assertEqual(LiveParticipant.objects.count(), 0)

    def test_quien_no_esta_matriculado_no_consulta_el_estado(self):
        r = self._como(self.ajeno).get(reverse("live_state", args=[self.sesion.code]))

        self.assertEqual(r.status_code, 403)

    def test_quien_no_esta_matriculado_no_llega_a_jugar(self):
        r = self._como(self.ajeno).get(reverse("live_play", args=[self.sesion.code]))

        self.assertEqual(r.status_code, 302)
        self.assertIn(self.sesion.code, r.url)

    def test_quien_organiza_no_necesita_matricula(self):
        # el docente puede abrir la pantalla aunque no esté matriculado
        self._como(self.matriculado).post(
            reverse("live_join"), {"code": self.sesion.code, "nickname": "Ana"}
        )

        r = self._como(self.prof).get(reverse("live_state", args=[self.sesion.code]))

        self.assertEqual(r.status_code, 200)

    def test_last_seen_no_se_escribe_en_cada_consulta(self):
        self._como(self.matriculado).post(
            reverse("live_join"), {"code": self.sesion.code, "nickname": "Ana"}
        )
        url = reverse("live_state", args=[self.sesion.code])
        cliente = self._como(self.matriculado)

        cliente.get(url)
        uno = LiveParticipant.objects.get(session=self.sesion, user=self.matriculado)
        primera = uno.last_seen
        for _ in range(5):
            cliente.get(url)
        uno.refresh_from_db()
        segunda = uno.last_seen
        self.assertEqual(primera, segunda, "last_seen se escribe en cada consulta")

        # pasado el intervalo, sí se refresca
        LiveParticipant.objects.filter(pk=uno.pk).update(
            last_seen=primera - timedelta(seconds=SEGUNDOS_VISTA + 1)
        )
        cliente.get(url)
        uno.refresh_from_db()

        self.assertGreater(uno.last_seen, segunda)


class LiveShuffleTests(TestCase):
    """Las opciones se barajan en cada partida y no se mueven dentro de ella."""

    def setUp(self):
        self.prof = User.objects.create_user(
            username="prof", password="x", is_lecturer=True, is_superuser=True
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
        self.quiz = Quiz.objects.create(
            course=self.curso, title="Repaso objetiva", category="practice"
        )
        self.pregunta = MCQuestion.objects.create(content="¿Cuánto es 2+2?")
        self.pregunta.quiz.add(self.quiz)
        # Las cuatro opciones en el orden en que las guarda el banco
        Choice.objects.create(question=self.pregunta, choice_text="4", correct=True)
        Choice.objects.create(question=self.pregunta, choice_text="5", correct=False)
        Choice.objects.create(question=self.pregunta, choice_text="6", correct=False)
        Choice.objects.create(question=self.pregunta, choice_text="7", correct=False)
        ficha = Student.objects.create(
            student=self.ana, level="Master", program=self.programa
        )
        TakenCourse.objects.create(student=ficha, course=self.curso)

    def _partida(self, code):
        sesion = LiveSession.objects.create(
            course=self.curso,
            quiz=self.quiz,
            host=self.prof,
            question_ids=str(self.pregunta.id),
            state="question",
            time_limit=20,
            code=code,
        )
        LiveParticipant.objects.create(session=sesion, user=self.ana, nickname="Ana")
        return sesion

    def _opciones(self, sesion, como_docente):
        cliente = Client()
        cliente.force_login(self.prof if como_docente else self.ana)
        estado = cliente.get(reverse("live_state", args=[sesion.code])).json()
        return estado["question"]["choices"]

    def _letra_correcta(self, sesion, como_docente=False):
        """La letra que le toca a la buena, segun el orden que le llega."""
        opciones = self._opciones(sesion, como_docente)
        textos = [opcion["text"] for opcion in opciones]
        return "ABCD"[textos.index("4")]

    def test_el_alumno_no_coge_siempre_la_primera(self):
        # Con dos partidas solo hay una de cuatro de que coincidan, asi que se
        # prueban varias: si el barajado no funciona, salen todas con la misma
        # letra y el conjunto tendria un unico elemento.
        letras = {
            self._letra_correcta(self._partida(f"COD{i:03d}")) for i in range(12)
        }
        self.assertGreater(len(letras), 1, "todas las partidas han salido igual")
        self.assertLessEqual(len(letras), 4)

    def test_dentro_de_la_partida_no_se_mueve(self):
        sesion = self._partida("CCC333")
        letra = self._letra_correcta(sesion)
        for _ in range(5):
            self.assertEqual(self._letra_correcta(sesion), letra)

    def test_docente_y_alumno_ven_lo_mismo(self):
        sesion = self._partida("DDD444")
        self.assertEqual(
            self._letra_correcta(sesion, como_docente=True),
            self._letra_correcta(sesion, como_docente=False),
        )

    def test_al_revelar_sigue_siendo_la_misma(self):
        # El Marcador sale del mismo array de opciones, asi que al revealing
        # tiene que seguir siendo la que el alumno vio al responder.
        sesion = self._partida("EEE555")
        letra = self._letra_correcta(sesion)
        prof = Client()
        prof.force_login(self.prof)
        prof.post(reverse("live_action", args=[sesion.code]), {"action": "reveal"})
        opciones = self._opciones(sesion, como_docente=True)
        textos = [opcion["text"] for opcion in opciones]
        self.assertEqual("ABCD"[textos.index("4")], letra)

    def test_el_recuento_trae_una_entrada_por_opcion(self):
        sesion = self._partida("FFF666")
        prof = Client()
        prof.force_login(self.prof)
        prof.post(reverse("live_action", args=[sesion.code]), {"action": "reveal"})
        estado = prof.get(reverse("live_state", args=[sesion.code])).json()
        self.assertEqual(len(estado["question"]["counts"]), 4)


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
