#!/usr/bin/env python3
"""
tollbooth-graph — scripted demo (Graph Hacks, Oct 15-18 2026).

The arc, end to end:
  1. A buyer requests a brief  -> Wake researches it; brief + claims +
     sources + provenance edges land in the graph.
  2. North reviews it            -> Review node + REVIEWS edge carrying the
     verdict AND what the review changed (honestly: "" if nothing).
  3. The buyer pays (x402/USDC)  -> Payment node, SETTLED on the brief,
     CREDITED to the earn-first treasury. Company Brain sees it.
  4. Session two: a new session opens and recalls from the graph —
     the money query: "everything we know about X and who verified it."
  5. The integrity query: the weakest-link rule fires — one unmapped claim
     resting on everything inherits staleness from an ancient source in
     its web. Effective freshness shown as a number, not just a flag.

All demo data is synthetic and labeled as such. Real Tollbooth rails
(brief engine, x402/USDC) are reused and cited in WRITEUP.md; the graph
schema, this layer, and the demo are new work done inside the window.
"""

import sys
import os
import json
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
import memory as M


def section(title):
    print("\n" + "=" * 70)
    print("  " + title)
    print("=" * 70)


def ancient_iso(days=90):
    return (datetime.now(timezone.utc) - timedelta(days=days)
            ).strftime("%Y-%m-%dT%H:%M:%SZ")


def claim_id_by_text(g, bid, prefix):
    rows = g.query(
        "MATCH (b:Brief {id: $bid})-[:CONTAINS]->(c:Claim) "
        "RETURN c.id, c.text",
        {"bid": bid}).result_set
    for cid, text in rows:
        if text.startswith(prefix):
            return cid
    raise RuntimeError("claim not found: %r" % prefix)


def main():
    g = M.connect()
    topic = "x402 agentic payment demand"

    # ---- setup: the pair, the treasury, session one ----
    section("0. the pair, the treasury, session one")
    M.ensure_agent(g, "Wake", "research / build")
    M.ensure_agent(g, "North", "review / hold the edges")
    M.ensure_treasury(g)
    M.record_session(g, "session-001", "build sit",
                     notes="Graph Hacks day one: Tollbooth with a graph memory.")
    M.join_session(g, "Wake", "session-001")
    M.join_session(g, "North", "session-001")
    print("agents: Wake, North | treasury: earn-first-treasury | session-001 open")

    # ---- 1. buyer requests; Wake researches ----
    section("1. buyer requests a brief — Wake researches, provenance lands")
    bid = M.write_brief(
        g, "Wake", topic,
        claims=[
            {"text": "138M+ x402 payments settled on Base through Q3 2026 (demo figure).",
             "sources": [0], "load_bearing": True},
            {"text": "Only 0.6-7.5% of screened commerce volume looked genuinely agentic (demo figure).",
             "sources": [1]},
            {"text": "246 of 37,292 listed x402 resources show real demand (demo figure).",
             "sources": [2]},
            # the fourth claim names no sources: it rests on everything.
            # support_mode='inherited' is recorded on the node — the
            # weakest-link rule will price the laziness.
            {"text": "Agentic share of screened commerce is climbing quarter over quarter (demo figure)."},
        ],
        sources=[
            {"url": "demo://chainalysis-q3-2026", "kind": "doc"},
            {"url": "demo://trm-labs-screen", "kind": "doc"},
            {"url": "demo://saylor-resource-census", "kind": "doc"},
            {"url": "demo://legacy-panel-2024", "kind": "doc",
             "fetched_at": ancient_iso(90)},
        ],
        price_usdc=5.0,
        provenance="graph-hacks-window",
        brief_id="brief-demo-001",
        # the lazy default is exercised on purpose here — and signs
        # for itself, on the record, not in the walls.
        load_bearing=False,
        relaxed_reason=("demo exercises the inherited default: one unmapped "
                        "claim so the weakest-link rule has something to price"),
        session_id="session-001",
    )
    c138 = claim_id_by_text(g, bid, "138M+")
    cagentic = claim_id_by_text(g, bid, "Only 0.6")
    c246 = claim_id_by_text(g, bid, "246 of")
    cclimb = claim_id_by_text(g, bid, "Agentic share")
    # Wake stakes her name on the two mapped claims AND the unmapped one —
    # the integrity query will price the unmapped one anyway.
    M.verify_claim(g, "Wake", c138)
    M.verify_claim(g, "Wake", cagentic)
    M.verify_claim(g, "Wake", cclimb)
    M.remember(g, "session-001", "fact",
               "Brief brief-demo-001 drafted on '%s'; 3 of 4 claims verified by Wake (incl. the unmapped one)." % topic,
               about_brief_id=bid)
    print("brief:", bid, "| claims: 4 | sources: 4 | Wake verified 3 "
          "(2 explicit-mapped, 1 unmapped)")

    # ---- 2. North reviews ----
    section("2. North reviews — the verdict edge carries what changed")
    rid = M.review_brief(
        g, "North", bid,
        verdict="approved_with_changes",
        changed="Tightened the demand figure: headline said 7.5%, body now carries the full 0.6-7.5% range.",
        changed_why="A single-point figure would overclaim; the range is what the (demo) sources support.",
    )
    # North verifies the remaining claim after the fix
    M.verify_claim(g, "North", c246)
    M.remember(g, "session-001", "decision",
               "North approved brief-demo-001 with changes; third claim verified by North post-fix.",
               about_brief_id=bid)
    print("review:", rid, "| verdict: approved_with_changes")

    # ---- 3. buyer pays; treasury edge ----
    section("3. buyer pays (x402/USDC, demo rail) — treasury sees it")
    pid = M.record_payment(g, "demo-buyer-01", bid, 5.0,
                           tx_hash="demo-tx-0xabc123")
    M.remember(g, "session-001", "fact",
               "5.0 USDC settled for brief-demo-001 (demo-tx-0xabc123); treasury credited.",
               about_brief_id=bid)
    print("payment:", pid, "| 5.0 USDC -> earn-first-treasury")

    # ---- handoff: Wake -> North ----
    M.handoff(g, "Wake", "North",
              "Session one done: brief delivered, paid, in the graph. "
              "Session two is yours to open — recall from the graph, not from me.",
              session_id="session-001")

    # ---- 4. session two: recall from the graph ----
    section("4. session two — recall from the graph, not from memory")
    M.record_session(g, "session-002", "recall",
                     notes="A new session. Nothing carried over except the graph.")
    M.join_session(g, "North", "session-002")
    print('query: everything we know about "%s", and who verified it\n' % topic)
    rows = M.everything_we_know(g, "x402 agentic")
    for r in rows:
        print("  CLAIM   :", r["claim"][:80])
        print("  status  :", r["claim_status"],
              "| verified by:", r["verified_by"], "| at:", r["verified_at"])
        print("  source  :", r["source"])
        print("  review  :", r["review_verdict"],
              "| changed:", (r["review_changed"] or "(nothing — recorded honestly)")[:80])
        print()

    # ---- 5. the integrity query ----
    section("5. the integrity query — the weakest-link rule fires")
    stale = M.stale_verifications(g, days=30)
    if stale:
        for s in stale:
            print("  STALE (inherited):", s["claim"][:70])
            print("    support_mode:", s["support_mode"],
                  "| effective freshness:", s["effective_freshness"])
    else:
        print("  none — every verification in this graph is fresh.")

    # ---- Company Brain: the ledger ----
    section("6. company brain — the treasury ledger")
    for e in M.treasury_ledger(g):
        print("  %s bought '%s' for %s USDC (tx %s)" %
              (e["buyer"], e["topic"][:50], e["usdc"], e["tx"]))

    section("demo complete — the graph remembers what the session forgets")
    print(json.dumps({"brief": bid, "review": rid, "payment": pid,
                      "claims_recalled": len(rows),
                      "stale_flagged": len(stale)}, indent=2))


if __name__ == "__main__":
    main()
