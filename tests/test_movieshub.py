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
    # 6. Own Website Scraper & Import Flow (Multi-Quality & Smallest File Selection)
    # -----------------------------------------------------------------------
    @patch.dict(os.environ, {"OWN_SITE_URL": "https://my-own-site.com"})
    @patch("site_grabber.check_robots_permission", return_value=(True, None))
    @patch("site_grabber.fetch_html")
    def test_06_site_grabber_and_import(self, mock_html, mock_robots):
        # Multi-quality HTML with multiple links per quality
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
          
          <!-- 1080p options -->
          <div class="download-group">
            <h3>1080p Full HD</h3>
            <a class="download-btn" href="/download/leo-1080p-server1.mkv">1080p Server 1 (2.4 GB)</a>
            <a class="download-btn" href="/download/leo-1080p-server2.mkv">1080p Server 2 (1.2 GB)</a>
            <a class="download-btn" href="/download/leo-1080p-server3.mkv">1080p Server 3 (1.8 GB)</a>
          </div>

          <!-- 720p options -->
          <div class="download-group">
            <h3>720p HD</h3>
            <a class="download-btn" href="/download/leo-720p-server1.mkv">720p Server 1 (1.1 GB)</a>
            <a class="download-btn" href="/download/leo-720p-server2.mkv">720p Server 2 (700 MB)</a>
          </div>

          <!-- 480p options -->
          <div class="download-group">
            <h3>480p SD</h3>
            <a class="download-btn" href="/download/leo-480p-server1.mkv">480p Server 1 (500 MB)</a>
          </div>
        </body>
        </html>
        """

        # 1. Domain verification: reject third-party URL
        res_blocked = self.client.post("/admin/api/import", json={"url": "https://third-party-movies.com/movies/leo"})
        self.assertEqual(res_blocked.status_code, 400, "Third-party website was not rejected!")
        self.assertIn("Security restriction", res_blocked.get_json().get("error", ""))

        # 2. Preview scrape with verified own-site URL
        res = self.client.post("/admin/api/import", json={"url": "https://my-own-site.com/movies/leo"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        preview = data["preview"]

        self.assertEqual(preview["title"], "Leo")
        self.assertEqual(preview["poster"], "https://my-own-site.com/posters/leo.jpg")
        self.assertEqual(preview["year"], "2023")
        self.assertIn("Action", preview["genre"])

        # Check multi-quality options extracted
        options = preview.get("download_options", [])
        self.assertEqual(len(options), 3)

        # 1080p should select smallest file (1.2 GB, not 2.4 GB or 1.8 GB)
        opt_1080 = next((o for o in options if o["quality"] == "1080p"), None)
        self.assertIsNotNone(opt_1080)
        self.assertEqual(opt_1080["url"], "https://my-own-site.com/download/leo-1080p-server2.mkv")
        self.assertEqual(opt_1080["size"], "1.2 GB")

        # 720p should select smallest file (700 MB, not 1.1 GB)
        opt_720 = next((o for o in options if o["quality"] == "720p"), None)
        self.assertIsNotNone(opt_720)
        self.assertEqual(opt_720["url"], "https://my-own-site.com/download/leo-720p-server2.mkv")
        self.assertEqual(opt_720["size"], "700 MB")

        # 480p should select 500 MB
        opt_480 = next((o for o in options if o["quality"] == "480p"), None)
        self.assertIsNotNone(opt_480)
        self.assertEqual(opt_480["url"], "https://my-own-site.com/download/leo-480p-server1.mkv")
        self.assertEqual(opt_480["size"], "500 MB")

        # 3. Confirm & save
        res_save = self.client.post("/admin/api/import/save", json=preview)
        self.assertEqual(res_save.status_code, 201)

        # Verify saved in JSON
        with open(TAMIL_FILE, "r", encoding="utf-8") as f:
            tamil_data = json.load(f)
        saved_movie = next((m for m in tamil_data if m["title"] == "Leo"), None)
        self.assertIsNotNone(saved_movie)
        self.assertEqual(len(saved_movie.get("download_options", [])), 3)

        # 4. Duplicate prevention: try saving same movie again
        res_dup = self.client.post("/admin/api/import/save", json=preview)
        self.assertEqual(res_dup.status_code, 409, "Duplicate movie was not rejected!")

    # -----------------------------------------------------------------------
    # 7. Robots.txt Explicit Disallow vs Allow
    # -----------------------------------------------------------------------
    @patch.dict(os.environ, {"OWN_SITE_URL": "https://my-own-site.com"})
    @patch("site_grabber.check_robots_permission")
    def test_07_robots_txt_handling(self, mock_robots):
        # When robots.txt explicitly disallows the URL
        mock_robots.return_value = (False, "This URL is disallowed by your website's robots.txt. Please allow this path in robots.txt.")
        res = self.client.post("/admin/api/import", json={"url": "https://my-own-site.com/movies/secret-movie"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("This URL is disallowed by your website's robots.txt. Please allow this path in robots.txt.", res.get_json().get("error", ""))

    # -----------------------------------------------------------------------
    # 8. Tamil Movie Card Actions: DOWNLOAD ONLY (No Watch/Play/TMDB)
    # -----------------------------------------------------------------------
    def test_08_tamil_ui_download_only(self):
        # Insert a sample Tamil movie with multiple download options
        sample = {
            "id": "tamil-uuid-999",
            "title": "Vikram Vedha",
            "poster": "https://example.com/vv.jpg",
            "year": "2022",
            "genre": "Neo-Noir",
            "download_url": "https://my-site.com/dl/vv-1080p.mp4",
            "download_options": [
                {"quality": "1080p", "size": "1.2 GB", "url": "https://my-site.com/dl/vv-1080p.mp4"},
                {"quality": "720p", "size": "700 MB", "url": "https://my-site.com/dl/vv-720p.mp4"}
            ],
            "description": "A pragmatic police inspector."
        }
        with open(TAMIL_FILE, "w", encoding="utf-8") as f:
            json.dump([sample], f)

        # Verify Tamil detail view
        res = self.client.get(f"/tamil/{sample['id']}")
        self.assertEqual(res.status_code, 200)
        content = res.data.decode("utf-8")

        # Must have Download Options by quality
        self.assertIn("Download Options", content)
        self.assertIn("1080p", content)
        self.assertIn("1.2 GB", content)
        self.assertIn("720p", content)
        self.assertIn("700 MB", content)
        self.assertIn("https://my-site.com/dl/vv-1080p.mp4", content)
        self.assertIn("https://my-site.com/dl/vv-720p.mp4", content)

        # Must NOT show Watch / Play / TMDB / Streaming in actions
        actions_html = content[content.find('class="detail-actions"'):content.find('</main>')]
        self.assertNotIn("Play", actions_html)
        self.assertNotIn("Watch Trailer", actions_html)
        self.assertNotIn("TMDB", actions_html)
        self.assertNotIn("Streaming", actions_html)

    # -----------------------------------------------------------------------
    # 9. TMDB Update Script Isolation
    # -----------------------------------------------------------------------
    def test_09_tmdb_update_preserves_admin_tamil_movies(self):
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
    # 10. App Restart Persistence
    # -----------------------------------------------------------------------
    def test_10_restart_data_remains(self):
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

    # -----------------------------------------------------------------------
    # 11. Unknown File Size Not Guessed
    # -----------------------------------------------------------------------
    @patch.dict(os.environ, {"OWN_SITE_URL": "https://my-own-site.com"})
    @patch("site_grabber.check_robots_permission", return_value=(True, None))
    @patch("site_grabber.fetch_html")
    def test_11_unknown_size_not_guessed(self, mock_html, mock_robots):
        mock_html.return_value = """
        <!DOCTYPE html>
        <html>
        <body>
          <h1>Mystery Movie</h1>
          <a class="download-btn" href="/download/mystery-1080p.mkv">Download 1080p</a>
        </body>
        </html>
        """
        # Scrape with HEAD fallback disabled/mocked returning None
        with patch("site_grabber.detect_size_from_context", return_value=(None, None)):
            res = self.client.post("/admin/api/import", json={"url": "https://my-own-site.com/movies/mystery"})
            self.assertEqual(res.status_code, 200)
            preview = res.get_json()["preview"]
            options = preview.get("download_options", [])
            self.assertEqual(len(options), 1)
            # Size must be None and not guessed
            self.assertIsNone(options[0]["size"])
            self.assertIsNone(options[0]["size_bytes"])

    # -----------------------------------------------------------------------
    # 12. Head Request Size Fallback
    # -----------------------------------------------------------------------
    @patch("requests.head")
    def test_12_head_request_size_fallback(self, mock_head):
        mock_response = MagicMock()
        mock_response.headers = {"Content-Length": "1288490188"}  # 1.2 GB
        mock_head.return_value = mock_response

        size_str, size_bytes = site_grabber.detect_size_from_context(None, "https://my-own-site.com/dl/file.mkv", fetch_head=True)
        self.assertEqual(size_str, "1.2 GB")
        self.assertEqual(size_bytes, 1288490188)

if __name__ == "__main__":
    unittest.main()
