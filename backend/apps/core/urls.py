from django.urls import path

from apps.accounts import api as accounts
from apps.audit import api as audit
from apps.clients import api as clients
from apps.organizations import api as organizations

from .api import HealthView

urlpatterns = [
    path("health", HealthView.as_view()),
    path("auth/csrf", accounts.CsrfView.as_view()),
    path("auth/login", accounts.LoginView.as_view()),
    path("auth/logout", accounts.LogoutView.as_view()),
    path("me", accounts.MeView.as_view()),
    path("me/active-organization", accounts.ActiveOrganizationView.as_view()),
    path("organization/members", organizations.MemberListView.as_view()),
    path("organization/members/<uuid:member_id>/roles", organizations.MemberRolesView.as_view()),
    path("organization/members/<uuid:member_id>/deactivate", organizations.MemberDeactivateView.as_view()),
    path("importers", clients.ImporterListView.as_view()),
    path("importers/<uuid:pk>", clients.ImporterDetailView.as_view()),
    path("audit-events", audit.AuditEventListView.as_view()),
]
