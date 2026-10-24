import pytest

from apps.cases.workflow_policy import allowed_transition
from apps.organizations.business_models import BusinessProfile, OrganizationBusinessProfile
from apps.organizations.business_permissions import has_feature
from apps.organizations.models import Membership, Organization


def test_preparation_and_return_only():
    assert allowed_transition("in_preparation", "to_validate", ["declarant"])
    assert not allowed_transition("to_validate", "validated", ["validator"])
    assert not allowed_transition("to_validate", "to_correct", ["validator"])
    assert allowed_transition("to_validate", "to_correct", ["validator"], "Pièce absente")


@pytest.mark.django_db
def test_membership_isolated_between_organizations(django_user_model):
    first = Organization.objects.create(name="Transit A")
    second = Organization.objects.create(name="Expert B")
    user = django_user_model.objects.create_user(
        email="isolation@example.test", password="Test_password_long_3928",
    )
    Membership.objects.create(organization=first, user=user, roles=["declarant"])
    OrganizationBusinessProfile.objects.create(organization=first, primary_profile=BusinessProfile.TRANSIT)
    OrganizationBusinessProfile.objects.create(organization=second, primary_profile=BusinessProfile.EXPERT)
    assert has_feature(user, first, "cases")
    assert not has_feature(user, first, "audit")
    assert not has_feature(user, second, "audit")
