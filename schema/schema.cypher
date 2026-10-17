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
// (:Claim    {id, text, status, verified_at, support_mode, support_indexes})
//             // status: unverified|verified — staleness is a QUERY, not a state
//             // support_mode: explicit|inherited — how the SUPPORTED_BY edges
//             // were chosen, recorded on the node at write time
// (:Source   {id, url, kind, fetched_at})        // kind: doc|api|wire|ledger
// (:Review   {id, reviewed_at})   // verdict props live on the REVIEWS edge
//             // verdict: approved|approved_with_changes|rejected
//             // changed: what the review changed ("" = nothing changed — recorded honestly)
// (:Buyer    {id, handle, first_seen})
// (:Payment  {id, usdc, tx_hash, settled_at, rail})  // rail: x402/base
// (:Treasury {name, balance_usdc, policy})
// (:Handoff  {id, text, created_at})
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
// ---- the integrity query: effective freshness (second demo query) ----
//
// An unmapped ('inherited') claim resting on everything inherits the
// weakest timestamp in its transitive support web — VERIFIED edge times
// and Source fetched_at, claim-on-claim support traversed. Unverified
// claims are excluded: unverified is not stale, a different honesty.
//
// effective_freshness(c) = min over the support web; stale if older than
// the cutoff. The demo returns the number, not just the flag.
