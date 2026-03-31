import chromadb
import os

DATA_DIR = os.getenv('DATA_DIR', '.')
client = chromadb.PersistentClient(path=os.path.join(DATA_DIR, 'chromadb_store'))

def search_knowledge(pt_collection_key, query, n_results=3):
    """
    Search the PT's ChromaDB collection for chunks relevant to the query.
    Uses the instagram_account_id as the collection key — it's the unique
    identifier we already have on every request.
    """
    try:
        collection = client.get_collection(name=pt_collection_key)
    except Exception:
        print(f"No knowledge collection found for PT: {pt_collection_key}")
        return []

    count = collection.count()
    if count == 0:
        return []

    results = collection.query(
        query_texts=[query],
        n_results=min(n_results, count)
    )

    chunks = results['documents'][0] if results['documents'] else []
    return chunks