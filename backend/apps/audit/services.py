from apps.core.middleware import get_request_id

from .models import AuditEvent


def record_event(*, organization, actor, event_type: str, entity, previous=None, current=None, scope="") -> AuditEvent:
    return AuditEvent.objects.create(
        organization=organization,
        actor=actor if actor is not None and getattr(actor, "is_authenticated", False) else None,
        event_type=event_type,
        entity_type=entity._meta.label_lower,
        entity_id=str(entity.pk),
        previous=previous,
        current=current,
        scope=scope,
        request_id=get_request_id() if get_request_id() != "-" else "",
    )
