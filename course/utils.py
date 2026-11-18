from django.shortcuts import get_object_or_404

from .models import Course, Upload


def deck_del_curso(curso, solo_visibles=False):
    """El mazo de diapositivas del curso, si tiene uno.

    Se reconoce por extension (.html). Es el que el docente ha marcado como
    principal: se embebe arriba del curso, encima de las pestanas. Si ninguno
    esta marcado, se coge el primero por pk, como se hacia antes, para que el
    embed y la descarga cojan siempre el mismo fichero, y no uno distinto
    segun el dia.

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
    principal = mazos.filter(es_principal=True).order_by("pk").first()
    if principal is not None:
        return principal
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


def es_docente_asignado(user, curso):
    """El docente solo ve y toca lo de los cursos que tiene asignados.

    El flag `is_lecturer` solo dice que es docente, no de que: con el flag a
    secas, un docente ajeno veia material oculto, entregas y ficheros
    personales de cualquier curso. El superusuario entra siempre, que es como
    se ha usado el panel.
    """
    return user.is_superuser or curso.allocated_course.filter(lecturer=user).exists()


# Las unidades de aprendizaje: el material del curso se reparte por ellas.
UA_SIN_UNIDAD = None


def unidades_del_curso(curso):
    """Las unidades de aprendizaje del curso, en orden."""
    return list(curso.unidades.all())


def ua_de_fecha(unidades, fecha):
    """La unidad a la que pertenece una fecha.

    Cada unidad va desde la fecha de la anterior hasta la suya: lo que se sube
    hasta la fecha de una unidad va a esa unidad, y lo de despues, a la
    siguiente. Lo que se sube antes de la primera va a la primera, y lo de
    despues de la ultima, a la ultima.

    Sin unidades definidas no hay reparto: devuelve None.
    """
    if not unidades:
        return UA_SIN_UNIDAD
    ordenadas = sorted(unidades, key=lambda u: (u.fecha, u.numero))
    for unidad in ordenadas:
        if fecha <= unidad.fecha:
            return unidad
    return ordenadas[-1]


def ua_de_fichero(unidades, fichero):
    """La unidad de un fichero: la que tiene puesta a mano, o la que le toca.

    La que tiene puesta a mano manda: es para los ficheros que se suben fuera
    de su unidad (material de una clase que se sube antes de tiempo, por
    ejemplo).
    """
    if fichero.unidad_id:
        return fichero.unidad
    return ua_de_fecha(unidades, fichero.upload_time.date())


def marca_ua(unidades, ficheros):
    """Pone a cada fichero su unidad (`fichero.ua`) y su numero de fila.

    El numero es global: sigue contando aunque los ficheros se agrupen por
    unidades, para que la columna `#` no se reinicie en cada grupo.
    """
    for numero, fichero in enumerate(ficheros, start=1):
        fichero.ua = ua_de_fichero(unidades, fichero)
        fichero.num = numero
    return ficheros


def agrupa_por_ua(elementos, unidades, obtener_ua=None):
    """Agrupa elementos por unidad de aprendizaje.

    Devuelve una lista de grupos: `{"unidad": ua|None, "elementos": [...]}`, en
    el orden de las unidades. Lo que no cae en ninguna unidad (un curso sin
    unidades definidas) va en un grupo suelto, sin cabecera.

    `obtener_ua` saca la unidad de cada elemento; por defecto usa el atributo
    `ua`.
    """
    if obtener_ua is None:

        def obtener_ua(elemento):
            return getattr(elemento, "ua", UA_SIN_UNIDAD)

    grupos = {}
    for elemento in elementos:
        unidad = obtener_ua(elemento)
        clave = unidad.pk if unidad else UA_SIN_UNIDAD
        if clave not in grupos:
            grupos[clave] = {"unidad": unidad, "elementos": []}
        grupos[clave]["elementos"].append(elemento)

    orden = {u.pk: posicion for posicion, u in enumerate(unidades)}
    return sorted(
        grupos.values(),
        key=lambda g: orden.get(g["unidad"].pk, len(orden))
        if g["unidad"]
        else len(orden),
    )


def numera_grupos(grupos):
    """Numera las filas de cada grupo, de forma global.

    Sirve para las listas que no son de ficheros (las entregas del alumno van
    en diccionarios), donde no hay atributo donde colgar el numero.
    """
    numero = 0
    for grupo in grupos:
        for elemento in grupo["elementos"]:
            numero += 1
            if isinstance(elemento, dict):
                elemento["num"] = numero
            else:
                elemento.num = numero
    return grupos


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
