(async function () {
  const tbody = document.querySelector('[data-role="overlap-tbody"]');
  const statusEl = document.querySelector('[data-role="overlap-status"]');
  const refreshBtn = document.querySelector('[data-role="refresh-btn"]');
  const fromLabel = document.querySelector('[data-role="from-institution"]');
  const countEl = document.querySelector('[data-role="campus-count"]');

  function setStatus(msg, isError = false) {
    if (!statusEl) return;
    statusEl.textContent = msg || "";
    statusEl.style.color = isError ? "var(--danger)" : "var(--muted)";
  }

  function escapeHtml(value) {
    if (value === null || value === undefined) return "";
    return String(value).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  function render(result) {
    tbody.innerHTML = "";
    if (!result || !Array.isArray(result.overlap) || result.overlap.length === 0) {
      tbody.innerHTML =
        '<tr><td colspan="4" class="muted">No overlapping courses yet. Add schools on the Deadlines page first.</td></tr>';
      countEl.textContent = "0";
      return;
    }
    countEl.textContent = String(result.total_schools || 0);
    for (const row of result.overlap) {
      const tr = document.createElement("tr");
      const pills = (row.majors || [])
        .map((m) => `<span class="pill">${escapeHtml(m)}</span>`)
        .join("");
      tr.innerHTML = `
        <td>${escapeHtml(row.course)}</td>
        <td>${escapeHtml(row.title || "")}</td>
        <td><div class="pill-group">${pills}</div></td>
        <td>${row.school_count}<div class="muted">${escapeHtml(
        (row.schools || []).join(", ")
      )}</div></td>
      `;
      tbody.appendChild(tr);
    }
  }

  async function load({ refresh = false } = {}) {
    const list = CompassStore.DeadlineList.read();
    if (list.length === 0) {
      setStatus(
        "Your deadline list is empty. Visit the Deadlines page to add schools/majors first."
      );
      tbody.innerHTML =
        '<tr><td colspan="4" class="muted">No selections yet.</td></tr>';
      countEl.textContent = "0";
      return;
    }

    let cat;
    try {
      cat = await CompassAPI.catalog();
    } catch (_) {
      cat = {};
    }
    const fromInstitution = cat.default_from_institution || "College of San Mateo";
    if (fromLabel) fromLabel.textContent = fromInstitution;

    const selections = list.map((it) => ({
      institution: it.institution,
      major: it.major,
    }));

    setStatus("Computing course overlap…");
    try {
      const result = await CompassAPI.courseOverlap(
        fromInstitution,
        selections,
        refresh
      );
      const errs = result.errors || [];
      if (errs.length) {
        setStatus(
          `Computed with ${errs.length} lookup error(s): ` +
            errs.map((e) => `${e.institution} (${e.error})`).join("; "),
          true
        );
      } else {
        setStatus("Done.");
      }
      render(result);
    } catch (err) {
      setStatus(err.message || "Overlap calculation failed.", true);
    }
  }

  refreshBtn?.addEventListener("click", () => load({ refresh: true }));
  load();
})();
