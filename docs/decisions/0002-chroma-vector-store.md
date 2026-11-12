# ADR 0002: Use Chroma as a local, persistent vector store

- Status: Accepted
- Date: 2026-11-12

## Context

Retrieval needs a vector index over a small knowledge base: about a dozen documents and fewer than a hundred chunks. Options considered:

- **Managed vector databases** (for example Pinecone or a cloud vector search service): another account, network dependency and cost, all unnecessary at this scale.
- **PostgreSQL with pgvector**: solid, but adds a database server to operate.
- **In-memory NumPy search**: the simplest, but has no persistence or metadata filtering, and needs custom code for upserts and deletes.
- **Chroma in persistent local mode**: an embedded library that stores data in a directory, supports metadata, upsert and delete, and offers cosine distance.

## Decision

Use Chroma (`chromadb.PersistentClient`) with one collection, `knowledge_base`, stored under `DATA_DIR/chroma` on a Docker volume.

- The collection is created with `hnsw:space = cosine`. Distances are converted to similarity (`1 - distance`) before they are compared with `RETRIEVAL_MIN_SCORE`.
- Embeddings come from Gemini, not from Chroma's built-in embedding function, so no local model is downloaded.
- The collection metadata records the embedding model and dimension. If either changes, ingestion and bot startup fail with a clear message until `support-bot-ingest --rebuild` is run.
- Chunk ids are content hashes, so re-running ingestion is idempotent.

## Consequences

- Nothing extra to run or pay for, and a fast local query path.
- The index lives on one host. Running several bot replicas would need a Chroma server or another shared store.
- Chroma is a fast-moving dependency, so the lockfile pins it and upgrades should be followed by a re-ingest and an eval run.
