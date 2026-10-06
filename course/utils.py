from django.shortcuts import get_object_or_404

from .models import Course, Upload


def deck_del_curso(curso):
    """El mazo de diapositivas del curso, si tiene uno.

    Se reconoce por extension (.html). Ordena por pk para que el embed y la
    descarga cojan siempre el mismo fichero, y no uno distinto segun el dia.
    """
    return (
        Upload.objects.filter(course=curso, file__iendswith=".html")
        .order_by("pk")
        .first()
    )


def curso_asignado(request, slug):
    """El curso del slug, solo si el docente lo tiene asignado.

    `lecturer_required` deja pasar a cualquier docente, y estas vistas cogian el
    material por pk o por slug suelto: con solo la URL se editaba o borraba el
    material de otro curso. El superusuario entra siempre, que es como se ha
    usado el panel.
    """
    cursos = Course.objects.filter(slug=slug).distinct()
    if not request.user.is_superuser:
        cursos = cursos.filter(allocated_course__lecturer=request.user)
    return get_object_or_404(cursos)
