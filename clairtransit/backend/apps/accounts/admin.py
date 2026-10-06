from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("email",)
    list_display = ("email", "full_name", "is_active", "is_staff", "is_reference_manager")
    search_fields = ("email", "full_name")
    fieldsets = (
        (None, {"fields": ("email", "password", "full_name")}),
        ("Droits", {"fields": ("is_active", "is_staff", "is_superuser", "is_reference_manager")}),
        ("Dates", {"fields": ("last_login", "deactivated_at")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),)
    filter_horizontal = ()
    list_filter = ("is_active", "is_staff", "is_reference_manager")
