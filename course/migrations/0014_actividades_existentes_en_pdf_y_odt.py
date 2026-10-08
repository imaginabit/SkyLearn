from django.db import migrations

# Antes de poder elegir formatos, toda actividad admitia pdf, docx, odt, zip...
# Al poner el defecto en pdf, las actividades que ya existian se quedaron solo
# en pdf. Estas son las que habia antes del cambio: se les devuelve el pdf y el
# odt, que es lo que venian pidiendo.
ACTIVIDADES_EXISTENTES = "pdf,odt"


def pdf_y_odt(apps, schema_editor):
    Upload = apps.get_model("course", "Upload")
    Upload.objects.filter(is_activity=True).update(
        extensiones_permitidas=ACTIVIDADES_EXISTENTES
    )


class Migration(migrations.Migration):

    dependencies = [
        ("course", "0013_upload_extensiones_permitidas"),
    ]

    operations = [
        migrations.RunPython(pdf_y_odt, migrations.RunPython.noop),
    ]
