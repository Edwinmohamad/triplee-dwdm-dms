from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    ActivityLog,
    BackupRecord,
    Document,
    DocumentAttachment,
    DocumentComment,
    DocumentVersion,
    InstallationBatch,
    Notification,
    Project,
    Review,
    Site,
    User,
)


@admin.register(User)
class DMSUserAdmin(UserAdmin):
    model = User
    ordering = ("username",)
    list_display = ("username", "full_name", "role", "is_active")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Profile", {"fields": ("full_name", "role", "must_change_password")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("username", "full_name", "role", "password1", "password2")}),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Notification)
admin.site.register(BackupRecord)


class NoDeleteAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Project, NoDeleteAdmin)
admin.site.register(Site, NoDeleteAdmin)
admin.site.register(InstallationBatch, NoDeleteAdmin)
admin.site.register(Document, NoDeleteAdmin)


class ImmutableAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method in {"GET", "HEAD", "OPTIONS"}

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]


@admin.register(DocumentVersion)
class DocumentVersionAdmin(ImmutableAdmin):
    list_display = ("document", "revision_no", "uploaded_by", "uploaded_at", "is_locked")


@admin.register(DocumentAttachment)
class DocumentAttachmentAdmin(ImmutableAdmin):
    list_display = ("version", "sequence_no", "original_filename", "file_size", "created_at")


@admin.register(Review)
class ReviewAdmin(ImmutableAdmin):
    list_display = ("document", "version", "reviewer", "decision", "created_at")


@admin.register(DocumentComment)
class DocumentCommentAdmin(ImmutableAdmin):
    list_display = ("document", "version", "author", "created_at")


@admin.register(ActivityLog)
class ActivityLogAdmin(ImmutableAdmin):
    list_display = ("created_at", "actor", "action", "description", "ip_address")
    ordering = ("-created_at",)
