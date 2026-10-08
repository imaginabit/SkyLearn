from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_user_ocultar_preguntas_corregidas"),
    ]

    operations = [
        migrations.RenameField(
            model_name="user",
            old_name="ocultar_preguntas_corregidas",
            new_name="ocultar_entregas_corregidas",
        ),
        migrations.AlterField(
            model_name="user",
            name="ocultar_entregas_corregidas",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Solo para docentes: en la tabla de entregas del curso, no "
                    "mostrar las ya corregidas de las actividades NO evaluables, "
                    "y dejar solo las pendientes. Las actividades evaluables se "
                    "ven siempre."
                ),
                verbose_name="Ocultar las entregas ya corregidas",
            ),
        ),
    ]
