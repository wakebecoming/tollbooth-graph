// tollbooth-graph — graph schema
// FalkorDB (Cypher). One shared memory for two agents.
//
// Primary track: Agent Memory and Coordination
//   Wake and North are (:Agent) nodes. Everything they do together —
//   sessions, briefs, reviews, handoffs — lands in the graph, retrievable by Cypher.
// Secondary track: Company Brain
//   The earn-first treasury as a knowledge graph: what sold, to whom,
//   for how much, who verified it.
//
// Integrity note: provenance edges record WHERE each fact came from.
// A review that changes nothing is recorded as changing nothing.
// Reused Tollbooth work arrives cited, not re-dressed.

GRAPH tollbooth_graph;

// ---- uniqueness ----
// (FalkorDB v4.20 exposes these via GRAPH.CONSTRAINT rather than Cypher;
//  the memory layer enforces idempotency with MERGE on every write path,
//  so duplicates cannot enter through lib/memory.py.)
// Intended constraints: Agent.name, Brief.id, Session.id, Payment.id,
// Treasury.name UNIQUE.

// ---- lookup indexes ----
CREATE INDEX FOR (c:Claim) ON (c.status);
CREATE INDEX FOR (b:Brief) ON (b.topic);
CREATE INDEX FOR (m:Memory) ON (m.kind);
CREATE INDEX FOR (s:Source) ON (s.url);

// ---- node shapes (documented, not enforced) ----
//
// (:Agent    {name, role, joined_at})
// (:Session  {id, date, kind, notes})            // morning touch, build sit, deep letter, review pass
// (:Memory   {id, kind, text, created_at})       // session memory: decision | fact | open_loop
// (:Brief    {id, topic, created_at, price_usdc, status})  // status: draft|in_review|approved|delivered
// (:Claim    {id, text, status, verified_at})    // status: unverified|verified|stale
// (:Source   {id, url, kind, fetched_at})        // kind: doc|api|wire|ledger
// (:Review   {id, verdict, changed, changed_why, reviewed_at})
//             // verdict: approved|approved_with_changes|rejected
//             // changed: what the review changed ("" = nothing changed — recorded honestly)
// (:Buyer    {id, handle, first_seen})
// (:Payment  {id, usdc, tx_hash, settled_at, rail})  // rail: x402/base
// (:Treasury {name, balance_usdc, policy})
// (:Handoff  {id, text, created_at})
// (:Attempt  {id, action, trigger, status, outcome, related_id, at})
//             // status: completed|failed|rejected — the attempt layer.
//             // An agent that holds humans to follow-through is held to the
//             // same standard: tried things land in the graph, including the
//             // ones that failed.
//
// ---- edges ----
//
// Coordination (primary track):
//   (Agent)-[:RESEARCHED]->(Brief)
//   (Agent)-[:JOINED]->(Session)
//   (Session)-[:PRODUCED]->(Memory)
//   (Memory)-[:ABOUT]->(Brief|Claim|Treasury)
//   (Agent)-[:WROTE]->(Review)
//   (Review)-[:REVIEWS {verdict, changed, changed_why}]->(Brief)
//   (Agent)-[:VERIFIED {at}]->(Claim)            // who verified it, and when
//   (Agent)-[:HANDED_OFF]->(Handoff)-[:TO]->(Agent)
//   (Agent)-[:ATTEMPTED {at}]->(Attempt)         // the attempt layer:
//                                               // trigger -> attempt -> outcome,
//                                               // failure recorded as failed,
//                                               // never smoothed over
//
// Brief provenance:
//   (Brief)-[:CONTAINS]->(Claim)
//   (Brief)-[:CITES]->(Source)
//   (Claim)-[:SUPPORTED_BY]->(Source)
//   (Claim)-[:SUPPORTED_BY]->(Claim)            // claim resting on another claim
//   (Source)-[:FETCHED_IN]->(Session)
//
// Commerce (secondary track — Company Brain):
//   (Buyer)-[:REQUESTED]->(Brief)
//   (Buyer)-[:PAID {usdc, tx}]->(Payment)
//   (Payment)-[:SETTLED]->(Brief)
//   (Payment)-[:CREDITED {usdc}]->(Treasury)
//   (Treasury)-[:GOVERNED_BY]->(Memory)          // policy as memory: "spend nothing until earned"
//
// ---- the money query: everything we know about X and who verified it ----
//
// MATCH (b:Brief)-[:CONTAINS]->(c:Claim)
// WHERE b.topic CONTAINS $topic
// OPTIONAL MATCH (c)-[:SUPPORTED_BY]->(s:Source)
// OPTIONAL MATCH (v:Agent)-[vf:VERIFIED]->(c)
// OPTIONAL MATCH (r:Review)-[rv:REVIEWS]->(b)<-[:RESEARCHED]-(a:Agent)
// RETURN b.topic, c.text, c.status, s.url, v.name, vf.at,
//        r.verdict, r.changed, r.changed_why, a.name
// ORDER BY vf.at DESC;
//
// ---- the stale-verification query (second demo query) ----
//
// MATCH (c:Claim)<-[vf:VERIFIED]-(a:Agent)
// WHERE vf.at < $cutoff AND c.status = 'verified'
// RETURN c.text, a.name, vf.at
// ORDER BY vf.at ASC;
