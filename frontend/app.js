/* Manufacturing Quality Intelligence — vanilla JS frontend (no build step).
   Served same-origin by FastAPI, so API_BASE defaults to "". Use ?api=http://host:port
   when opening index.html directly from disk. */
(function () {
  "use strict";

  var params = new URLSearchParams(window.location.search);
  var API_BASE = params.get("api") || "";

  var state = { summary: null, selected: null, raw: {} };

  function $(id) { return document.getElementById(id); }
  function api(path, options) {
    return fetch(API_BASE + path, options).then(function (res) {
      if (!res.ok) {
        return res.json().catch(function () { return {}; }).then(function (body) {
          throw new Error(body.detail || ("HTTP " + res.status));
        });
      }
      return res.json();
    });
  }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function setHealth() {
    var el = $("health");
    api("/health").then(function (h) {
      el.textContent = "API ok · LLM: " + h.llm_provider + (h.has_database ? " · SQLite" : "");
      el.className = "health ok";
    }).catch(function () {
      el.textContent = "API unreachable — start it with: python main.py api";
      el.className = "health bad";
    });
  }

  function loadSummary() {
    var p1 = api("/summary").then(function (s) {
      state.summary = s;
      $("c-total").textContent = s.total;
      $("c-pass").textContent = s.counts.PASS || 0;
      $("c-fail").textContent = s.counts.FAIL || 0;
      $("c-review").textContent = s.counts.REVIEW || 0;
      $("c-disc").textContent = s.discrepancies;
    });
    // Raw CSV rows (recorded measurements) for the detail panel.
    var p2 = api("/batches").then(function (b) {
      (b.batches || []).forEach(function (r) { state.raw[r.batch_id] = r; });
    }).catch(function () { /* list is best-effort; validation still renders */ });
    return Promise.all([p1, p2]).then(renderList).catch(function (err) {
      $("batch-list").innerHTML = '<p class="note">Could not load summary: ' + esc(err.message) +
        '. Is the API running? (<code>python main.py api</code>)</p>';
    });
  }

  function filteredRows() {
    var rows = (state.summary && state.summary.results) || [];
    var p = $("f-product").value, st = $("f-status").value;
    var q = $("f-search").value.trim().toLowerCase();
    return rows.filter(function (r) {
      if (p !== "all" && r.product_type !== p) return false;
      if (st !== "all" && r.calculated_status !== st) return false;
      if (q && r.batch_id.toLowerCase().indexOf(q) === -1) return false;
      return true;
    });
  }

  function renderList() {
    var rows = filteredRows();
    $("list-count").textContent = "(" + rows.length + ")";
    var html = rows.map(function (r) {
      var sel = state.selected === r.batch_id ? " selected" : "";
      return '<button type="button" class="batch' + sel + '" data-id="' + esc(r.batch_id) + '">' +
        "<span><strong>" + esc(r.batch_id) + "</strong> <small>" + esc(r.product_type) + "</small></span>" +
        '<span class="badge ' + esc(r.calculated_status) + '">' + esc(r.calculated_status) + "</span>" +
        "</button>";
    }).join("");
    $("batch-list").innerHTML = html || '<p class="note">No batches match the filters.</p>';
    Array.prototype.forEach.call(document.querySelectorAll(".batch"), function (b) {
      b.addEventListener("click", function () { selectBatch(b.getAttribute("data-id")); });
    });
  }

  function selectBatch(id) {
    state.selected = id;
    renderList();
    $("detail-empty").hidden = true;
    $("detail").hidden = false;
    $("workflow").innerHTML = "";
    $("review-msg").textContent = "";
    api("/batches/" + encodeURIComponent(id)).then(renderDetail).catch(function (err) {
      $("detail").hidden = true;
      $("detail-empty").hidden = false;
      $("detail-empty").textContent = "Error: " + err.message;
    });
  }

  function renderDetail(v) {
    $("d-id").textContent = v.batch_id + " · " + v.product_type;
    var badges = '<span class="badge ' + esc(v.calculated_status) + '">calc ' + esc(v.calculated_status) + "</span>" +
      '<span class="badge REVIEW">recorded ' + esc(v.recorded_status || "?") + "</span>";
    if (v.discrepancy) badges += '<span class="badge DIFF">DISCREPANCY</span>';
    $("d-badges").innerHTML = badges;

    var m = $("d-measurements");
    m.innerHTML = "";
    function addRow(k, val) {
      var dt = document.createElement("dt"); dt.textContent = k;
      var dd = document.createElement("dd"); dd.textContent = (val === "" || val == null) ? "N/A" : val;
      m.appendChild(dt); m.appendChild(dd);
    }
    // Recorded raw measurements first, then the configured limits used.
    var raw = state.raw[v.batch_id] || {};
    ["purity_pct", "moisture_pct", "particle_size_um", "defect_count", "inspection_status"].forEach(function (k) {
      if (raw[k] !== undefined) addRow("measured " + k, raw[k]);
    });
    // Raw measurements come from /batches list; validation carries checks/limits.
    var lim = v.limits_used || {};
    Object.keys(lim).forEach(function (k) {
      var dt = document.createElement("dt"); dt.textContent = "limit " + k;
      var dd = document.createElement("dd"); dd.textContent = lim[k];
      m.appendChild(dt); m.appendChild(dd);
    });

    var c = $("d-checks");
    var html = "";
    if (v.failed_checks && v.failed_checks.length) {
      html += "<strong>Failed checks:</strong><ul class='checks'>" +
        v.failed_checks.map(function (f) { return "<li>" + esc(f.message) + "</li>"; }).join("") + "</ul>";
    } else {
      html += "<p class='note'>No failed checks.</p>";
    }
    if (v.missing_fields && v.missing_fields.length)
      html += "<p class='note'>Missing: " + esc(v.missing_fields.join(", ")) + "</p>";
    if (v.errors && v.errors.length)
      html += "<p class='note'>Notes: " + esc(v.errors.join(" | ")) + "</p>";
    c.innerHTML = html;
  }

  function investigate() {
    if (!state.selected) return;
    var btn = $("btn-investigate");
    btn.disabled = true;
    $("workflow").innerHTML = "<p class='note'>Investigating…</p>";
    api("/batches/" + encodeURIComponent(state.selected) + "/investigate", { method: "POST" })
      .then(function (wf) {
        var h = "<p class='note'>Iterations: " + wf.iterations +
          " · Final: <strong>" + esc(wf.final_disposition) + "</strong>" +
          " · Human review required: " + (wf.requires_human_review ? "yes" : "no") + "</p>";
        if (wf.investigation) {
          h += "<strong>Facts:</strong><ul class='fact-list'>" +
            wf.investigation.facts.map(function (f) { return "<li>" + esc(f) + "</li>"; }).join("") + "</ul>";
          h += "<strong>Hypotheses:</strong><ul class='hyp-list'>" +
            wf.investigation.hypotheses.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul>";
          if (wf.investigation.recommendations && wf.investigation.recommendations.length) {
            h += "<strong>Recommended next steps (require human approval):</strong><ul class='hyp-list'>" +
              wf.investigation.recommendations.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul>";
          }
          if (wf.investigation.llm_model) {
            h += "<p class='note'>Drafted with " + esc(wf.investigation.llm_model) + " (deterministic validation unchanged).</p>";
          }
          h += "<strong>SOP evidence:</strong>";
          if (wf.investigation.evidence.length) {
            h += wf.investigation.evidence.map(function (e) {
              return "<div class='evidence'><cite>" + esc(e.source_title) + " §" + esc(e.section) +
                " (" + esc(e.document_id) + " v" + esc(e.version) + ") score=" + e.score + "</cite>" +
                esc(e.text_excerpt.slice(0, 300)) + "</div>";
            }).join("");
          } else {
            h += "<p class='note'>No SOP evidence retrieved.</p>";
          }
        }
        if (wf.verification) {
          h += "<p class='note'>Verification supported=" + wf.verification.supported + ": " +
            esc(wf.verification.reasons.join(" | ")) + "</p>";
        }
        $("workflow").innerHTML = h;
      })
      .catch(function (err) { $("workflow").innerHTML = "<p class='note'>Error: " + esc(err.message) + "</p>"; })
      .finally(function () { btn.disabled = false; });
  }

  function showHistory() {
    if (!state.selected) return;
    $("workflow").innerHTML = "<p class='note'>Loading history…</p>";
    api("/batches/" + encodeURIComponent(state.selected) + "/history")
      .then(function (h) {
        var wf = h.workflow;
        $("workflow").innerHTML = "<p class='note'>Validation: <strong>" +
          esc(wf.validation.calculated_status) + "</strong> (recorded " +
          esc(wf.validation.recorded_status || "?") + ") · iterations " + wf.iterations +
          " · final " + esc(wf.final_disposition) + "</p><p class='note'>" +
          esc((wf.notes || []).join(" | ")) + "</p>";
      })
      .catch(function (err) { $("workflow").innerHTML = "<p class='note'>Error: " + esc(err.message) + "</p>"; });
  }

  function submitReview(ev) {
    ev.preventDefault();
    if (!state.selected) return;
    var body = {
      decision: $("r-decision").value,
      comments: $("r-comments").value,
      reviewer: $("r-reviewer").value || "human_reviewer"
    };
    $("review-msg").textContent = "Submitting…";
    api("/batches/" + encodeURIComponent(state.selected) + "/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (r) {
      $("review-msg").textContent = "Recorded " + r.decision + " for " + r.batch_id +
        (r.persisted ? " (persisted to SQLite)." : " (not persisted).");
    }).catch(function (err) { $("review-msg").textContent = "Error: " + err.message; });
  }

  function ingest() {
    var btn = $("btn-ingest");
    btn.disabled = true;
    $("ingest-msg").textContent = "ingesting…";
    api("/documents/ingest", { method: "POST" }).then(function (r) {
      $("ingest-msg").textContent = r.chunks + " chunks · " + r.persisted + " persisted.";
    }).catch(function (err) {
      $("ingest-msg").textContent = "Error: " + err.message;
    }).finally(function () { btn.disabled = false; });
  }

  // Wire up
  ["f-product", "f-status"].forEach(function (id) {
    $(id).addEventListener("change", renderList);
  });
  $("f-search").addEventListener("input", renderList);
  $("btn-ingest").addEventListener("click", ingest);
  $("btn-investigate").addEventListener("click", investigate);
  $("btn-history").addEventListener("click", showHistory);
  $("review-form").addEventListener("submit", submitReview);

  setHealth();
  loadSummary();
})();
