# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

PTBot is a multi-tenant AI chatbot for personal trainers (PTs) that responds to Instagram DMs on behalf of PTs. Each PT is a separate tenant with their own Instagram account, tone config, pricing strategy, and knowledge base. The bot qualifies leads and books discovery calls.

## Commands

**Install dependencies:**
```bash
pip install -r requirements.txt
```

**Run development server:**
```bash
python3 app.py
```

**Run production server:**
```bash
gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```

**Interactive agent testing (REPL against a PT):**
```bash
python3 test_agent.py
```

**Embed a PT's knowledge base into ChromaDB:**
```bash
python3 onboarding/embed_pt.py <instagram_account_id> <path_to_docs_folder>
```

**Seed a PT into the database:**
```bash
python3 add_arjhan.py   # or add_test_pt.py
```

## Architecture

### Request Flow
Instagram DM → POST `/instagram` webhook → parse sender/recipient → look up PT by `instagram_account_id` → get or create contact → load last 20 messages → ChromaDB semantic search (3 chunks) → `build_system_prompt()` → Claude API → save reply → Instagram Graph API send

### Key Design Decisions

- **Multi-tenancy is by `instagram_account_id`**: Instagram's webhook payload includes `recipient.id` — the account that *received* the DM (i.e., the PT's own Instagram account). This is looked up against `pts.instagram_account_id` to route the message to the right PT.
- **Knowledge grounding via ChromaDB**: Each PT has a vector store of 5 docs (philosophy, faqs, packages, results, discovery_call). `knowledge.py` searches it per message to prevent hallucination.
- **Prompt construction is the core logic**: `prompt.py`'s `build_system_prompt()` assembles PT identity, tone config, conversation strategy (discover→agitate→pitch→close), pricing rules, objection templates, and retrieved knowledge chunks into the Claude system prompt.
- **SQLite for relational data**: `ptbot.db` stores `pts`, `contacts`, and `messages`. Path is controlled by `DATA_DIR` env var (Railway uses a persistent volume).
- **No test suite**: Testing is done manually via `test_agent.py`.

### Module Responsibilities
- `app.py` — Flask server, webhook verification, message orchestration
- `agent.py` — Claude API call, conversation assembly
- `prompt.py` — System prompt construction
- `knowledge.py` — ChromaDB vector search
- `database/` — SQLite schema and CRUD (pts, contacts, conversations, db)
- `channels/instagram.py` — Instagram webhook parsing and Graph API replies
- `onboarding/embed_pt.py` — Chunk and embed PT docs into ChromaDB

### PT Knowledge Base Structure
Each PT has a folder under `pt_docs/<instagram_account_id>/` with: `philosophy.txt`, `faqs.txt`, `packages.txt`, `results.txt`, `discovery_call.txt`. These are embedded via `onboarding/embed_pt.py` and stored in `chromadb_store/`.

## Environment Variables

```
ANTHROPIC_API_KEY=
INSTAGRAM_VERIFY_TOKEN=
DATA_DIR=.          # optional; defaults to cwd; set to volume path on Railway
PORT=5000           # set automatically by Railway
```

## Deployment

Deployed on Railway. Config in `railway.toml`. The `DATA_DIR` env var points to a persistent volume for `ptbot.db` and `chromadb_store/`. Health check endpoint: `GET /health`.
