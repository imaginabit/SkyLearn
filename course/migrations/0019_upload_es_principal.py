from django.db import migrations, models


def marcar_principal(apps, schema_editor):
    """Deja como principal el mazo que ya se embebia en cada curso.

    Antes de este campo, el curso embebia el primer mazo (el de menor pk) y
    nada mas. Para que las pestanas sigan mostrando lo de siempre, se marca
    ese mismo mazo como principal de los cursos que tenian `embeber_mazo`.
    """
    Upload = apps.get_model("course", "Upload")
    Course = apps.get_model("course", "Course")
    for curso in Course.objects.filter(embeber_mazo=True):
        mazo = (
            Upload.objects.filter(course=curso, file__iendswith=".html")
            .order_by("pk")
            .first()
        )
        if mazo is not None:
            Upload.objects.filter(pk=mazo.pk).update(es_principal=True)


def quitar_principal(apps, schema_editor):
    """Al tirar atras, ninguna presentacion queda como principal."""
    Upload = apps.get_model("course", "Upload")
    Upload.objects.filter(es_principal=True).update(es_principal=False)


class Migration(migrations.Migration):

    dependencies = [
        ("course", "0018_upload_resaltado"),
    ]

    operations = [
        migrations.AddField(
            model_name="upload",
            name="es_principal",
            field=models.BooleanField(
                default=False,
                help_text="Solo para los mazos de diapositivas (.html): el que se muestra embebido arriba del curso, encima de las pestanas. Uno solo por curso; al marcarlo se desmarcan los demas.",
                verbose_name="Presentacion principal",
            ),
        ),
        migrations.AlterField(
            model_name="course",
            name="embeber_mazo",
            field=models.BooleanField(
                default=True,
                help_text="Si esta desmarcado, el curso no muestra ningun mazo embebido arriba: los mazos se abren y se descargan desde la pestana Presentaciones. Para los cursos que acumulan el material de varias clases, donde embeber solo uno deja a los demas escondidos.",
                verbose_name="Embeber la presentacion",
            ),
        ),
        migrations.RunPython(marcar_principal, quitar_principal),
    ]
