/* =====================================================================
   FlyHND — Client JS
   ===================================================================== */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  // ── DOM refs ──────────────────────────────────────────────────────────
  const form            = $("searchForm");
  const originInput     = $("originInput");
  const originId        = $("originId");
  const originSugg      = $("originSuggestions");
  const destInput       = $("destInput");
  const destId          = $("destId");
  const destSugg        = $("destSuggestions");
  const dateInput       = $("dateInput");
  const returnDateInput = $("returnDateInput");
  const returnDateGroup = $("returnDateGroup");
  const passInput       = $("passengersInput");
  const currencyInput   = $("currencyInput");
  const swapBtn         = $("swapBtn");
  const searchBtn       = $("searchBtn");
  const searchBtnText   = $("searchBtnText");
  const errorBanner     = $("errorBanner");

  const resultsSection  = $("resultsSection");
  const demoBanner      = $("demoBanner");
  const returnBlock     = $("returnBlock");
  const cardTemplate    = $("flightCardTemplate");

  const legs = {
    outbound: { offers: [], sort: "price", list: $("flightList"),       title: $("outboundTitle"), sub: $("outboundSub") },
    return:   { offers: [], sort: "price", list: $("returnFlightList"), title: $("returnTitle"),   sub: $("returnSub") },
  };

  // ── Dates ─────────────────────────────────────────────────────────────
  const today = new Date().toISOString().slice(0, 10);
  dateInput.min = today;
  returnDateInput.min = today;

  document.querySelectorAll("input[name='tripType']").forEach(radio => {
    radio.addEventListener("change", () => {
      returnDateGroup.hidden = !isReturnTrip();
      if (isReturnTrip() && dateInput.value) returnDateInput.min = dateInput.value;
    });
  });
  dateInput.addEventListener("change", () => {
    if (dateInput.value) returnDateInput.min = dateInput.value;
  });

  function isReturnTrip() {
    const r = document.querySelector("input[name='tripType']:checked");
    return r && r.value === "return";
  }

  // ── Autocomplete ──────────────────────────────────────────────────────
  function buildAutocomplete(textInput, hiddenInput, listEl) {
    let debounceTimer = null;

    textInput.addEventListener("input", () => {
      clearTimeout(debounceTimer);
      hiddenInput.value = "";
      const q = textInput.value.trim();
      if (q.length < 2) { hideList(textInput, listEl); return; }
      debounceTimer = setTimeout(() => fetchSuggestions(q, textInput, hiddenInput, listEl), 300);
    });

    textInput.addEventListener("keydown", (e) => {
      if (listEl.hidden) return;
      const items = listEl.querySelectorAll("li[data-id]");
      const active = listEl.querySelector("li.active");
      let idx = Array.from(items).indexOf(active);
      if (e.key === "ArrowDown" && items.length) {
        e.preventDefault();
        idx = (idx + 1) % items.length;
        items.forEach((li, i) => li.classList.toggle("active", i === idx));
        items[idx].scrollIntoView({ block: "nearest" });
      } else if (e.key === "ArrowUp" && items.length) {
        e.preventDefault();
        idx = (idx - 1 + items.length) % items.length;
        items.forEach((li, i) => li.classList.toggle("active", i === idx));
        items[idx].scrollIntoView({ block: "nearest" });
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (active) active.click();
      } else if (e.key === "Escape") {
        hideList(textInput, listEl);
      }
    });

    document.addEventListener("click", (e) => {
      if (!textInput.contains(e.target) && !listEl.contains(e.target)) hideList(textInput, listEl);
    });
  }

  async function fetchSuggestions(query, textInput, hiddenInput, listEl) {
    showListMessage(textInput, listEl, "Searching…");
    try {
      const res  = await fetch(`/api/suggest?q=${encodeURIComponent(query)}`);
      const data = await res.json();
      if (data.error && !data.suggestions.length) {
        showListMessage(textInput, listEl, "Place lookup needs a live provider. Type an airport code such as PNQ.");
        return;
      }
      renderSuggestions(data.suggestions, textInput, hiddenInput, listEl);
    } catch {
      showListMessage(textInput, listEl, "Could not load suggestions. Type an airport code instead.");
    }
  }

  function renderSuggestions(items, textInput, hiddenInput, listEl) {
    listEl.innerHTML = "";
    if (!items.length) { showListMessage(textInput, listEl, "No matching places found."); return; }
    items.forEach(item => {
      const li = document.createElement("li");
      li.setAttribute("role", "option");
      li.dataset.id = item.id || item.label;
      li.innerHTML =
        `<span class="body-6">${esc(item.label)}</span>` +
        (item.id ? `<span class="caption-5 sug-id">${esc(item.id)}${item.type ? " · " + esc(item.type) : ""}</span>` : "");
      li.addEventListener("click", () => {
        textInput.value   = item.label;
        hiddenInput.value = item.id || item.label;
        hideList(textInput, listEl);
      });
      listEl.appendChild(li);
    });
    openList(textInput, listEl);
  }

  function showListMessage(textInput, listEl, msg) {
    listEl.innerHTML = `<li class="sug-empty body-6">${esc(msg)}</li>`;
    openList(textInput, listEl);
  }
  function openList(textInput, listEl) { listEl.hidden = false; textInput.setAttribute("aria-expanded", "true"); }
  function hideList(textInput, listEl) { listEl.hidden = true; listEl.innerHTML = ""; textInput.setAttribute("aria-expanded", "false"); }

  buildAutocomplete(originInput, originId, originSugg);
  buildAutocomplete(destInput,   destId,   destSugg);

  // ── Swap ──────────────────────────────────────────────────────────────
  swapBtn.addEventListener("click", () => {
    [originInput.value, destInput.value] = [destInput.value, originInput.value];
    [originId.value,    destId.value]    = [destId.value,    originId.value];
    swapBtn.classList.toggle("is-swapped");
  });

  // ── Submit ────────────────────────────────────────────────────────────
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearError();

    // Fall back to typed text if the user didn't pick from the dropdown
    if (!originId.value && originInput.value.trim()) originId.value = originInput.value.trim();
    if (!destId.value   && destInput.value.trim())   destId.value   = destInput.value.trim();

    const missing = [];
    if (!originId.value) missing.push("where you are flying from");
    if (!destId.value) missing.push("where you are going");
    if (!dateInput.value) missing.push("a departure date");
    if (isReturnTrip() && !returnDateInput.value) missing.push("a return date");
    if (missing.length) { showError(`Add ${joinList(missing)} to search.`); return; }

    const payload = {
      origin_id:    originId.value.trim(),
      origin_label: originInput.value.trim(),
      dest_id:      destId.value.trim(),
      dest_label:   destInput.value.trim(),
      date:         dateInput.value,
      return_date:  isReturnTrip() ? returnDateInput.value : null,
      passengers:   parseInt(passInput.value, 10) || 1,
      currency:     currencyInput.value,
    };

    setLoading(true, !!payload.return_date);
    try {
      const res  = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!data.ok) {
        resultsSection.hidden = true;
        showError((data.errors || ["Search failed. Try again in a moment."]).join(" "));
        return;
      }
      renderResults(data, payload);
    } catch {
      resultsSection.hidden = true;
      showError("Could not reach the server. Check that FlyHND is still running, then search again.");
    } finally {
      setLoading(false);
    }
  });

  // ── Results ───────────────────────────────────────────────────────────
  function renderResults(data, payload) {
    const pax    = payload.passengers;
    const paxStr = `${pax} traveller${pax !== 1 ? "s" : ""}`;

    demoBanner.hidden = !(data.is_demo && data.demo_note);
    if (!demoBanner.hidden) {
      demoBanner.innerHTML = `<i class="ph ph-info" aria-hidden="true"></i><span>${esc(data.demo_note)}</span>`;
    }

    fillLeg(legs.outbound, data.outbound, payload.date, paxStr);

    returnBlock.hidden = !(data.return && payload.return_date);
    if (!returnBlock.hidden) fillLeg(legs.return, data.return, payload.return_date, paxStr);

    resultsSection.hidden = false;
    resultsSection.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  }

  function fillLeg(leg, legData, date, paxStr) {
    leg.offers = legData?.offers || [];
    leg.sort = "price";
    syncSortButtons(leg);
    const n = legData?.total_found ?? leg.offers.length;
    leg.title.textContent = legData?.route || "";
    leg.sub.textContent   = `${fmtDate(date)} · ${paxStr} · ${n} flight${n !== 1 ? "s" : ""} found`;
    renderCards(leg);
  }

  function renderCards(leg) {
    leg.list.innerHTML = "";
    const sorted = sortOffers([...leg.offers], leg.sort);
    if (!sorted.length) {
      leg.list.innerHTML = `
        <div class="empty">
          <i class="ph ph-airplane-tilt" aria-hidden="true"></i>
          <p class="title-3">No flights on this date</p>
          <p class="body-6 muted">Try a nearby date or a different airport in the same city.</p>
        </div>`;
      return;
    }
    sorted.forEach((offer, idx) => leg.list.appendChild(buildCard(offer, idx)));
  }

  function sortOffers(arr, sort) {
    if (sort === "price")    return arr.sort((a, b) => numFare(a) - numFare(b));
    if (sort === "duration") return arr.sort((a, b) => (a.duration_minutes || 9999) - (b.duration_minutes || 9999));
    if (sort === "best")     return arr.sort((a, b) => ((a.stops || 0) - (b.stops || 0)) || numFare(a) - numFare(b));
    return arr;
  }

  // ── Sort buttons ──────────────────────────────────────────────────────
  document.querySelectorAll(".sort-group").forEach(group => {
    const leg = legs[group.dataset.target];
    group.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-sort]");
      if (!btn) return;
      leg.sort = btn.dataset.sort;
      syncSortButtons(leg);
      renderCards(leg);
    });
  });

  function syncSortButtons(leg) {
    const target = leg === legs.outbound ? "outbound" : "return";
    document.querySelectorAll(`.sort-group[data-target="${target}"] [data-sort]`).forEach(b =>
      b.setAttribute("aria-pressed", String(b.dataset.sort === leg.sort)));
  }

  // ── Card ──────────────────────────────────────────────────────────────
  function buildCard(offer, idx) {
    const frag = cardTemplate.content.cloneNode(true);
    const card = frag.querySelector(".flight-card");
    const q    = (sel) => card.querySelector(sel);
    card.style.setProperty("--i", Math.min(idx, 6));
    if (idx === 0) card.classList.add("is-top");

    // Badges
    const badgeMap = {
      cheapest:   ["Cheapest",   "badge-cheapest",   "ph-tag"],
      fastest:    ["Fastest",    "badge-fastest",    "ph-lightning"],
      best_value: ["Best value", "badge-best-value", "ph-star"],
    };
    const badgesEl = q(".card-badges");
    (offer.badges || []).forEach(b => {
      if (badgeMap[b]) badgesEl.appendChild(badge(...badgeMap[b]));
    });
    if (offer.over_budget) badgesEl.appendChild(badge("Over budget", "badge-over", "ph-warning"));
    const src = offer.source || "";
    if (src.includes("DEMO") || src.includes("CACHE")) badgesEl.appendChild(badge("Demo fare", "badge-demo"));

    // Airline
    const airline = offer.airline || "Airline";
    q(".airline-mark").textContent  = (offer.airline_code || airline.slice(0, 2)).toUpperCase();
    q(".airline-name").textContent  = airline;
    q(".flight-number").textContent = [offer.flight_number, offer.cabin].filter(Boolean).join(" · ");

    // Route
    q(".dep-time").textContent = fmtTime(offer.departure_time);
    q(".dep-code").textContent = offer.origin || "";
    q(".arr-time").textContent = fmtTime(offer.arrival_time);
    q(".arr-code").textContent = offer.destination || "";
    q(".route-duration").textContent = offer.duration || "";
    const stops = parseInt(offer.stops ?? 0, 10);
    const stopsEl = q(".route-stops");
    stopsEl.textContent = stops === 0 ? "Non stop"
      : `${stops} stop${stops > 1 ? "s" : ""}${offer.layovers?.length ? " via " + offer.layovers.join(", ") : ""}`;
    stopsEl.classList.toggle("is-direct", stops === 0);

    // Price
    const cur = offer.currency || "INR";
    q(".price-amount").textContent = fmtMoney(numFare(offer), cur);
    const tax = parseFloat(offer.tax_fees || 0);
    q(".price-note").textContent = offer.fare_breakdown_available !== false && tax > 0
      ? `Includes ${fmtMoney(tax, cur)} taxes`
      : "Total fare";

    // Meta
    q(".meta-cabin").textContent   = offer.cabin || "Economy";
    q(".meta-baggage").textContent = offer.baggage || "Baggage not listed";
    q(".meta-source").textContent  = offer.source_label || src;

    // Booking actions
    const bookLink = q(".book-link");
    const airlineLink = q(".airline-link");
    if (offer.price_check_url) {
      bookLink.href = offer.price_check_url;
      bookLink.setAttribute("aria-label", `Check live price and book ${airline} ${offer.flight_number || ""} (opens in a new tab)`);
    } else {
      bookLink.remove();
    }
    if (offer.airline_url) {
      airlineLink.href = offer.airline_url;
      airlineLink.innerHTML = `${esc(airline)} site <i class="ph ph-arrow-square-out" aria-hidden="true"></i>`;
      airlineLink.setAttribute("aria-label", `Open the ${airline} website (opens in a new tab)`);
    } else {
      airlineLink.remove();
    }

    // Details
    const detailsEl  = q(".card-details");
    const detailsBtn = q(".details-btn");
    detailsEl.id = `details-${offer.offer_id || Math.random().toString(36).slice(2)}-${idx}`;
    detailsBtn.setAttribute("aria-controls", detailsEl.id);
    q(".segments").innerHTML = segmentsHtml(offer, stops);
    detailsBtn.addEventListener("click", () => {
      const open = detailsBtn.getAttribute("aria-expanded") === "true";
      detailsBtn.setAttribute("aria-expanded", String(!open));
      detailsEl.hidden = open;
    });

    return frag;
  }

  function segmentsHtml(offer, stops) {
    const segs = offer.segments || [];
    if (!segs.length) {
      const via = stops === 0 ? "Non stop" : `${stops} stop${stops > 1 ? "s" : ""} via ${(offer.layovers || []).join(", ") || "a connecting airport"}`;
      return segmentHtml(
        { id: offer.origin, time: offer.departure_time },
        { id: offer.destination, time: offer.arrival_time },
        `${esc(offer.duration || "")}<br>${esc(via)}`, null);
    }
    return segs.map(seg => {
      const head = `
        <div class="segment-head">
          <span class="title-4">${esc(seg.airline || offer.airline || "")} ${esc(seg.flight_number || "")}</span>
          <span class="caption-5 muted">${esc([seg.airplane, seg.travel_class].filter(Boolean).join(" · "))}</span>
        </div>`;
      let html = segmentHtml(seg.departure_airport || {}, seg.arrival_airport || {}, esc(seg.duration || ""), head);
      if (seg.layover_after) {
        const lo = seg.layover_after;
        html += `<div class="layover caption-4"><i class="ph ph-clock" aria-hidden="true"></i>
          ${esc(lo.duration_str || "")} layover in ${esc(lo.name || lo.id || "")}${lo.id && lo.name ? ` (${esc(lo.id)})` : ""}</div>`;
      }
      return html;
    }).join("");
  }

  function segmentHtml(dep, arr, midHtml, headHtml) {
    return `
      <div class="segment">
        ${headHtml || ""}
        <div class="segment-end">
          <span class="title-3">${esc(dep.id || "")} ${fmtTime(dep.time)}</span>
          <span class="caption-5 muted">${esc(dep.name || "")}</span>
        </div>
        <div class="segment-mid caption-5">${midHtml}</div>
        <div class="segment-end segment-end--right">
          <span class="title-3">${fmtTime(arr.time)} ${esc(arr.id || "")}</span>
          <span class="caption-5 muted">${esc(arr.name || "")}</span>
        </div>
      </div>`;
  }

  function badge(text, cls, icon) {
    const span = document.createElement("span");
    span.className = `badge caption-3 ${cls}`;
    span.innerHTML = (icon ? `<i class="ph-fill ${icon}" aria-hidden="true"></i>` : "") + esc(text);
    return span;
  }

  // ── Loading skeleton ──────────────────────────────────────────────────
  function skeletonHtml(count) {
    const card = `
      <div class="flight-card skeleton-card" aria-hidden="true">
        <div class="sk-row">
          <span class="sk" style="width:40px;height:40px;border-radius:9999px"></span>
          <span class="sk sk-line" style="width:120px"></span>
          <span class="sk sk-line" style="flex:1"></span>
          <span class="sk" style="width:96px;height:32px"></span>
        </div>
        <div class="sk-row"><span class="sk sk-line" style="width:40%"></span><span style="flex:1"></span><span class="sk" style="width:176px;height:32px"></span></div>
      </div>`;
    return card.repeat(count);
  }

  function setLoading(on, withReturn) {
    searchBtn.disabled = on;
    searchBtn.setAttribute("aria-busy", String(on));
    searchBtnText.textContent = on ? "Searching flights…" : "Search flights";
    if (!on) return;
    demoBanner.hidden = true;
    legs.outbound.title.textContent = "Finding flights…";
    legs.outbound.sub.textContent = "Comparing fares from every source";
    legs.outbound.list.innerHTML = skeletonHtml(3);
    returnBlock.hidden = !withReturn;
    if (withReturn) { legs.return.title.textContent = "Finding return flights…"; legs.return.sub.textContent = ""; legs.return.list.innerHTML = skeletonHtml(2); }
    resultsSection.hidden = false;
  }

  // ── Helpers ───────────────────────────────────────────────────────────
  function showError(msg) {
    errorBanner.innerHTML = `<i class="ph ph-warning-circle" aria-hidden="true"></i><span>${esc(msg)}</span>`;
    errorBanner.hidden = false;
  }
  function clearError() { errorBanner.innerHTML = ""; errorBanner.hidden = true; }

  function numFare(o) { return parseFloat(o.total_fare_num ?? o.total_fare ?? 0); }

  function fmtMoney(n, cur) {
    try {
      return new Intl.NumberFormat(undefined, { style: "currency", currency: cur, maximumFractionDigits: 0 }).format(n);
    } catch {
      return `${cur} ${Math.round(n).toLocaleString()}`;
    }
  }

  function fmtTime(s) {
    if (!s) return "";
    const d = new Date(s);
    if (isNaN(d)) return s.length > 10 ? s.slice(11, 16) : s;
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  }

  function fmtDate(s) {
    const d = new Date(`${s}T00:00:00`);
    return isNaN(d) ? s : d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
  }

  function joinList(a) { return a.length < 2 ? a.join("") : `${a.slice(0, -1).join(", ")} and ${a[a.length - 1]}`; }

  function esc(s) {
    return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

})();
