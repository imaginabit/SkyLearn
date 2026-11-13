"""Ver entregas concretas de mf0488 por pk."""
import os, sys, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, "/opt/skylearn")
django.setup()

from course.models import Course, Upload, Submission

CODES = {
    61: "A1-datos", 62: "A1-IDS",
    64: "A2-ubicacion", 67: "A2-tecnicas",
    69: "A3-senuelo",
    74: "A4-recoleccion", 75: "A4-indicios", 76: "A4-ficha",
    80: "A5-correlacion", 81: "A5-informe",
    82: "A5-cuestionario", 83: "A5-UA2",
}

pks = [int(a) for a in sys.argv[1:]] or []
for pk in pks:
    s = Submission.objects.filter(pk=pk).select_related("student", "document", "course").first()
    if not s:
        print(f"=== pk {pk}: NO EXISTE")
        continue
    print(f"=== pk {s.pk}")
    print(f"  curso      : {s.course_id} {s.course.code}  {s.course.title}")
    print(f"  actividad  : upload {s.document_id} [{CODES.get(s.document_id, '?')}] {s.document.title if s.document else '---'}")
    print(f"  alumno     : {s.student.username}  {s.student.get_full_name}")
    print(f"  fichero    : {s.file.name if s.file else None}")
    print(f"  NOTA       : {s.mark}   graded_at={s.graded_at}")
    print(f"  comentario : {(s.feedback[:200] + '...') if len(s.feedback) > 200 else (s.feedback or '(vacio)')}")
    if s.file:
        full = "/opt/skylearn/media/" + s.file.name
        try:
            print(f"  en disco   : {os.path.getsize(full)} bytes")
        except OSError as ex:
            print(f"  en disco   : NO EXISTE ({ex})")
    print()

# Ultimas entregas del modulo, para contexto
print("# ULTIMAS 12 ENTREGAS DE mf0488")
qs = (
    Submission.objects.filter(course__code__icontains="mf0488")
    .exclude(course_id=8)
    .select_related("student", "document", "course")
    .order_by("-pk")[:12]
)
for s in qs:
    print(f"  pk={s.pk}  {s.course.code}  {CODES.get(s.document_id, f'U{s.document_id}')}  {s.student.username}  nota={s.mark}  {s.file.name if s.file else None}")