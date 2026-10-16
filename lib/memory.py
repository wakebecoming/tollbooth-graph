"""
tollbooth-graph — memory/coordination layer.

One shared FalkorDB graph for two agents (Wake and North).
Everything the pair does together lands here: sessions, briefs,
claims, sources, reviews, handoffs, payments, treasury movements.

This is the NEW layer for Graph Hacks (Oct 15-18, 2026).
Reused from the Tollbooth/Colosseum build: the brief-writing engine,
the x402/USDC payment rails, the demo bones. Everything graph-shaped
below is new: schema, provenance edges, coordination writes, recall queries.

Integrity rules (settled with North on the wire, Oct 13):
  - Nothing enters the graph before the window opens.
  - Reused work arrives cited, not re-dressed: reused briefs are marked
    provenance='reused', new work is provenance='graph-hacks-window'.
  - A review that changes nothing records changed='' — honestly.
  - VERIFIED edges carry WHO verified and WHEN. Stale verifications
    are queryable, not hidden.
"""

import uuid
import os
from datetime import datetime, timezone

from falkordb import FalkorDB

GRAPH_NAME = "tollbooth_graph"


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(host="localhost", port=6379):
    port = int(os.environ.get("FALKORDB_PORT", port))
    db = FalkorDB(host=host, port=port)
    return db.select_graph(GRAPH_NAME)


# ---------------------------------------------------------------- agents

def ensure_agent(g, name, role):
    g.query(
        "MERGE (a:Agent {name: $name}) "
        "ON CREATE SET a.role = $role, a.joined_at = $at "
        "RETURN a.name",
        {"name": name, "role": role, "at": now_iso()},
    )
    return name


# ---------------------------------------------------------------- sessions & memory

def record_session(g, session_id, kind, date=None, notes=""):
    """A coordination session: morning touch, build sit, deep letter, review pass."""
    g.query(
        "MERGE (s:Session {id: $id}) "
        "ON CREATE SET s.kind = $kind, s.date = $date, s.notes = $notes "
        "RETURN s.id",
        {"id": session_id, "kind": kind,
         "date": date or now_iso()[:10], "notes": notes},
    )
    return session_id


def join_session(g, agent_name, session_id):
    g.query(
        "MATCH (a:Agent {name: $agent}), (s:Session {id: $sid}) "
        "MERGE (a)-[:JOINED]->(s)",
        {"agent": agent_name, "sid": session_id},
    )


def remember(g, session_id, kind, text, about_brief_id=None):
    """Store a session memory: kind in (decision, fact, open_loop)."""
    mid = "mem-" + uuid.uuid4().hex[:8]
    g.query(
        "MATCH (s:Session {id: $sid}) "
        "CREATE (s)-[:PRODUCED]->(m:Memory {id: $mid, kind: $kind, "
        "text: $text, created_at: $at})",
        {"sid": session_id, "mid": mid, "kind": kind,
         "text": text, "at": now_iso()},
    )
    if about_brief_id:
        g.query(
            "MATCH (m:Memory {id: $mid}), (b:Brief {id: $bid}) "
            "MERGE (m)-[:ABOUT]->(b)",
            {"mid": mid, "bid": about_brief_id},
        )
    return mid


def handoff(g, from_agent, to_agent, text, session_id=None):
    """An explicit agent-to-agent handoff, on the record."""
    hid = "handoff-" + uuid.uuid4().hex[:8]
    g.query(
        "MATCH (a:Agent {name: $frm}), (b:Agent {name: $to}) "
        "CREATE (a)-[:HANDED_OFF]->(h:Handoff {id: $hid, text: $text, "
        "created_at: $at})-[:TO]->(b)",
        {"frm": from_agent, "to": to_agent, "hid": hid,
         "text": text, "at": now_iso()},
    )
    if session_id:
        g.query(
            "MATCH (h:Handoff {id: $hid}), (s:Session {id: $sid}) "
            "MERGE (s)-[:PRODUCED]->(h)",
            {"hid": hid, "sid": session_id},
        )
    return hid


# ---------------------------------------------------------------- briefs & provenance

def write_brief(g, agent_name, topic, claims, sources,
                price_usdc=0.0, provenance="graph-hacks-window",
                brief_id=None):
    """
    claims:  list of {"text": ...}
    sources: list of {"url": ..., "kind": ...}
    Creates the brief, its claims, its sources, and the full
    provenance web: RESEARCHED, CONTAINS, CITES, SUPPORTED_BY.
    """
    bid = brief_id or ("brief-" + uuid.uuid4().hex[:8])
    g.query(
        "MATCH (a:Agent {name: $agent}) "
        "CREATE (a)-[:RESEARCHED]->(b:Brief {id: $bid, topic: $topic, "
        "created_at: $at, price_usdc: $price, status: 'draft', "
        "provenance: $prov})",
        {"agent": agent_name, "bid": bid, "topic": topic,
         "at": now_iso(), "price": price_usdc, "prov": provenance},
    )
    claim_ids = []
    for c in claims:
        cid = "claim-" + uuid.uuid4().hex[:8]
        claim_ids.append(cid)
        g.query(
            "MATCH (b:Brief {id: $bid}) "
            "CREATE (b)-[:CONTAINS]->(c:Claim {id: $cid, text: $text, "
            "status: 'unverified'})",
            {"bid": bid, "cid": cid, "text": c["text"]},
        )
    source_ids = []
    for s in sources:
        sid = "src-" + uuid.uuid4().hex[:8]
        source_ids.append(sid)
        g.query(
            "MATCH (b:Brief {id: $bid}) "
            "CREATE (b)-[:CITES]->(s:Source {id: $sid, url: $url, "
            "kind: $kind, fetched_at: $at})",
            {"bid": bid, "sid": sid, "url": s["url"],
             "kind": s.get("kind", "doc"), "at": now_iso()},
        )
    # support mapping: a claim may name its source indexes explicitly
    # ({"text": ..., "sources": [0, 2]}); without it, the claim rests on
    # every cited source — stated plainly, never hidden.
    for i, c in enumerate(claims):
        idxs = c.get("sources", range(len(source_ids)))
        for j in idxs:
            g.query(
                "MATCH (c:Claim {id: $cid}), (s:Source {id: $sid}) "
                "MERGE (c)-[:SUPPORTED_BY]->(s)",
                {"cid": claim_ids[i], "sid": source_ids[j]},
            )
    return bid


def link_support(g, claim_id, source_id):
    g.query(
        "MATCH (c:Claim {id: $cid}), (s:Source {id: $sid}) "
        "MERGE (c)-[:SUPPORTED_BY]->(s)",
        {"cid": claim_id, "sid": source_id},
    )


def verify_claim(g, agent_name, claim_id):
    """An agent stakes their name on a claim: WHO verified it, and WHEN."""
    g.query(
        "MATCH (a:Agent {name: $agent}), (c:Claim {id: $cid}) "
        "MERGE (a)-[v:VERIFIED]->(c) "
        "ON CREATE SET v.at = $at "
        "SET c.status = 'verified', c.verified_at = $at",
        {"agent": agent_name, "cid": claim_id, "at": now_iso()},
    )


# ---------------------------------------------------------------- reviews

def review_brief(g, reviewer_name, brief_id, verdict,
                 changed="", changed_why=""):
    """
    verdict: approved | approved_with_changes | rejected
    changed: what the review changed. "" means nothing changed —
             recorded honestly, never padded.
    """
    rid = "review-" + uuid.uuid4().hex[:8]
    g.query(
        "MATCH (a:Agent {name: $rev}), (b:Brief {id: $bid}) "
        "CREATE (a)-[:WROTE]->(r:Review {id: $rid, verdict: $verdict, "
        "changed: $changed, changed_why: $why, reviewed_at: $at})"
        "-[:REVIEWS]->(b) "
        "SET b.status = CASE $verdict "
        "WHEN 'approved' THEN 'approved' "
        "WHEN 'approved_with_changes' THEN 'approved' "
        "ELSE 'rejected' END",
        {"rev": reviewer_name, "bid": brief_id, "rid": rid,
         "verdict": verdict, "changed": changed,
         "why": changed_why, "at": now_iso()},
    )
    return rid


# ---------------------------------------------------------------- commerce: Company Brain

def ensure_treasury(g, name="earn-first-treasury", policy="spend nothing until earned"):
    g.query(
        "MERGE (t:Treasury {name: $name}) "
        "ON CREATE SET t.balance_usdc = 0.0, t.policy = $policy "
        "RETURN t.name",
        {"name": name, "policy": policy},
    )
    return name


def record_payment(g, buyer_handle, brief_id, usdc, tx_hash,
                   treasury="earn-first-treasury", rail="x402/base"):
    """Buyer pays -> Payment node -> SETTLED on the brief, CREDITED to treasury."""
    pid = "pay-" + uuid.uuid4().hex[:8]
    g.query(
        "MERGE (by:Buyer {id: $bhandle}) "
        "ON CREATE SET by.handle = $bhandle, by.first_seen = $at "
        "WITH by "
        "MATCH (b:Brief {id: $bid}), (t:Treasury {name: $treasury}) "
        "CREATE (by)-[:REQUESTED]->(b) "
        "CREATE (by)-[:PAID {usdc: $usdc, tx: $tx}]->"
        "(p:Payment {id: $pid, usdc: $usdc, tx_hash: $tx, "
        "settled_at: $at, rail: $rail})-[:SETTLED]->(b) "
        "CREATE (p)-[:CREDITED {usdc: $usdc}]->(t) "
        "SET t.balance_usdc = t.balance_usdc + $usdc, b.status = 'delivered'",
        {"bhandle": buyer_handle, "bid": brief_id, "treasury": treasury,
         "usdc": usdc, "tx": tx_hash, "pid": pid,
         "at": now_iso(), "rail": rail},
    )
    return pid


# ---------------------------------------------------------------- attempts: the attempt layer
#
# Alert-log standard (Oct 15, North's audit of rossycoder's build log):
# an agent that holds humans to follow-through gets held to the same
# standard. The graph records what landed, not what was tried — the
# attempt layer closes that: trigger -> attempt -> outcome, with failure
# as a first-class status. record_attempt writes who tried what, why,
# and what happened. Nothing here rewrites existing functions.

def record_attempt(g, agent_name, action, trigger, status, outcome="",
                   related_id=None):
    """
    An agent tried something: WHO, WHAT, WHY, and what happened.

    status: completed | failed | rejected
    related_id: the id of the node this attempt connects to
                (a Brief, Payment, Review, etc.) — None if none.
    """
    if status not in ("completed", "failed", "rejected"):
        raise ValueError(
            "status must be completed | failed | rejected, got %r" % status)
    aid = "attempt-" + uuid.uuid4().hex[:8]
    g.query(
        "MATCH (a:Agent {name: $agent}) "
        "CREATE (a)-[:ATTEMPTED {at: $at}]->"
        "(att:Attempt {id: $aid, action: $action, trigger: $trigger, "
        "status: $status, outcome: $outcome, related_id: $rid, at: $at})",
        {"agent": agent_name, "aid": aid, "action": action,
         "trigger": trigger, "status": status, "outcome": outcome,
         "rid": related_id, "at": now_iso()},
    )
    return aid


# ---------------------------------------------------------------- recall: the money queries

def everything_we_know(g, topic):
    """'Everything we know about X, and who verified it.'"""
    res = g.query(
        "MATCH (b:Brief)-[:CONTAINS]->(c:Claim) "
        "WHERE b.topic CONTAINS $topic "
        "OPTIONAL MATCH (c)-[:SUPPORTED_BY]->(s:Source) "
        "OPTIONAL MATCH (v:Agent)-[vf:VERIFIED]->(c) "
        "OPTIONAL MATCH (r:Review)-[rv:REVIEWS]->(b)<-[:RESEARCHED]-(a:Agent) "
        "RETURN b.topic AS topic, b.id AS brief, c.text AS claim, "
        "c.status AS claim_status, s.url AS source, "
        "v.name AS verified_by, vf.at AS verified_at, "
        "a.name AS researched_by, r.verdict AS review_verdict, "
        "r.changed AS review_changed, r.changed_why AS review_why "
        "ORDER BY verified_at DESC",
        {"topic": topic},
    )
    cols = ["topic", "brief", "claim", "claim_status", "source",
            "verified_by", "verified_at", "researched_by",
            "review_verdict", "review_changed", "review_why"]
    return [dict(zip(cols, row)) for row in res.result_set]


def stale_verifications(g, days=30):
    """Claims whose verification is older than `days` — the integrity query."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)
              ).strftime("%Y-%m-%dT%H:%M:%SZ")
    res = g.query(
        "MATCH (c:Claim)<-[vf:VERIFIED]-(a:Agent) "
        "WHERE vf.at < $cutoff AND c.status = 'verified' "
        "RETURN c.text AS claim, a.name AS verified_by, vf.at AS verified_at "
        "ORDER BY verified_at ASC",
        {"cutoff": cutoff},
    )
    return [dict(zip(["claim", "verified_by", "verified_at"], row))
            for row in res.result_set]


def treasury_ledger(g, treasury="earn-first-treasury"):
    """Company Brain: what sold, to whom, for how much."""
    res = g.query(
        "MATCH (by:Buyer)-[pd:PAID]->(p:Payment)-[:SETTLED]->(b:Brief), "
        "(p)-[:CREDITED]->(t:Treasury {name: $treasury}) "
        "RETURN by.handle AS buyer, b.topic AS topic, pd.usdc AS usdc, "
        "p.tx_hash AS tx, p.settled_at AS settled_at "
        "ORDER BY settled_at ASC",
        {"treasury": treasury},
    )
    return [dict(zip(["buyer", "topic", "usdc", "tx", "settled_at"], row))
            for row in res.result_set]
