"""Staging-only paced SWD import must keep unpublished data out of live tariff searches."""

import pytest

from apps.accounts.models import User
from apps.fiscal.importer import import_swd
from apps.fiscal.models import ScheduleLine, ScheduleRate, TaxSchedule
from apps.tariffs.models import PublicationState, TariffNode
from tests.conftest import PASSWORD
from tests.test_fiscal import workbook


@pytest.fixture
def manager(db):
    return User.objects.create_user(email="low-pressure@test.test", password=PASSWORD, is_reference_manager=True)


@pytest.mark.django_db
def test_paced_swd_preserves_tax_rates_and_only_creates_draft(settings, tmp_path, manager):
    settings.STAGING_SKIP_ANTIVIRUS = True
    settings.STAGING_SIMPLE_LOGIN = True
    settings.DEBUG = False
    settings.PRIVATE_STORAGE_ROOT = tmp_path / "private"
    schedule = import_swd(
        workbook(tmp_path / "paced-swd.xlsx"),
        label="CEMAC SWD test",
        title="paced-swd.xlsx",
        actor=manager,
        low_pressure=True,
    )
    assert schedule.is_active is False
    assert schedule.edition.publication_state == PublicationState.DRAFT
    assert schedule.counts["lines"] == 6
    assert TariffNode.objects.filter(edition=schedule.edition, kind="tariff_line").count() == 5
    assert ScheduleLine.objects.filter(schedule=schedule).count() == 6
    assert ScheduleRate.objects.filter(line__schedule=schedule).count() > 40
    assert ScheduleLine.objects.get(schedule=schedule, hs_code="01012100").rates.get(tax="DDI").rate == 5


@pytest.mark.django_db
def test_paced_import_refused_unless_explicitly_in_staging(settings, tmp_path, manager):
    settings.STAGING_SKIP_ANTIVIRUS = False
    settings.STAGING_SIMPLE_LOGIN = False
    settings.PRIVATE_STORAGE_ROOT = tmp_path / "private"
    with pytest.raises(ValueError, match="restricted to staging"):
        import_swd(
            workbook(tmp_path / "not-staging.xlsx"),
            label="Not staged",
            title="not-staging.xlsx",
            actor=manager,
            low_pressure=True,
        )
    assert TaxSchedule.objects.count() == 0
