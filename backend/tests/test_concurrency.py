"""T33 (socle) : version périmée → 409, aucune perte silencieuse."""


def test_stale_row_version_returns_409(world, session):
    url = f"/api/v1/importers/{world['importer_a'].id}"
    first, second = session("declarant@a.test"), session("validateur@a.test")

    ok = first.patch(url, {"address": "Libreville", "row_version": 1})
    assert ok.status_code == 200
    assert ok.json()["row_version"] == 2

    conflict = second.patch(url, {"address": "Port-Gentil", "row_version": 1})
    assert conflict.status_code == 409
    body = conflict.json()
    assert body["code"] == "REVISION_CONFLICT"
    assert body["details"] == {"expected_version": 1, "current_version": 2}
    assert first.get(url).json()["address"] == "Libreville"


def test_if_match_header_is_accepted(world, session):
    url = f"/api/v1/importers/{world['importer_a'].id}"
    resp = session("declarant@a.test").patch(url, {"notes": "via If-Match"}, HTTP_IF_MATCH='"1"')
    assert resp.status_code == 200


def test_missing_row_version_is_rejected(world, session):
    url = f"/api/v1/importers/{world['importer_a'].id}"
    resp = session("declarant@a.test").patch(url, {"notes": "sans version"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "ROW_VERSION_REQUIRED"
