"""
Completes onboarding for a real PT whose bare record was created by OAuth.

Updates the PT record with fields from config.json and embeds their docs
into ChromaDB. Does not touch instagram_account_id or instagram_token.

Usage:
    python setup_pt.py ./pt_docs/tom_holman <instagram_account_id>
"""

import json
import os
import sys

import chromadb
from dotenv import load_dotenv

from database.db import get_db, init_db

load_dotenv()

DATA_DIR = os.getenv('DATA_DIR', '.')


def embed_documents(account_id, pt_folder):
    chroma = chromadb.PersistentClient(path=os.path.join(DATA_DIR, 'chromadb_store'))

    try:
        chroma.delete_collection(name=account_id)
        print(f"Deleted existing ChromaDB collection '{account_id}'.")
    except Exception:
        pass

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


def setup(pt_folder, instagram_account_id):
    config_path = os.path.join(pt_folder, 'config.json')

    if not os.path.isdir(pt_folder):
        raise ValueError(f"'{pt_folder}' is not a directory.")
    if not os.path.exists(config_path):
        raise ValueError(f"No config.json found in '{pt_folder}'.")

    with open(config_path, 'r') as f:
        config = json.load(f)

    required = {'name', 'tone_config', 'price_mode', 'calendly_link', 'handoff_number'}
    missing = required - config.keys()
    if missing:
        raise ValueError(f"config.json is missing keys: {', '.join(missing)}")

    init_db()
    conn = get_db()

    pt = conn.execute(
        'SELECT id FROM pts WHERE instagram_account_id = ?',
        (instagram_account_id,)
    ).fetchone()
    if not pt:
        conn.close()
        raise ValueError(
            f"No PT found with instagram_account_id='{instagram_account_id}'. "
            f"Has the PT connected via OAuth?"
        )

    try:
        conn.execute('''
            UPDATE pts SET name = ?, tone_config = ?, price_mode = ?,
                           calendly_link = ?, handoff_number = ?
            WHERE instagram_account_id = ?
        ''', (
            config['name'],
            config['tone_config'],
            config['price_mode'],
            config['calendly_link'],
            config['handoff_number'],
            instagram_account_id,
        ))
        conn.commit()
        print(f"Updated PT record for '{config['name']}'.")
    finally:
        conn.close()

    embed_documents(instagram_account_id, pt_folder)
    print(f"\nDone. '{config['name']}' is fully set up and ready to handle DMs.")


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python setup_pt.py <pt_folder> <instagram_account_id>")
        sys.exit(1)
    try:
        setup(sys.argv[1], sys.argv[2])
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
