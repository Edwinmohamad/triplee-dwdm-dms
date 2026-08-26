from ..models import ActivityLog


def client_ip(request):
    forwarded = request.META.get("HTTP_CF_CONNECTING_IP") or request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_activity(request, action, entity, description, metadata=None):
    return ActivityLog.objects.create(
        actor=request.user if request.user.is_authenticated else None,
        action=action,
        entity_type=entity.__class__.__name__ if entity is not None else "System",
        entity_id=str(getattr(entity, "pk", "")) if entity is not None else "",
        description=description,
        metadata=metadata or {},
        ip_address=client_ip(request),
    )

