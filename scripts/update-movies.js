#!/usr/bin/env node
/**
 * scripts/update-movies.js
 *
 * Fetches popular, top-rated, and trending non-Tamil movies from TMDB
 * and writes them to data/movies.json.
 *
 * NEVER touches data/admin_tamil_movies.json.
 *
 * Usage:
 *   node --env-file=.env scripts/update-movies.js
 *
 * Requires Node 20+ for --env-file support.
 * Falls back to reading .env manually for older Node.
 */

"use strict";

const fs = require("fs");
const path = require("path");
const https = require("https");

// ---------------------------------------------------------------------------
// Read .env manually as fallback (Node < 20 doesn't have --env-file)
// ---------------------------------------------------------------------------
function loadEnvFallback() {
  const envPath = path.join(__dirname, "..", ".env");
  if (!fs.existsSync(envPath)) return;
  const lines = fs.readFileSync(envPath, "utf-8").split("\n");
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const idx = trimmed.indexOf("=");
    if (idx === -1) continue;
    const key = trimmed.slice(0, idx).trim();
    const val = trimmed.slice(idx + 1).trim().replace(/^["']|["']$/g, "");
    if (!process.env[key]) process.env[key] = val;
  }
}
loadEnvFallback();

const API_KEY = process.env.TMDB_API_KEY;
if (!API_KEY) {
  console.error("[ERROR] TMDB_API_KEY is not set. Aborting.");
  process.exit(1);
}

const TMDB_BASE = "https://api.themoviedb.org/3";
const OUTPUT_FILE = path.join(__dirname, "..", "data", "movies.json");

// ---------------------------------------------------------------------------
// HTTP helper
// ---------------------------------------------------------------------------
function get(url) {
  return new Promise((resolve, reject) => {
    https.get(url, { headers: { "User-Agent": "MoviesHub/1.0" } }, (res) => {
      let body = "";
      res.on("data", (chunk) => (body += chunk));
      res.on("end", () => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          try {
            resolve(JSON.parse(body));
          } catch (e) {
            reject(new Error(`JSON parse error: ${e.message}`));
          }
        } else {
          reject(new Error(`HTTP ${res.statusCode}: ${url}`));
        }
      });
    }).on("error", reject);
  });
}

function tmdbUrl(endpoint, params = {}) {
  const p = new URLSearchParams({ api_key: API_KEY, language: "en-US", ...params });
  return `${TMDB_BASE}${endpoint}?${p}`;
}

// ---------------------------------------------------------------------------
// Fetch helper — multiple pages
// ---------------------------------------------------------------------------
async function fetchPages(endpoint, extraParams = {}, pages = 3) {
  const results = [];
  for (let page = 1; page <= pages; page++) {
    try {
      const data = await get(tmdbUrl(endpoint, { page, ...extraParams }));
      results.push(...(data.results || []));
    } catch (e) {
      console.warn(`[WARN] ${endpoint} page ${page}: ${e.message}`);
    }
  }
  return results;
}

// ---------------------------------------------------------------------------
// Filter — exclude Tamil-language movies
// ---------------------------------------------------------------------------
function filterNonTamil(movies) {
  return movies.filter((m) => m.original_language !== "ta");
}

// ---------------------------------------------------------------------------
// Deduplicate by TMDB id
// ---------------------------------------------------------------------------
function dedupe(movies) {
  const seen = new Set();
  return movies.filter((m) => {
    if (seen.has(m.id)) return false;
    seen.add(m.id);
    return true;
  });
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
async function main() {
  console.log("[INFO] Fetching movies from TMDB...");

  const [popular, topRated, trending, upcoming] = await Promise.all([
    fetchPages("/movie/popular", { vote_count_gte: 50 }, 5),
    fetchPages("/movie/top_rated", {}, 5),
    fetchPages("/trending/movie/week", {}, 2),
    fetchPages("/movie/upcoming", {}, 2),
  ]);

  const all = [...popular, ...topRated, ...trending, ...upcoming];
  const filtered = filterNonTamil(all);
  const unique = dedupe(filtered);

  console.log(`[INFO] Total fetched: ${all.length}`);
  console.log(`[INFO] After Tamil filter: ${filtered.length}`);
  console.log(`[INFO] After dedup: ${unique.length}`);

  // SAFETY: Never touch admin_tamil_movies.json
  const tamilFile = path.join(__dirname, "..", "data", "admin_tamil_movies.json");
  if (fs.existsSync(tamilFile)) {
    const tamilContent = fs.readFileSync(tamilFile, "utf-8");
    const tamilMovies = JSON.parse(tamilContent);
    console.log(`[INFO] Tamil admin movies untouched: ${tamilMovies.length} movies preserved.`);
  }

  // Atomic write: write to tmp, rename
  const tmpFile = OUTPUT_FILE + ".tmp";
  fs.writeFileSync(tmpFile, JSON.stringify(unique, null, 2), "utf-8");
  fs.renameSync(tmpFile, OUTPUT_FILE);

  console.log(`[SUCCESS] Wrote ${unique.length} movies to ${OUTPUT_FILE}`);
}

main().catch((e) => {
  console.error("[ERROR]", e.message);
  process.exit(1);
});
