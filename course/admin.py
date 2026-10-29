from django.contrib import admin
from django.contrib.auth.models import Group

from .models import (
    Course,
    CourseAllocation,
    Program,
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
    inlines = [UploadFileInline]


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


admin.site.register(Program, ProgramAdmin)
admin.site.register(Course, CourseAdmin)
admin.site.register(CourseAllocation)
admin.site.register(Upload, UploadAdmin)
admin.site.register(UploadVideo, UploadVideoAdmin)
