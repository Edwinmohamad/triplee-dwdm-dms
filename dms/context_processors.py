from .models import GoogleDriveCredential


def navigation_context(request):
    if not request.user.is_authenticated:
        return {"unread_notifications": 0, "drive_connected": False}
    return {
        "unread_notifications": request.user.notifications.filter(is_read=False).count(),
        "drive_connected": GoogleDriveCredential.objects.exists(),
    }

