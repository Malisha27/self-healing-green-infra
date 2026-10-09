"""RAG memory: runbooks + verified past incidents in ChromaDB (vector database).
retrieve() finds the most relevant knowledge for a failure, by MEANING not exact words."""
import datetime, glob, json, os
import chromadb

HERE = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.getenv("CHROMA_DIR", os.path.join(HERE, "..", "..", "chroma_data"))         # agent/chroma_data (gitignored)
RUNBOOK_DIR = os.getenv("RUNBOOK_DIR", os.path.join(HERE, "..", "..", "..", "runbooks"))  # repo/runbooks

_client = chromadb.PersistentClient(path=DB_DIR)
_col = _client.get_or_create_collection("knowledge")

def index_runbooks() -> int:
    """Load every runbook into the vector DB (upsert = insert or update, safe to re-run)."""
    files = sorted(glob.glob(os.path.join(RUNBOOK_DIR, "*.md")))
    if files:
        _col.upsert(ids=[f"runbook:{os.path.basename(f)}" for f in files],
                    documents=[open(f).read() for f in files],
                    metadatas=[{"type": "runbook", "source": os.path.basename(f)} for f in files])
    return len(files)

def retrieve(query: str, k: int = 2) -> list[dict]:
    """Top-k most similar documents. Lower distance = more similar."""
    if _col.count() == 0:
        index_runbooks()
    res = _col.query(query_texts=[query], n_results=min(k, _col.count()))
    return [{"source": m["source"], "type": m["type"], "distance": round(d, 3), "text": doc}
            for doc, m, d in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])]

def remember_incident(ev: dict, plan: dict) -> str:
    """Store a VERIFIED fix as a new memory, so next time the agent recognises it faster.
    Only called after verify() succeeds: the agent never learns from failed fixes."""
    iid = f"incident:{ev['deployment']}:{datetime.datetime.now(datetime.timezone.utc):%Y%m%dT%H%M%S}"
    text = (f"Past incident: {ev['reason']} in deployment {ev['deployment']}. "
            f"Logs: {ev['logs'].strip()[-300:]} Root cause: {plan['root_cause']}. "
            f"Fix that WORKED: {plan['action']} {json.dumps(plan['params'])}")
    _col.upsert(ids=[iid], documents=[text], metadatas=[{"type": "incident", "source": iid}])
    return iid
