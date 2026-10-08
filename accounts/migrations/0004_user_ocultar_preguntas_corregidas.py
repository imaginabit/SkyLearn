from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_consentrecord"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="ocultar_preguntas_corregidas",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Solo para docentes: al corregir un examen no mostrar las "
                    "preguntas cuya respuesta ya esta bien, y dejar solo las que "
                    "hay que revisar."
                ),
                verbose_name="Ocultar las preguntas ya corregidas",
            ),
        ),
    ]
