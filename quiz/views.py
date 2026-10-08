import random

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.timezone import now
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django.views.generic import (
    CreateView,
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
)

from accounts.decorators import lecturer_required
from course.utils import curso_asignado
from .forms import (
    EssayForm,
    MCQuestionForm,
    MCQuestionFormSet,
    QuestionForm,
    QuizAddForm,
)
from .models import (
    Course,
    EssayQuestion,
    LiveAnswer,
    LiveParticipant,
    LiveSession,
    MCQuestion,
    Progress,
    Question,
    Quiz,
    Sitting,
)
from result.models import TakenCourse

# Cada cuanto se refresca `last_seen` de cada participante. El estado de la
# partida se consulta cada 1,2 s, asi que refrescarlo en cada consulta son unas
# doce escrituras por segundo con 15 alumnos, sobre un SQLite.
SEGUNDOS_VISTA = 10


# ########################################################
# Quiz Views
# ########################################################


@method_decorator([login_required, lecturer_required], name="dispatch")
class QuizCreateView(CreateView):
    model = Quiz
    form_class = QuizAddForm
    template_name = "quiz/quiz_form.html"

    def get_initial(self):
        initial = super().get_initial()
        course = get_object_or_404(Course, slug=self.kwargs["slug"])
        initial["course"] = course
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["course"] = get_object_or_404(Course, slug=self.kwargs["slug"])
        return context

    def form_valid(self, form):
        form.instance.course = get_object_or_404(Course, slug=self.kwargs["slug"])
        with transaction.atomic():
            self.object = form.save()
            return redirect(
                "mc_create", slug=self.kwargs["slug"], quiz_id=self.object.id
            )


@method_decorator([login_required, lecturer_required], name="dispatch")
class QuizUpdateView(UpdateView):
    model = Quiz
    form_class = QuizAddForm
    template_name = "quiz/quiz_form.html"

    def get_object(self, queryset=None):
        return get_object_or_404(Quiz, pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["course"] = get_object_or_404(Course, slug=self.kwargs["slug"])
        return context

    def form_valid(self, form):
        with transaction.atomic():
            self.object = form.save()
            return redirect("quiz_index", self.kwargs["slug"])


@require_POST
@login_required
@lecturer_required
def quiz_delete(request, slug, pk):
    course = curso_asignado(request, slug)
    quiz = get_object_or_404(Quiz, pk=pk, course=course)
    quiz.delete()
    messages.success(request, "Quiz successfully deleted.")
    return redirect("quiz_index", slug=slug)


@login_required
def quiz_list(request, slug):
    course = get_object_or_404(Course, slug=slug)
    quizzes = Quiz.objects.filter(course=course).order_by("-timestamp")
    if not (request.user.is_lecturer or request.user.is_superuser):
        quizzes = quizzes.filter(draft=False)
    return render(
        request, "quiz/quiz_list.html", {"quizzes": quizzes, "course": course}
    )


# ########################################################
# Multiple Choice Question Views
# ########################################################


@method_decorator([login_required, lecturer_required], name="dispatch")
class MCQuestionCreate(CreateView):
    model = MCQuestion
    form_class = MCQuestionForm
    template_name = "quiz/mcquestion_form.html"

    # def get_form_kwargs(self):
    #     kwargs = super().get_form_kwargs()
    #     kwargs["quiz"] = get_object_or_404(Quiz, id=self.kwargs["quiz_id"])
    #     return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["course"] = get_object_or_404(Course, slug=self.kwargs["slug"])
        context["quiz_obj"] = get_object_or_404(Quiz, id=self.kwargs["quiz_id"])
        context["quiz_questions_count"] = Question.objects.filter(
            quiz=self.kwargs["quiz_id"]
        ).count()
        if self.request.method == "POST":
            context["formset"] = MCQuestionFormSet(self.request.POST)
        else:
            context["formset"] = MCQuestionFormSet()
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formset = context["formset"]
        if formset.is_valid():
            with transaction.atomic():
                # Save the MCQuestion instance without committing to the database yet
                self.object = form.save(commit=False)
                self.object.save()

                # Retrieve the Quiz instance
                quiz = get_object_or_404(Quiz, id=self.kwargs["quiz_id"])

                # set the many-to-many relationship
                self.object.quiz.add(quiz)

                # Save the formset (choices for the question)
                formset.instance = self.object
                formset.save()

                if "another" in self.request.POST:
                    return redirect(
                        "mc_create",
                        slug=self.kwargs["slug"],
                        quiz_id=self.kwargs["quiz_id"],
                    )
                return redirect("quiz_index", slug=self.kwargs["slug"])
        else:
            return self.form_invalid(form)


# ########################################################
# Quiz Progress and Marking Views
# ########################################################


@method_decorator([login_required], name="dispatch")
class QuizUserProgressView(TemplateView):
    template_name = "quiz/progress.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        progress, _ = Progress.objects.get_or_create(user=self.request.user)
        context["cat_scores"] = progress.list_all_cat_scores
        context["exams"] = progress.show_exams()
        context["exams_counter"] = context["exams"].count()
        return context


@method_decorator([login_required, lecturer_required], name="dispatch")
class QuizMarkingList(ListView):
    model = Sitting
    template_name = "quiz/quiz_marking_list.html"

    def get_queryset(self):
        queryset = Sitting.objects.filter(complete=True)
        if not self.request.user.is_superuser:
            queryset = queryset.filter(
                quiz__course__allocated_course__lecturer__pk=self.request.user.id
            )
        quiz_filter = self.request.GET.get("quiz_filter")
        if quiz_filter:
            queryset = queryset.filter(quiz__title__icontains=quiz_filter)
        user_filter = self.request.GET.get("user_filter")
        if user_filter:
            queryset = queryset.filter(user__username__icontains=user_filter)
        return queryset


@method_decorator([login_required, lecturer_required], name="dispatch")
class QuizMarkingDetail(DetailView):
    model = Sitting
    template_name = "quiz/quiz_marking_detail.html"

    def post(self, request, *args, **kwargs):
        sitting = self.get_object()
        question_id = request.POST.get("qid")
        if question_id:
            question = Question.objects.get_subclass(id=int(question_id))
            if int(question_id) in sitting.get_incorrect_questions:
                sitting.remove_incorrect_question(question)
            else:
                sitting.add_incorrect_question(question)
        return self.get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["questions"] = self.object.get_questions(with_answers=True)
        return context


# ########################################################
# Quiz Taking View
# ########################################################


@method_decorator([login_required], name="dispatch")
class QuizTake(FormView):
    form_class = QuestionForm
    template_name = "quiz/question.html"
    result_template_name = "quiz/result.html"

    def dispatch(self, request, *args, **kwargs):
        self.quiz = get_object_or_404(Quiz, slug=self.kwargs["slug"])
        self.course = get_object_or_404(Course, pk=self.kwargs["pk"])
        if self.quiz.draft and not (
            request.user.is_lecturer or request.user.is_superuser
        ):
            messages.info(request, "This quiz is not available yet.")
            return redirect("quiz_index", slug=self.course.slug)
        if not Question.objects.filter(quiz=self.quiz).exists():
            messages.warning(request, "This quiz has no questions available.")
            return redirect("quiz_index", slug=self.course.slug)

        self.sitting = Sitting.objects.user_sitting(
            request.user, self.quiz, self.course
        )
        if not self.sitting:
            messages.info(
                request,
                "You have already completed this quiz. Only one attempt is permitted.",
            )
            return redirect("quiz_index", slug=self.course.slug)

        # Set self.question and self.progress here
        self.question = self.sitting.get_first_question()
        self.progress = self.sitting.progress()

        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["question"] = self.question
        return kwargs

    def get_form_class(self):
        if isinstance(self.question, EssayQuestion):
            return EssayForm
        return self.form_class

    def form_valid(self, form):
        self.form_valid_user(form)
        if not self.sitting.get_first_question():
            return self.final_result_user()
        return super().get(self.request)

    def form_valid_user(self, form):
        progress, _ = Progress.objects.get_or_create(user=self.request.user)
        guess = form.cleaned_data["answers"]
        is_correct = self.question.check_if_correct(guess)

        if is_correct:
            self.sitting.add_to_score(1)
            progress.update_score(self.question, 1, 1)
        else:
            self.sitting.add_incorrect_question(self.question)
            progress.update_score(self.question, 0, 1)

        if not self.quiz.answers_at_end:
            self.previous = {
                "previous_answer": guess,
                "previous_outcome": is_correct,
                "previous_question": self.question,
                "answers": self.question.get_choices(),
                "question_type": {self.question.__class__.__name__: True},
            }
        else:
            self.previous = {}

        self.sitting.add_user_answer(self.question, guess)
        self.sitting.remove_first_question()

        # Update self.question and self.progress for the next question
        self.question = self.sitting.get_first_question()
        self.progress = self.sitting.progress()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["question"] = self.question
        context["quiz"] = self.quiz
        context["course"] = self.course
        if hasattr(self, "previous"):
            context["previous"] = self.previous
        if hasattr(self, "progress"):
            context["progress"] = self.progress
        return context

    def final_result_user(self):
        self.sitting.mark_quiz_complete()
        results = {
            "course": self.course,
            "quiz": self.quiz,
            "score": self.sitting.get_current_score,
            "max_score": self.sitting.get_max_score,
            "percent": self.sitting.get_percent_correct,
            "sitting": self.sitting,
            "previous": getattr(self, "previous", {}),
        }

        if self.quiz.answers_at_end:
            results["questions"] = self.sitting.get_questions(with_answers=True)
            results["incorrect_questions"] = self.sitting.get_incorrect_questions

        if (
            not self.quiz.exam_paper
            or self.request.user.is_superuser
            or self.request.user.is_lecturer
        ):
            self.sitting.delete()

        return render(self.request, self.result_template_name, results)


# ############################################################################
# Partidas en vivo (al estilo Kahoot)
# ############################################################################


def _puntos_kahoot(correcto, seconds, limite):
    """Puntuación tipo Kahoot: hasta 1000, más cuanto antes se acierte."""
    if not correcto:
        return 0
    if not limite:
        return 1000
    frac = min(max(seconds, 0.0), float(limite)) / float(limite)
    return int(round(1000 * (1 - frac / 2)))


def _preguntas_mc(quiz):
    """Las preguntas de opción múltiple del quiz, en el orden que toca."""
    preguntas = list(MCQuestion.objects.filter(quiz=quiz).order_by("pk"))
    if quiz.random_order:
        random.shuffle(preguntas)
    return preguntas


def _opciones_barajadas(session, pregunta):
    """Las opciones en un orden distinto en cada partida.

    La semilla sale del codigo de la partida y de la pregunta. Asi, dentro de
    la misma partida el orden no cambia nunca (el docente, el alumnado y el
    recuento ven las mismas letras, que es lo que hace falta para que el
    recuento cuadre) pero de una partida a otra sale distinta, que es lo que
    evita aprender de memoria «la buena es la A».

    Ojo: `get_choices()` con `choice_order='random'` baraja en cada consulta, y
    aqui se consulta cada 1,2 s: las opciones se moverian solas en pantalla.
    """
    opciones = list(pregunta.get_choices())
    random.Random(f"{session.code}-{pregunta.id}").shuffle(opciones)
    return opciones


def _es_host(request, session):
    return request.user.is_superuser or session.host_id == request.user.id


def _puede_entrar(request, session):
    """Solo entra quien está matriculado en el curso, o quien la organiza.

    El código de la partida son seis caracteres: sin esta comprobación, cualquier
    cuenta con sesión iniciada que lo acertara se colaba en el juego y en el
    ranking. Se deja fuera a quien organiza la partida, que puede estar probando
    la pantalla, y a los superusuarios.
    """
    if _es_host(request, session):
        return True
    return TakenCourse.objects.filter(
        student__student=request.user, course=session.course
    ).exists()


def _anota_vista(participante):
    """Deja constancia de que el alumno sigue mirando la partida.

    El estado se consulta cada 1,2 s y con 15 alumnos eso son unas doce
    escrituras por segundo sobre un SQLite. Como `last_seen` solo sirve para ver
    quién sigue dentro, se refresca cada `SEGUNDOS_VISTA` en lugar de en cada
    consulta.
    """
    if (now() - participante.last_seen).total_seconds() < SEGUNDOS_VISTA:
        return
    LiveParticipant.objects.filter(pk=participante.pk).update(last_seen=now())


@login_required
@lecturer_required
def live_create_pick(request):
    """Elige de que curso sale la partida en vivo.

    El enlace del menu apunta aqui y no a `live_create`, que necesita el slug
    del curso: con un curso por clase no hay forma de decidirlo en la URL.
    Solo se listan los cursos que tienen algun cuestionario con preguntas de
    opcion multiple, que es lo unico que se puede jugar. Si hay uno solo, se
    entra directamente a el.
    """
    cursos = Course.objects.distinct()
    if not request.user.is_superuser:
        cursos = cursos.filter(allocated_course__lecturer=request.user)
    con_preguntas = []
    for curso in cursos.order_by("code"):
        quizzes = [
            quiz
            for quiz in Quiz.objects.filter(course=curso).order_by("title")
            if MCQuestion.objects.filter(quiz=quiz).exists()
        ]
        if quizzes:
            con_preguntas.append((curso, quizzes))
    if len(con_preguntas) == 1:
        return redirect("live_create", slug=con_preguntas[0][0].slug)
    return render(request, "quiz/live_pick.html", {"cursos": con_preguntas})


@login_required
@lecturer_required
def live_create(request, slug):
    course = curso_asignado(request, slug)
    quizzes = Quiz.objects.filter(course=course).order_by("title")
    if request.method == "POST":
        quiz = get_object_or_404(Quiz, pk=request.POST.get("quiz"), course=course)
        preguntas = _preguntas_mc(quiz)
        cuantas = int(request.POST.get("cuantas") or 0)
        if cuantas and cuantas < len(preguntas):
            preguntas = random.sample(preguntas, cuantas)
        if not preguntas:
            messages.error(
                request, _("Ese cuestionario no tiene preguntas de opción múltiple.")
            )
            return redirect("live_create", slug=slug)
        session = LiveSession.objects.create(
            course=course,
            quiz=quiz,
            host=request.user,
            question_ids=",".join(str(q.id) for q in preguntas),
            time_limit=int(request.POST.get("time_limit") or 20),
        )
        messages.success(
            request,
            _("Partida creada. El código es %(code)s.") % {"code": session.code},
        )
        return redirect("live_host", code=session.code)
    return render(
        request, "quiz/live_create.html", {"course": course, "quizzes": quizzes}
    )


@login_required
def live_host(request, code):
    session = get_object_or_404(LiveSession, code=code)
    if not _es_host(request, session):
        return redirect("/")
    return render(request, "quiz/live_host.html", {"session": session})


@login_required
def live_join(request):
    error = None
    code = (request.GET.get("code") or "").strip().upper()
    if request.method == "POST":
        code = (request.POST.get("code") or "").strip().upper()
        nickname = (request.POST.get("nickname") or "").strip()
        session = LiveSession.objects.filter(code=code).first()
        if not session:
            error = _("Ese código no existe. Comprueba que lo has copiado bien.")
        elif not _puede_entrar(request, session):
            error = _(
                "No estás matriculado en este curso, así que no puedes entrar en "
                "esta partida. Pídeselo a quien la organiza."
            )
        elif not nickname:
            error = _("Escribe un apodo para el ranking.")
        else:
            participante, creado = LiveParticipant.objects.get_or_create(
                session=session,
                user=request.user,
                defaults={"nickname": nickname[:40]},
            )
            if not creado and participante.nickname != nickname[:40]:
                participante.nickname = nickname[:40]
                participante.save(update_fields=["nickname"])
            return redirect("live_play", code=session.code)
    return render(request, "quiz/live_join.html", {"code": code, "error": error})


@login_required
def live_play(request, code):
    session = get_object_or_404(LiveSession, code=code)
    if not _puede_entrar(request, session):
        return redirect(f"{reverse('live_join')}?code={session.code}")
    participante = LiveParticipant.objects.filter(
        session=session, user=request.user
    ).first()
    if not participante:
        return redirect(f"{reverse('live_join')}?code={session.code}")
    return render(
        request,
        "quiz/live_play.html",
        {"session": session, "participante": participante},
    )


@login_required
def live_state(request, code):
    session = get_object_or_404(LiveSession, code=code)
    host = _es_host(request, session)
    participante = None
    if not host:
        if not _puede_entrar(request, session):
            return JsonResponse({"error": "no entras en esta partida"}, status=403)
        participante = LiveParticipant.objects.filter(
            session=session, user=request.user
        ).first()
        if participante:
            _anota_vista(participante)

    data = {
        "state": session.state,
        "index": session.current_index,
        "total": session.total,
        "seconds_left": session.seconds_left,
        "time_limit": session.time_limit,
        "quiz": session.quiz.title,
        "code": session.code,
    }

    pregunta = session.current_question
    if pregunta and session.state in ("question", "reveal"):
        choices = _opciones_barajadas(session, pregunta)
        data["question"] = {
            "id": pregunta.id,
            "content": pregunta.content,
            "choices": [{"id": c.id, "text": c.choice_text} for c in choices],
        }
        if session.state == "reveal":
            correcta = next((c for c in choices if c.correct), None)
            data["question"]["correct_id"] = correcta.id if correcta else None
            data["question"]["explanation"] = pregunta.explanation
            data["question"]["counts"] = {
                c.id: LiveAnswer.objects.filter(
                    participant__session=session, question=pregunta, choice=c
                ).count()
                for c in choices
            }

    data["count"] = session.participants.count()
    if host:
        data["participants"] = [
            {
                "nickname": p.nickname,
                "score": p.score,
                "answered": p.ha_respondido(pregunta),
            }
            for p in session.participants.order_by("-score", "joined")
        ]

    if participante:
        data["you"] = {
            "nickname": participante.nickname,
            "score": participante.score,
        }
        if pregunta:
            respuesta = participante.answers.filter(question=pregunta).first()
            data["you"]["answered"] = bool(respuesta)
            if respuesta:
                data["you"]["correct"] = respuesta.correct
                data["you"]["points"] = respuesta.points
        data["you"]["rank"] = (
            session.participants.filter(score__gt=participante.score).count() + 1
        )

    if session.state in ("ranking", "ended"):
        data["ranking"] = [
            {"rank": i, "nickname": p.nickname, "score": p.score}
            for i, p in enumerate(
                session.participants.order_by("-score", "joined"), start=1
            )
        ]

    return JsonResponse(data)


@login_required
@require_POST
def live_action(request, code):
    session = get_object_or_404(LiveSession, code=code)
    if not _es_host(request, session):
        return JsonResponse({"error": "no autorizado"}, status=403)
    accion = request.POST.get("action")
    if accion == "start":
        session.empezar()
    elif accion == "reveal":
        session.revelar()
    elif accion == "next":
        session.avanzar()
    elif accion == "ranking":
        session.state = "ranking"
        session.save()
    elif accion == "end":
        session.terminar()
    return JsonResponse({"ok": True, "state": session.state})


@login_required
@require_POST
def live_answer(request, code):
    session = get_object_or_404(LiveSession, code=code)
    if session.state != "question":
        return JsonResponse({"error": "no es el momento de responder"}, status=400)
    participante = LiveParticipant.objects.filter(
        session=session, user=request.user
    ).first()
    if not participante:
        return JsonResponse({"error": "no participas en esta partida"}, status=403)
    pregunta = session.current_question
    if not pregunta:
        return JsonResponse({"error": "sin pregunta"}, status=400)
    if participante.answers.filter(question=pregunta).exists():
        return JsonResponse({"error": "ya has respondido"}, status=400)
    choice = pregunta.get_choices().filter(pk=request.POST.get("choice")).first()
    if not choice:
        return JsonResponse({"error": "opción no válida"}, status=400)
    seconds = 0.0
    if session.question_started:
        seconds = (now() - session.question_started).total_seconds()
    if seconds > session.time_limit + 2:
        return JsonResponse({"error": "se acabó el tiempo"}, status=400)
    correcto = bool(choice.correct)
    puntos = _puntos_kahoot(correcto, seconds, session.time_limit)
    LiveAnswer.objects.create(
        participant=participante,
        question=pregunta,
        choice=choice,
        correct=correcto,
        seconds=seconds,
        points=puntos,
    )
    if puntos:
        LiveParticipant.objects.filter(pk=participante.pk).update(
            score=F("score") + puntos
        )
    return JsonResponse({"ok": True, "correct": correcto, "points": puntos})
