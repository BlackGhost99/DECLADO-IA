import pytest

from apps.organizations.business_models import BusinessProfile, OrganizationBusinessProfile
from apps.organizations.context import SESSION_KEY
from apps.organizations.models import Membership, Organization


@pytest.mark.django_db
def test_profile_endpoint_is_bound_to_session(client, django_user_model):
    alpha = Organization.objects.create(name="Alpha")
    beta = Organization.objects.create(name="Beta")
    user = django_user_model.objects.create_user(
        email="profile-test@example.test", password="A-long-test-password-35"
    )
    Membership.objects.create(organization=alpha, user=user, roles=["declarant"])
    OrganizationBusinessProfile.objects.create(
        organization=alpha, primary_profile=BusinessProfile.TRANSIT
    )
    OrganizationBusinessProfile.objects.create(
        organization=beta, primary_profile=BusinessProfile.EXPERT
    )
    client.force_login(user)
    session = client.session
    session[SESSION_KEY] = str(alpha.pk)
    session.save()
    response = client.get("/api/v1/organization/business-profile")
    assert response.status_code == 200
    assert response.json()["primary_profile"] == "transit"
    assert "audit" not in response.json()["features"]
    session = client.session
    session[SESSION_KEY] = str(beta.pk)
    session.save()
    assert client.get("/api/v1/organization/business-profile").status_code == 403


@pytest.mark.django_db
def test_workflow_endpoint_requires_session(client, django_user_model):
    user = django_user_model.objects.create_user(
        email="no-org@example.test", password="A-long-test-password-35"
    )
    client.force_login(user)
    response = client.post(
        "/api/v1/revisions/00000000-0000-0000-0000-000000000001/transition",
        data='{"target":"in_preparation","row_version":1}',
        content_type="application/json",
    )
    assert response.status_code == 403
