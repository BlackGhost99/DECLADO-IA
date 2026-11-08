from django.conf import settings
from django.contrib import admin
from django.http import FileResponse, Http404
from django.urls import include, path, re_path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.core.urls")),
]


def frontend_index(_request):
    """React SPA entrypoint; never capture API or admin routes."""
    index = settings.FRONTEND_DIST_DIR / "index.html"
    if not index.is_file():
        raise Http404("Frontend build unavailable")
    response = FileResponse(index.open("rb"), content_type="text/html; charset=utf-8")
    response["Cache-Control"] = "no-store"
    return response


if settings.SERVE_FRONTEND:
    urlpatterns += [
        path("", frontend_index),
        re_path(r"^(?!api/|admin/|static/|assets/).+$", frontend_index),
    ]
