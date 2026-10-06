"""AUD-01 / AUD-02 (socle) : journal en ajout seul, filtrable, borné à la société."""

import pytest
from django.db import DatabaseError, connection, transaction

from apps.audit.models import AppendOnlyError, AuditEvent


def test_changes_are_journaled_with_before_after(world, session):
    s = session("declarant@a.test")
    s.patch(f"/api/v1/importers/{world['importer_a'].id}", {"address": "Owendo", "row_version": 1})
    event = AuditEvent.objects.get(event_type="importer.updated")
    assert event.organization == world["org_a"]
    assert event.actor.email == "declarant@a.test"
    assert event.previous == {"address": ""}
    assert event.current == {"address": "Owendo"}
    assert event.request_id


def test_orm_cannot_modify_or_delete_events(world, session):
    session("declarant@a.test").post("/api/v1/importers", {"name": "Z"})
    event = AuditEvent.objects.first()
    event.event_type = "falsifié"
    with pytest.raises(AppendOnlyError):
        event.save()
    with pytest.raises(AppendOnlyError):
        event.delete()


def test_database_refuses_update_and_delete(world, session):
    session("declarant@a.test").post("/api/v1/importers", {"name": "Z"})
    for sql in ("UPDATE audit_auditevent SET event_type = 'x'", "DELETE FROM audit_auditevent"):
        with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(sql)
    assert AuditEvent.objects.filter(event_type="importer.created").exists()


def test_audit_list_filters(world, session):
    session("declarant@a.test").post("/api/v1/importers", {"name": "Z"})
    session("validateur@a.test").post("/api/v1/importers", {"name": "W"})
    s = session("admin@a.test")
    by_actor = s.get("/api/v1/audit-events", actor="validateur@a.test").json()["results"]
    assert {e["actor_email"] for e in by_actor} == {"validateur@a.test"}
    by_type = s.get("/api/v1/audit-events", event_type="importer.created").json()["results"]
    assert len(by_type) == 2


def test_declarant_cannot_read_audit(world, session):
    assert session("declarant@a.test").get("/api/v1/audit-events").status_code == 403
