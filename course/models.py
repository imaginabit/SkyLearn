from decimal import Decimal

from django.conf import settings
from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models
from django.db.models import Q
from django.db.models.signals import pre_delete, pre_save, post_delete, post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from core.models import ActivityLog, Semester
from core.utils import unique_slug_generator


# Las extensiones que se admiten, para el fichero principal de una actividad y
# para los adicionales. De aquí sale tambien el icono del fichero.
EXTENSIONES = [
    "pdf",
    "docx",
    "doc",
    "odt",
    "html",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "zip",
    "rar",
    "7zip",
]

ICONOS = {
    "doc": "word",
    "docx": "word",
    "odt": "lines",
    "pdf": "pdf",
    "xls": "excel",
    "xlsx": "excel",
    "ppt": "powerpoint",
    "pptx": "powerpoint",
    "zip": "archive",
    "rar": "archive",
    "7zip": "archive",
}

# Que programa abre cada formato. El .odt es de LibreOffice, no de Word, y se
# avisa en el `title` del icono para que no parezca el formato pobre.
PROGRAMAS = {
    "doc": "Microsoft Word",
    "docx": "Microsoft Word",
    "odt": "LibreOffice Writer",
    "pdf": "PDF",
    "xls": "Microsoft Excel",
    "xlsx": "Microsoft Excel",
    "ppt": "Microsoft PowerPoint",
    "pptx": "Microsoft PowerPoint",
    "zip": "ZIP",
    "rar": "RAR",
    "7zip": "7-Zip",
}

# Formatos que el alumno puede entregar en una actividad (`Submission.file`).
EXTENSIONES_ENTREGA = [
    "pdf",
    "docx",
    "doc",
    "odt",
    "zip",
    "rar",
    "7zip",
    "png",
    "jpg",
    "jpeg",
]

# Por defecto una actividad solo admite PDF.
EXTENSION_ENTREGA_POR_DEFECTO = "pdf"


def extension_short(nombre):
    """El nombre del icono de Font Awesome para un fichero, por su extensión."""
    return ICONOS.get(nombre.rsplit(".", 1)[-1].lower(), "file")


def programa(nombre):
    """El programa que abre el fichero, por su extensión ('' si no se sabe)."""
    return PROGRAMAS.get(nombre.rsplit(".", 1)[-1].lower(), "")


def extension(nombre):
    """La extensión del fichero, en minúsculas y sin el punto."""
    return nombre.rsplit(".", 1)[-1].lower()


class ProgramManager(models.Manager):
    def search(self, query=None):
        queryset = self.get_queryset()
        if query:
            or_lookup = Q(title__icontains=query) | Q(summary__icontains=query)
            queryset = queryset.filter(or_lookup).distinct()
        return queryset


class Program(models.Model):
    title = models.CharField(max_length=150, unique=True)
    summary = models.TextField(blank=True)

    objects = ProgramManager()

    def __str__(self):
        return f"{self.title}"

    def get_absolute_url(self):
        return reverse("program_detail", kwargs={"pk": self.pk})


@receiver(post_save, sender=Program)
def log_program_save(sender, instance, created, **kwargs):
    verb = "created" if created else "updated"
    ActivityLog.objects.create(message=_(f"The program '{instance}' has been {verb}."))


@receiver(post_delete, sender=Program)
def log_program_delete(sender, instance, **kwargs):
    ActivityLog.objects.create(message=_(f"The program '{instance}' has been deleted."))


class CourseManager(models.Manager):
    def search(self, query=None):
        queryset = self.get_queryset()
        if query:
            or_lookup = (
                Q(title__icontains=query)
                | Q(summary__icontains=query)
                | Q(code__icontains=query)
                | Q(slug__icontains=query)
            )
            queryset = queryset.filter(or_lookup).distinct()
        return queryset


class Course(models.Model):
    slug = models.SlugField(unique=True, blank=True)
    title = models.CharField(max_length=200)
    code = models.CharField(max_length=200, unique=True)
    credit = models.IntegerField(default=0)
    summary = models.TextField(max_length=200, blank=True)
    program = models.ForeignKey(Program, on_delete=models.CASCADE)
    level = models.CharField(max_length=25, choices=settings.LEVEL_CHOICES)
    year = models.IntegerField(choices=settings.YEARS, default=1)
    semester = models.CharField(choices=settings.SEMESTER_CHOICES, max_length=200)
    is_elective = models.BooleanField(default=False)

    objects = CourseManager()

    def __str__(self):
        return f"{self.title} ({self.code})"

    def get_absolute_url(self):
        return reverse("course_detail", kwargs={"slug": self.slug})

    @property
    def is_current_semester(self):

        current_semester = Semester.objects.filter(is_current_semester=True).first()
        return self.semester == current_semester.semester if current_semester else False


@receiver(pre_save, sender=Course)
def course_pre_save_receiver(sender, instance, **kwargs):
    if not instance.slug:
        instance.slug = unique_slug_generator(instance)


@receiver(post_save, sender=Course)
def log_course_save(sender, instance, created, **kwargs):
    verb = "created" if created else "updated"
    ActivityLog.objects.create(message=_(f"The course '{instance}' has been {verb}."))


@receiver(post_delete, sender=Course)
def log_course_delete(sender, instance, **kwargs):
    ActivityLog.objects.create(message=_(f"The course '{instance}' has been deleted."))


class CourseAllocation(models.Model):
    lecturer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="allocated_lecturer",
    )
    courses = models.ManyToManyField(Course, related_name="allocated_course")
    session = models.ForeignKey(
        "core.Session", on_delete=models.CASCADE, blank=True, null=True
    )

    def __str__(self):
        return self.lecturer.get_full_name

    def get_absolute_url(self):
        return reverse("edit_allocated_course", kwargs={"pk": self.pk})


class Upload(models.Model):
    title = models.CharField(max_length=100)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    file = models.FileField(
        upload_to="course_files/",
        help_text=_(
            "Valid Files: pdf, docx, doc, odt, html, xls, xlsx, ppt, pptx, zip, rar, 7zip"
        ),
        validators=[FileExtensionValidator(EXTENSIONES)],
    )
    updated_date = models.DateTimeField(auto_now=True)
    upload_time = models.DateTimeField(auto_now_add=True)
    is_activity = models.BooleanField(
        default=False,
        verbose_name=_("Actividad"),
        help_text=_("El alumno puede entregar su ejercicio de esta actividad."),
    )
    is_evaluable = models.BooleanField(
        default=False,
        verbose_name=_("Actividad evaluable"),
        help_text=_("Solo las actividades evaluables cuentan para la nota final."),
    )
    extensiones_permitidas = models.CharField(
        max_length=100,
        default=EXTENSION_ENTREGA_POR_DEFECTO,
        verbose_name=_("Formatos que puede entregar el alumno"),
        help_text=_(
            "Solo para actividades: extensiones separadas por comas. "
            "Por defecto, solo pdf."
        ),
    )

    def __str__(self):
        return f"{self.title}"

    def get_extension_short(self):
        return extension_short(self.file.name)

    def get_program_name(self):
        return programa(self.file.name)

    def get_extensiones_permitidas(self):
        """Los formatos que se aceptan en la entrega de esta actividad.

        Se guardan separados por comas; si el campo quedara vacio, se admite
        solo PDF, que es el comportamiento por defecto.
        """
        elegidas = [
            e.strip().lower().lstrip(".")
            for e in self.extensiones_permitidas.split(",")
            if e.strip()
        ]
        return elegidas or [EXTENSION_ENTREGA_POR_DEFECTO]

    def formatos_entrega(self):
        """Los formatos admitidos, separados por comas, para la pantalla."""
        return ", ".join(e.upper() for e in self.get_extensiones_permitidas())


class UploadFile(models.Model):
    """Un fichero más de una actividad, que el alumno también puede bajar.

    El principal sigue siendo `Upload.file`; estos son los adicionales: el
    mismo documento en otro formato, el enunciado aparte, las capturas.
    """

    upload = models.ForeignKey(
        Upload, on_delete=models.CASCADE, related_name="archivos"
    )
    file = models.FileField(
        upload_to="course_files/",
        help_text=_(
            "Valid Files: pdf, docx, doc, odt, html, xls, xlsx, ppt, pptx, zip, rar, 7zip"
        ),
        validators=[FileExtensionValidator(EXTENSIONES)],
    )

    class Meta:
        verbose_name = _("Fichero adicional")
        verbose_name_plural = _("Ficheros adicionales")

    def __str__(self):
        return f"{self.upload.title}: {self.file.name}"

    @property
    def nombre(self):
        """El nombre tal cual se sube, sin la carpeta de `MEDIA_ROOT`.

        `file.name` lleva delante `course_files/` porque Django lo guarda ahí;
        al alumno le interesa el nombre del fichero, no dónde se guarda.
        """
        return self.file.name.rsplit("/", 1)[-1]

    def get_extension_short(self):
        return extension_short(self.file.name)

    def get_program_name(self):
        return programa(self.file.name)


@receiver(post_save, sender=Upload)
def log_upload_save(sender, instance, created, **kwargs):
    if created:
        message = _(
            f"The file '{instance.title}' has been uploaded to the course '{instance.course}'."
        )
    else:
        message = _(
            f"The file '{instance.title}' of the course '{instance.course}' has been updated."
        )
    ActivityLog.objects.create(message=message)


@receiver(pre_delete, sender=Upload)
@receiver(pre_delete, sender=UploadFile)
def borra_el_fichero_del_disco(sender, instance, **kwargs):
    """Se borra el fichero de verdad, y no solo su fila.

    Con el `delete()` reescrito en `Upload` el borrado en cascada (al borrar un
    curso entero, o al borrar una actividad con sus archivos adicionales) se
    llevaba por delante la fila y dejaba el fichero en el disco. Por eso la
    limpieza va en `pre_delete` y no en un método: así salta por cualquier vía.
    """
    if instance.file:
        instance.file.delete(save=False)


@receiver(post_delete, sender=Upload)
def log_upload_delete(sender, instance, **kwargs):
    ActivityLog.objects.create(
        message=_(
            f"The file '{instance.title}' of the course '{instance.course}' has been deleted."
        )
    )


class UploadVideo(models.Model):
    title = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    video = models.FileField(
        upload_to="course_videos/",
        help_text=_("Valid video formats: mp4, mkv, wmv, 3gp, f4v, avi, mp3"),
        validators=[
            FileExtensionValidator(["mp4", "mkv", "wmv", "3gp", "f4v", "avi", "mp3"])
        ],
    )
    summary = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title}"

    def get_absolute_url(self):
        return reverse(
            "video_single", kwargs={"slug": self.course.slug, "video_slug": self.slug}
        )

    def delete(self, *args, **kwargs):
        self.video.delete(save=False)
        super().delete(*args, **kwargs)


@receiver(pre_save, sender=UploadVideo)
def video_pre_save_receiver(sender, instance, **kwargs):
    if not instance.slug:
        instance.slug = unique_slug_generator(instance)


@receiver(post_save, sender=UploadVideo)
def log_uploadvideo_save(sender, instance, created, **kwargs):
    if created:
        message = _(
            f"The video '{instance.title}' has been uploaded to the course '{instance.course}'."
        )
    else:
        message = _(
            f"The video '{instance.title}' of the course '{instance.course}' has been updated."
        )
    ActivityLog.objects.create(message=message)


@receiver(post_delete, sender=UploadVideo)
def log_uploadvideo_delete(sender, instance, **kwargs):
    ActivityLog.objects.create(
        message=_(
            f"The video '{instance.title}' of the course '{instance.course}' has been deleted."
        )
    )


class CourseOffer(models.Model):
    """NOTE: Only department head can offer semester courses"""

    dep_head = models.ForeignKey("accounts.DepartmentHead", on_delete=models.CASCADE)

    def __str__(self):
        return str(self.dep_head)


class Submission(models.Model):
    """Entrega de un alumno para una actividad: un fichero, reemplazable."""

    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="submissions"
    )
    document = models.ForeignKey(
        Upload,
        on_delete=models.SET_NULL,
        related_name="submissions",
        null=True,
        blank=False,
        verbose_name=_("Actividad"),
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="submissions",
    )
    file = models.FileField(
        upload_to="submissions/",
        help_text=_("Valid Files: pdf, docx, doc, odt, zip, rar, 7zip, png, jpg"),
        validators=[FileExtensionValidator(EXTENSIONES_ENTREGA)],
    )
    uploaded_at = models.DateTimeField(auto_now=True)
    mark = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Nota"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("10"))],
    )
    feedback = models.TextField(blank=True, verbose_name=_("Comentarios"))
    graded_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["course", "student", "document"],
                name="one_submission_per_student_and_document",
            )
        ]

    @property
    def filename(self):
        return self.file.name.rsplit("/", 1)[-1]

    def __str__(self):
        return f"{self.student} - {self.document}"
