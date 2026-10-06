"""Défense en profondeur : la base refuse toute modification ou suppression du journal."""

from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION audit_event_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_auditevent est en ajout seul (%)', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_event_no_update_delete
BEFORE UPDATE OR DELETE ON audit_auditevent
FOR EACH ROW EXECUTE FUNCTION audit_event_append_only();
"""

BACKWARD = """
DROP TRIGGER IF EXISTS audit_event_no_update_delete ON audit_auditevent;
DROP FUNCTION IF EXISTS audit_event_append_only();
"""


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]
    operations = [migrations.RunSQL(FORWARD, BACKWARD)]
