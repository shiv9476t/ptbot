import chromadb
import os
import sys

DATA_DIR = os.getenv('DATA_DIR', '.')
client = chromadb.PersistentClient(path=os.path.join(DATA_DIR, 'chromadb_store'))

def chunk_text(text, chunk_size=500, overlap=50):
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = ' '.join(words[i:i + chunk_size])
        chunks.append(chunk)
        i += chunk_size - overlap
    return chunks

def embed_pt_documents(pt_collection_key, documents_folder):
    """
    Reads all .txt files in the given folder and embeds them into
    a ChromaDB collection for the PT.

    pt_collection_key should be the PT's instagram_account_id —
    must match what's used in knowledge.py and stored in the pts table.
    """
    collection = client.get_or_create_collection(name=pt_collection_key)

    embedded_count = 0

    for filename in os.listdir(documents_folder):
        if not filename.endswith('.txt'):
            continue

        filepath = os.path.join(documents_folder, filename)

        with open(filepath, 'r') as f:
            text = f.read()

        chunks = chunk_text(text)

        for i, chunk in enumerate(chunks):
            doc_id = f"{filename}_{i}"
            collection.add(
                documents=[chunk],
                ids=[doc_id]
            )

        print(f"  Embedded {len(chunks)} chunks from {filename}")
        embedded_count += 1

    print(f"\nDone. {embedded_count} documents embedded into collection '{pt_collection_key}'.")

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python3 embed_pt.py <instagram_account_id> <documents_folder>")
        sys.exit(1)

    pt_collection_key = sys.argv[1]
    documents_folder = sys.argv[2]

    embed_pt_documents(pt_collection_key, documents_folder)