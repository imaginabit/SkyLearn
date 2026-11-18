from django.contrib import admin
from django.contrib.auth.models import Group

from .models import (
    Course,
    CourseAllocation,
    Program,
    UnidadAprendizaje,
    Upload,
    UploadFile,
    UploadVideo,
)
from modeltranslation.admin import TranslationAdmin


class ProgramAdmin(TranslationAdmin):
    pass


class CourseAdmin(TranslationAdmin):
    pass


class UploadFileInline(admin.TabularInline):
    """Los ficheros adicionales se editan en la propia actividad."""

    model = UploadFile
    extra = 1


class UploadAdmin(TranslationAdmin):
    """Las actividades y el material del curso.

    La casilla de `es_principal` (y su accion) solo significa algo en los
    mazos de diapositivas: el docente la marca desde la pestana
    Presentaciones del curso, aqui queda para desmarcar a mano.
    """

    inlines = [UploadFileInline]
    list_display = ("title", "course", "es_principal", "visible", "upload_time")
    list_editable = ("es_principal", "visible")
    list_filter = ("visible", "course")
    search_fields = ("title",)
    actions = ("quitar_principal",)

    @admin.action(description="Desmarcar como presentacion principal")
    def quitar_principal(self, request, queryset):
        queryset.update(es_principal=False)


class UploadVideoAdmin(admin.ModelAdmin):
    """Los vídeos del curso: se singly y se revelan desde aquí.

    Nacen ocultos. La casilla de `visible` se puede marcar en la propia lista
    o con las acciones de abajo, para revelar el vídeo del día sin entrar en
    cada ficha.
    """

    list_display = ("title", "course", "visible", "orden", "timestamp")
    list_editable = ("visible", "orden")
    list_filter = ("visible", "course")
    search_fields = ("title", "url", "summary")
    ordering = ("course", "orden", "timestamp")
    actions = ("mostrar_al_alumnado", "ocultar_al_alumnado")

    @admin.action(description="Mostrar los vídeos seleccionados al alumnado")
    def mostrar_al_alumnado(self, request, queryset):
        queryset.update(visible=True)

    @admin.action(description="Ocultar los vídeos seleccionados al alumnado")
    def ocultar_al_alumnado(self, request, queryset):
        queryset.update(visible=False)


class UnidadAprendizajeAdmin(admin.ModelAdmin):
    """Las unidades de aprendizaje: en que se reparte el material del curso."""

    list_display = ("course", "numero", "nombre", "fecha")
    list_filter = ("course",)
    search_fields = ("nombre",)
    ordering = ("course", "numero")


admin.site.register(Program, ProgramAdmin)
admin.site.register(Course, CourseAdmin)
admin.site.register(CourseAllocation)
admin.site.register(UnidadAprendizaje, UnidadAprendizajeAdmin)
admin.site.register(Upload, UploadAdmin)
admin.site.register(UploadVideo, UploadVideoAdmin)
