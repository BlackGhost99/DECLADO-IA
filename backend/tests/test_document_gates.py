from apps.regulations.readiness import legal_coverage_gate


def test_no_legal_source_fails():
    assert not legal_coverage_gate(verified_sources=0, published_rules=0, coverage_certified=False)["ready"]


def test_uncertified_scope_fails_even_with_rules():
    assert not legal_coverage_gate(verified_sources=1, published_rules=10, coverage_certified=False)["ready"]
