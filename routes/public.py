"""
routes/public.py - Public-facing HTML and API routes.
"""

import os
import json
import requests
from flask import Blueprint, render_template, jsonify, request, abort

public_bp = Blueprint("public", __name__)

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")
TMDB_BASE = "https://api.themoviedb.org/3"
MOVIES_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "movies.json")
TAMIL_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "admin_tamil_movies.json")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_json(path):
    """Safely read a JSON file; return empty list on any error."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def tmdb_get(endpoint, params=None):
    """Make a TMDB API request; return parsed JSON or None on failure."""
    if not TMDB_API_KEY:
        return None
    base_params = {"api_key": TMDB_API_KEY, "language": "en-US"}
    if params:
        base_params.update(params)
    try:
        resp = requests.get(f"{TMDB_BASE}{endpoint}", params=base_params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def filter_non_tamil(movies):
    """Remove Tamil-language movies from a list."""
    return [m for m in movies if m.get("original_language", "") != "ta"]


# ---------------------------------------------------------------------------
# HTML Routes
# ---------------------------------------------------------------------------

@public_bp.route("/")
def index():
    return render_template("index.html")


@public_bp.route("/movies")
def movies_page():
    return render_template("movies.html")


@public_bp.route("/movies/<int:movie_id>")
def movie_detail(movie_id):
    return render_template("movie.html", movie_id=movie_id)


@public_bp.route("/tamil")
def tamil_page():
    return render_template("tamil.html")


@public_bp.route("/tamil/<tamil_id>")
def tamil_detail(tamil_id):
    movies = load_json(TAMIL_FILE)
    movie = next((m for m in movies if str(m.get("id")) == str(tamil_id)), None)
    if not movie:
        abort(404)
    return render_template("tamil_detail.html", movie=movie)


@public_bp.route("/watchlist")
def watchlist_page():
    return render_template("watchlist.html")


@public_bp.route("/bestlist")
def bestlist_page():
    return render_template("bestlist.html")


# ---------------------------------------------------------------------------
# International (TMDB) API
# ---------------------------------------------------------------------------

@public_bp.route("/api/movies")
def api_movies():
    """
    Return paginated, filtered non-Tamil movies from TMDB.
    Falls back to cached data/movies.json if TMDB is unreachable.
    Query params: page, genre, year, query
    """
    page = request.args.get("page", 1, type=int)
    genre = request.args.get("genre", "")
    year = request.args.get("year", "")
    query = request.args.get("query", "").strip()

    results = []

    if query:
        data = tmdb_get("/search/movie", {"query": query, "page": page})
        if data:
            results = filter_non_tamil(data.get("results", []))
            total_pages = data.get("total_pages", 1)
        else:
            cached = load_json(MOVIES_FILE)
            results = [m for m in filter_non_tamil(cached)
                       if query.lower() in m.get("title", "").lower()]
            total_pages = 1
    else:
        params = {"page": page}
        if genre:
            params["with_genres"] = genre
        if year:
            params["primary_release_year"] = year

        data = tmdb_get("/discover/movie", {
            **params,
            "sort_by": "popularity.desc",
            "vote_count.gte": 50,
        })
        if data:
            results = filter_non_tamil(data.get("results", []))
            total_pages = data.get("total_pages", 1)
        else:
            cached = load_json(MOVIES_FILE)
            results = filter_non_tamil(cached)
            if genre:
                results = [m for m in results if str(genre) in
                           [str(g) for g in m.get("genre_ids", [])]]
            if year:
                results = [m for m in results if
                           str(m.get("release_date", "")).startswith(str(year))]
            total_pages = 1

    return jsonify({
        "results": results,
        "page": page,
        "total_pages": total_pages,
    })


@public_bp.route("/api/movies/<int:movie_id>")
def api_movie_detail(movie_id):
    """Return full details for one TMDB movie."""
    data = tmdb_get(f"/movie/{movie_id}", {"append_to_response": "credits,videos"})
    if not data:
        abort(404)
    if data.get("original_language") == "ta":
        abort(404)
    return jsonify(data)


@public_bp.route("/api/movies/featured")
def api_featured():
    """Return a handful of trending non-Tamil movies for the hero banner."""
    data = tmdb_get("/trending/movie/week")
    if not data:
        cached = load_json(MOVIES_FILE)
        results = filter_non_tamil(cached)[:5]
        return jsonify(results)
    results = filter_non_tamil(data.get("results", []))[:5]
    return jsonify(results)


@public_bp.route("/api/movies/popular")
def api_popular():
    """Return popular non-Tamil movies for home carousels."""
    data = tmdb_get("/movie/popular")
    if not data:
        cached = load_json(MOVIES_FILE)
        return jsonify(filter_non_tamil(cached)[:20])
    return jsonify(filter_non_tamil(data.get("results", []))[:20])


@public_bp.route("/api/movies/top-rated")
def api_top_rated():
    """Return top-rated non-Tamil movies for home carousels."""
    data = tmdb_get("/movie/top_rated")
    if not data:
        cached = load_json(MOVIES_FILE)
        return jsonify(filter_non_tamil(cached)[:20])
    return jsonify(filter_non_tamil(data.get("results", []))[:20])


@public_bp.route("/api/movies/upcoming")
def api_upcoming():
    """Return upcoming non-Tamil movies for home carousels."""
    data = tmdb_get("/movie/upcoming")
    if not data:
        return jsonify([])
    return jsonify(filter_non_tamil(data.get("results", []))[:20])


@public_bp.route("/api/genres")
def api_genres():
    """Return TMDB genre list."""
    data = tmdb_get("/genre/movie/list")
    if not data:
        return jsonify([])
    return jsonify(data.get("genres", []))


# ---------------------------------------------------------------------------
# Tamil Movies API
# ---------------------------------------------------------------------------

@public_bp.route("/api/tamil-movies")
def api_tamil_movies():
    """Return all Tamil admin/imported movies from JSON storage."""
    movies = load_json(TAMIL_FILE)
    query = request.args.get("query", "").strip().lower()
    genre = request.args.get("genre", "").strip().lower()
    year = request.args.get("year", "").strip()

    if query:
        movies = [m for m in movies if query in m.get("title", "").lower()
                  or query in m.get("description", "").lower()]
    if genre:
        movies = [m for m in movies if genre in m.get("genre", "").lower()]
    if year:
        movies = [m for m in movies if str(m.get("year", "")) == year]

    return jsonify(movies)


@public_bp.route("/api/tamil-movies/<tamil_id>")
def api_tamil_movie_detail(tamil_id):
    """Return one Tamil movie by ID."""
    movies = load_json(TAMIL_FILE)
    movie = next((m for m in movies if str(m.get("id")) == str(tamil_id)), None)
    if not movie:
        abort(404)
    return jsonify(movie)
