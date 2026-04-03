#!/usr/bin/env python3
"""
Generate a PT knowledge base from website content and Instagram captions.

Usage:
    python generate_kb.py pt_docs/new_pt_name --website https://theirwebsite.com
"""

import argparse
import json
import sys
from html.parser import HTMLParser
from pathlib import Path

import requests
import anthropic
from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# HTML text extraction
# ---------------------------------------------------------------------------

class _TextExtractor(HTMLParser):
    _SKIP = {'script', 'style', 'noscript', 'head', 'meta', 'link'}

    def __init__(self):
        super().__init__()
        self._depth = 0
        self._chunks = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._SKIP:
            self._depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in self._SKIP:
            self._depth = max(0, self._depth - 1)

    def handle_data(self, data):
        if self._depth == 0:
            text = data.strip()
            if text:
                self._chunks.append(text)

    def get_text(self):
        return '\n'.join(self._chunks)


def _fetch_website(url: str) -> str:
    print(f"Fetching {url}...")
    try:
        resp = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"Warning: could not fetch website: {e}", file=sys.stderr)
        return ""
    parser = _TextExtractor()
    parser.feed(resp.text)
    text = parser.get_text()
    if len(text) > 8000:
        text = text[:8000] + "\n[truncated]"
    return text


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_PROMPT = """\
You are helping onboard a new personal trainer (PT) onto a coaching chatbot platform.

Your job is to generate their complete knowledge base from the raw source material below.

## Source material

### Website content
{website_text}

### Instagram captions
{captions_text}

## What to generate

Return a single JSON object (no markdown, no code fences) with exactly these keys:

- "philosophy.txt" — The PT's coaching philosophy in their voice. Cover their backstory, \
core beliefs, methodology, and what makes them different. 150-250 words.

- "packages.txt" — Their coaching offer(s). Cover what's included, who it's for, and how \
to get started. If specific packages or prices aren't clear from the source material, \
describe the general offering and direct people to book a call. 100-200 words.

- "faqs.txt" — 5-8 Q&A pairs covering the most common objections and questions a prospect \
would have (cost, time commitment, diet, results timeline, how it works, etc.). Use their \
voice and philosophy to answer. Format each as "Question?\\nAnswer." separated by a blank line.

- "results.txt" — Client results and transformations. Include specific numbers and timeframes \
where available. If no client results appear in the source material, use the PT's own \
transformation story. 100-150 words.

- "discovery_call.txt" — Short doc explaining what the discovery call is, what happens on it, \
and why someone should book. Low-pressure, warm tone. End with the booking link if one is \
found, otherwise a placeholder. 80-120 words.

- "config.json" — A JSON string (it will be parsed separately) containing:
  - "name": PT's full name
  - "tone_config": Rich 2-4 sentence description of their voice and communication style. \
Cover energy level, humour, language patterns, cultural references, what they avoid, and \
the emotional register they operate in. This is injected verbatim into an AI system prompt \
that must sound like a real human from their team — make it specific and vivid.
  - "price_mode": "deflect" if pricing is vague or absent, "reveal" if specific prices are given
  - "calendly_link": their booking link if found, otherwise ""
  - "handoff_number": their WhatsApp or phone number if found, otherwise ""

Rules:
- Write everything in the PT's authentic voice. Match their energy, vocabulary, and tone.
- Do NOT invent specific claims (prices, client names, exact results) not present in the \
source material.
- Where information is missing, write around it naturally rather than fabricating details.
- The five .txt files are used as a retrieval knowledge base by an AI chatbot responding to \
Instagram DMs. Write them to be informative and scannable when retrieved as short chunks, \
not as website marketing copy.
- Return only valid JSON. No preamble, no explanation, no markdown fences.
"""

_KB_FILES = ["philosophy.txt", "packages.txt", "faqs.txt", "results.txt", "discovery_call.txt"]


# ---------------------------------------------------------------------------
# Main generation logic
# ---------------------------------------------------------------------------

def generate(pt_folder: Path, website_url: str):
    pt_folder.mkdir(parents=True, exist_ok=True)

    website_text = _fetch_website(website_url) if website_url else ""

    captions_path = pt_folder / "captions.txt"
    if captions_path.exists():
        captions_text = captions_path.read_text(encoding="utf-8").strip()
    else:
        print(f"Warning: {captions_path} not found — proceeding without captions.", file=sys.stderr)
        captions_text = ""

    if not website_text and not captions_text:
        print("Error: no source material (website fetch failed and no captions.txt).", file=sys.stderr)
        sys.exit(1)

    prompt = _PROMPT.format(
        website_text=website_text or "(none provided)",
        captions_text=captions_text or "(none provided)",
    )

    print("Sending to Claude...")
    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        debug_path = Path("generate_kb_debug.txt")
        debug_path.write_text(raw)
        print(f"Error: Claude returned invalid JSON: {e}", file=sys.stderr)
        print(f"Raw response saved to {debug_path}", file=sys.stderr)
        sys.exit(1)

    for filename in _KB_FILES:
        if filename not in data:
            print(f"Warning: {filename} missing from Claude response, skipping.", file=sys.stderr)
            continue
        out = pt_folder / filename
        out.write_text(data[filename], encoding="utf-8")
        print(f"  wrote {out}")

    if "config.json" not in data:
        print("Warning: config.json missing from Claude response.", file=sys.stderr)
    else:
        config_raw = data["config.json"]
        config = json.loads(config_raw) if isinstance(config_raw, str) else config_raw
        out = pt_folder / "config.json"
        out.write_text(json.dumps(config, indent=2), encoding="utf-8")
        print(f"  wrote {out}")

    print("\nDone. Review the files before running embed_pt.py.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate a PT knowledge base from website content and Instagram captions."
    )
    parser.add_argument("pt_folder", help="Path to the PT's folder, e.g. pt_docs/new_pt_name")
    parser.add_argument("--website", default="", metavar="URL", help="PT's website URL")
    args = parser.parse_args()

    generate(Path(args.pt_folder), args.website)


if __name__ == "__main__":
    main()
