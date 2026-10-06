from django import forms
from accounts.models import User
from .models import (
    Course,
    CourseAllocation,
    Program,
    Submission,
    Upload,
    UploadFile,
    UploadVideo,
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

    class Meta:
        model = Upload
        fields = (
            "title",
            "file",
            "is_activity",
            "is_evaluable",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].widget.attrs.update({"class": "form-control"})
        self.fields["file"].widget.attrs.update({"class": "form-control"})
        self.fields["is_activity"].widget.attrs.update({"class": "form-check-input"})
        self.fields["is_evaluable"].widget.attrs.update({"class": "form-check-input"})

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
        self.fields["document"].widget.attrs.update({"class": "form-select"})
        self.fields["file"].widget.attrs.update({"class": "form-control"})


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
