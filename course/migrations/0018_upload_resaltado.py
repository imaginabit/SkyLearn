from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("course", "0017_alter_uploadvideo_options_uploadvideo_orden_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="upload",
            name="resaltado",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Marca el documento para que el alumnado lo vea destacado en la "
                    "tabla. Solo uno puede estar resaltado a la vez."
                ),
                verbose_name="Resaltado",
            ),
        ),
        migrations.AddField(
            model_name="upload",
            name="resaltado_hasta",
            field=models.DateTimeField(
                blank=True,
                help_text=(
                    "El resalte caduca solo a las 24 horas, o antes si se resalta "
                    "otro documento."
                ),
                null=True,
                verbose_name="Resaltado hasta",
            ),
        ),
    ]
