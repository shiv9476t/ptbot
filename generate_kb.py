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

- "packages.txt" — Packages and pricing. Cover what's included day-to-day (check-ins, \
app, programming, nutrition support, etc.), how it works, duration, and what the client \
actually gets. If specific prices are present in the source material, include them. If \
pricing is vague or absent, describe the offering and direct people to book a call. \
This gets pulled when leads ask "what do I actually get?" or "how does it work?" 150-250 words.

- "philosophy.txt" — The PT's coaching philosophy. How they think about training and \
nutrition, what they stand against, their core beliefs and what makes them different from \
generic coaches. Pull strongly from any strong opinions or recurring themes in their \
captions or website — these are what make the bot sound like this specific PT rather than \
anyone else. 150-250 words.

- "results.txt" — Real client outcomes and transformations. Be as specific as possible — \
numbers, timeframes, and context ("lost 12kg in 16 weeks while still eating curry every \
day") are infinitely more useful than vague claims. If no client results appear in the \
source material, use the PT's own transformation story. This gets pulled when nurturing \
warm leads who need social proof. 150-200 words.

- "faqs.txt" — Common operational questions a prospect would ask: how does online coaching \
work, what app do you use, how often do we check in, do you do face to face, how long \
until I see results, what happens if I travel or miss a week. These are questions the bot \
should be able to answer confidently rather than deflect. Format each as "Question?\\nAnswer." \
separated by a blank line. 6-10 Q&A pairs.

- "background.txt" — The PT's background and credentials. Qualifications, years of \
experience, their own fitness journey, why they got into coaching, and what makes them \
trustworthy. Gets pulled when leads ask "who is this person?" or "why should I trust them?" \
Write it in the PT's voice, not as a third-person bio. 150-200 words.

- "objections.txt" — Dedicated responses to the most common objections for this PT's niche. \
Each entry should be a specific objection followed by how this PT would genuinely respond to \
it — in their voice, using their philosophy and results. Include at least: "I've tried online \
coaching before and it didn't work", "I can't afford a coach right now", "I don't have time", \
and any niche-specific objections evident from the source material. These get pulled verbatim \
during objection handling so they must feel authentic, not generic. Format each as \
"Objection: [objection]\\nResponse: [response]" separated by a blank line. 4-6 objections.

- "config.json" — A JSON string (it will be parsed separately) containing:
  - "name": PT's full name
  - "demo_slug": URL-friendly slug, e.g. "arjhan-rai" or "tom-holman"
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
- These files are used as a retrieval knowledge base by an AI chatbot responding to Instagram \
DMs. Write them to be informative and scannable when retrieved as short chunks, not as \
website marketing copy.
- Return only valid JSON. No preamble, no explanation, no markdown fences.
"""

_KB_FILES = ["packages.txt", "philosophy.txt", "results.txt", "faqs.txt", "background.txt", "objections.txt"]


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
