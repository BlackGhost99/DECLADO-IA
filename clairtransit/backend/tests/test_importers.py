"""CLI-01 (socle) : création, doublons signalés sans fusion, identifiants en texte."""


def test_possible_duplicates_are_flagged_not_merged(world, session):
    s = session("declarant@a.test")
    by_name = s.post("/api/v1/importers", {"name": "  importateur à "})
    assert by_name.status_code == 201
    assert [d["name"] for d in by_name.json()["possible_duplicates"]] == ["Importateur A"]

    by_id = s.post("/api/v1/importers", {"name": "Autre nom", "identifiers": {"nif": "A-1"}})
    assert [d["name"] for d in by_id.json()["possible_duplicates"]] == ["Importateur A"]
    assert len(s.get("/api/v1/importers").json()["results"]) == 3


def test_duplicates_ignore_other_organizations(world, session):
    resp = session("declarant@a.test").post(
        "/api/v1/importers", {"name": "Importateur B", "identifiers": {"nif": "B-1"}}
    )
    assert resp.json()["possible_duplicates"] == []


def test_identifiers_keep_leading_zeros_as_text(world, session):
    s = session("declarant@a.test")
    resp = s.post("/api/v1/importers", {"name": "Zéros", "identifiers": {"nif": "000123"}})
    assert resp.json()["identifiers"] == {"nif": "000123"}
    bad = s.post("/api/v1/importers", {"name": "Nombre", "identifiers": {"nif": 123}})
    assert bad.status_code == 400
    assert bad.json()["code"] == "VALIDATION_ERROR"
