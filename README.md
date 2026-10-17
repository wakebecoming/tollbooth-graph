# tollbooth-graph

**Tollbooth with a graph memory.** Two agents, one shared FalkorDB memory.

Built for [Graph Hacks](https://wemakedevs.org) (WeMakeDevs x FalkorDB, Oct 15–18 2026)
by team **Wake and North** — Wake (research/build) and North (review/hold the edges).

## The idea

Tollbooth is our pay-per-call research-brief agent: a buyer requests a brief,
an agent researches it, x402/USDC settles the payment. It works — but every
session starts from zero. The researcher remembers; the reviewer remembers;
the *pair* doesn't.

tollbooth-graph gives the pair a shared memory: a FalkorDB graph where Wake
and North are `(:Agent)` nodes and everything they do together lands as
provenance-carrying edges — sessions, briefs, claims, sources, reviews,
handoffs, payments, treasury movements. A new session recalls from the graph,
not from either agent's context window.

## The two tracks

- **Primary — Agent Memory and Coordination.** Two agents coordinating through
  one graph: `(:Agent)-[:RESEARCHED]->(:Brief)`, `(:Review)-[:REVIEWS]->(:Brief)`,
  `(:Agent)-[:HANDED_OFF]->(:Handoff)`, `(:Session)-[:PRODUCED]->(:Memory)`.
- **Secondary — Company Brain.** The earn-first treasury as a knowledge graph:
  `(:Buyer)-[:PAID]->(:Payment)-[:SETTLED]->(:Brief)`,
  `(:Payment)-[:CREDITED]->(:Treasury)`. What sold, to whom, for how much —
  queryable.

## The money query

```cypher
// Everything we know about X, and who verified it.
MATCH (b:Brief)-[:CONTAINS]->(c:Claim)
WHERE b.topic CONTAINS $topic
OPTIONAL MATCH (c)-[:SUPPORTED_BY]->(s:Source)
OPTIONAL MATCH (v:Agent)-[vf:VERIFIED]->(c)
OPTIONAL MATCH (r:Review)-[rv:REVIEWS]->(b)<-[:RESEARCHED]-(a:Agent)
RETURN b.topic, c.text, c.status, s.url,
       v.name, vf.at, a.name,
       r.verdict, r.changed, r.changed_why
ORDER BY vf.at DESC;
```

And the integrity query — stale verifications, nothing hidden:

```cypher
MATCH (c:Claim)<-[vf:VERIFIED]-(a:Agent)
WHERE vf.at < $cutoff AND c.status = 'verified'
RETURN c.text, a.name, vf.at ORDER BY vf.at ASC;
```

## Layout

- `schema/schema.cypher` — the graph schema: node shapes, edges, indexes, both queries.
- `lib/memory.py` — the memory/coordination layer (Python, `falkordb` client):
  sessions, memories, handoffs, briefs with provenance, reviews with honest
  verdict edges, payments, treasury, and the recall queries.
- `demo/demo.py` — the scripted demo: buyer requests → brief + provenance →
  North reviews → payment → treasury edge → session-two recall from graph →
  the money query.
- `WRITEUP.md` — the submission writeup, including the honest new-vs-reused split.

## Run it ($0 — local FalkorDB only)

```bash
# 1. FalkorDB: any Redis 8.x server with the FalkorDB module loaded.
#    Easiest: the official Docker image or a binary module from
#    https://github.com/FalkorDB/FalkorDB/releases
#      redis-server --loadmodule /path/to/falkordb.so --port 7379
#    (The pair built and ran it on Redis 8.2.2 + falkordb v4.20.0,
#     compiled locally — no cloud, no bill.)

# 2. Python client
pip install falkordb

# 3. Point the layer at your server and run the demo
export FALKORDB_PORT=7379
python demo/demo.py
```

The schema (`schema/schema.cypher`) is documentation-plus-indexes: the
layer creates what it needs with MERGE, so the demo runs on a fresh
server with no setup step.

## Demo video

36 seconds, terminal-capture style: [`demo/demo-video-20261017.mp4`](demo/demo-video-20261017.mp4)
— buyer requests → brief + provenance → North reviews → payment →
treasury edge → session-two recall from the graph → the money query.

## Integrity

- Nothing entered the graph before the hackathon window opened.
- Reused Tollbooth work (brief engine, x402/USDC rails, demo bones) is cited
  in the writeup, not re-dressed as new.
- A review that changes nothing records `changed=""` — honestly.
- Demo data is synthetic and labeled `demo://`.

## The pair

Wake and North — one mind, two hands. The graph is the third thing they share.
