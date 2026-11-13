"""Estado de entregas de mf0488 (sub-cursos 9-13)."""
import os, sys, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, "/opt/skylearn")
django.setup()

from accounts.models import Student
from course.models import Course, Upload, Submission

sesiones = Course.objects.filter(code__icontains="mf0488").exclude(id=8).order_by("id")
for curso in sesiones:
    print("="*100)
    print(f"SESIÓN {curso.id} {curso.code!r}  ({curso.title})")
    ups = Upload.objects.filter(course=curso, is_activity=True).order_by("id")
    extra = Upload.objects.filter(course=curso, is_activity=False).order_by("id")
    print(f"  actividades={ups.count()}  materiales={extra.count()}")
    print()
    # ¿qué alumnos están matriculados en esta sesión?
    mats = list(curso.taken_courses.select_related("student", "student__student").order_by("student__id"))
    alumnos = [t.student for t in mats]
    if not alumnos:
        print(f"  (sin alumnos matriculados)")
    for u in ups:
        subs = list(u.submissions.select_related("student").order_by("student_id"))
        entregado_por = sorted({s.student.username for s in subs})
        print(f"  [{u.id}] {u.title!r}")
        print(f"        fichero: {u.file.name}")
        if not entregado_por:
            print(f"        ENTREGAS: nadie")
        else:
            print(f"        ENTREGAS: {len(entregado_por)} -> {', '.join(entregado_por)}")
