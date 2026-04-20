(async function () {
  const schoolSelect = document.querySelector('[data-role="school-select"]');
  const majorSelect = document.querySelector('[data-role="major-select"]');
  const lookupBtn = document.querySelector('[data-role="lookup-btn"]');
  const refreshBtn = document.querySelector('[data-role="refresh-btn"]');
  const tbody = document.querySelector('[data-role="ap-tbody"]');
  const notesEl = document.querySelector('[data-role="ap-notes"]');
  const statusEl = document.querySelector('[data-role="ap-status"]');

  function setStatus(message, isError = false) {
    if (!statusEl) return;
    statusEl.textContent = message || "";
    statusEl.style.color = isError ? "var(--danger)" : "var(--muted)";
  }

  function renderRows(institution, data) {
    tbody.innerHTML = "";
    notesEl.textContent = "";
    if (!data || typeof data !== "object") {
      tbody.innerHTML = '<tr><td colspan="5">No data returned.</td></tr>';
      return;
    }

    const entries = Object.entries(data).filter(([key]) => key !== "SiteNotes");
    if (entries.length === 0) {
      tbody.innerHTML =
        '<tr><td colspan="5">No AP credit information found.</td></tr>';
    }

    for (const [subject, valueRaw] of entries) {
      const records = Array.isArray(valueRaw) ? valueRaw : [valueRaw];
      for (const record of records) {
        if (!record || typeof record !== "object") continue;
        const tr = document.createElement("tr");
        const courses = Array.isArray(record.courses)
          ? record.courses.join(", ")
          : record.courses || "-";
        const minScore = record.min_score ?? "-";
        const maxScore = record.max_score ?? "-";
        const scoreText =
          minScore === maxScore || maxScore === "-"
            ? `${minScore}`
            : `${minScore}–${maxScore}`;
        const units = record.units !== undefined ? record.units : "-";
        const notes = Array.isArray(record.notes)
          ? record.notes.join(". ")
          : record.notes || "";

        tr.innerHTML = `
          <td>${escapeHtml(subject)}</td>
          <td>${escapeHtml(scoreText)}</td>
          <td>${escapeHtml(units)}</td>
          <td>${escapeHtml(courses)}</td>
          <td>${escapeHtml(institution)}${
          notes ? `<div class="muted">${escapeHtml(notes)}</div>` : ""
        }</td>
        `;
        tbody.appendChild(tr);
      }
    }

    const siteNotes = data.SiteNotes;
    if (siteNotes) {
      let text = "";
      if (Array.isArray(siteNotes)) {
        text = siteNotes
          .map((s) => (typeof s === "object" ? s.notes || "" : s))
          .filter(Boolean)
          .join(" ");
      } else if (typeof siteNotes === "object") {
        text = siteNotes.notes || "";
      } else {
        text = String(siteNotes);
      }
      notesEl.textContent = text;
    }
  }

  function escapeHtml(value) {
    if (value === null || value === undefined) return "";
    return String(value).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  async function lookup({ refresh = false } = {}) {
    const institution = schoolSelect.value;
    const major = majorSelect.value;
    if (!institution || !major) {
      setStatus("Please select both a school and a major.", true);
      return;
    }
    setStatus("Looking up AP credit policy…");
    try {
      const result = await CompassAPI.apScores(institution, major, refresh);
      const sourceLabel =
        result.source === "cache"
          ? "Loaded from cache."
          : "Fetched fresh from Gemini and cached.";
      setStatus(sourceLabel);
      renderRows(institution, result.data);
    } catch (err) {
      setStatus(err.message || "Lookup failed.", true);
    }
  }

  try {
    const cat = await CompassAPI.catalog();
    CompassUI.fillSelect(schoolSelect, cat.schools || [], "Select School/University");
    CompassUI.fillSelect(majorSelect, cat.majors || [], "Select Major");
  } catch (err) {
    setStatus("Could not load catalog: " + err.message, true);
  }

  lookupBtn?.addEventListener("click", () => lookup({ refresh: false }));
  refreshBtn?.addEventListener("click", () => lookup({ refresh: true }));
})();
