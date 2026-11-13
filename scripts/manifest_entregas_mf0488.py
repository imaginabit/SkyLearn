"""Genera un manifiesto con la info de cada Submission de mf0488.

Salida: NDJSON por línea con
  { pk, course, course_code, upload_id, code, username, full_name,
    remote_path, original_filename, size }
"""
import os, sys, json, django
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

sesiones = Course.objects.filter(code__icontains="mf0488").exclude(id=8).order_by("id")
for cur in sesiones:
    ups_ids = list(Upload.objects.filter(course=cur, is_activity=True).values_list("id", flat=True))
    subs = (
        Submission.objects.filter(course=cur, document_id__in=ups_ids)
        .select_related("student", "document")
        .order_by("document_id", "student__username")
    )
    for s in subs:
        if not s.file:
            continue
        path = s.file.name
        full = "/opt/skylearn/media/" + path
        try:
            sz = os.path.getsize(full)
        except OSError:
            sz = 0
        rec = {
            "pk": s.pk,
            "course_id": cur.id,
            "course_code": cur.code,
            "course_title": cur.title,
            "upload_id": s.document_id,
            "code": CODES.get(s.document_id, f"U{s.document_id}"),
            "username": s.student.username,
            "full_name": s.student.get_full_name or s.student.username,
            "remote_path": full,
            "original_filename": os.path.basename(path),
            "size": sz,
        }
        print(json.dumps(rec, ensure_ascii=False))
