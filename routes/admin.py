"""
routes/admin.py - Admin panel routes (no authentication required).
All admin routes are under /admin prefix (set in app.py).
"""

import os
import json
import uuid
from flask import Blueprint, render_template, jsonify, request, redirect, url_for

admin_bp = Blueprint("admin", __name__)

TAMIL_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "admin_tamil_movies.json")

# ---------------------------------------------------------------------------
# JSON helpers — always read-append-write, NEVER overwrite with single item
# ---------------------------------------------------------------------------

def load_tamil():
    """Load Tamil movies list safely."""
    try:
        with open(TAMIL_FILE, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_tamil(movies):
    """
    Atomically save Tamil movies list.
    Writes to a temp file first, then renames to prevent corruption.
    """
    os.makedirs(os.path.dirname(TAMIL_FILE), exist_ok=True)
    tmp = TAMIL_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(movies, f, ensure_ascii=False, indent=2)
    os.replace(tmp, TAMIL_FILE)


# ---------------------------------------------------------------------------
# HTML Pages
# ---------------------------------------------------------------------------

@admin_bp.route("/")
def dashboard():
    return render_template("admin/dashboard.html")


@admin_bp.route("/movies")
def admin_movies():
    return render_template("admin/movies.html")


@admin_bp.route("/add-movie")
def add_movie_page():
    return render_template("admin/add_movie.html")


@admin_bp.route("/edit-movie/<movie_id>")
def edit_movie_page(movie_id):
    movies = load_tamil()
    movie = next((m for m in movies if str(m.get("id")) == str(movie_id)), None)
    if not movie:
        return redirect(url_for("admin.admin_movies"))
    return render_template("admin/edit_movie.html", movie=movie)


@admin_bp.route("/import")
def import_page():
    return render_template("admin/import.html")


# ---------------------------------------------------------------------------
# Tamil Movie CRUD API
# ---------------------------------------------------------------------------

@admin_bp.route("/api/tamil-movies", methods=["GET"])
def api_list():
    """Return all Tamil admin movies."""
    return jsonify(load_tamil())


@admin_bp.route("/api/tamil-movies", methods=["POST"])
def api_add():
    """
    Add a new Tamil movie.
    Required fields: title
    """
    data = request.get_json(silent=True) or {}
    title = data.get("title", "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400

    movies = load_tamil()

    # Duplicate check by title (case-insensitive)
    existing = next((m for m in movies if m.get("title", "").lower() == title.lower()), None)
    if existing:
        return jsonify({"error": "A movie with this title already exists", "id": existing["id"]}), 409

    movie = {
        "id": str(uuid.uuid4()),
        "source": data.get("source", "admin"),
        "title": title,
        "poster": data.get("poster", "").strip(),
        "description": data.get("description", "").strip(),
        "year": data.get("year", ""),
        "genre": data.get("genre", "").strip(),
        "download_url": data.get("download_url", "").strip(),
        "source_url": data.get("source_url", "").strip(),
    }

    movies.append(movie)
    save_tamil(movies)
    return jsonify({"success": True, "movie": movie}), 201


@admin_bp.route("/api/tamil-movies/<movie_id>", methods=["PUT"])
def api_update(movie_id):
    """
    Update one Tamil movie by ID.
    Only the provided fields are updated; all other movies remain untouched.
    """
    data = request.get_json(silent=True) or {}
    movies = load_tamil()

    idx = next((i for i, m in enumerate(movies) if str(m.get("id")) == str(movie_id)), None)
    if idx is None:
        return jsonify({"error": "Movie not found"}), 404

    movie = movies[idx]

    # Update only provided fields
    updatable = ["title", "poster", "description", "year", "genre", "download_url", "source_url"]
    for field in updatable:
        if field in data:
            movie[field] = str(data[field]).strip() if isinstance(data[field], str) else data[field]

    movies[idx] = movie
    save_tamil(movies)
    return jsonify({"success": True, "movie": movie})


@admin_bp.route("/api/tamil-movies/<movie_id>", methods=["DELETE"])
def api_delete(movie_id):
    """
    Delete one Tamil movie by ID.
    All other movies remain untouched.
    """
    movies = load_tamil()
    original_count = len(movies)
    movies = [m for m in movies if str(m.get("id")) != str(movie_id)]

    if len(movies) == original_count:
        return jsonify({"error": "Movie not found"}), 404

    save_tamil(movies)
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# Import from own website
# ---------------------------------------------------------------------------

@admin_bp.route("/api/import", methods=["POST"])
def api_import():
    """
    Scrape a movie page from the user's own website.
    Returns extracted metadata for admin preview before saving.
    Does NOT automatically save.
    """
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()

    if not url:
        return jsonify({"error": "url is required"}), 400

    # Import the scraper module
    try:
        import site_grabber as grabber
    except Exception as e:
        return jsonify({"error": f"Scraper unavailable: {str(e)}"}), 500

    # Load selectors from optional config
    selectors_path = os.path.join(os.path.dirname(__file__), "..", "data", "scraper_config.json")
    selectors = dict(grabber.DEFAULT_SELECTORS)
    try:
        with open(selectors_path, encoding="utf-8") as f:
            selectors.update(json.load(f))
    except (OSError, json.JSONDecodeError):
        pass  # Use defaults if no config

    try:
        result = grabber.scrape(url, selectors)
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 502
    except Exception as e:
        return jsonify({"error": f"Scrape failed: {str(e)}"}), 500

    # Get download URL from scraper result or fallback inspection
    download_url = result.get("download_url") or _find_download_url(url, selectors)

    genre = result.get("genre", [])
    if isinstance(genre, list):
        genre = ", ".join(genre)

    preview = {
        "title": result.get("title") or "",
        "poster": result.get("poster_url") or "",
        "description": result.get("description") or "",
        "year": result.get("release_year") or "",
        "genre": genre,
        "download_url": download_url or "",
        "source_url": url,
        "source": "own-site",
    }

    return jsonify({"preview": preview})


def _find_download_url(page_url, selectors):
    """
    Attempt to find a download link on the scraped page.
    Uses 'download_link' selector from config if present,
    otherwise applies common heuristics.
    Returns URL string or None.
    """
    import requests as req
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin

    download_selector = selectors.get(
        "download_link",
        "a[href*='download'], a.download-btn, a.download, .download-link a, "
        "a[download], button.download, a[href*='/download/']"
    )

    try:
        import site_grabber
        from bs4 import BeautifulSoup
        html = site_grabber.fetch_html(page_url)
        if html:
            soup = BeautifulSoup(html, "html.parser")
            return site_grabber.extract_download_url(soup, page_url, download_selector)
    except Exception:
        pass

    return None


@admin_bp.route("/api/import/save", methods=["POST"])
def api_import_save():
    """
    Save an import-preview result as a Tamil movie after admin confirmation.
    Prevents duplicates by source_url.
    """
    data = request.get_json(silent=True) or {}

    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400

    movies = load_tamil()

    # Duplicate check by source_url
    source_url = (data.get("source_url") or "").strip()
    if source_url:
        dup = next((m for m in movies if m.get("source_url") == source_url), None)
        if dup:
            return jsonify({
                "error": "This movie was already imported",
                "id": dup["id"]
            }), 409

    # Duplicate check by title
    dup_title = next((m for m in movies if m.get("title", "").lower() == title.lower()), None)
    if dup_title:
        return jsonify({
            "error": "A movie with this title already exists",
            "id": dup_title["id"]
        }), 409

    movie = {
        "id": str(uuid.uuid4()),
        "source": "own-site",
        "title": title,
        "poster": (data.get("poster") or "").strip(),
        "description": (data.get("description") or "").strip(),
        "year": data.get("year", ""),
        "genre": (data.get("genre") or "").strip(),
        "download_url": (data.get("download_url") or "").strip(),
        "source_url": source_url,
    }

    movies.append(movie)
    save_tamil(movies)
    return jsonify({"success": True, "movie": movie}), 201
