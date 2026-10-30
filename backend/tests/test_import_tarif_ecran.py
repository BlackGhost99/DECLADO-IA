# ruff: noqa: F811  (fixtures importées de test_fiscal)
"""Import d'un tarif depuis l'écran Administration tarifaire (T78), sur des données fictives.

Le gestionnaire du référentiel dépose le classeur SWD : édition publiée en consultation,
barème des taxes activé, codes cherchables avec leurs taux. Personne d'autre ne peut importer.
"""

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.fiscal.models import TaxSchedule
from tests.test_fiscal import _private_storage, manager, workbook  # noqa: F401


def upload(s, path, name="Tarif_CEMAC_2022_SWD.xlsx", label=""):
    f = SimpleUploadedFile(name, path.read_bytes())
    return s.upload("/api/v1/tariffs/imports", {"file": f, "label": label})


def test_t78_swd_workbook_uploaded_from_the_screen_brings_tariff_and_taxes(world, manager, session, tmp_path):
    s = session(manager.email)
    resp = upload(s, workbook(tmp_path / "swd.xlsx"), label="Tarif CEMAC 2022 (SWD)")
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["edition"]["publication_state"] == "consultation"
    assert body["taxes"]["active"] is True
    assert TaxSchedule.objects.get(is_active=True).label == "Tarif CEMAC 2022 (SWD)"
    found = session("declarant@a.test").get("/api/v1/tariffs/search", q="4201").json()["results"]
    assert found
    rates = s.get("/api/v1/fiscal/rates", code="42010000").json()
    assert any(r.get("tax") == "DDI" or r.get("code") == "DDI" for r in rates.get("rates", rates.get("results", [])))


def test_only_reference_managers_import_and_bad_files_are_refused(world, manager, session, tmp_path):
    path = workbook(tmp_path / "swd.xlsx")
    assert upload(session("admin@a.test"), path).status_code == 403
    s = session(manager.email)
    assert upload(s, path, name="tarif.pdf").status_code == 400
    bad = tmp_path / "faux.xlsx"
    bad.write_bytes(b"pas un classeur")
    assert upload(s, bad, name="faux.xlsx").status_code == 400
