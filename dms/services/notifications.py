from ..models import Notification, User


def notify_roles(roles, title, message, url="", exclude_user=None):
    users = User.objects.filter(role__in=roles, is_active=True)
    if exclude_user:
        users = users.exclude(pk=exclude_user.pk)
    Notification.objects.bulk_create(
        [Notification(user=user, title=title, message=message, url=url) for user in users]
    )


def notify_user(user, title, message, url=""):
    if user and user.is_active:
        Notification.objects.create(user=user, title=title, message=message, url=url)

