from django.shortcuts import get_object_or_404

from .models import Course, Upload


def deck_del_curso(curso, solo_visibles=False):
    """El mazo de diapositivas del curso, si tiene uno.

    Se reconoce por extension (.html). Ordena por pk para que el embed y la
    descarga cojan siempre el mismo fichero, y no uno distinto segun el dia.

    Un curso puede no embeber ninguno: es lo que hace el curso del temario
    completo, que acumula el material de todas las clases y donde embeber solo
    uno dejaria a los demas escondidos. Se decide con `embeber_mazo`.

    Con `solo_visibles` se ignoran los mazos ocultos: uno que todavia no se ha
    revelado no puede embeberse ni descargarse, o el alumnado lo veria antes
    de tiempo.
    """
    if not curso.embeber_mazo:
        return None
    mazos = Upload.objects.filter(course=curso, file__iendswith=".html")
    if solo_visibles:
        mazos = mazos.filter(visible=True)
    return mazos.order_by("pk").first()


def decks_del_curso(curso, solo_visibles=False):
    """Todos los mazos del curso, en el orden en que se fueron subiendo.

    Cada uno es un HTML autocontenido, asi que se puede abrir en el navegador
    tal cual, sin la plataforma de por medio.
    """
    mazos = Upload.objects.filter(course=curso, file__iendswith=".html")
    if solo_visibles:
        mazos = mazos.filter(visible=True)
    return mazos.order_by("upload_time", "pk")


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
