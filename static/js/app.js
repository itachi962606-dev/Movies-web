/**
 * app.js — MoviesHub main frontend JavaScript
 * Handles: navbar, hero, carousels, watchlist, best list, search, toast
 */

"use strict";

/* ── Constants ──────────────────────────────────────────────────────────── */
const TMDB_IMG  = "https://image.tmdb.org/t/p/w500";
const TMDB_ORIG = "https://image.tmdb.org/t/p/original";
const WL_KEY    = "movieshub_watchlist";
const BL_KEY    = "movieshub_bestlist";

/* ── Utilities ──────────────────────────────────────────────────────────── */

function posterUrl(path) {
  if (!path) return null;
  if (path.startsWith("http")) return path;
  return TMDB_IMG + path;
}

function backdropUrl(path) {
  if (!path) return null;
  if (path.startsWith("http")) return path;
  return TMDB_ORIG + path;
}

function formatRating(r) {
  if (!r) return "";
  return "★ " + parseFloat(r).toFixed(1);
}

function formatYear(date) {
  if (!date) return "";
  return String(date).slice(0, 4);
}

function escHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/* ── Toast ──────────────────────────────────────────────────────────────── */
let _toastTimer;
function showToast(msg, type = "") {
  let t = document.getElementById("global-toast");
  if (!t) {
    t = document.createElement("div");
    t.id = "global-toast";
    t.className = "toast";
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.className = "toast show" + (type ? " " + type : "");
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => t.classList.remove("show"), 3000);
}

/* ── Navbar ─────────────────────────────────────────────────────────────── */
function initNavbar() {
  const nav = document.querySelector(".navbar");
  if (!nav) return;

  // Scroll effect
  window.addEventListener("scroll", () => {
    nav.classList.toggle("scrolled", window.scrollY > 50);
  });

  // Active link
  const links = nav.querySelectorAll(".nav-links a, .nav-mobile a");
  links.forEach((a) => {
    if (a.href && window.location.pathname === new URL(a.href).pathname) {
      a.classList.add("active");
    }
  });

  // Hamburger
  const hamburger = document.getElementById("nav-hamburger");
  const mobileNav = document.getElementById("nav-mobile");
  const mobileClose = document.getElementById("nav-mobile-close");
  if (hamburger && mobileNav) {
    hamburger.addEventListener("click", () => mobileNav.classList.add("open"));
    mobileClose?.addEventListener("click", () => mobileNav.classList.remove("open"));
  }

  // Search overlay
  const searchBtn = document.getElementById("nav-search-btn");
  const searchOverlay = document.getElementById("search-overlay");
  const searchClose = document.getElementById("search-overlay-close");
  const searchInput = document.getElementById("search-input");
  const searchForm = document.getElementById("search-form");

  if (searchBtn && searchOverlay) {
    searchBtn.addEventListener("click", () => {
      searchOverlay.classList.add("open");
      setTimeout(() => searchInput?.focus(), 100);
    });
    searchClose?.addEventListener("click", () => searchOverlay.classList.remove("open"));
    searchOverlay.addEventListener("click", (e) => {
      if (e.target === searchOverlay) searchOverlay.classList.remove("open");
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") searchOverlay.classList.remove("open");
    });
  }

  if (searchForm) {
    searchForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const q = searchInput?.value?.trim();
      if (q) window.location.href = `/movies?query=${encodeURIComponent(q)}`;
    });
  }
}

/* ── Watchlist ──────────────────────────────────────────────────────────── */
function loadWatchlist() {
  try {
    return JSON.parse(localStorage.getItem(WL_KEY) || "[]");
  } catch { return []; }
}

function saveWatchlist(list) {
  localStorage.setItem(WL_KEY, JSON.stringify(list));
}

function isInWatchlist(id, source) {
  return loadWatchlist().some((m) => String(m.id) === String(id) && m.source === source);
}

function toggleWatchlist(movie, source) {
  let list = loadWatchlist();
  const id = String(movie.id);
  const idx = list.findIndex((m) => String(m.id) === id && m.source === source);
  if (idx === -1) {
    list.push({
      id,
      source,
      title: movie.title,
      poster: movie.poster_path || movie.poster || "",
      year: formatYear(movie.release_date || movie.year),
      rating: movie.vote_average || "",
    });
    saveWatchlist(list);
    showToast("Added to Watchlist ❤️", "success");
    return true;
  } else {
    list.splice(idx, 1);
    saveWatchlist(list);
    showToast("Removed from Watchlist");
    return false;
  }
}

function updateWlBtnState(btn, id, source) {
  if (!btn) return;
  const active = isInWatchlist(id, source);
  btn.classList.toggle("active", active);
  btn.title = active ? "Remove from Watchlist" : "Add to Watchlist";
  btn.innerHTML = active ? "❤️" : "🤍";
}

/* ── Best List ──────────────────────────────────────────────────────────── */
function loadBestList() {
  try {
    return JSON.parse(localStorage.getItem(BL_KEY) || "[]");
  } catch { return []; }
}

function saveBestList(list) {
  localStorage.setItem(BL_KEY, JSON.stringify(list));
}

function isInBestList(id, source) {
  return loadBestList().some((m) => String(m.id) === String(id) && m.source === source);
}

function toggleBestList(movie, source) {
  let list = loadBestList();
  const id = String(movie.id);
  const idx = list.findIndex((m) => String(m.id) === id && m.source === source);
  if (idx === -1) {
    list.push({
      id,
      source,
      title: movie.title,
      poster: movie.poster_path || movie.poster || "",
      year: formatYear(movie.release_date || movie.year),
      rating: movie.vote_average || "",
    });
    saveBestList(list);
    showToast("Added to Best List ⭐", "success");
    return true;
  } else {
    list.splice(idx, 1);
    saveBestList(list);
    showToast("Removed from Best List");
    return false;
  }
}

/* ── Movie Card Builders ────────────────────────────────────────────────── */

/**
 * Build a TMDB movie card element.
 */
function buildTmdbCard(movie) {
  const poster = posterUrl(movie.poster_path);
  const year = formatYear(movie.release_date);
  const rating = formatRating(movie.vote_average);
  const id = movie.id;

  const card = document.createElement("div");
  card.className = "movie-card";
  card.dataset.id = id;
  card.dataset.source = "tmdb";
  card.innerHTML = `
    ${poster
      ? `<img class="movie-card-poster" src="${escHtml(poster)}" alt="${escHtml(movie.title)}" loading="lazy">`
      : `<div class="movie-card-poster-placeholder">🎬</div>`}
    <button class="wl-btn" title="Add to Watchlist" data-id="${id}" data-source="tmdb">🤍</button>
    <div class="movie-card-body">
      <div class="movie-card-title">${escHtml(movie.title)}</div>
      <div class="movie-card-meta">
        <span>${escHtml(year)}</span>
        ${rating ? `<span class="movie-card-rating">${escHtml(rating)}</span>` : ""}
      </div>
    </div>
    <div class="movie-card-overlay">
      <a href="/movies/${id}" class="btn btn-primary btn-sm">Details</a>
    </div>
  `;

  // Watchlist button
  const wlBtn = card.querySelector(".wl-btn");
  updateWlBtnState(wlBtn, id, "tmdb");
  wlBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleWatchlist(movie, "tmdb");
    updateWlBtnState(wlBtn, id, "tmdb");
  });

  card.addEventListener("click", () => { window.location.href = `/movies/${id}`; });
  return card;
}

/**
 * Build a Tamil admin movie card element.
 */
function buildTamilCard(movie) {
  const poster = movie.poster;
  const id = movie.id;

  const card = document.createElement("div");
  card.className = "movie-card";
  card.dataset.id = id;
  card.dataset.source = "admin";
  card.innerHTML = `
    ${poster
      ? `<img class="movie-card-poster" src="${escHtml(poster)}" alt="${escHtml(movie.title)}" loading="lazy">`
      : `<div class="movie-card-poster-placeholder">🎬</div>`}
    <div class="movie-card-body">
      <div class="movie-card-title">${escHtml(movie.title)}</div>
      <div class="movie-card-meta">
        <span>${escHtml(movie.year || "")}</span>
        <span>${escHtml(movie.genre || "")}</span>
      </div>
    </div>
    <div class="movie-card-overlay">
      ${movie.download_url
        ? `<a href="${escHtml(movie.download_url)}" class="btn btn-accent btn-sm" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">⬇ Download</a>`
        : `<span class="btn btn-secondary btn-sm" style="opacity:0.6;cursor:default;">No Link</span>`}
      <a href="/tamil/${escHtml(id)}" class="btn btn-secondary btn-sm" onclick="event.stopPropagation()">Details</a>
    </div>
  `;

  card.addEventListener("click", () => { window.location.href = `/tamil/${id}`; });
  return card;
}

/* ── Carousel ───────────────────────────────────────────────────────────── */
function initCarousel(wrapEl) {
  const track = wrapEl.querySelector(".carousel");
  if (!track) return;
  const leftBtn = wrapEl.querySelector(".carousel-arrow.left");
  const rightBtn = wrapEl.querySelector(".carousel-arrow.right");

  const scroll = (dir) => {
    const w = track.getBoundingClientRect().width;
    track.scrollBy({ left: dir * w * 0.75, behavior: "smooth" });
  };
  leftBtn?.addEventListener("click", () => scroll(-1));
  rightBtn?.addEventListener("click", () => scroll(1));
}

function renderCarousel(wrapEl, movies, builder) {
  const track = wrapEl.querySelector(".carousel");
  if (!track) return;
  track.innerHTML = "";
  movies.forEach((m) => track.appendChild(builder(m)));
  initCarousel(wrapEl);
}

/* ── Hero Banner ────────────────────────────────────────────────────────── */
let _heroSlides = [];
let _heroCurrent = 0;
let _heroTimer;

function initHero(movies) {
  if (!movies || !movies.length) return;
  _heroSlides = movies.slice(0, 5);
  _heroCurrent = 0;

  const slidesEl  = document.querySelector(".hero-slides");
  const dotsEl    = document.querySelector(".hero-dots");
  const titleEl   = document.querySelector(".hero-title");
  const descEl    = document.querySelector(".hero-desc");
  const ratingEl  = document.querySelector(".hero-rating");
  const yearEl    = document.querySelector(".hero-year");
  const detailBtn = document.getElementById("hero-detail-btn");
  const wlBtn     = document.getElementById("hero-wl-btn");

  if (!slidesEl) return;

  // Build slide backgrounds
  slidesEl.innerHTML = "";
  _heroSlides.forEach((m, i) => {
    const div = document.createElement("div");
    div.className = "hero-slide" + (i === 0 ? " active" : "");
    const bg = backdropUrl(m.backdrop_path) || posterUrl(m.poster_path);
    if (bg) div.style.backgroundImage = `url('${bg}')`;
    slidesEl.appendChild(div);
  });

  // Dots
  if (dotsEl) {
    dotsEl.innerHTML = "";
    _heroSlides.forEach((_, i) => {
      const dot = document.createElement("button");
      dot.className = "hero-dot" + (i === 0 ? " active" : "");
      dot.setAttribute("aria-label", `Slide ${i + 1}`);
      dot.addEventListener("click", () => goHero(i));
      dotsEl.appendChild(dot);
    });
  }

  function goHero(idx) {
    clearInterval(_heroTimer);
    _heroCurrent = idx;
    updateHero();
    _heroTimer = setInterval(nextHero, 6000);
  }

  function nextHero() {
    _heroCurrent = (_heroCurrent + 1) % _heroSlides.length;
    updateHero();
  }

  function updateHero() {
    const m = _heroSlides[_heroCurrent];
    // Slides
    document.querySelectorAll(".hero-slide").forEach((s, i) =>
      s.classList.toggle("active", i === _heroCurrent));
    // Dots
    document.querySelectorAll(".hero-dot").forEach((d, i) =>
      d.classList.toggle("active", i === _heroCurrent));
    // Text
    if (titleEl) titleEl.textContent = m.title || "";
    if (descEl)  descEl.textContent  = m.overview || "";
    if (ratingEl) ratingEl.textContent = formatRating(m.vote_average);
    if (yearEl)   yearEl.textContent  = formatYear(m.release_date);
    // Buttons
    if (detailBtn) detailBtn.href = `/movies/${m.id}`;
    if (wlBtn) updateWlBtnState(wlBtn, m.id, "tmdb");
    if (wlBtn) {
      wlBtn.onclick = (e) => {
        e.preventDefault();
        toggleWatchlist(m, "tmdb");
        updateWlBtnState(wlBtn, m.id, "tmdb");
      };
    }
  }

  updateHero();
  _heroTimer = setInterval(nextHero, 6000);
}

/* ── Expose for inline HTML use ─────────────────────────────────────────── */
window.MH = {
  posterUrl,
  backdropUrl,
  formatRating,
  formatYear,
  escHtml,
  showToast,
  loadWatchlist,
  saveWatchlist,
  isInWatchlist,
  toggleWatchlist,
  loadBestList,
  saveBestList,
  isInBestList,
  toggleBestList,
  updateWlBtnState,
  buildTmdbCard,
  buildTamilCard,
  renderCarousel,
  initCarousel,
  initHero,
  initNavbar,
};

/* ── Auto-init ──────────────────────────────────────────────────────────── */
document.addEventListener("DOMContentLoaded", () => {
  initNavbar();
});
