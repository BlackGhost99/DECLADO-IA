from django.urls import path

from apps.accounts import api as accounts
from apps.audit import api as audit
from apps.clients import api as clients
from apps.organizations import api as organizations
from apps.tariffs import api as tariffs

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
    path("tariffs/editions", tariffs.EditionListView.as_view()),
    path("tariffs/editions/<uuid:edition_id>/publish", tariffs.PublishEditionView.as_view()),
    path("tariffs/editions/<uuid:edition_id>/withdraw", tariffs.WithdrawEditionView.as_view()),
    path("tariffs/search", tariffs.SearchView.as_view()),
    path("tariffs/nodes/<uuid:node_id>", tariffs.NodeDetailView.as_view()),
    path("tariffs/records/<uuid:record_id>", tariffs.RecordView.as_view()),
    path("reference-imports", tariffs.ImportRunListView.as_view()),
    path("reference-imports/<uuid:run_id>/issues", tariffs.IssueListView.as_view()),
    path("reference-issues/<uuid:issue_id>/resolve", tariffs.ResolveIssueView.as_view()),
]
