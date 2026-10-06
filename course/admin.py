from django.contrib import admin
from django.contrib.auth.models import Group

from .models import Program, Course, CourseAllocation, Upload, UploadFile
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


admin.site.register(Program, ProgramAdmin)
admin.site.register(Course, CourseAdmin)
admin.site.register(CourseAllocation)
admin.site.register(Upload, UploadAdmin)
