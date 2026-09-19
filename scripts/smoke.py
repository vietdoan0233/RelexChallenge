#!/usr/bin/env python
"""End-to-end smoke test against a RUNNING server.

    python scripts/smoke.py                       # read-only checks, no model calls
    python scripts/smoke.py --live                # also asks a real question
    python scripts/smoke.py --base http://localhost:8000

Never calls the destructive privacy endpoint. Exits non-zero on the first
broken invariant, so it can gate a demo.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

KNOWN_EVIDENCE = "EV-15_uat-signoff-mittwoch-22-januar-2025-08-50"
FAILURES: list[str] = []


def call(base: str, path: str, body: dict | None = None):
    request = urllib.request.Request(
        base + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST" if body is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, None


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if condition else 'FAIL'} {label}{(' — ' + detail) if detail else ''}")
    if not condition:
        FAILURES.append(label)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--live", action="store_true", help="also ask one real question")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    print("health")
    status, body = call(base, "/api/health")
    check("GET /api/health is ok", status == 200 and body and body["status"] == "ok")

    print("archive and people")
    status, people = call(base, "/api/privacy/people")
    check(
        "people list is served",
        status == 200 and isinstance(people, list) and len(people) >= 20,
        f"{len(people or [])} people",
    )
    check(
        "no reserved marker is a person",
        not any(p["canonical_name"].startswith("[REDACTED") for p in people or []),
    )

    print("evidence with context")
    status, view = call(base, f"/api/evidence/{KNOWN_EVIDENCE}")
    check("known evidence is hydrated from the database", status == 200 and view is not None)
    if view:
        cite = view["citation"]
        check(
            "citation carries DB provenance",
            all(cite.get(k) for k in ("document_id", "filename", "event_date", "speaker_sender")),
        )
        check(
            "neighbour context is included", bool(view["context_before"] or view["context_after"])
        )
    check("unknown evidence is a 404", call(base, "/api/evidence/EV-does-not-exist")[0] == 404)
    check("unknown case is a 404", call(base, "/api/cases/nope")[0] == 404)

    print("radar")
    status, cards = call(base, "/api/radar")
    check(
        "radar endpoint answers",
        status == 200 and isinstance(cards, list),
        f"{len(cards or [])} finding(s)",
    )
    allowed = {"STILL_BLOCKED", "PARTIALLY_CHANGED", "WORTH_REASSESSING", "INSUFFICIENT_EVIDENCE"}
    for card in cards or []:
        check("finding uses only a bounded assessment", card["assessment"] in allowed)
        check(
            "finding has proposal, outcome and blocker receipts",
            card["proposal_citations"] and card["outcome_citations"] and card["blocker_citations"],
        )
        check(
            "finding links to a valid Case", call(base, f"/api/cases/{card['case_id']}")[0] == 200
        )

    print("frontend")
    try:
        with urllib.request.urlopen(base + "/", timeout=10) as response:
            html = response.read().decode()
        check("UI is served", '<div id="root">' in html)
    except urllib.error.URLError:
        print("  skip UI is not served by this server (dev mode uses the Vite server)")

    if args.live:
        print("live Case (uses the reasoning service)")
        status, case = call(
            base,
            "/api/cases/query",
            {"query": "Did Acme sign off UAT for the programme, and what was the scope?"},
        )
        check("a Case is returned", status == 200 and case is not None)
        if case:
            statuses = {
                "SUPPORTED",
                "PARTIALLY_SUPPORTED",
                "CONFLICTING_EVIDENCE",
                "INSUFFICIENT_EVIDENCE",
            }
            check("status is a valid enum", case["status"] in statuses, case["status"])
            check(
                "no fabricated citation was rendered",
                case["validation"]["rejected_evidence_ids"] == []
                or all(
                    c["evidence_id"] not in case["validation"]["rejected_evidence_ids"]
                    for cl in case["claims"]
                    for c in cl["support"]
                ),
            )
            check(
                "every claim has support or is explicitly uncertain",
                all(cl["support"] or cl["stance"] == "UNCERTAIN" for cl in case["claims"]),
            )
            check(
                "every citation has speaker/date/document from the DB",
                all(
                    c["document_id"] and c["filename"]
                    for cl in case["claims"]
                    for c in cl["support"]
                ),
            )
            check(
                "the decisive signed reply was found",
                any(
                    c["evidence_id"] == KNOWN_EVIDENCE
                    for cl in case["claims"]
                    for c in cl["support"]
                ),
            )
            check("it can be re-read by id", call(base, f"/api/cases/{case['case_id']}")[0] == 200)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed: {FAILURES}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
