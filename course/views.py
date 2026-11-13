import os
import re
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import FileResponse, Http404
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.text import slugify
from django.views.decorators.http import require_POST
from django.views.generic import CreateView
from django_filters.views import FilterView

from accounts.decorators import lecturer_required, student_required
from accounts.models import Student
from core.models import Semester
from course.filters import CourseAllocationFilter, ProgramFilter
from course.forms import (
    CourseAddForm,
    CourseAllocationForm,
    EditCourseAllocationForm,
    ProgramForm,
    SubmissionForm,
    SubmissionGradeForm,
    UploadFormFile,
    UploadFormVideo,
)
from course.models import (
    Course,
    CourseAllocation,
    Program,
    Submission,
    Upload,
    UploadFile,
    UploadVideo,
)
from course.utils import (
    curso_asignado,
    deck_del_curso,
    decks_del_curso,
    es_docente_asignado,
)
from result.models import TakenCourse


# Las pestanas de la pagina del curso. La que se muestra va en la URL
# (?tab=...), para que el enlace se pueda compartir y la pestana sobreviva a
# un F5.
PESTANAS = (
    "presentaciones",
    "actividades",
    "entregas",
    "videos",
    "documentacion",
)


def al_curso(slug, tab):
    """El curso abierto en la pestana `tab`, para no perderla al volver."""
    return redirect(f"{reverse('course_detail', kwargs={'slug': slug})}?tab={tab}")


def pestana_de(upload, curso):
    """La pestana donde vive un fichero del curso.

    Cada tipo se consulta en la suya, y asi el redirect vuelve a la que
    estaba mirando quien lo ha tocado: las presentaciones (.html) en
    Presentaciones, las actividades en Actividades y el resto en
    Documentacion.
    """
    if upload.es_html:
        return "presentaciones"
    if upload.is_activity:
        return "actividades"
    return "documentacion"


# ########################################################
# Program Views
# ########################################################


@method_decorator([login_required, lecturer_required], name="dispatch")
class ProgramFilterView(FilterView):
    filterset_class = ProgramFilter
    template_name = "course/program_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Programs"
        return context


@login_required
@lecturer_required
def program_add(request):
    if request.method == "POST":
        form = ProgramForm(request.POST)
        if form.is_valid():
            program = form.save()
            messages.success(request, f"{program.title} program has been created.")
            return redirect("programs")
        messages.error(request, "Correct the error(s) below.")
    else:
        form = ProgramForm()
    return render(
        request, "course/program_add.html", {"title": "Add Program", "form": form}
    )


@login_required
def program_detail(request, pk):
    program = get_object_or_404(Program, pk=pk)
    all_courses = Course.objects.filter(program_id=pk).order_by("-year")
    courses = all_courses
    credits = courses.aggregate(total_credits=Sum("credit"))
    paginator = Paginator(courses, 10)
    page = request.GET.get("page")
    courses = paginator.get_page(page)

    activity_reports = []
    if request.user.is_superuser or request.user.is_lecturer:
        report_courses = all_courses
        if not request.user.is_superuser:
            report_courses = report_courses.filter(
                allocated_course__lecturer=request.user
            ).distinct()

        activities = list(
            Upload.objects.filter(course__in=report_courses, is_activity=True)
            .select_related("course")
            .order_by("course__code", "upload_time", "pk")
        )
        enrollments = list(
            TakenCourse.objects.filter(course__in=report_courses)
            .select_related("student__student", "course")
            .order_by(
                "course__code",
                "student__student__last_name",
                "student__student__first_name",
            )
        )
        submissions = Submission.objects.filter(
            course__in=report_courses, document__is_activity=True
        ).select_related("document")
        submissions_by_key = {
            (
                submission.student_id,
                submission.course_id,
                submission.document_id,
            ): submission
            for submission in submissions
        }

        activities_by_course = {}
        for activity in activities:
            activities_by_course.setdefault(activity.course_id, []).append(activity)

        enrollments_by_course = {}
        for enrollment in enrollments:
            enrollments_by_course.setdefault(enrollment.course_id, []).append(
                enrollment
            )

        for course in report_courses:
            course_activities = activities_by_course.get(course.pk, [])
            if not course_activities:
                continue

            rows = []
            for enrollment in enrollments_by_course.get(course.pk, []):
                user_id = enrollment.student.student_id
                cells = [
                    submissions_by_key.get((user_id, course.pk, activity.pk))
                    for activity in course_activities
                ]
                grades = [
                    submission.mark
                    for submission in cells
                    if submission and submission.mark is not None
                ]
                rows.append(
                    {
                        "student": enrollment.student.student,
                        "cells": cells,
                        "average": sum(grades) / len(grades) if grades else None,
                    }
                )
            activity_reports.append(
                {"course": course, "activities": course_activities, "rows": rows}
            )

    return render(
        request,
        "course/program_single.html",
        {
            "title": program.title,
            "program": program,
            "courses": courses,
            "credits": credits,
            "activity_reports": activity_reports,
        },
    )


@login_required
@lecturer_required
def program_edit(request, pk):
    program = get_object_or_404(Program, pk=pk)
    if request.method == "POST":
        form = ProgramForm(request.POST, instance=program)
        if form.is_valid():
            program = form.save()
            messages.success(request, f"{program.title} program has been updated.")
            return redirect("programs")
        messages.error(request, "Correct the error(s) below.")
    else:
        form = ProgramForm(instance=program)
    return render(
        request, "course/program_add.html", {"title": "Edit Program", "form": form}
    )


@require_POST
@login_required
@lecturer_required
def program_delete(request, pk):
    program = get_object_or_404(Program, pk=pk)
    title = program.title
    program.delete()
    messages.success(request, f"Program {title} has been deleted.")
    return redirect("programs")


# ########################################################
# Course Views
# ########################################################


# Un t??tulo que empieza por un n??mero ("0 ?? El m??dulo", "7 ?? Herramientas")
# es una presentaci??n numerada. Esas van primero y en orden num??rico; el
# resto de los documentos conserva el orden por fecha de subida.
NUMERO_DE_TITULO = re.compile(r"^(?:Actividad\s+)?(\d+)\s*\u00b7")


def _orden_de_lectura(documento):
    empareja = NUMERO_DE_TITULO.match(documento.title or "")
    if empareja:
        return (0, int(empareja.group(1)), documento.upload_time, documento.pk)
    return (1, 0, documento.upload_time, documento.pk)


@login_required
def course_single(request, slug):
    course = get_object_or_404(Course, slug=slug)
    # La pestana activa va en la URL (?tab=...). Sin javascript, cada enlace
    # de pestana recarga la pagina con esa pestana abierta; con javascript el
    # cambio no recarga y solo se actualiza la URL.
    tab = request.GET.get("tab", "presentaciones")
    if tab not in PESTANAS:
        tab = "presentaciones"
    # prefetch de los ficheros adicionales: sin esto, la tabla del curso hace
    # una consulta por actividad para listar sus .odt y .docx alternativos
    # por fecha de subida: el material sale en el orden de las clases, y no
    # en el orden en que se fue creando cada fila
    files = (
        Upload.objects.filter(course__slug=slug)
        .prefetch_related("archivos")
        .order_by("upload_time", "pk")
    )
    videos = UploadVideo.objects.filter(course__slug=slug)
    lecturers = CourseAllocation.objects.filter(courses__pk=course.id)
    # El docente solo ve lo oculto y las entregas de sus cursos asignados:
    # el flag is_lecturer a secas dejaba verlo todo en cualquier curso.
    is_editor = es_docente_asignado(request.user, course)
    # Los documentos ocultos son los que el profesorado sube antes de tiempo: una
    # prueba que no debe ver el alumnado hasta que toque. El docente los ve
    # siempre, para poder prepararlos.
    if not is_editor:
        files = files.filter(visible=True)
        # Los vídeos también: se revelan el día de cada clase.
        videos = videos.filter(visible=True)
    # Orden de lectura: las presentaciones numeradas ("0 - ...", "1 - ...") van
    # primero y en orden numerico; el resto de los documentos conserva el
    # orden por fecha de subida. Asi el alumnado ve la secuencia del modulo
    # sin tener que descifrar los numeros.
    # Las presentaciones (.html) tienen su propia pestana: de lo demas, las
    # actividades van a la suya (el alumno entrega ahi) y el resto de los
    # documentos a Documentacion.
    files = sorted(files.exclude(file__iendswith=".html"), key=_orden_de_lectura)
    # El resalte caduca solo: se marca mientras no haya pasado la hora.
    ahora = timezone.now()
    for documento in files:
        documento.resaltado_activo = bool(
            documento.resaltado
            and documento.resaltado_hasta
            and documento.resaltado_hasta > ahora
        )
    # La misma lista, separada por pestanas: la actividad se entrega, el
    # documento solo se consulta.
    actividades = [d for d in files if d.is_activity]
    documentos = [d for d in files if not d.is_activity]
    # solo se entrega si hay matricula: antes cualquier cuenta que entraba
    # podia entregar en cualquier curso
    matriculado = TakenCourse.objects.filter(
        student__student=request.user, course=course
    ).exists()
    # el mazo de diapositivas, si lo hay: se muestra embebido arriba del curso
    deck = deck_del_curso(course, solo_visibles=not is_editor)
    # todos los mazos, para la pestana de presentaciones
    decks = sorted(
        decks_del_curso(course, solo_visibles=not is_editor), key=_orden_de_lectura
    )

    if request.method == "POST":
        # ponytail: entrega del alumno; el profesor solo revisa la tabla de abajo
        # El POST sale de la pestana de entregas, asi que ahi se vuelve a abrir.
        tab = "entregas"
        if is_editor:
            messages.error(request, "Solo los alumnos pueden entregar trabajos.")
            return redirect("course_detail", slug=slug)
        if not matriculado:
            messages.error(request, "No estas matriculado en este curso.")
            return redirect("course_detail", slug=slug)
        form = SubmissionForm(
            request.POST,
            request.FILES,
            course=course,
            solo_visibles=not is_editor,
            alumno=request.user,
        )
        if form.is_valid():
            document = form.cleaned_data["document"]
            with transaction.atomic():
                entrega_previa = (
                    Submission.objects.select_for_update()
                    .filter(course=course, student=request.user, document=document)
                    .first()
                )
                if entrega_previa and entrega_previa.mark is not None:
                    messages.error(
                        request,
                        "Esta entrega ya esta calificada y no se puede reemplazar: "
                        "habla con tu docente.",
                    )
                    return al_curso(slug, "entregas")
                submission, _ = Submission.objects.get_or_create(
                    course=course, student=request.user, document=document
                )
                # El fichero nuevo se guarda antes de tirar el viejo: si el
                # save falla (o dos envios corren a la vez), la entrega no se
                # pierde; el fichero sobrante se limpia al final.
                fichero_viejo = submission.file
                submission.file = form.cleaned_data["file"]
                submission.save()
                if fichero_viejo:
                    fichero_viejo.delete(save=False)
            if entrega_previa:
                messages.success(
                    request,
                    f"Se ha reemplazado tu entrega anterior de '{document.title}'.",
                )
            else:
                messages.success(request, "Tu entrega se ha enviado correctamente.")
            return al_curso(slug, "entregas")
        messages.error(request, "Revisa los errores del formulario.")
    else:
        form = (
            SubmissionForm(
                course=course,
                solo_visibles=not is_editor,
                alumno=request.user,
            )
            if matriculado
            else None
        )

    my_submissions = None
    entregas_evaluables = None
    entregas_ordinarias = None
    submissions = None
    entregas_ocultas = 0
    entregas_totales = 0
    entregas_visibles = 0
    entregas_calificadas = 0
    entregas_sin_calificar = 0
    if is_editor:
        submissions = (
            Submission.objects.filter(course=course)
            .select_related("student", "document")
            .order_by("document__upload_time", "student__username")
        )
        entregas_totales = submissions.count()
        # Reparto sobre TODAS las entregas del curso, no solo sobre las visibles:
        # es la medida del trabajo que queda, y no debe cambiar al marcar el check.
        entregas_calificadas = submissions.aggregate(
            n=Count("pk", filter=Q(mark__isnull=False))
        )["n"]
        # Con el check del curso puesto, al docente no se le muestran las
        # entregas ya corregidas de las actividades NO evaluables: solo le queda
        # lo pendiente. Las evaluables se ven siempre.
        if request.user.ocultar_entregas_corregidas:
            submissions = submissions.exclude(
                document__is_evaluable=False, mark__isnull=False
            )
        entregas_visibles = submissions.count()
        entregas_ocultas = entregas_totales - entregas_visibles
        entregas_sin_calificar = entregas_totales - entregas_calificadas
    else:
        my_submissions = (
            Submission.objects.filter(course=course, student=request.user)
            .select_related("document")
            .order_by("document__upload_time")
        )
        # La tabla de la pestana de entregas: cada actividad visible del curso
        # con su entrega, si la hay. Asi el alumno ve de un vistazo cual falta
        # por entregar; el select de arriba sigue siendo la via de entrega.
        if matriculado:
            mis = {s.document_id: s for s in my_submissions}
            filas = [{"actividad": a, "entrega": mis.get(a.pk)} for a in actividades]
            # Dos tablas: las evaluables aparte, porque cuentan para la nota y
            # son lo primero que hay que mirar; el resto conserva el orden de
            # lectura.
            entregas_evaluables = [f for f in filas if f["actividad"].is_evaluable]
            entregas_ordinarias = [f for f in filas if not f["actividad"].is_evaluable]

    return render(
        request,
        "course/course_single.html",
        {
            "title": course.title,
            "course": course,
            "actividades": actividades,
            "documentos": documentos,
            "videos": videos,
            "lecturers": lecturers,
            "media_url": settings.MEDIA_URL,
            "is_editor": is_editor,
            "deck": deck,
            "decks": decks,
            "tab_activa": tab,
            "submission_form": form,
            "my_submissions": my_submissions,
            "entregas_evaluables": entregas_evaluables,
            "entregas_ordinarias": entregas_ordinarias,
            "submissions": submissions,
            "entregas_ocultas": entregas_ocultas,
            "entregas_totales": entregas_totales,
            "entregas_visibles": entregas_visibles,
            "entregas_calificadas": entregas_calificadas,
            "entregas_sin_calificar": entregas_sin_calificar,
        },
    )


@require_POST
@login_required
@lecturer_required
def course_ocultar_corregidas(request, slug):
    """El docente decide si en la tabla de entregas quiere ver las ya corregidas.

    Es una preferencia de la cuenta (vale para todos sus cursos) y se cambia con
    el check de la pagina del curso.
    """
    course = get_object_or_404(Course, slug=slug)
    request.user.ocultar_entregas_corregidas = request.POST.get("ocultar") == "on"
    request.user.save(update_fields=["ocultar_entregas_corregidas"])
    if request.user.ocultar_entregas_corregidas:
        messages.success(
            request,
            "Se ocultaran las entregas ya corregidas de las actividades no evaluables.",
        )
    else:
        messages.success(request, "Se veran todas las entregas.")
    return al_curso(course.slug, "entregas")


@require_POST
@login_required
@lecturer_required
def course_mazo_principal(request, slug, file_id):
    """El docente elige la presentacion principal del curso.

    La principal es la que se muestra embebida arriba de la pagina del curso,
    encima de las pestanas: solo puede haber una, y al marcarla se desmarcan
    las demas. Quitarla deja el curso sin mazo embebido (los mazos siguen en
    su pestana, abribles y descargables).
    """
    course = curso_asignado(request, slug)
    mazo = get_object_or_404(Upload, pk=file_id, course=course)
    if not mazo.es_html:
        messages.error(
            request,
            "Solo un mazo de diapositivas (.html) puede ser la presentacion principal.",
        )
        return redirect("course_detail", slug=slug)
    if mazo.es_principal:
        mazo.es_principal = False
        mazo.save(update_fields=["es_principal"])
        course.embeber_mazo = False
        course.save(update_fields=["embeber_mazo"])
        messages.success(
            request,
            f"'{mazo.title}' ya no es la presentacion principal del curso.",
        )
    else:
        Upload.objects.filter(course=course).exclude(pk=mazo.pk).update(
            es_principal=False
        )
        mazo.es_principal = True
        mazo.save(update_fields=["es_principal"])
        course.embeber_mazo = True
        course.save(update_fields=["embeber_mazo"])
        messages.success(
            request,
            f"'{mazo.title}' es ahora la presentacion principal del curso.",
        )
    return al_curso(course.slug, "presentaciones")


@require_POST
@login_required
def submission_delete(request, slug, pk):
    """El alumno se arrepiente: borra su propia entrega para volver a entregar.

    Solo se puede borrar la propia y solo mientras no este calificada: una
    entrega con nota forma parte del expediente, y para cambiarla hay que
    hablar con el docente.
    """
    course = get_object_or_404(Course, slug=slug)
    submission = get_object_or_404(Submission, pk=pk, course=course)
    if submission.student_id != request.user.id:
        raise Http404
    with transaction.atomic():
        # El check del estado va dentro de la transaccion y con lock: si el
        # docente califica justo entre el check y el borrado, la entrega ya
        # calificada no desaparece del expediente.
        submission = (
            Submission.objects.select_for_update()
            .select_related("document")
            .get(pk=submission.pk)
        )
        if submission.mark is not None:
            messages.error(
                request,
                "No se puede borrar una entrega ya calificada: habla con tu docente.",
            )
            return al_curso(course.slug, "entregas")
        titulo = (
            submission.document.title if submission.document else submission.filename
        )
        submission.file.delete(save=False)
        submission.delete()
    messages.success(request, f"Se ha borrado tu entrega de '{titulo}'.")
    return al_curso(course.slug, "entregas")


@login_required
def submission_download(request, slug, pk):
    course = get_object_or_404(Course, slug=slug)
    submission = get_object_or_404(Submission, pk=pk, course=course)
    # La entrega es un fichero personal del alumno: la baja quien la hizo o
    # el docente del curso, no cualquier docente.
    if not (
        submission.student_id == request.user.id
        or es_docente_asignado(request.user, course)
    ):
        raise Http404
    return FileResponse(
        submission.file.open("rb"),
        as_attachment=True,
        filename=submission.filename,
    )


@login_required
def deck_download(request, slug):
    """Descarga el mazo de diapositivas del curso como fichero adjunto.

    `as_attachment` manda Content-Disposition: attachment, asi que el navegador
    guarda el HTML en vez de abrirlo en una pestana. Es lo mismo que hace
    submission_download con las entregas.
    """
    course = get_object_or_404(Course, slug=slug)
    deck = deck_del_curso(
        course,
        # solo el docente asignado ve los mazos aun ocultos
        solo_visibles=not es_docente_asignado(request.user, course),
    )
    if deck is None:
        raise Http404("Este curso no tiene presentacion")
    return FileResponse(
        deck.file.open("rb"),
        as_attachment=True,
        filename=deck.file.name.rsplit("/", 1)[-1],
    )


@login_required
def upload_file_download(request, slug, file_id, archivo_id=None):
    """Descarga un fichero del curso con el usuario en el nombre local.

    La URL directa del fichero la sirve el servidor de ficheros, asi que ahi no
    hay forma de renombrar la descarga. Al pasar por Django se puede, y asi cada
    usuario se baja su propia copia: al devolverla se sabe de quien es sin mirar
    el contenido. Acepta tanto el fichero principal de Upload como uno adicional
    de UploadFile.

    El prefijo sale del titulo: si hay un codigo de actividad (E1, E2...) se
    usa ese, y si no, el titulo en minusculas y con guiones.
    """
    course = get_object_or_404(Course, slug=slug)
    upload = get_object_or_404(Upload, pk=file_id, course=course)
    # el documento oculto no se descarga por id: si no está en la lista, no existe
    if not upload.visible and not es_docente_asignado(request.user, course):
        raise Http404
    fichero = upload.file
    if archivo_id is not None:
        adicional = get_object_or_404(UploadFile, pk=archivo_id, upload=upload)
        fichero = adicional.file

    codigo = re.search(r"\bE\d+\b", upload.title)
    if codigo:
        prefijo = codigo.group(0)
    else:
        prefijo = slugify(upload.title)[:40].strip("-") or "material"
    extension = os.path.splitext(fichero.name)[1]
    return FileResponse(
        fichero.open("rb"),
        as_attachment=True,
        filename=f"{prefijo}_{request.user.username}{extension}",
    )


@login_required
def deck_abrir(request, slug, file_id):
    """Abre un mazo de diapositivas en el navegador, sin descargarlo.

    El mazo es un HTML autocontenido, con el estilo y el motor de navegacion
    dentro, asi que se puede abrir desde el disco. Aqui se sirve en linea, con
    `Content-Disposition: inline`, para que se abra en una pestana nueva.
    """
    course = get_object_or_404(Course, slug=slug)
    upload = get_object_or_404(Upload, pk=file_id, course=course)
    if not upload.es_html:
        raise Http404("Este documento no es una presentacion")
    if not upload.visible and not es_docente_asignado(request.user, course):
        raise Http404
    respuesta = FileResponse(
        upload.file.open("rb"), content_type="text/html; charset=utf-8"
    )
    respuesta["Content-Disposition"] = 'inline; filename="%s"' % os.path.basename(
        upload.file.name
    )
    return respuesta


@login_required
@lecturer_required
def submission_grade(request, slug, pk):
    course = get_object_or_404(Course, slug=slug)
    submission = get_object_or_404(Submission, pk=pk, course=course)
    # Calificar solo lo del propio curso: el pk suelto dejaba calificar a un
    # docente ajeno.
    if not es_docente_asignado(request.user, course):
        raise Http404
    if request.method == "POST":
        form = SubmissionGradeForm(request.POST, instance=submission)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.graded_at = timezone.now()
            submission.save()
            messages.success(request, "Calificacion guardada.")
            return al_curso(slug, "entregas")
        messages.error(request, "Revisa los errores del formulario.")
    else:
        form = SubmissionGradeForm(instance=submission)
    return render(
        request,
        "course/submission_grade.html",
        {
            "title": "Calificar entrega",
            "course": course,
            "submission": submission,
            "form": form,
        },
    )


@login_required
@lecturer_required
def course_add(request, pk):
    program = get_object_or_404(Program, pk=pk)
    if request.method == "POST":
        form = CourseAddForm(request.POST)
        if form.is_valid():
            course = form.save()
            messages.success(
                request, f"{course.title} ({course.code}) has been created."
            )
            return redirect("program_detail", pk=program.pk)
        messages.error(request, "Correct the error(s) below.")
    else:
        form = CourseAddForm(initial={"program": program})
    return render(
        request,
        "course/course_add.html",
        {"title": "Add Course", "form": form, "program": program},
    )


@login_required
@lecturer_required
def course_edit(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if request.method == "POST":
        form = CourseAddForm(request.POST, instance=course)
        if form.is_valid():
            course = form.save()
            messages.success(
                request, f"{course.title} ({course.code}) has been updated."
            )
            return redirect("program_detail", pk=course.program.pk)
        messages.error(request, "Correct the error(s) below.")
    else:
        form = CourseAddForm(instance=course)
    return render(
        request, "course/course_add.html", {"title": "Edit Course", "form": form}
    )


@require_POST
@login_required
@lecturer_required
def course_delete(request, slug):
    course = get_object_or_404(Course, slug=slug)
    title = course.title
    program_id = course.program.id
    course.delete()
    messages.success(request, f"Course {title} has been deleted.")
    return redirect("program_detail", pk=program_id)


# ########################################################
# Course Allocation Views
# ########################################################


@method_decorator([login_required, lecturer_required], name="dispatch")
class CourseAllocationFormView(CreateView):
    form_class = CourseAllocationForm
    template_name = "course/course_allocation_form.html"

    def form_valid(self, form):
        lecturer = form.cleaned_data["lecturer"]
        selected_courses = form.cleaned_data["courses"]
        allocation, created = CourseAllocation.objects.get_or_create(lecturer=lecturer)
        allocation.courses.set(selected_courses)
        messages.success(
            self.request, f"Courses allocated to {lecturer.get_full_name} successfully."
        )
        return redirect("course_allocation_view")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Assign Course"
        return context


@method_decorator([login_required, lecturer_required], name="dispatch")
class CourseAllocationFilterView(FilterView):
    filterset_class = CourseAllocationFilter
    template_name = "course/course_allocation_view.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Course Allocations"
        return context


@login_required
@lecturer_required
def edit_allocated_course(request, pk):
    allocation = get_object_or_404(CourseAllocation, pk=pk)
    if request.method == "POST":
        form = EditCourseAllocationForm(request.POST, instance=allocation)
        if form.is_valid():
            form.save()
            messages.success(request, "Course allocation has been updated.")
            return redirect("course_allocation_view")
        messages.error(request, "Correct the error(s) below.")
    else:
        form = EditCourseAllocationForm(instance=allocation)
    return render(
        request,
        "course/course_allocation_form.html",
        {"title": "Edit Course Allocation", "form": form},
    )


@require_POST
@login_required
@lecturer_required
def deallocate_course(request, pk):
    allocation = get_object_or_404(CourseAllocation, pk=pk)
    allocation.delete()
    messages.success(request, "Successfully deallocated courses.")
    return redirect("course_allocation_view")


# ########################################################
# File Upload Views
# ########################################################


@login_required
@lecturer_required
def handle_file_upload(request, slug):
    # `curso_asignado`: un docente solo sube material a los cursos que tiene
    # asignados. Antes cogia el curso por el slug y cualquiera podia subir
    # (incluido un mazo .html con javascript) a un curso ajeno cambiando la
    # URL; sus hermanas edit/delete ya lo hacian asi.
    course = curso_asignado(request, slug)
    if request.method == "POST":
        form = UploadFormFile(request.POST, request.FILES)
        if form.is_valid():
            upload = form.save(commit=False)
            upload.course = course
            upload.save()
            form.guardar_archivos(upload)
            messages.success(request, f"{upload.title} has been uploaded.")
            return al_curso(slug, pestana_de(upload, course))
        messages.error(request, "Correct the error(s) below.")
    else:
        form = UploadFormFile()
    return render(
        request,
        "upload/upload_file_form.html",
        {"title": "File Upload", "form": form, "course": course},
    )


@login_required
@lecturer_required
def handle_file_edit(request, slug, file_id):
    course = curso_asignado(request, slug)
    upload = get_object_or_404(Upload, pk=file_id, course=course)
    if request.method == "POST":
        form = UploadFormFile(request.POST, request.FILES, instance=upload)
        if form.is_valid():
            with transaction.atomic():
                # Si se sube un fichero nuevo, el anterior queda en el disco
                # y servible bajo /media/: se borra despues de guardar.
                fichero_viejo = upload.file
                upload = form.save()
                form.guardar_archivos(upload)
                if (
                    fichero_viejo
                    and upload.file
                    and fichero_viejo.name != upload.file.name
                ):
                    fichero_viejo.delete(save=False)
            messages.success(request, f"{upload.title} has been updated.")
            return al_curso(slug, pestana_de(upload, course))
        messages.error(request, "Correct the error(s) below.")
    else:
        form = UploadFormFile(instance=upload)
    return render(
        request,
        "upload/upload_file_form.html",
        {"title": "Edit File", "form": form, "course": course},
    )


@require_POST
@login_required
@lecturer_required
def handle_file_delete(request, slug, file_id):
    course = curso_asignado(request, slug)
    upload = get_object_or_404(Upload, pk=file_id, course=course)
    title = upload.title
    # La pestana de destino, antes de borrar: el pre_delete limpia el fichero
    # del disco y deja el nombre a None, asi que luego ya no se sabe.
    pestana = pestana_de(upload, course)
    upload.delete()
    messages.success(request, f"{title} has been deleted.")
    return al_curso(slug, pestana)


@require_POST
@login_required
@lecturer_required
def resaltar_documento(request, slug, file_id):
    """Resalta una fila de la tabla de actividades o de documentaciones.

    El resalte dura 24 horas, o hasta que se resalte otra: al resaltar una
    fila, las demas se apagan. Pulsando otra vez la misma fila se quita.
    """
    course = curso_asignado(request, slug)
    upload = get_object_or_404(Upload, pk=file_id, course=course)
    ahora = timezone.now()
    # Solo una fila puede estar resaltada: al resaltar esta, se apagan las demas.
    Upload.objects.filter(course=course).exclude(pk=upload.pk).update(
        resaltado=False, resaltado_hasta=None
    )
    if upload.resaltado and upload.resaltado_hasta and upload.resaltado_hasta > ahora:
        upload.resaltado = False
        upload.resaltado_hasta = None
    else:
        upload.resaltado = True
        upload.resaltado_hasta = ahora + timedelta(days=1)
    upload.save(update_fields=["resaltado", "resaltado_hasta"])
    return al_curso(course.slug, pestana_de(upload, course))


@require_POST
@login_required
@lecturer_required
def handle_archivo_delete(request, slug, file_id, archivo_id):
    """Borra un fichero adicional suelto, sin tocar el principal ni el resto."""
    course = curso_asignado(request, slug)
    upload = get_object_or_404(Upload, pk=file_id, course=course)
    archivo = get_object_or_404(UploadFile, pk=archivo_id, upload=upload)
    nombre = archivo.file.name
    archivo.delete()
    messages.success(request, f"{nombre} has been deleted.")
    return al_curso(slug, pestana_de(upload, course))


# ########################################################
# Video Upload Views
# ########################################################


@login_required
@lecturer_required
def handle_video_upload(request, slug):
    # `curso_asignado`: un docente solo sube material a los cursos que tiene
    # asignados. Antes cogía el curso por el slug y cualquiera podía subir a
    # un curso ajeno cambiando la URL.
    course = curso_asignado(request, slug)
    if request.method == "POST":
        form = UploadFormVideo(request.POST, request.FILES)
        if form.is_valid():
            video = form.save(commit=False)
            video.course = course
            video.save()
            messages.success(request, f"{video.title} has been uploaded.")
            return al_curso(slug, "videos")
        messages.error(request, "Correct the error(s) below.")
    else:
        form = UploadFormVideo()
    return render(
        request,
        "upload/upload_video_form.html",
        {"title": "Video Upload", "form": form, "course": course},
    )


@login_required
def handle_video_single(request, slug, video_slug):
    course = get_object_or_404(Course, slug=slug)
    # El vídeo se busca dentro del curso de la URL: con el slug suelto se
    # veía el vídeo de otro curso. Y un vídeo oculto solo lo abre el
    # profesorado: el alumnado, hasta que se revela.
    videos = UploadVideo.objects.filter(course=course)
    if not es_docente_asignado(request.user, course):
        videos = videos.filter(visible=True)
    video = get_object_or_404(videos, slug=video_slug)
    return render(
        request,
        "upload/video_single.html",
        {"video": video, "course": course},
    )


@login_required
@lecturer_required
def handle_video_edit(request, slug, video_slug):
    course = curso_asignado(request, slug)
    video = get_object_or_404(UploadVideo, slug=video_slug, course=course)
    if request.method == "POST":
        form = UploadFormVideo(request.POST, request.FILES, instance=video)
        if form.is_valid():
            video = form.save()
            messages.success(request, f"{video.title} has been updated.")
            return al_curso(slug, "videos")
        messages.error(request, "Correct the error(s) below.")
    else:
        form = UploadFormVideo(instance=video)
    return render(
        request,
        "upload/upload_video_form.html",
        {"title": "Edit Video", "form": form, "course": course},
    )


@require_POST
@login_required
@lecturer_required
def handle_video_delete(request, slug, video_slug):
    course = curso_asignado(request, slug)
    video = get_object_or_404(UploadVideo, slug=video_slug, course=course)
    title = video.title
    video.delete()
    messages.success(request, f"{title} has been deleted.")
    return al_curso(slug, "videos")


# ########################################################
# Course Registration Views
# ########################################################


@login_required
@student_required
def course_registration(request):
    if request.method == "POST":
        student = get_object_or_404(Student, student__pk=request.user.id)
        current_semester = Semester.objects.filter(is_current_semester=True).first()
        if not current_semester:
            messages.error(request, "No active semester found.")
            return render(request, "course/course_registration.html")

        data = request.POST.copy()
        data.pop("csrfmiddlewaretoken", None)  # remove csrf_token
        # antes cogia los ids del POST tal cual (Course.objects.get) y admitia
        # cualquier curso del mundo; ahora solo los de su programa, nivel y
        # semestre, que es lo mismo que le ofrecian en el formulario
        # Solo las claves del POST que sean ids numericos: una clave sobrante
        # (csrf, un input de un plugin...) era un ValueError y un 500.
        ids_validos = {int(clave) for clave in data.keys() if clave.isdigit()}
        cursos = Course.objects.filter(
            program__pk=student.program_id,
            level=student.level,
            semester=current_semester,
        ).filter(pk__in=ids_validos)
        for course in cursos:
            TakenCourse.objects.get_or_create(student=student, course=course)
        messages.success(request, "Courses registered successfully!")
        return redirect("course_registration")
    else:
        current_semester = Semester.objects.filter(is_current_semester=True).first()
        if not current_semester:
            messages.error(request, "No active semester found.")
            return render(request, "course/course_registration.html")

        # student = Student.objects.get(student__pk=request.user.id)
        student = get_object_or_404(Student, student__id=request.user.id)
        taken_courses = TakenCourse.objects.filter(student__student__id=request.user.id)
        t = ()
        for i in taken_courses:
            t += (i.course.pk,)

        courses = (
            Course.objects.filter(
                program__pk=student.program_id,
                level=student.level,
                semester=current_semester,
            )
            .exclude(id__in=t)
            .order_by("year")
        )
        all_courses = Course.objects.filter(
            level=student.level, program__pk=student.program_id
        )

        no_course_is_registered = False  # Check if no course is registered
        all_courses_are_registered = False

        registered_courses = Course.objects.filter(level=student.level).filter(id__in=t)
        if (
            registered_courses.count() == 0
        ):  # Check if number of registered courses is 0
            no_course_is_registered = True

        if registered_courses.count() == all_courses.count():
            all_courses_are_registered = True

        total_first_semester_credit = 0
        total_sec_semester_credit = 0
        total_registered_credit = 0
        for i in courses:
            if i.semester == "First":
                total_first_semester_credit += int(i.credit)
            if i.semester == "Second":
                total_sec_semester_credit += int(i.credit)
        for i in registered_courses:
            total_registered_credit += int(i.credit)
        context = {
            "is_calender_on": True,
            "all_courses_are_registered": all_courses_are_registered,
            "no_course_is_registered": no_course_is_registered,
            "current_semester": current_semester,
            "courses": courses,
            "total_first_semester_credit": total_first_semester_credit,
            "total_sec_semester_credit": total_sec_semester_credit,
            "registered_courses": registered_courses,
            "total_registered_credit": total_registered_credit,
            "student": student,
        }
        return render(request, "course/course_registration.html", context)


# ########################################################
# User Course List View
# ########################################################


@login_required
def user_course_list(request):
    if request.user.is_lecturer:
        courses = Course.objects.filter(allocated_course__lecturer__pk=request.user.id)
        return render(request, "course/user_course_list.html", {"courses": courses})

    if request.user.is_student:
        student = get_object_or_404(Student, student__pk=request.user.id)
        taken_courses = TakenCourse.objects.filter(student=student)
        return render(
            request,
            "course/user_course_list.html",
            {"student": student, "taken_courses": taken_courses},
        )

    # For other users
    return render(request, "course/user_course_list.html")
