/**
 * admin.js — MoviesHub Admin Panel frontend scripts
 * Handles: CRUD for Tamil movies, Import from own site with preview & confirmation
 */

"use strict";

function showAdminAlert(text, type = "success") {
  const el = document.getElementById("admin-alert");
  if (!el) return;
  el.textContent = text;
  el.className = `alert alert-${type} visible`;
  setTimeout(() => {
    el.classList.remove("visible");
  }, 4000);
}

// ---------------------------------------------------------------------------
// Movies List & Table
// ---------------------------------------------------------------------------
async function loadAdminMoviesTable() {
  const tbody = document.getElementById("admin-movies-tbody");
  if (!tbody) return;

  try {
    const res = await fetch("/admin/api/tamil-movies");
    const movies = await res.json();

    if (!movies || movies.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="6" style="text-align:center; padding: 2.5rem; color: var(--text-muted);">
            No Tamil movies added yet. <a href="/admin/add-movie" style="color:var(--primary); font-weight:600;">Add one manually</a> or <a href="/admin/import" style="color:var(--accent); font-weight:600;">import from website</a>.
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = movies.map((m, idx) => {
      const posterHtml = m.poster 
        ? `<img src="${encodeURI(m.poster)}" class="movie-thumb" alt="${m.title}" onerror="this.outerHTML='<div class=\\'movie-thumb-placeholder\\'>🎬</div>'">`
        : `<div class="movie-thumb-placeholder">🎬</div>`;
      
      const badgeClass = m.source === "own-site" ? "source-own" : "source-admin";
      const badgeText = m.source === "own-site" ? "Imported" : "Manual";

      const downloadDisplay = m.download_url
        ? `<a href="${encodeURI(m.download_url)}" target="_blank" rel="noopener noreferrer" style="color:var(--accent); font-size:0.8rem; word-break:break-all;">Link Available</a>`
        : `<span style="color:var(--text-muted); font-size:0.8rem;">No link</span>`;

      return `
        <tr id="row-${m.id}">
          <td style="width: 50px;">${idx + 1}</td>
          <td style="width: 60px;">${posterHtml}</td>
          <td>
            <strong>${escapeHtml(m.title)}</strong>
            <div style="font-size:0.75rem; color:var(--text-muted);">${escapeHtml(m.genre || "Unknown Genre")}</div>
          </td>
          <td>${escapeHtml(m.year || "N/A")}</td>
          <td><span class="source-badge ${badgeClass}">${badgeText}</span></td>
          <td>${downloadDisplay}</td>
          <td>
            <div class="action-btns">
              <a href="/admin/edit-movie/${m.id}" class="btn btn-secondary btn-sm">Edit</a>
              <button class="btn btn-danger btn-sm" onclick="deleteMovie('${m.id}', '${escapeHtml(m.title)}')">Delete</button>
            </div>
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    console.error("Failed to load movies:", err);
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:#f87171;">Error loading movies: ${err.message}</td></tr>`;
  }
}

async function deleteMovie(id, title) {
  if (!confirm(`Are you sure you want to delete "${title}"? This cannot be undone.`)) {
    return;
  }

  try {
    const res = await fetch(`/admin/api/tamil-movies/${id}`, {
      method: "DELETE"
    });
    const result = await res.json();
    if (res.ok && result.success) {
      showAdminAlert(`Movie "${title}" removed successfully.`, "success");
      const row = document.getElementById(`row-${id}`);
      if (row) row.remove();
      // Reload stats if present
      if (document.getElementById("total-movies-count")) {
        loadAdminDashboardStats();
      }
    } else {
      showAdminAlert(result.error || "Failed to delete movie.", "error");
    }
  } catch (err) {
    showAdminAlert(`Delete failed: ${err.message}`, "error");
  }
}

// ---------------------------------------------------------------------------
// Dashboard Stats
// ---------------------------------------------------------------------------
async function loadAdminDashboardStats() {
  try {
    const res = await fetch("/admin/api/tamil-movies");
    const movies = await res.json();
    
    const totalEl = document.getElementById("total-movies-count");
    const manualEl = document.getElementById("manual-movies-count");
    const importedEl = document.getElementById("imported-movies-count");

    if (totalEl) totalEl.textContent = movies.length;
    if (manualEl) manualEl.textContent = movies.filter(m => m.source !== "own-site").length;
    if (importedEl) importedEl.textContent = movies.filter(m => m.source === "own-site").length;

    // Load recent 5
    const recentTbody = document.getElementById("admin-recent-tbody");
    if (recentTbody) {
      const recent = [...movies].reverse().slice(0, 5);
      if (recent.length === 0) {
        recentTbody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--text-muted); padding:1.5rem;">No movies yet.</td></tr>`;
      } else {
        recentTbody.innerHTML = recent.map(m => `
          <tr>
            <td><strong>${escapeHtml(m.title)}</strong></td>
            <td>${escapeHtml(m.year || "N/A")}</td>
            <td><span class="source-badge ${m.source === 'own-site' ? 'source-own' : 'source-admin'}">${m.source === 'own-site' ? 'Imported' : 'Manual'}</span></td>
            <td>
              <a href="/admin/edit-movie/${m.id}" class="btn btn-secondary btn-sm">Edit</a>
            </td>
          </tr>
        `).join("");
      }
    }
  } catch (err) {
    console.error("Dashboard stats error:", err);
  }
}

// ---------------------------------------------------------------------------
// Add Movie Form
// ---------------------------------------------------------------------------
function initAddMovieForm() {
  const form = document.getElementById("add-movie-form");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = form.querySelector("button[type='submit']");
    btn.disabled = true;
    btn.textContent = "Saving...";

    const payload = {
      title: document.getElementById("movie-title").value.trim(),
      poster: document.getElementById("movie-poster").value.trim(),
      description: document.getElementById("movie-desc").value.trim(),
      year: document.getElementById("movie-year").value.trim(),
      genre: document.getElementById("movie-genre").value.trim(),
      download_url: document.getElementById("movie-download").value.trim(),
      source: "admin"
    };

    try {
      const res = await fetch("/admin/api/tamil-movies", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();

      if (res.ok && data.success) {
        showAdminAlert("Movie added successfully!", "success");
        setTimeout(() => {
          window.location.href = "/admin/movies";
        }, 1000);
      } else {
        showAdminAlert(data.error || "Failed to add movie.", "error");
        btn.disabled = false;
        btn.textContent = "Add Movie";
      }
    } catch (err) {
      showAdminAlert(`Network error: ${err.message}`, "error");
      btn.disabled = false;
      btn.textContent = "Add Movie";
    }
  });
}

// ---------------------------------------------------------------------------
// Edit Movie Form
// ---------------------------------------------------------------------------
function initEditMovieForm(movieId) {
  const form = document.getElementById("edit-movie-form");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = form.querySelector("button[type='submit']");
    btn.disabled = true;
    btn.textContent = "Updating...";

    const payload = {
      title: document.getElementById("movie-title").value.trim(),
      poster: document.getElementById("movie-poster").value.trim(),
      description: document.getElementById("movie-desc").value.trim(),
      year: document.getElementById("movie-year").value.trim(),
      genre: document.getElementById("movie-genre").value.trim(),
      download_url: document.getElementById("movie-download").value.trim()
    };

    try {
      const res = await fetch(`/admin/api/tamil-movies/${movieId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();

      if (res.ok && data.success) {
        showAdminAlert("Movie updated successfully!", "success");
        setTimeout(() => {
          window.location.href = "/admin/movies";
        }, 1000);
      } else {
        showAdminAlert(data.error || "Failed to update movie.", "error");
        btn.disabled = false;
        btn.textContent = "Save Changes";
      }
    } catch (err) {
      showAdminAlert(`Network error: ${err.message}`, "error");
      btn.disabled = false;
      btn.textContent = "Save Changes";
    }
  });
}

// ---------------------------------------------------------------------------
// Import from Own Website
// ---------------------------------------------------------------------------
let currentImportPreview = null;

function initImportPage() {
  const importForm = document.getElementById("import-form");
  const previewCard = document.getElementById("import-preview");
  const saveBtn = document.getElementById("btn-confirm-import");
  const cancelBtn = document.getElementById("btn-cancel-import");

  if (!importForm) return;

  importForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const urlInput = document.getElementById("scrape-url");
    const fetchBtn = document.getElementById("btn-fetch-scrape");
    const url = urlInput.value.trim();

    if (!url) return;

    fetchBtn.disabled = true;
    fetchBtn.textContent = "Inspecting site...";
    previewCard.classList.remove("visible");

    try {
      const res = await fetch("/admin/api/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url })
      });
      const data = await res.json();

      if (!res.ok) {
        showAdminAlert(data.error || "Could not extract movie data.", "error");
        fetchBtn.disabled = false;
        fetchBtn.textContent = "Inspect & Extract";
        return;
      }

      currentImportPreview = data.preview;
      renderImportPreview(currentImportPreview);
      previewCard.classList.add("visible");
      fetchBtn.disabled = false;
      fetchBtn.textContent = "Inspect & Extract";
    } catch (err) {
      showAdminAlert(`Extraction failed: ${err.message}`, "error");
      fetchBtn.disabled = false;
      fetchBtn.textContent = "Inspect & Extract";
    }
  });

  if (saveBtn) {
    saveBtn.addEventListener("click", async () => {
      if (!currentImportPreview) return;
      saveBtn.disabled = true;
      saveBtn.textContent = "Saving to Tamil catalogue...";

      try {
        const res = await fetch("/admin/api/import/save", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(currentImportPreview)
        });
        const data = await res.json();

        if (res.ok && data.success) {
          showAdminAlert("Movie saved to Tamil catalogue successfully!", "success");
          setTimeout(() => {
            window.location.href = "/admin/movies";
          }, 1000);
        } else {
          showAdminAlert(data.error || "Failed to save movie.", "error");
          saveBtn.disabled = false;
          saveBtn.textContent = "Confirm & Save Movie";
        }
      } catch (err) {
        showAdminAlert(`Failed to save: ${err.message}`, "error");
        saveBtn.disabled = false;
        saveBtn.textContent = "Confirm & Save Movie";
      }
    });
  }

  if (cancelBtn) {
    cancelBtn.addEventListener("click", () => {
      previewCard.classList.remove("visible");
      currentImportPreview = null;
    });
  }
}

function renderImportPreview(prev) {
  const posterImg = document.getElementById("prev-poster-img");
  const titleEl = document.getElementById("prev-title");
  const metaEl = document.getElementById("prev-meta");
  const descEl = document.getElementById("prev-desc");
  const dlEl = document.getElementById("prev-download-link");
  const dlWarn = document.getElementById("prev-download-warn");

  if (posterImg) {
    if (prev.poster) {
      posterImg.src = prev.poster;
      posterImg.style.display = "block";
    } else {
      posterImg.style.display = "none";
    }
  }

  if (titleEl) titleEl.textContent = prev.title || "No Title Found";
  if (metaEl) {
    metaEl.textContent = `${prev.year || "Unknown Year"} • ${prev.genre || "Unknown Genre"}`;
  }
  if (descEl) descEl.textContent = prev.description || "No description extracted.";

  if (dlEl && dlWarn) {
    if (prev.download_url) {
      dlEl.innerHTML = `<strong>Download URL:</strong> <a href="${encodeURI(prev.download_url)}" target="_blank" style="color:var(--accent);">${escapeHtml(prev.download_url)}</a>`;
      dlWarn.style.display = "none";
    } else {
      dlEl.innerHTML = "";
      dlWarn.textContent = "Download link unavailable (no verified link detected on page)";
      dlWarn.style.display = "block";
    }
  }
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
