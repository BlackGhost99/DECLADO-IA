"""Rapprochement de pièces au sein d'un seul dépôt, sans fusion sur le nom seul."""

import re
import unicodedata
from collections import defaultdict
from itertools import combinations


def _name(value):
    plain = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().upper()
    return " ".join(re.findall(r"[A-Z0-9]+", plain))


def _reference(value):
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _measure(field, value):
    pattern = r"(\d+(?:[.,]\d{1,2})?)\s*(?:KG|KGS)?" if field == "gross_weight" else r"(\d+)(?:\s+(?:COLIS|PACKAGES))?"
    # Une unité inconnue ou un nombre ambigu est écarté.
    match = re.fullmatch(pattern, value.strip().upper())
    return float(match[1].replace(",", ".")) if match else None


def _facts(piece):
    references = defaultdict(set)
    for ref in piece["references"]:
        value = _reference(ref["value"])
        if value and any(c.isdigit() for c in value):
            references[ref["kind"]].add(value)
    shipment = {
        field: _measure(field, value) if field in {"packages", "gross_weight"} else _name(value)
        for field, value in piece["shipment"].items()
    }
    return _name(piece["party"]), references, shipment


def _conflict(a, b):
    party, refs, shipment = a
    other_party, other_refs, other_shipment = b
    return (
        bool(party and other_party and party != other_party)
        or any(refs[k] and other_refs[k] and refs[k].isdisjoint(other_refs[k]) for k in ("invoice", "bl"))
        or any(
            shipment.get(k) and other_shipment.get(k) and shipment[k] != other_shipment[k] for k in ("vessel", "voyage")
        )
    )


def _strong(a, b):
    return any(a[1][kind] & b[1][kind] for kind in ("invoice", "bl"))


def _context(a, b):
    party, refs, shipment = a
    other_party, other_refs, other_shipment = b

    def matches(field):
        return bool(shipment.get(field) and shipment[field] == other_shipment.get(field))

    if not party or party != other_party:
        return ""
    if refs["container"] & other_refs["container"]:
        return "container_party"
    cargo = matches("packages") and matches("gross_weight")
    if cargo and matches("shipper"):
        return "cargo_shipper"
    if cargo and matches("vessel") and matches("voyage"):
        return "cargo_voyage"
    return ""


def _components(size, edges):
    remaining = set(range(size))
    components = []
    while remaining:
        start = min(remaining)
        remaining.remove(start)
        pending, members = [start], [start]
        while pending:
            current = pending.pop()
            fresh = remaining.intersection(edges[current])
            pending.extend(sorted(fresh))
            members.extend(sorted(fresh))
            remaining.difference_update(fresh)
        components.append(sorted(members))
    return components


def _anchor(piece):
    return next(
        (
            ref["value"]
            for ref in piece["references"]
            if ref["role"] == "own" and ref["kind"] in {"invoice", "bl"} and any(c.isdigit() for c in ref["value"])
        ),
        "",
    )


def group_shipments(pieces):
    facts = [_facts(piece) for piece in pieces]
    strong, conflicts = defaultdict(set), defaultdict(set)
    for i, j in combinations(range(len(pieces)), 2):
        if _strong(facts[i], facts[j]):
            strong[i].add(j)
            strong[j].add(i)
        if _conflict(facts[i], facts[j]):
            conflicts[i].add(j)
            conflicts[j].add(i)

    groups, ambiguous = [], set()
    for members in _components(len(pieces), strong):
        if any(
            conflicts[i].intersection(members) or any(len(facts[i][1][kind]) > 1 for kind in ("invoice", "bl"))
            for i in members
        ):
            # Un document pont peut citer deux envois. Garder chaque dossier séparé.
            ambiguous.update(members)
            groups.extend([i] for i in members)
        else:
            groups.append(members)

    anchors = {i for i, members in enumerate(groups) if any(_anchor(pieces[k]) for k in members)}
    anchor_edges = _candidates(groups, facts, conflicts, ambiguous, combinations(sorted(anchors), 2))
    contexts, review = {}, set()
    for i in sorted(anchors):
        neighbors = anchor_edges[i]
        if len(neighbors) == 1:
            j = next(iter(neighbors))
            if len(anchor_edges[j]) == 1:
                if i < j:
                    groups[i].extend(groups[j])
                    groups[j] = []
                    contexts[i] = neighbors[j]
                continue
        if neighbors:
            review.add(i)

    # Comparer toutes les pièces restantes aux dossiers avant d'en déplacer une.
    # Une pièce déjà rapprochée ne sert jamais de preuve pour la suivante.
    attachments = _candidates(
        groups,
        facts,
        conflicts,
        ambiguous,
        ((i, j) for i in range(len(groups)) if i not in anchors for j in sorted(anchors)),
    )
    by_destination = defaultdict(list)
    for i in range(len(groups)):
        if i in anchors:
            continue
        choices = attachments[i]
        if len(choices) == 1:
            by_destination[next(iter(choices))].append(i)
        elif choices:
            review.add(i)
    for j, sources in by_destination.items():
        if any(conflicts[k].intersection(groups[b]) for a, b in combinations(sources, 2) for k in groups[a]):
            review.update(sources)
            review.add(j)
            continue
        for i in sources:
            groups[j].extend(groups[i])
            groups[i] = []
            contexts.setdefault(j, attachments[i][j])

    proposals, unassigned = [], []
    for i, members in enumerate(groups):
        if not members:
            continue
        needs_review = bool(ambiguous.intersection(members) or i in review)
        docs = [pieces[k] for k in members]
        if len(docs) == 1 and not _anchor(docs[0]):
            unassigned.append({**docs[0], "assignment_issue": "ambiguous" if needs_review else "insufficient"})
            continue
        proposals.append(_proposal(docs, contexts.get(i, ""), needs_review))
    titles = defaultdict(int)
    for proposal in proposals:
        titles[proposal["title"]] += 1
    for proposal in proposals:
        if titles[proposal["title"]] > 1:
            if anchor := next((_anchor(p) for p in proposal["documents"] if _anchor(p)), ""):
                proposal["title"] += f" · {anchor}"
    proposals.sort(key=lambda proposal: proposal["title"].casefold())
    return {"groups": proposals, "unassigned": unassigned}


def _candidates(groups, facts, conflicts, ambiguous, pairs):
    candidates = defaultdict(dict)
    for i, j in pairs:
        left, right = groups[i], groups[j]
        if ambiguous.intersection(left + right) or any(conflicts[k].intersection(right) for k in left):
            continue
        context = next((match for k in left for m in right if (match := _context(facts[k], facts[m]))), "")
        if context:
            candidates[i][j] = candidates[j][i] = context
    return candidates


def _proposal(pieces, context, review):
    references = defaultdict(dict)
    parties = {}
    for piece in pieces:
        if piece["party"]:
            parties.setdefault(_name(piece["party"]), piece["party"])
        for ref in piece["references"]:
            references[ref["kind"], _reference(ref["value"])][piece["document_id"]] = ref["value"]
    reasons = [
        {"kind": kind, "value": next(iter(docs.values())), "documents": len(docs)}
        for (kind, key), docs in references.items()
        if key and len(docs) > 1
    ]
    party = next(iter(parties.values()), "")
    return {
        "title": party or pieces[0]["name"],
        "party": party,
        "parties": list(parties.values()),
        "documents": pieces,
        "reasons": reasons,
        "warnings": ["ambiguous"] if review else [],
        "confidence": "review" if review else "medium" if context else "high" if reasons else "single",
        "context": context,
    }
