"""
Adds a demo PT to the database without deleting any existing records.

Usage:
    python add_demo_pt.py ./pt_docs/tom_holman

The PT folder must contain:
  - config.json  with keys: name, demo_slug, tone_config, price_mode,
                             calendly_link, handoff_number
  - *.txt        knowledge base documents to embed

The PT is inserted with instagram_account_id = 'demo_<demo_slug>' and no
instagram_token (demo conversations go through /demo/<slug>/chat directly).
"""

import json
import os
import sys

import chromadb
from dotenv import load_dotenv

from database.db import get_db, init_db

load_dotenv()

DATA_DIR = os.getenv('DATA_DIR', '.')


def insert_pt(conn, config, account_id, slug, pt_folder):
    required = {'name', 'demo_slug', 'tone_config', 'price_mode', 'calendly_link', 'handoff_number'}
    missing = required - config.keys()
    if missing:
        raise ValueError(f"config.json is missing keys: {', '.join(missing)}")

    conn.execute('''
        INSERT INTO pts (name, instagram_account_id, instagram_token, handoff_number,
                         tone_config, calendly_link, price_mode, channels, demo_slug, pt_folder)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        config['name'],
        account_id,
        None,
        config['handoff_number'],
        config['tone_config'],
        config['calendly_link'],
        config['price_mode'],
        '["instagram"]',
        slug,
        pt_folder,
    ))
    print(f"Inserted PT record for '{config['name']}' with demo_slug='{slug}'.")


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


def update(pt_folder):
    config_path = os.path.join(pt_folder, 'config.json')

    if not os.path.isdir(pt_folder):
        raise ValueError(f"'{pt_folder}' is not a directory.")
    if not os.path.exists(config_path):
        raise ValueError(f"No config.json found in '{pt_folder}'.")

    with open(config_path, 'r') as f:
        config = json.load(f)

    slug = config.get('demo_slug')
    if not slug:
        raise ValueError("config.json must contain a 'demo_slug' field.")

    account_id = f'demo_{slug}'

    init_db()
    conn = get_db()

    pt = conn.execute(
        'SELECT id FROM pts WHERE instagram_account_id = ? AND demo_slug = ?',
        (account_id, slug)
    ).fetchone()
    if not pt:
        conn.close()
        raise ValueError(
            f"No demo PT found with instagram_account_id='{account_id}'. "
            f"Use add_demo_pt.py to create it first."
        )

    required = {'name', 'demo_slug', 'tone_config', 'price_mode', 'calendly_link', 'handoff_number'}
    missing = required - config.keys()
    if missing:
        raise ValueError(f"config.json is missing keys: {', '.join(missing)}")

    try:
        conn.execute('''
            UPDATE pts SET name = ?, tone_config = ?, price_mode = ?,
                           calendly_link = ?, handoff_number = ?, pt_folder = ?
            WHERE instagram_account_id = ?
        ''', (
            config['name'],
            config['tone_config'],
            config['price_mode'],
            config['calendly_link'],
            config['handoff_number'],
            pt_folder,
            account_id,
        ))
        conn.commit()
        print(f"Updated PT record for '{config['name']}'.")
    finally:
        conn.close()

    # Re-embed: delete existing collection and re-create from current docs
    chroma = chromadb.PersistentClient(path=os.path.join(DATA_DIR, 'chromadb_store'))
    try:
        chroma.delete_collection(name=account_id)
        print(f"Deleted existing ChromaDB collection '{account_id}'.")
    except Exception:
        print(f"No existing ChromaDB collection for '{account_id}', skipping delete.")

    embed_documents(account_id, pt_folder)
    print(f"\nDone. Demo PT '{config['name']}' updated at /demo/{slug}")


def add(pt_folder):
    config_path = os.path.join(pt_folder, 'config.json')

    if not os.path.isdir(pt_folder):
        raise ValueError(f"'{pt_folder}' is not a directory.")
    if not os.path.exists(config_path):
        raise ValueError(f"No config.json found in '{pt_folder}'.")

    with open(config_path, 'r') as f:
        config = json.load(f)

    slug = config.get('demo_slug')
    if not slug:
        raise ValueError("config.json must contain a 'demo_slug' field (e.g. 'tom-holman').")

    account_id = f'demo_{slug}'

    init_db()
    conn = get_db()

    # Check for conflicts
    existing = conn.execute(
        'SELECT id FROM pts WHERE instagram_account_id = ? OR demo_slug = ?',
        (account_id, slug)
    ).fetchone()
    if existing:
        conn.close()
        raise ValueError(
            f"A PT with instagram_account_id='{account_id}' or demo_slug='{slug}' already exists. "
            f"Use /admin/pt/update to modify it, or remove it first."
        )

    try:
        insert_pt(conn, config, account_id, slug, pt_folder)
        conn.commit()
    finally:
        conn.close()

    embed_documents(account_id, pt_folder)
    print(f"\nDone. Demo PT '{config['name']}' available at /demo/{slug}")


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python add_demo_pt.py <pt_folder>")
        sys.exit(1)
    try:
        add(sys.argv[1])
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
