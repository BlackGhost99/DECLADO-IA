from django.urls import path

from apps.accounts import api as accounts
from apps.audit import api as audit
from apps.cases import api as cases
from apps.clients import api as clients
from apps.extraction import api as extraction
from apps.organizations import api as organizations
from apps.scans import api as scans
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
    path("cases", cases.CaseListView.as_view()),
    path("cases/<uuid:case_id>", cases.CaseDetailView.as_view()),
    path("cases/<uuid:case_id>/assign", cases.CaseAssignView.as_view()),
    path("cases/<uuid:case_id>/revisions", cases.CaseRevisionsView.as_view()),
    path("cases/<uuid:case_id>/documents", cases.CaseDocumentsView.as_view()),
    path("cases/<uuid:case_id>/documents/reuse", cases.CaseDocumentReuseView.as_view()),
    path("cases/<uuid:case_id>/audit", cases.CaseAuditView.as_view()),
    path("case-documents/<uuid:link_id>/replace", cases.CaseDocumentReplaceView.as_view()),
    path("revisions/<uuid:revision_id>", cases.RevisionDetailView.as_view()),
    path("revisions/<uuid:revision_id>/invoices", cases.InvoiceCreateView.as_view()),
    path("revisions/<uuid:revision_id>/goods-lines", cases.GoodsLineCreateView.as_view()),
    path("invoices/<uuid:invoice_id>", cases.InvoiceDetailView.as_view()),
    path("invoices/<uuid:invoice_id>/lines", cases.InvoiceLineCreateView.as_view()),
    path("invoices/<uuid:invoice_id>/goods-lines", cases.InvoiceGoodsLinesView.as_view()),
    path("invoice-lines/<uuid:line_id>", cases.InvoiceLineDetailView.as_view()),
    path("goods-lines/<uuid:goods_id>", cases.GoodsLineDetailView.as_view()),
    path("goods-lines/<uuid:goods_id>/code-checks", cases.CodeCheckView.as_view()),
    path("goods-lines/<uuid:goods_id>/decisions", cases.DecisionView.as_view()),
    path("goods-lines/<uuid:goods_id>/proposals", cases.ProposalView.as_view()),
    path("case-documents/<uuid:link_id>/extractions", extraction.CaseDocumentExtractionsView.as_view()),
    path("extraction-runs/<uuid:run_id>", extraction.ExtractionRunView.as_view()),
    path("jobs/<uuid:job_id>", extraction.JobView.as_view()),
    path("divergences/<uuid:divergence_id>/resolve", extraction.DivergenceResolveView.as_view()),
    path("cases/<uuid:case_id>/scan-batches", scans.CaseBatchesView.as_view()),
    path("scan-batches/<uuid:batch_id>", scans.BatchDetailView.as_view()),
    path("scan-batches/<uuid:batch_id>/files", scans.BatchFilesView.as_view()),
    path("scan-batches/<uuid:batch_id>/photos", scans.BatchPhotoView.as_view()),
    path("scan-batches/<uuid:batch_id>/<str:action>", scans.BatchActionView.as_view()),
    path("scan-pages/<uuid:page_id>", scans.PageDetailView.as_view()),
    path("scan-pages/<uuid:page_id>/split", scans.PageSplitView.as_view()),
    path("scan-pages/<uuid:page_id>/replace", scans.PageReplaceView.as_view()),
    path("scan-pages/<uuid:page_id>/image", scans.PageImageView.as_view()),
    path("scan-pieces/<uuid:piece_id>", scans.PieceDetailView.as_view()),
    path("scan-pieces/<uuid:piece_id>/join-previous", scans.PieceJoinView.as_view()),
    path("documents/limits", cases.DocumentLimitsView.as_view()),
    path("documents/<uuid:document_id>", cases.DocumentDetailView.as_view()),
    path("documents/<uuid:document_id>/download", cases.DocumentDownloadView.as_view()),
    path("documents/<uuid:document_id>/preview", cases.DocumentPreviewView.as_view()),
    path("files/<str:token>/<str:name>", cases.FileView.as_view()),
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
