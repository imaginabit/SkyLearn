# Partidas en vivo (al estilo Kahoot): sesión, participantes y respuestas.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("course", "0014_actividades_existentes_en_pdf_y_odt"),
        ("quiz", "0004_alter_essayquestion_options_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="LiveSession",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("code", models.CharField(blank=True, max_length=8, unique=True)),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("lobby", "Sala de espera"),
                            ("question", "Pregunta en curso"),
                            ("reveal", "Respuesta y recuento"),
                            ("ranking", "Clasificación"),
                            ("ended", "Terminada"),
                        ],
                        default="lobby",
                        max_length=10,
                    ),
                ),
                (
                    "question_ids",
                    models.CharField(blank=True, default="", max_length=4000),
                ),
                ("current_index", models.PositiveIntegerField(default=0)),
                ("time_limit", models.PositiveIntegerField(default=20)),
                ("question_started", models.DateTimeField(blank=True, null=True)),
                ("created", models.DateTimeField(auto_now_add=True)),
                (
                    "course",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="course.course",
                    ),
                ),
                (
                    "host",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "quiz",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="quiz.quiz"
                    ),
                ),
            ],
            options={
                "verbose_name": "Partida en vivo",
                "verbose_name_plural": "Partidas en vivo",
                "ordering": ("-created",),
            },
        ),
        migrations.CreateModel(
            name="LiveParticipant",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("nickname", models.CharField(max_length=40)),
                ("score", models.IntegerField(default=0)),
                ("joined", models.DateTimeField(auto_now_add=True)),
                ("last_seen", models.DateTimeField(auto_now=True)),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="participants",
                        to="quiz.livesession",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Participante",
                "verbose_name_plural": "Participantes",
                "unique_together": {("session", "user")},
            },
        ),
        migrations.CreateModel(
            name="LiveAnswer",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("correct", models.BooleanField(default=False)),
                ("seconds", models.FloatField(default=0)),
                ("points", models.IntegerField(default=0)),
                ("answered", models.DateTimeField(auto_now_add=True)),
                (
                    "choice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="quiz.choice"
                    ),
                ),
                (
                    "participant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="answers",
                        to="quiz.liveparticipant",
                    ),
                ),
                (
                    "question",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="quiz.mcquestion",
                    ),
                ),
            ],
            options={
                "verbose_name": "Respuesta en vivo",
                "verbose_name_plural": "Respuestas en vivo",
                "unique_together": {("participant", "question")},
            },
        ),
    ]
