"""Prepara la lista de rutas a descargar y los metadatos para presentar al usuario."""
import os, sys, django, json
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, "/opt/skylearn")
django.setup()

from course.models import Course, Upload

# IDs de actividades sin entregas (calculados aparte, validados en el listado previo)
PENDIENTES = [64, 67, 74, 75, 80, 81, 82, 83]

sesiones = Course.objects.filter(code__icontains="mf0488").exclude(id=8).order_by("id")
print("# Rutas a descargar (vía scp desde /opt/skylearn/media):\n")
for cur in sesiones:
    ups = Upload.objects.filter(course=cur, id__in=PENDIENTES).order_by("id")
    if not ups.exists():
        continue
    print(f"## {cur.code}  ({cur.title})")
    for u in ups:
        main = u.file.name if u.file else None
        print(f"  Upload {u.id}  {u.title}")
        print(f"    main: /opt/skylearn/media/{main}")
        extras = list(u.archivos.values_list("file", flat=True))
        for e in extras:
            print(f"    extra: /opt/skylearn/media/{e}")
    print()
