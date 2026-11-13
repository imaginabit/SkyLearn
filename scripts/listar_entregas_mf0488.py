"""Lista todas las entregas de actividades de mf0488 (cursos 9-13).

Salida TSV: pk curso upload_id alumno username nombre actividad_code nombre_fichero_submission tamaño
"""
import os, sys, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, "/opt/skylearn")
django.setup()

from django.db.models import Q
from course.models import Course, Upload, Submission

# Códigos de actividad (mismo criterio que seguimiento-actividades-MF0488_3.md)
CODES = {
    61: "A1-datos",
    62: "A1-IDS",
    64: "A2-ubicacion",
    67: "A2-tecnicas",
    69: "A3-senuelo",
    74: "A4-recoleccion",
    75: "A4-indicios",
    76: "A4-ficha",
    80: "A5-correlacion",
    81: "A5-informe",
    82: "A5-cuestionario",
    83: "A5-UA2",
}

sesiones = (
    Course.objects.filter(code__icontains="mf0488")
    .exclude(id=8)
    .order_by("id")
)
print(f"# ENTREGAS DE MF0488", flush=True)
total = 0
for cur in sesiones:
    ups_ids = list(Upload.objects.filter(course=cur, is_activity=True).values_list("id", flat=True))
    subs = (
        Submission.objects.filter(course=cur, document_id__in=ups_ids)
        .select_related("student", "document")
        .order_by("document_id", "student__username")
    )
    n = subs.count()
    if not n:
        continue
    print(f"\n## {cur.code}  ({cur.title})  ({n} entregas)")
    print("pk\tupload\tcode\talumno\tusername\tnombre\tfichero\ttamaño")
    for s in subs:
        path = s.file.name if s.file else None
        size = s.file.size if s.file and hasattr(s.file, "size") else 0
        try:
            sz = os.path.getsize("/opt/skylearn/media/" + path) if path else 0
        except OSError:
            sz = -1
        nombre = (s.student.get_full_name or s.student.username).replace("\t", " ")
        code = CODES.get(s.document_id, f"?{s.document_id}")
        print(f"{s.pk}\t{s.document_id}\t{code}\t{nombre}\t{s.student.username}\t{s.student.username}\t{os.path.basename(path) if path else None}\t{sz}")
        total += 1
print(f"\n# TOTAL: {total} entregas", flush=True)
