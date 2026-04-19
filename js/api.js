/* Lightweight wrapper around the Compass backend API.
 *
 * The backend serves both the API and these static pages under the same
 * origin, so relative URLs are sufficient.
 */
(function () {
  const API_BASE = window.COMPASS_API_BASE || "/api";

  async function request(path, { method = "GET", body, query } = {}) {
    let url = `${API_BASE}${path}`;
    if (query) {
      const qs = new URLSearchParams(
        Object.entries(query).filter(([, v]) => v !== undefined && v !== null && v !== "")
      ).toString();
      if (qs) url += `?${qs}`;
    }

    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }

    const res = await fetch(url, opts);
    let data = null;
    try {
      data = await res.json();
    } catch (_) {
      /* response was not JSON */
    }
    if (!res.ok) {
      const message = (data && (data.error || data.message)) || `HTTP ${res.status}`;
      const err = new Error(message);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  const CompassAPI = {
    catalog() {
      return request("/catalog");
    },
    apScores(institution, major, refresh = false) {
      return request("/ap-scores", {
        query: { institution, major, refresh: refresh ? 1 : undefined },
      });
    },
    deadline(institution, major, term, refresh = false) {
      return request("/deadlines", {
        query: { institution, major, term, refresh: refresh ? 1 : undefined },
      });
    },
    courseOverlap(fromInstitution, selections, refresh = false) {
      return request("/course-overlap", {
        method: "POST",
        body: {
          from_institution: fromInstitution,
          selections,
          refresh,
        },
      });
    },
  };

  function fillSelect(selectEl, items, placeholder) {
    if (!selectEl) return;
    selectEl.innerHTML = "";
    if (placeholder) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = placeholder;
      selectEl.appendChild(opt);
    }
    for (const item of items) {
      const opt = document.createElement("option");
      opt.value = item;
      opt.textContent = item;
      selectEl.appendChild(opt);
    }
  }

  // localStorage-backed persistence for the user's transfer-deadlines list.
  // The course-overlap page reads from this same store.
  const DeadlineList = {
    KEY: "compass.deadlineList",
    read() {
      try {
        const raw = localStorage.getItem(this.KEY);
        if (!raw) return [];
        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed : [];
      } catch (_) {
        return [];
      }
    },
    write(list) {
      localStorage.setItem(this.KEY, JSON.stringify(list));
    },
    add(entry) {
      const list = this.read();
      const exists = list.some(
        (it) =>
          it.institution === entry.institution &&
          it.major === entry.major &&
          it.term === entry.term
      );
      if (!exists) {
        list.push(entry);
        this.write(list);
      }
      return this.read();
    },
    remove(index) {
      const list = this.read();
      list.splice(index, 1);
      this.write(list);
      return list;
    },
  };

  window.CompassAPI = CompassAPI;
  window.CompassUI = { fillSelect };
  window.CompassStore = { DeadlineList };
})();
