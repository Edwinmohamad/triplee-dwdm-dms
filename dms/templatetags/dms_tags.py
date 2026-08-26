from django import template

from ..services.local_storage import download_filename

register = template.Library()


@register.filter
def status_class(value):
    return {
        "APPROVED": "success",
        "COMPLETED": "success",
        "INSTALLED": "info",
        "DOCUMENT_PREPARATION": "info",
        "UNDER_REVIEW": "warning",
        "UPLOADED": "info",
        "IN_PROGRESS": "info",
        "DRAFT": "neutral",
        "REVISION_REQUIRED": "danger",
        "REJECTED": "danger",
        "PENDING_INSTALLATION": "neutral",
        "NOT_STARTED": "neutral",
        "NOT_APPLICABLE": "neutral",
    }.get(value, "neutral")


@register.filter
def file_size(value):
    try:
        size = float(value)
    except (TypeError, ValueError):
        return "—"
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


@register.filter
def simple_filename(entity):
    try:
        return download_filename(entity)
    except (AttributeError, TypeError, ValueError):
        return getattr(entity, "stored_filename", "document")
