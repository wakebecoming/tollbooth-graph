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
                brief_id=None, load_bearing=True, relaxed_reason=None,
                session_id=None):
    """
    claims:  list of {"text": ...} — a claim may name its source indexes
             explicitly ({"text": ..., "sources": [0, 2]}). A claim may
             also carry "load_bearing": True — such claims require
             explicit non-empty sources even inside a relaxed brief.
    sources: list of {"url": ..., "kind": ...} — a source may carry
             "fetched_at" to override the now-stamp (demo: ancient sources).
    load_bearing: default True. When True, raise unless EVERY claim names
             its source indexes explicitly and non-emptily. Structure is
             the default; scaffolding has to sign for itself: to relax,
             pass load_bearing=False WITH a non-empty relaxed_reason —
             the reason lands on the Brief node, so the laziness is on
             the record, not in the walls.
    session_id: when given, each source gets (Source)-[:FETCHED_IN]->(Session).
    Creates the brief, its claims, its sources, and the full
    provenance web: RESEARCHED, CONTAINS, CITES, SUPPORTED_BY.
    The choice of support mapping is recorded on each Claim node as
    support_mode ('explicit' | 'inherited') plus the support_indexes used —
    explicit [0, 2] and default-to-everything no longer look identical.
    """
    if not load_bearing and not relaxed_reason:
        raise ValueError(
            "load_bearing=False requires a non-empty relaxed_reason: "
            "the inherited default has to sign for itself.")
    # validate the support mapping BEFORE writing anything
    for i, c in enumerate(claims):
        idxs = c.get("sources")
        must_map = load_bearing or c.get("load_bearing")
        if must_map and not idxs:
            raise ValueError(
                "load_bearing brief requires explicit non-empty \"sources\" "
                "on every claim; claim %d (%r) has none"
                % (i, c.get("text", "")[:60]))
        for j in (idxs if idxs is not None else []):
            if not 0 <= j < len(sources):
                raise ValueError(
                    "claim %d (%r) names source index %d, but only %d "
                    "sources were cited" % (i, c.get("text", "")[:60],
                                            j, len(sources)))
    bid = brief_id or ("brief-" + uuid.uuid4().hex[:8])
    g.query(
        "MATCH (a:Agent {name: $agent}) "
        "CREATE (a)-[:RESEARCHED]->(b:Brief {id: $bid, topic: $topic, "
        "created_at: $at, price_usdc: $price, status: 'draft', "
        "provenance: $prov, load_bearing: $lb, "
        "mapping_relaxed_reason: $reason})",
        {"agent": agent_name, "bid": bid, "topic": topic,
         "at": now_iso(), "price": price_usdc, "prov": provenance,
         "lb": load_bearing, "reason": relaxed_reason or ""},
    )
    claim_ids = []
    for c in claims:
        cid = "claim-" + uuid.uuid4().hex[:8]
        claim_ids.append(cid)
        mode = "explicit" if "sources" in c else "inherited"
        idxs = list(c["sources"]) if "sources" in c else list(range(len(sources)))
        g.query(
            "MATCH (b:Brief {id: $bid}) "
            "CREATE (b)-[:CONTAINS]->(c:Claim {id: $cid, text: $text, "
            "status: 'unverified', support_mode: $mode, "
            "support_indexes: $sidx, claim_load_bearing: $clb})",
            {"bid": bid, "cid": cid, "text": c["text"],
             "mode": mode, "sidx": idxs,
             "clb": bool(c.get("load_bearing"))},
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
             "kind": s.get("kind", "doc"),
             "at": s.get("fetched_at", now_iso())},
        )
    if session_id:
        for sid in source_ids:
            g.query(
                "MATCH (s:Source {id: $sid}), (sess:Session {id: $sess}) "
                "MERGE (s)-[:FETCHED_IN]->(sess)",
                {"sid": sid, "sess": session_id},
            )
    # support mapping: the choice is already validated above; here we
    # materialize the edges. 'inherited' claims rest on every cited source.
    for i, c in enumerate(claims):
        idxs = list(c["sources"]) if "sources" in c else list(range(len(source_ids)))
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
        "SET v.at = $at, "
        "c.status = 'verified', c.verified_at = $at",
        # re-staking refreshes the edge too: the stale query reads v.at,
        # so that is where the truth has to live.
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
        "CREATE (a)-[:WROTE]->(r:Review {id: $rid, reviewed_at: $at})"
        "-[:REVIEWS {verdict: $verdict, changed: $changed, "
        "changed_why: $why}]->(b) "
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
        "c.status AS claim_status, c.claim_load_bearing AS claim_load_bearing, "
        "s.url AS source, b.load_bearing AS brief_load_bearing, "
        "b.mapping_relaxed_reason AS mapping_relaxed_reason, "
        "v.name AS verified_by, vf.at AS verified_at, "
        "a.name AS researched_by, rv.verdict AS review_verdict, "
        "rv.changed AS review_changed, rv.changed_why AS review_why "
        "ORDER BY verified_at DESC",
        {"topic": topic},
    )
    cols = ["topic", "brief", "claim", "claim_status", "claim_load_bearing",
           "source", "brief_load_bearing", "mapping_relaxed_reason",
            "verified_by", "verified_at", "researched_by",
            "review_verdict", "review_changed", "review_why"]
    return [dict(zip(cols, row)) for row in res.result_set]


def effective_freshness(g, claim_id):
    """Earliest freshness timestamp across a claim's transitive support web:
    the min of VERIFIED edge times (on the claim itself and any claim it
    rests on — the schema allows claim-on-claim SUPPORTED_BY) and Source
    fetched_at. ISO 'Z' stamps compare lexicographically. None if the web
    carries no timestamps."""
    res = g.query(
        "MATCH (c:Claim {id: $cid})-[:SUPPORTED_BY*1..]->(sc:Claim) "
        "RETURN DISTINCT sc.id",
        {"cid": claim_id})
    web_claims = [claim_id] + [r[0] for r in res.result_set]
    res = g.query(
        "MATCH (c:Claim {id: $cid})-[:SUPPORTED_BY*1..]->(s:Source) "
        "RETURN DISTINCT s.fetched_at",
        {"cid": claim_id})
    fetched = [r[0] for r in res.result_set if r[0]]
    res = g.query(
        "MATCH (:Agent)-[vf:VERIFIED]->(sc:Claim) "
        "WHERE sc.id IN $ids RETURN min(vf.at)",
        {"ids": web_claims})
    verified = res.result_set[0][0] if res.result_set else None
    stamps = [t for t in fetched + ([verified] if verified else []) if t]
    return min(stamps) if stamps else None


def stale_verifications(g, days=30):
    """The integrity query: claims whose *effective* freshness is older than
    `days`. Effective freshness is the min over VERIFIED edge times and
    Source fetched_at across the claim's transitive support web — so an
    unmapped ('inherited') claim resting on everything inherits the
    weakest timestamp it rests on. Unverified claims are excluded:
    unverified is not stale, it is a different honesty. Returns the
    effective freshness per claim so the demo can show the number."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)
              ).strftime("%Y-%m-%dT%H:%M:%SZ")
    res = g.query(
        "MATCH (c:Claim) WHERE c.status = 'verified' "
        "RETURN c.id, c.text, c.support_mode",
        {})
    out = []
    for cid, text, mode in res.result_set:
        eff = effective_freshness(g, cid)
        if eff and eff < cutoff:
            out.append({"claim": text, "claim_id": cid,
                        "support_mode": mode or "unknown",
                        "effective_freshness": eff})
    return sorted(out, key=lambda d: d["effective_freshness"])


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
