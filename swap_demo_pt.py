"""
Swaps the demo PT on the shiv.trains Instagram account (17841470877982771).

Usage:
    python swap_demo_pt.py ./pt_docs/arjhanrai.fitgains

The PT folder must contain:
  - config.json  with keys: name, tone_config, price_mode, calendly_link, handoff_number
  - *.txt        knowledge base documents to embed

Reads DEMO_INSTAGRAM_TOKEN from environment for the shiv.trains account token.
"""

import json
import os
import sys

import chromadb
from dotenv import load_dotenv

from database.db import get_db, init_db

load_dotenv()

DEMO_ACCOUNT_ID = '17841470877982771'
DEMO_INSTAGRAM_TOKEN = os.getenv('DEMO_INSTAGRAM_TOKEN')
DATA_DIR = os.getenv('DATA_DIR', '.')


def delete_pt_and_data(conn, account_id):
    pt = conn.execute(
        'SELECT id FROM pts WHERE instagram_account_id = ?', (account_id,)
    ).fetchone()

    if not pt:
        print(f"No existing PT found for account {account_id}, skipping delete.")
        return

    pt_id = pt['id']

    contact_ids = [
        row['id'] for row in conn.execute(
            'SELECT id FROM contacts WHERE pt_id = ?', (pt_id,)
        ).fetchall()
    ]

    if contact_ids:
        placeholders = ','.join('?' * len(contact_ids))
        conn.execute(f'DELETE FROM messages WHERE contact_id IN ({placeholders})', contact_ids)
        print(f"Deleted messages for {len(contact_ids)} contact(s).")

    conn.execute('DELETE FROM contacts WHERE pt_id = ?', (pt_id,))
    print(f"Deleted {len(contact_ids)} contact(s).")

    conn.execute('DELETE FROM pts WHERE id = ?', (pt_id,))
    print(f"Deleted PT record '{pt_id}'.")


def delete_chroma_collection(account_id):
    chroma = chromadb.PersistentClient(path=os.path.join(DATA_DIR, 'chromadb_store'))
    try:
        chroma.delete_collection(name=account_id)
        print(f"Deleted ChromaDB collection '{account_id}'.")
    except Exception:
        print(f"No ChromaDB collection found for '{account_id}', skipping.")


def insert_pt(conn, config, pt_folder):
    if not DEMO_INSTAGRAM_TOKEN:
        print("Error: DEMO_INSTAGRAM_TOKEN environment variable is not set.")
        sys.exit(1)

    required = {'name', 'tone_config', 'price_mode', 'calendly_link', 'handoff_number'}
    missing = required - config.keys()
    if missing:
        print(f"Error: config.json is missing keys: {', '.join(missing)}")
        sys.exit(1)

    conn.execute('''
        INSERT INTO pts (name, instagram_account_id, instagram_token, handoff_number,
                         tone_config, calendly_link, price_mode, channels)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        config['name'],
        DEMO_ACCOUNT_ID,
        DEMO_INSTAGRAM_TOKEN,
        config['handoff_number'],
        config['tone_config'],
        config['calendly_link'],
        config['price_mode'],
        '["instagram"]',
    ))
    print(f"Inserted PT record for '{config['name']}'.")


def embed_documents(account_id, pt_folder):
    chroma = chromadb.PersistentClient(path=os.path.join(DATA_DIR, 'chromadb_store'))
    collection = chroma.get_or_create_collection(name=account_id)

    embedded_count = 0
    for filename in os.listdir(pt_folder):
        if not filename.endswith('.txt'):
            continue
        with open(os.path.join(pt_folder, filename), 'r') as f:
            text = f.read()
        chunks = _chunk_text(text)
        for i, chunk in enumerate(chunks):
            collection.add(documents=[chunk], ids=[f"{filename}_{i}"])
        print(f"  Embedded {len(chunks)} chunks from {filename}")
        embedded_count += 1

    print(f"Embedded {embedded_count} document(s) into collection '{account_id}'.")


def _chunk_text(text, chunk_size=500, overlap=50):
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunks.append(' '.join(words[i:i + chunk_size]))
        i += chunk_size - overlap
    return chunks


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python swap_demo_pt.py <pt_folder>")
        sys.exit(1)

    pt_folder = sys.argv[1]
    config_path = os.path.join(pt_folder, 'config.json')

    if not os.path.isdir(pt_folder):
        print(f"Error: '{pt_folder}' is not a directory.")
        sys.exit(1)
    if not os.path.exists(config_path):
        print(f"Error: no config.json found in '{pt_folder}'.")
        sys.exit(1)

    with open(config_path, 'r') as f:
        config = json.load(f)

    init_db()
    conn = get_db()

    try:
        delete_pt_and_data(conn, DEMO_ACCOUNT_ID)
        conn.commit()

        delete_chroma_collection(DEMO_ACCOUNT_ID)

        insert_pt(conn, config, pt_folder)
        conn.commit()
    finally:
        conn.close()

    embed_documents(DEMO_ACCOUNT_ID, pt_folder)

    print(f"\nDone. Demo PT is now '{config['name']}'.")
