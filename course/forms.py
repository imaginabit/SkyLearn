from django import forms
from accounts.models import User
from .models import (
    Course,
    CourseAllocation,
    EXTENSIONES_ENTREGA,
    EXTENSION_ENTREGA_POR_DEFECTO,
    Program,
    Submission,
    UnidadAprendizaje,
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


class UnidadAprendizajeForm(forms.ModelForm):
    """Alta y edicion de una unidad de aprendizaje del curso."""

    class Meta:
        model = UnidadAprendizaje
        fields = ("numero", "nombre", "fecha")
        widgets = {
            # El navegador solo entiende el formato ISO en un campo de fecha:
            # con el formato del idioma (13/11/2026) el campo se leeria vacio.
            "fecha": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs.update({"class": "form-control"})
        # Al enviar se acepta el ISO y tambien el formato espanol.
        self.fields["fecha"].input_formats = ["%Y-%m-%d", "%d/%m/%Y"]


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
            "visible",
            "es_principal",
            "extensiones_permitidas",
            "unidad",
        )

    def __init__(self, *args, **kwargs):
        curso = kwargs.pop("curso", None)
        super().__init__(*args, **kwargs)
        self.fields["title"].widget.attrs.update({"class": "form-control"})
        self.fields["file"].widget.attrs.update({"class": "form-control"})
        self.fields["is_activity"].widget.attrs.update({"class": "form-check-input"})
        self.fields["is_evaluable"].widget.attrs.update({"class": "form-check-input"})
        self.fields["visible"].widget.attrs.update({"class": "form-check-input"})
        self.fields["es_principal"].widget.attrs.update({"class": "form-check-input"})
        # La unidad de aprendizaje: vacia, la deduce el propio curso de la
        # fecha de subida. Solo se ofrecen las del curso en el que se sube.
        self.fields["unidad"].required = False
        self.fields["unidad"].empty_label = "Automatico: la unidad segun la fecha"
        if curso is not None:
            self.fields["unidad"].queryset = UnidadAprendizaje.objects.filter(
                course=curso
            )
        self.fields["unidad"].widget.attrs.update({"class": "form-select"})
        # El campo del modelo guarda "pdf,odt"; el formulario trabaja con una
        # lista, asi que el initial hay que darlo ya troceado.
        if self.instance.pk:
            self.initial[
                "extensiones_permitidas"
            ] = self.instance.get_extensiones_permitidas()

    def clean_es_principal(self):
        """Solo un mazo de diapositivas puede ser la presentacion principal.

        Con otro fichero marcado no pasa nada grave, pero el campo es para
        elegir que mazo se embebe arriba del curso: en un pdf no significa
        nada, asi que se le quita la marca y punto.
        """
        if not self.cleaned_data.get("es_principal"):
            return False
        fichero = self.cleaned_data.get("file") or self.instance.file
        if fichero and not fichero.name.lower().endswith(".html"):
            return False
        return True

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
        """Crea un `UploadFile` por cada fichero adicional marcado.

        Al reenviar el formulario de edicion, los que ya esten (por nombre)
        no se vuelven a crear: duplicarlos dejaba dos filas para el mismo
        fichero.
        """
        existentes = {a.nombre for a in upload.archivos.all()}
        for fichero in self.cleaned_data.get("archivos") or []:
            if fichero.name in existentes:
                continue
            UploadFile.objects.create(upload=upload, file=fichero)
            existentes.add(fichero.name)


# Upload video to specific course
class UploadFormVideo(forms.ModelForm):
    """Un vídeo del curso: un fichero subido o un enlace externo.

    Lo normal es el enlace: una clase de Class4crypt, un documental. El
    fichero se deja para el material propio.
    """

    class Meta:
        model = UploadVideo
        fields = (
            "title",
            "video",
            "url",
            "summary",
            "orden",
            "visible",
            "unidad",
        )

    def __init__(self, *args, **kwargs):
        curso = kwargs.pop("curso", None)
        super().__init__(*args, **kwargs)
        self.fields["title"].widget.attrs.update({"class": "form-control"})
        self.fields["video"].widget.attrs.update({"class": "form-control"})
        self.fields["url"].widget.attrs.update({"class": "form-control"})
        self.fields["summary"].widget.attrs.update({"class": "form-control", "rows": 3})
        self.fields["orden"].widget.attrs.update({"class": "form-control"})
        self.fields["visible"].widget.attrs.update({"class": "form-check-input"})
        # La unidad de aprendizaje: vacia, la deduce el propio curso de la
        # fecha. Solo se ofrecen las del curso en el que se sube.
        self.fields["unidad"].required = False
        self.fields["unidad"].empty_label = "Automatico: la unidad segun la fecha"
        if curso is not None:
            self.fields["unidad"].queryset = UnidadAprendizaje.objects.filter(
                course=curso
            )
        self.fields["unidad"].widget.attrs.update({"class": "form-select"})


class SubmissionForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ("document", "file")

    def __init__(self, *args, course=None, solo_visibles=False, alumno=None, **kwargs):
        super().__init__(*args, **kwargs)
        if course is not None:
            actividades = Upload.objects.filter(course=course, is_activity=True)
            # lo oculto es lo que el profesorado sube antes de tiempo: el alumnado
            # no puede ni entregarlo ni verlo en la lista
            if solo_visibles:
                actividades = actividades.filter(visible=True)
            # Una entrega ya calificada forma parte del expediente: no se puede
            # reemplazar, asi que su actividad sale del selector.
            if alumno is not None:
                calificadas = Submission.objects.filter(
                    course=course, student=alumno, mark__isnull=False
                ).values_list("document_id", flat=True)
                actividades = actividades.exclude(pk__in=calificadas)
            self.fields["document"].queryset = actividades.order_by("upload_time")
        # El alumno tiene que ver, al elegir la actividad, en que formato puede
        # entregarla: la etiqueta lleva los formatos admitidos.
        self.fields[
            "document"
        ].label_from_instance = (
            lambda actividad: f"{actividad.title} ({actividad.formatos_entrega()})"
        )
        self.fields["document"].widget.attrs.update({"class": "form-select"})
        self.fields["file"].widget.attrs.update({"class": "form-control"})

    def clean(self):
        """El fichero tiene que ser de uno de los formatos de esa actividad.

        Y tiene que parecer un trabajo hecho: un fichero de 0 KB es una
        version rota o sin guardar, y uno que pesa exactamente lo mismo que
        el enunciado es casi siempre el original subido sin hacer. En los dos
        casos se bloquea el envio y se explica, para que no se mande por
        equivocacion.
        """
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
            try:
                peso_enunciado = actividad.file.size
            except (OSError, ValueError, AttributeError):
                # el enunciado no esta en el disco: sin el peso no se compara
                peso_enunciado = None
            if fichero.size == 0:
                self.add_error(
                    "file",
                    "El fichero esta vacio (0 KB): parece una version rota o "
                    "sin guardar. No se ha enviado; elige el fichero bueno y "
                    "vuelve a enviar.",
                )
            elif peso_enunciado and fichero.size == peso_enunciado:
                self.add_error(
                    "file",
                    "El fichero pesa exactamente lo mismo que el enunciado de "
                    "la actividad: parece que has subido el original, no tu "
                    "trabajo. Revisalo y envia tu version.",
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
