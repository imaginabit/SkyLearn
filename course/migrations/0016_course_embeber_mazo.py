from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("course", "0015_upload_visible"),
    ]

    operations = [
        migrations.AddField(
            model_name="course",
            name="embeber_mazo",
            field=models.BooleanField(
                default=True,
                help_text="Si esta desmarcado, el curso no muestra ningun mazo embebido arriba: los mazos se abren y se descargan desde la tabla de documentos. Para los cursos que acumulan el material de varias clases, donde embeber solo uno deja a los demas escondidos.",
                verbose_name="Embeber la presentacion",
            ),
        ),
    ]
