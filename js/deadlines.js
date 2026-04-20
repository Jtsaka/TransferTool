(async function () {
  const schoolSelect = document.querySelector('[data-role="school-select"]');
  const majorSelect = document.querySelector('[data-role="major-select"]');
  const termSelect = document.querySelector('[data-role="term-select"]');
  const addBtn = document.querySelector('[data-role="add-btn"]');
  const tbody = document.querySelector('[data-role="deadline-tbody"]');
  const statusEl = document.querySelector('[data-role="deadline-status"]');

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

  function render() {
    const list = CompassStore.DeadlineList.read();
    tbody.innerHTML = "";
    if (list.length === 0) {
      tbody.innerHTML =
        '<tr><td colspan="5" class="muted">Add a school/major/term above to get started.</td></tr>';
      return;
    }
    list.forEach((entry, idx) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeHtml(entry.institution)}</td>
        <td>${escapeHtml(entry.major)}</td>
        <td>${escapeHtml(entry.term)}</td>
        <td>${escapeHtml(entry.deadline || "Loading…")}</td>
        <td><button class="delete-btn" data-idx="${idx}">x</button></td>
      `;
      tbody.appendChild(tr);
    });

    tbody.querySelectorAll("button.delete-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const idx = Number(e.currentTarget.getAttribute("data-idx"));
        CompassStore.DeadlineList.remove(idx);
        render();
      });
    });
  }

  async function add() {
    const institution = schoolSelect.value;
    const major = majorSelect.value;
    const term = termSelect.value;
    if (!institution || !major || !term) {
      setStatus("Please select a school, major, and term.", true);
      return;
    }
    setStatus("Looking up deadline…");
    try {
      const result = await CompassAPI.deadline(institution, major, term);
      CompassStore.DeadlineList.add({
        institution,
        major,
        term,
        deadline: result.deadline,
      });
      const label =
        result.source === "cache"
          ? "Added (loaded from cache)."
          : "Added (fetched from Gemini).";
      setStatus(label);
      render();
    } catch (err) {
      setStatus(err.message || "Lookup failed.", true);
    }
  }

  try {
    const cat = await CompassAPI.catalog();
    CompassUI.fillSelect(schoolSelect, cat.schools || [], "School/University");
    CompassUI.fillSelect(majorSelect, cat.majors || [], "Major");
    CompassUI.fillSelect(termSelect, cat.terms || [], "Season, Year");
  } catch (err) {
    setStatus("Could not load catalog: " + err.message, true);
  }

  addBtn?.addEventListener("click", add);
  render();
})();
