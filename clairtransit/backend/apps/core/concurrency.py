"""Verrou optimiste : chaque mutation présente la version lue (If-Match ou row_version)."""

from .exceptions import ApiError, RevisionConflict


def expected_version(request) -> int | None:
    raw = request.headers.get("If-Match")
    if raw is None and isinstance(request.data, dict):
        raw = request.data.get("row_version")
    if raw is None:
        return None
    try:
        return int(str(raw).strip().strip('"').removeprefix("W/").strip('"'))
    except ValueError:
        return -1


def check_version(obj, expected: int | None) -> None:
    """À appeler sur un objet verrouillé (select_for_update) ; 409 sans rien écraser si périmé."""
    if expected is None:
        raise ApiError("ROW_VERSION_REQUIRED", "La version de l'élément (row_version) est obligatoire.", 400)
    if obj.row_version != expected:
        raise RevisionConflict(expected, obj.row_version)


def bump(obj) -> None:
    obj.row_version += 1
