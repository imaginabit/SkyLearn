#!/usr/bin/env bash
set -e
for f in \
  /opt/skylearn/media/course_files/Actividad-ubicacion-del-ids_ibALy0m.pdf \
  /opt/skylearn/media/course_files/Actividad-ubicacion-del-ids.odt \
  /opt/skylearn/media/course_files/Actividad-tecnicas-de-deteccion_x1kN1zD.pdf \
  /opt/skylearn/media/course_files/Actividad-tecnicas-de-deteccion.odt \
  /opt/skylearn/media/course_files/Actividad-recoleccion-de-informacion.pdf \
  /opt/skylearn/media/course_files/Actividad-recoleccion-de-informacion.odt \
  /opt/skylearn/media/course_files/Actividad-indicios-de-intrusion.pdf \
  /opt/skylearn/media/course_files/Actividad-indicios-de-intrusion.odt \
  /opt/skylearn/media/course_files/Actividad-correlacion-de-alertas.pdf \
  /opt/skylearn/media/course_files/Actividad-correlacion-de-alertas.odt \
  /opt/skylearn/media/course_files/Actividad-informe-de-incidente.pdf \
  /opt/skylearn/media/course_files/Actividad-informe-de-incidente.odt \
  /opt/skylearn/media/course_files/Actividad-cuestionario-respuesta-incidentes.pdf \
  /opt/skylearn/media/course_files/Actividad-repaso-UA2.pdf \
  /opt/skylearn/media/course_files/Actividad-repaso-UA2.odt
do
  if [ -f "$f" ]; then
    printf '%-95s %8d bytes\n' "$(basename "$f")" "$(stat -c %s "$f")"
  else
    echo "MISSING: $f"
  fi
done
