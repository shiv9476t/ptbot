import json
import os

from config import BASE_URL


def load_photos(pt_folder):
    """Load photos.json from the PT's photos subfolder. Returns [] if not found."""
    photos_path = os.path.join(pt_folder, 'photos.json')
    if not os.path.exists(photos_path):
        return []
    with open(photos_path, 'r') as f:
        return json.load(f)


def find_best_photo(photos, query):
    """
    Score each photo by keyword overlap between the query and the photo's
    description + tags. Returns the best match, or None if no photos.
    """
    if not photos:
        return None

    query_words = set(query.lower().split())

    best, best_score = None, -1
    for photo in photos:
        searchable = photo.get('description', '') + ' ' + ' '.join(photo.get('tags', []))
        photo_words = set(searchable.lower().split())
        score = len(query_words & photo_words)
        if score > best_score:
            best, best_score = photo, score

    return best


def get_photo_url(account_id, filename):
    """Construct the public URL for a photo served by this Flask app."""
    return f"{BASE_URL.rstrip('/')}/photos/{account_id}/{filename}"
