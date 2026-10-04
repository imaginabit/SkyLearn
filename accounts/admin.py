from django.contrib import admin
from .models import User, Student, Parent, ConsentRecord


class UserAdmin(admin.ModelAdmin):
    list_display = [
        "get_full_name",
        "username",
        "email",
        "is_active",
        "is_student",
        "is_lecturer",
        "is_parent",
        "is_staff",
    ]
    search_fields = [
        "username",
        "first_name",
        "last_name",
        "email",
        "is_active",
        "is_lecturer",
        "is_parent",
        "is_staff",
    ]

    class Meta:
        managed = True
        verbose_name = "User"
        verbose_name_plural = "Users"


class ConsentRecordAdmin(admin.ModelAdmin):
    """La prueba del consentimiento se consulta, no se edita.

    Es la evidencia de que el tratamiento se aceptó: si se pudiera tocar, no
    valdría como prueba.
    """

    list_display = ["user", "version", "accepted_at", "ip", "recorded_by"]
    list_filter = ["version"]
    search_fields = ["user__username", "user__first_name", "user__last_name", "ip"]
    date_hierarchy = "accepted_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(User, UserAdmin)
admin.site.register(Student)
admin.site.register(Parent)
admin.site.register(ConsentRecord, ConsentRecordAdmin)
