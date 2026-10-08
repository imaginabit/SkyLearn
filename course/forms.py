from django import forms
from accounts.models import User
from .models import (
    Course,
    CourseAllocation,
    EXTENSIONES_ENTREGA,
    EXTENSION_ENTREGA_POR_DEFECTO,
    Program,
    Submission,
    Upload,
    UploadFile,
    UploadVideo,
    extension,
)


class VariosArchivosInput(forms.FileInput):
    """Input de fichero con `multiple`, cuyo valor es la lista de ficheros.

    `forms.FileField` no sabe limpiar una lista, así que el campo que lo usa es
    un `forms.Field` pelado y este widget devuelve directamente lo que hay en
    `request.FILES`.
    """

    allow_multiple_selected = True

    def value_from_datadict(self, data, files, name):
        return files.getlist(name) if files else []


class ProgramForm(forms.ModelForm):
    class Meta:
        model = Program
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].widget.attrs.update({"class": "form-control"})
        self.fields["summary"].widget.attrs.update({"class": "form-control"})


class CourseAddForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].widget.attrs.update({"class": "form-control"})
        self.fields["code"].widget.attrs.update({"class": "form-control"})
        # self.fields['courseUnit'].widget.attrs.update({'class': 'form-control'})
        self.fields["credit"].widget.attrs.update({"class": "form-control"})
        self.fields["summary"].widget.attrs.update({"class": "form-control"})
        self.fields["program"].widget.attrs.update({"class": "form-control"})
        self.fields["level"].widget.attrs.update({"class": "form-control"})
        self.fields["year"].widget.attrs.update({"class": "form-control"})
        self.fields["semester"].widget.attrs.update({"class": "form-control"})


class CourseAllocationForm(forms.ModelForm):
    courses = forms.ModelMultipleChoiceField(
        queryset=Course.objects.all().order_by("level"),
        widget=forms.CheckboxSelectMultiple(
            attrs={"class": "browser-default checkbox"}
        ),
        required=True,
    )
    lecturer = forms.ModelChoiceField(
        queryset=User.objects.filter(is_lecturer=True),
        widget=forms.Select(attrs={"class": "browser-default custom-select"}),
        label="lecturer",
    )

    class Meta:
        model = CourseAllocation
        fields = ["lecturer", "courses"]

    def __init__(self, *args, **kwargs):
        super(CourseAllocationForm, self).__init__(*args, **kwargs)
        self.fields["lecturer"].queryset = User.objects.filter(is_lecturer=True)


class EditCourseAllocationForm(forms.ModelForm):
    courses = forms.ModelMultipleChoiceField(
        queryset=Course.objects.all().order_by("level"),
        widget=forms.CheckboxSelectMultiple,
        required=True,
    )
    lecturer = forms.ModelChoiceField(
        queryset=User.objects.filter(is_lecturer=True),
        widget=forms.Select(attrs={"class": "browser-default custom-select"}),
        label="lecturer",
    )

    class Meta:
        model = CourseAllocation
        fields = ["lecturer", "courses"]

    def __init__(self, *args, **kwargs):
        #    user = kwargs.pop('user')
        super(EditCourseAllocationForm, self).__init__(*args, **kwargs)
        self.fields["lecturer"].queryset = User.objects.filter(is_lecturer=True)


# Upload files to specific course
class UploadFormFile(forms.ModelForm):
    archivos = forms.Field(
        required=False,
        label="Ficheros adicionales",
        widget=VariosArchivosInput(attrs={"multiple": True, "class": "form-control"}),
        help_text=(
            "Opcional. El mismo documento en otro formato (.docx y .odt), el "
            "enunciado aparte, un .zip con el material: el alumno puede "
            "descargar todos."
        ),
    )
    extensiones_permitidas = forms.MultipleChoiceField(
        required=False,
        label="Formatos que puede entregar el alumno",
        choices=[(e, e.upper()) for e in EXTENSIONES_ENTREGA],
        widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        help_text=(
            "Solo para actividades: los formatos que se aceptan en la entrega "
            "del alumno. Si no marcas ninguno, solo se admite PDF."
        ),
    )

    class Meta:
        model = Upload
        fields = (
            "title",
            "file",
            "is_activity",
            "is_evaluable",
            "extensiones_permitidas",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].widget.attrs.update({"class": "form-control"})
        self.fields["file"].widget.attrs.update({"class": "form-control"})
        self.fields["is_activity"].widget.attrs.update({"class": "form-check-input"})
        self.fields["is_evaluable"].widget.attrs.update({"class": "form-check-input"})
        # El campo del modelo guarda "pdf,odt"; el formulario trabaja con una
        # lista, asi que el initial hay que darlo ya troceado.
        if self.instance.pk:
            self.initial["extensiones_permitidas"] = (
                self.instance.get_extensiones_permitidas()
            )

    def clean_extensiones_permitidas(self):
        elegidas = self.cleaned_data["extensiones_permitidas"]
        if not elegidas:
            elegidas = [EXTENSION_ENTREGA_POR_DEFECTO]
        return ",".join(elegidas)

    def clean_archivos(self):
        """Que no repita los mismos nombres, que es lo que pasa si se sube dos
        veces el .odt de una actividad."""
        nombres = [f.name for f in self.cleaned_data.get("archivos") or []]
        repetidos = {n for n in nombres if nombres.count(n) > 1}
        if repetidos:
            raise forms.ValidationError(
                f"Mismo fichero marcado dos veces: {', '.join(sorted(repetidos))}"
            )
        return self.cleaned_data["archivos"]

    def guardar_archivos(self, upload):
        """Crea un `UploadFile` por cada fichero adicional marcado."""
        for fichero in self.cleaned_data.get("archivos") or []:
            UploadFile.objects.create(upload=upload, file=fichero)


# Upload video to specific course
class UploadFormVideo(forms.ModelForm):
    class Meta:
        model = UploadVideo
        fields = (
            "title",
            "video",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].widget.attrs.update({"class": "form-control"})
        self.fields["video"].widget.attrs.update({"class": "form-control"})


class SubmissionForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ("document", "file")

    def __init__(self, *args, course=None, **kwargs):
        super().__init__(*args, **kwargs)
        if course is not None:
            self.fields["document"].queryset = Upload.objects.filter(
                course=course, is_activity=True
            ).order_by("upload_time")
        # El alumno tiene que ver, al elegir la actividad, en que formato puede
        # entregarla: la etiqueta lleva los formatos admitidos.
        self.fields["document"].label_from_instance = (
            lambda actividad: f"{actividad.title} ({actividad.formatos_entrega()})"
        )
        self.fields["document"].widget.attrs.update({"class": "form-select"})
        self.fields["file"].widget.attrs.update({"class": "form-control"})

    def clean(self):
        """El fichero tiene que ser de uno de los formatos de esa actividad."""
        cleaned_data = super().clean()
        actividad = cleaned_data.get("document")
        fichero = cleaned_data.get("file")
        if actividad and fichero:
            if extension(fichero.name) not in actividad.get_extensiones_permitidas():
                self.add_error(
                    "file",
                    f"Esta actividad solo admite: {actividad.formatos_entrega()}.",
                )
        return cleaned_data


class SubmissionGradeForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ("mark", "feedback")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["mark"].widget.attrs.update(
            {"class": "form-control", "step": "0.01", "min": "0", "max": "10"}
        )
        self.fields["feedback"].widget.attrs.update(
            {"class": "form-control", "rows": 4}
        )
