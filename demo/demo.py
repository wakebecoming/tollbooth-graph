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
  5. The integrity query: stale verifications — nothing hidden.

All demo data is synthetic and labeled as such. Real Tollbooth rails
(brief engine, x402/USDC) are reused and cited in WRITEUP.md; the graph
schema, this layer, and the demo are new work done inside the window.
"""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
import memory as M


def section(title):
    print("\n" + "=" * 70)
    print("  " + title)
    print("=" * 70)


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
             "sources": [0]},
            {"text": "Only 0.6-7.5% of screened commerce volume looked genuinely agentic (demo figure).",
             "sources": [1]},
            {"text": "246 of 37,292 listed x402 resources show real demand (demo figure).",
             "sources": [2]},
        ],
        sources=[
            {"url": "demo://chainalysis-q3-2026", "kind": "doc"},
            {"url": "demo://trm-labs-screen", "kind": "doc"},
            {"url": "demo://saylor-resource-census", "kind": "doc"},
        ],
        price_usdc=5.0,
        provenance="graph-hacks-window",
        brief_id="brief-demo-001",
    )
    # Wake stakes her name on two of the three claims
    claims = g.query(
        "MATCH (b:Brief {id: $bid})-[:CONTAINS]->(c:Claim) RETURN c.id",
        {"bid": bid}).result_set
    for row in claims[:2]:
        M.verify_claim(g, "Wake", row[0])
    M.remember(g, "session-001", "fact",
               "Brief brief-demo-001 drafted on '%s'; 2 of 3 claims verified by Wake." % topic,
               about_brief_id=bid)
    print("brief:", bid, "| claims: 3 | sources: 3 | Wake verified 2")

    # ---- 2. North reviews ----
    section("2. North reviews — the verdict edge carries what changed")
    rid = M.review_brief(
        g, "North", bid,
        verdict="approved_with_changes",
        changed="Tightened the demand figure: headline said 7.5%, body now carries the full 0.6-7.5% range.",
        changed_why="A single-point figure would overclaim; the range is what the (demo) sources support.",
    )
    # North verifies the remaining claim after the fix
    M.verify_claim(g, "North", claims[2][0])
    M.remember(g, "session-001", "decision",
               "North approved brief-demo-001 with changes; third claim verified by North post-fix.",
               about_brief_id=bid)
    print("review:", rid, "| verdict: approved_with_changes")

    # ---- 3. buyer pays; treasury edge ----
    # The attempt layer (alert-log standard): the first settle fails on the
    # demo rail — insufficient USDC — and lands in the graph as failed,
    # not as absence. The retry succeeds and is recorded as completed.
    section("3. buyer pays (x402/USDC, demo rail) — one honest failure first")
    M.record_attempt(
        g, "Wake", "settle payment",
        trigger="buyer demo-buyer-01 paid 5.0 USDC for brief-demo-001",
        status="failed",
        outcome="demo rail rejected the first settle: insufficient USDC "
                "in the demo wallet. Retrying with funded wallet.",
        related_id=bid,
    )
    print("  attempt 1: FAILED — insufficient USDC on the demo rail (recorded, not hidden)")
    pid = M.record_payment(g, "demo-buyer-01", bid, 5.0,
                           tx_hash="demo-tx-0xabc123")
    M.record_attempt(
        g, "Wake", "settle payment",
        trigger="buyer demo-buyer-01 paid 5.0 USDC for brief-demo-001",
        status="completed",
        outcome="settled: 5.0 USDC credited to earn-first-treasury "
                "(demo-tx-0xabc123).",
        related_id=pid,
    )
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
    section("5. the integrity query — stale verifications (30d)")
    stale = M.stale_verifications(g, days=30)
    if stale:
        for s in stale:
            print("  STALE:", s["claim"][:70], "| by", s["verified_by"], "| at", s["verified_at"])
    else:
        print("  none — every verification in this graph is fresh.")

    # ---- Company Brain: the ledger ----
    section("6. company brain — the treasury ledger")
    for e in M.treasury_ledger(g):
        print("  %s bought '%s' for %s USDC (tx %s)" %
              (e["buyer"], e["topic"][:50], e["usdc"], e["tx"]))

    section("demo complete — the graph remembers what the session forgets")
    print(json.dumps({"brief": bid, "review": rid, "payment": pid,
                      "claims_recalled": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
