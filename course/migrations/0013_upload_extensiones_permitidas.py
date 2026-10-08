from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("course", "0012_uploadfile"),
    ]

    operations = [
        migrations.AddField(
            model_name="upload",
            name="extensiones_permitidas",
            field=models.CharField(
                default="pdf",
                help_text=(
                    "Solo para actividades: extensiones separadas por comas. "
                    "Por defecto, solo pdf."
                ),
                max_length=100,
                verbose_name="Formatos que puede entregar el alumno",
            ),
        ),
    ]
