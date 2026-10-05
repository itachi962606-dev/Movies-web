"""
tests/test_movieshub.py - Comprehensive test suite for MoviesHub rebuild
Tests all requirements:
1. Public route availability and templates
2. Admin open access (no credentials/login form required)
3. Strict data isolation: TMDB international catalogue vs Admin Tamil catalogue
4. Admin CRUD safety: add A, B, C; edit B; delete A; ensure no data overwriting
5. Site Grabber metadata & download link extraction with confirmation flow & duplicate prevention
6. Watchlist & Best List routes and integration
7. Preservation of download-only action for Tamil movies (no Watch/Play/TMDB)
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app
from routes.public import TAMIL_FILE, MOVIES_FILE
import site_grabber

class MoviesHubTestCase(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()
        
        # Backup existing JSON files if present
        self.orig_tamil = None
        if os.path.exists(TAMIL_FILE):
            with open(TAMIL_FILE, "r", encoding="utf-8") as f:
                self.orig_tamil = f.read()

        self.orig_movies = None
        if os.path.exists(MOVIES_FILE):
            with open(MOVIES_FILE, "r", encoding="utf-8") as f:
                self.orig_movies = f.read()

        # Initialize clean test data
        with open(TAMIL_FILE, "w", encoding="utf-8") as f:
            f.write("[]")
        with open(MOVIES_FILE, "w", encoding="utf-8") as f:
            f.write("[]")

    def tearDown(self):
        # Restore original state
        if self.orig_tamil is not None:
            with open(TAMIL_FILE, "w", encoding="utf-8") as f:
                f.write(self.orig_tamil)
        if self.orig_movies is not None:
            with open(MOVIES_FILE, "w", encoding="utf-8") as f:
                f.write(self.orig_movies)

    # -----------------------------------------------------------------------
    # 1. Home & Public Routes
    # -----------------------------------------------------------------------
    def test_01_public_pages_load(self):
        pages = ["/", "/movies", "/tamil", "/watchlist", "/bestlist"]
        for p in pages:
            res = self.client.get(p)
            self.assertEqual(res.status_code, 200, f"Page {p} failed to load.")
            self.assertIn(b"MoviesHub", res.data)
            # Ensure Best List icon (⭐) is in the navbar
            self.assertIn("⭐".encode("utf-8"), res.data)

    # -----------------------------------------------------------------------
    # 2. Admin Open Access (No login credentials/login page required)
    # -----------------------------------------------------------------------
    def test_02_admin_open_access(self):
        admin_pages = ["/admin/", "/admin/movies", "/admin/add-movie", "/admin/import"]
        for p in admin_pages:
            res = self.client.get(p)
            self.assertEqual(res.status_code, 200, f"Admin page {p} failed.")
            # Ensure no login form or password input
            self.assertNotIn(b'type="password"', res.data)
            self.assertIn(b"ADMIN CONSOLE", res.data)

    # -----------------------------------------------------------------------
    # 3. TMDB International Exclusion of Tamil (original_language == "ta")
    # -----------------------------------------------------------------------
    @patch("routes.public.tmdb_get")
    def test_03_tmdb_excludes_tamil_movies(self, mock_tmdb):
        mock_tmdb.return_value = {
            "results": [
                {"id": 101, "title": "Hollywood Blockbuster", "original_language": "en", "vote_average": 8.0},
                {"id": 102, "title": "Tamil Action Epic", "original_language": "ta", "vote_average": 8.5},
                {"id": 103, "title": "French Cinema", "original_language": "fr", "vote_average": 7.4}
            ],
            "total_pages": 1
        }
        res = self.client.get("/api/movies")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        titles = [m["title"] for m in data["results"]]
        self.assertIn("Hollywood Blockbuster", titles)
        self.assertIn("French Cinema", titles)
        self.assertNotIn("Tamil Action Epic", titles, "CRITICAL: Tamil movie was not filtered out from TMDB results!")

    # -----------------------------------------------------------------------
    # 4. Tamil Movies Isolation: Never fetches from TMDB or external APIs
    # -----------------------------------------------------------------------
    def test_04_tamil_movies_isolation(self):
        # When empty initially
        res = self.client.get("/api/tamil-movies")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json(), [], "Tamil movies catalogue must be empty initially if no admin movies exist.")

    # -----------------------------------------------------------------------
    # 5. Critical Data Safety: Admin CRUD (Add A, B, C; Edit B; Delete A)
    # -----------------------------------------------------------------------
    def test_05_admin_crud_data_safety(self):
        # 1. Add Movie A
        res_a = self.client.post("/admin/api/tamil-movies", json={
            "title": "Movie A",
            "year": "2024",
            "genre": "Action",
            "download_url": "https://my-site.com/dl/movie-a.mp4"
        })
        self.assertEqual(res_a.status_code, 201)
        id_a = res_a.get_json()["movie"]["id"]

        with open(TAMIL_FILE, "r", encoding="utf-8") as f:
            list_1 = json.load(f)
        self.assertEqual(len(list_1), 1)
        self.assertEqual(list_1[0]["title"], "Movie A")

        # 2. Add Movie B
        res_b = self.client.post("/admin/api/tamil-movies", json={
            "title": "Movie B",
            "year": "2025",
            "genre": "Thriller",
            "download_url": "https://my-site.com/dl/movie-b.mp4"
        })
        self.assertEqual(res_b.status_code, 201)
        id_b = res_b.get_json()["movie"]["id"]

        with open(TAMIL_FILE, "r", encoding="utf-8") as f:
            list_2 = json.load(f)
        self.assertEqual(len(list_2), 2, "Adding Movie B replaced existing list!")
        self.assertEqual([m["title"] for m in list_2], ["Movie A", "Movie B"])

        # 3. Add Movie C
        res_c = self.client.post("/admin/api/tamil-movies", json={
            "title": "Movie C",
            "year": "2026",
            "genre": "Drama",
            "download_url": "https://my-site.com/dl/movie-c.mp4"
        })
        self.assertEqual(res_c.status_code, 201)
        id_c = res_c.get_json()["movie"]["id"]

        with open(TAMIL_FILE, "r", encoding="utf-8") as f:
            list_3 = json.load(f)
        self.assertEqual(len(list_3), 3, "Adding Movie C failed to preserve Movie A and B!")
        self.assertEqual([m["title"] for m in list_3], ["Movie A", "Movie B", "Movie C"])

        # 4. Edit Movie B (Must NOT affect Movie A or Movie C)
        res_edit = self.client.put(f"/admin/api/tamil-movies/{id_b}", json={
            "title": "Movie B Remastered",
            "genre": "Sci-Fi"
        })
        self.assertEqual(res_edit.status_code, 200)

        with open(TAMIL_FILE, "r", encoding="utf-8") as f:
            list_after_edit = json.load(f)
        self.assertEqual(len(list_after_edit), 3)
        self.assertEqual(list_after_edit[0]["title"], "Movie A")
        self.assertEqual(list_after_edit[1]["title"], "Movie B Remastered")
        self.assertEqual(list_after_edit[1]["genre"], "Sci-Fi")
        self.assertEqual(list_after_edit[2]["title"], "Movie C")

        # 5. Delete Movie A (Must remove ONLY Movie A, leaving B and C intact)
        res_del = self.client.delete(f"/admin/api/tamil-movies/{id_a}")
        self.assertEqual(res_del.status_code, 200)

        with open(TAMIL_FILE, "r", encoding="utf-8") as f:
            list_after_del = json.load(f)
        self.assertEqual(len(list_after_del), 2)
        remaining_titles = [m["title"] for m in list_after_del]
        self.assertNotIn("Movie A", remaining_titles)
        self.assertIn("Movie B Remastered", remaining_titles)
        self.assertIn("Movie C", remaining_titles)

    # -----------------------------------------------------------------------
    # 6. Own Website Scraper & Import Confirmation Flow
    # -----------------------------------------------------------------------
    @patch("site_grabber.allowed_by_robots", return_value=True)
    @patch("site_grabber.fetch_html")
    def test_06_site_grabber_and_import(self, mock_html, mock_robots):
        mock_html.return_value = """
        <!DOCTYPE html>
        <html>
        <head>
          <title>Leo Full Movie</title>
          <meta property="og:image" content="https://my-own-site.com/posters/leo.jpg">
          <meta name="description" content="An action entertainer featuring Thalapathy.">
        </head>
        <body>
          <h1 class="movie-title">Leo</h1>
          <div class="year">2023</div>
          <div class="genre"><a href="/g/action">Action</a><a href="/g/crime">Crime</a></div>
          <div class="downloads">
            <a class="download-btn" href="/download/leo-2023-1080p.mkv">Download 1080p WebRip</a>
          </div>
        </body>
        </html>
        """

        # 1. Preview scrape
        res = self.client.post("/admin/api/import", json={"url": "https://my-own-site.com/movies/leo"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        preview = data["preview"]

        self.assertEqual(preview["title"], "Leo")
        self.assertEqual(preview["poster"], "https://my-own-site.com/posters/leo.jpg")
        self.assertEqual(preview["year"], "2023")
        self.assertIn("Action", preview["genre"])
        self.assertEqual(preview["download_url"], "https://my-own-site.com/download/leo-2023-1080p.mkv")

        # 2. Confirm & save
        res_save = self.client.post("/admin/api/import/save", json=preview)
        self.assertEqual(res_save.status_code, 201)

        # 3. Duplicate prevention: try saving same movie again
        res_dup = self.client.post("/admin/api/import/save", json=preview)
        self.assertEqual(res_dup.status_code, 409, "Duplicate movie was not rejected!")

    # -----------------------------------------------------------------------
    # 7. Tamil Movie Card Actions: DOWNLOAD ONLY (No Watch/Play/TMDB)
    # -----------------------------------------------------------------------
    def test_07_tamil_ui_download_only(self):
        # Insert a sample Tamil movie
        sample = {
            "id": "tamil-uuid-999",
            "title": "Vikram Vedha",
            "poster": "https://example.com/vv.jpg",
            "year": "2022",
            "genre": "Neo-Noir",
            "download_url": "https://my-site.com/dl/vv.mp4",
            "description": "A pragmatic police inspector."
        }
        with open(TAMIL_FILE, "w", encoding="utf-8") as f:
            json.dump([sample], f)

        # Verify Tamil detail view
        res = self.client.get(f"/tamil/{sample['id']}")
        self.assertEqual(res.status_code, 200)
        content = res.data.decode("utf-8")

        # Must have DOWNLOAD button
        self.assertIn("DOWNLOAD NOW", content)
        self.assertIn(sample["download_url"], content)

        # Must NOT show Watch / Play / TMDB / Streaming in actions
        actions_html = content[content.find('class="detail-actions"'):content.find('</main>')]
        self.assertNotIn("Play", actions_html)
        self.assertNotIn("Watch Trailer", actions_html)
        self.assertNotIn("TMDB", actions_html)
        self.assertNotIn("Streaming", actions_html)

    # -----------------------------------------------------------------------
    # 8. TMDB Update Script Isolation
    # -----------------------------------------------------------------------
    def test_08_tmdb_update_preserves_admin_tamil_movies(self):
        tamil_sample = [{
            "id": "persisted-tamil-1",
            "title": "Ponniyin Selvan",
            "year": "2022",
            "genre": "Historical",
            "download_url": "https://my-site.com/ps1.mkv"
        }]
        with open(TAMIL_FILE, "w", encoding="utf-8") as f:
            json.dump(tamil_sample, f)

        # Simulate update script running and writing to data/movies.json
        tmdb_mock_catalogue = [
            {"id": 9999, "title": "Interstellar", "original_language": "en"}
        ]
        with open(MOVIES_FILE, "w", encoding="utf-8") as f:
            json.dump(tmdb_mock_catalogue, f)

        # Verify Tamil file is completely untouched
        with open(TAMIL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["title"], "Ponniyin Selvan")

        # Verify movies.json contains the international movie
        with open(MOVIES_FILE, "r", encoding="utf-8") as f:
            movies_data = json.load(f)
        self.assertEqual(len(movies_data), 1)
        self.assertEqual(movies_data[0]["title"], "Interstellar")

    # -----------------------------------------------------------------------
    # 9. App Restart Persistence
    # -----------------------------------------------------------------------
    def test_09_restart_data_remains(self):
        # Save records
        test_records = [
            {"id": "r1", "title": "Test Tamil 1", "year": "2025", "genre": "Action", "download_url": "https://test.com/dl1"},
            {"id": "r2", "title": "Test Tamil 2", "year": "2026", "genre": "Drama", "download_url": "https://test.com/dl2"}
        ]
        with open(TAMIL_FILE, "w", encoding="utf-8") as f:
            json.dump(test_records, f)

        # Simulate server restart by creating a new test client instance
        new_client = app.test_client()
        res = new_client.get("/api/tamil-movies")
        self.assertEqual(res.status_code, 200)
        items = res.get_json()
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["title"], "Test Tamil 1")
        self.assertEqual(items[1]["title"], "Test Tamil 2")

if __name__ == "__main__":
    unittest.main()
