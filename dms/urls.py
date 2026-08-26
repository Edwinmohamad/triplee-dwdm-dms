from django.urls import path

from . import views


urlpatterns = [
    path("health/", views.health, name="health"),
    path("setup/", views.setup_view, name="setup"),
    path("login/", views.DMSLoginView.as_view(), name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("change-password/", views.change_password, name="change_password"),
    path("", views.dashboard, name="dashboard"),
    path("sites/", views.site_list, name="site_list"),
    path("sites/<int:pk>/", views.site_detail, name="site_detail"),
    path("batches/<int:pk>/", views.batch_detail, name="batch_detail"),
    path("batches/<int:pk>/edit/", views.batch_update, name="batch_update"),
    path("documents/<int:pk>/", views.document_detail, name="document_detail"),
    path("documents/<int:pk>/upload/", views.document_upload, name="document_upload"),
    path("documents/<int:pk>/submit/", views.document_submit, name="document_submit"),
    path("documents/<int:pk>/review/", views.document_review, name="document_review"),
    path("documents/<int:pk>/reopen/", views.document_reopen, name="document_reopen"),
    path("documents/<int:pk>/comment/", views.document_comment, name="document_comment"),
    path("versions/<int:version_pk>/preview/", views.document_file, {"mode": "preview"}, name="document_preview"),
    path("versions/<int:version_pk>/download/", views.document_file, {"mode": "download"}, name="document_download"),
    path("notifications/", views.notifications, name="notifications"),
    path("notifications/<int:pk>/read/", views.notification_read, name="notification_read"),
    path("notifications/read-all/", views.notifications_read_all, name="notifications_read_all"),
    path("audit/", views.audit_log, name="audit_log"),
    path("users/", views.user_management, name="user_management"),
    path("users/<int:pk>/update/", views.user_update, name="user_update"),
    path("integrations/", views.integrations, name="integrations"),
    path("integrations/google-drive/connect/", views.google_drive_connect, name="google_drive_connect"),
    path("integrations/google-drive/callback/", views.google_drive_callback, name="google_drive_callback"),
    path("backups/", views.backup_status, name="backup_status"),
    path("backups/run/", views.backup_run, name="backup_run"),
]
