"use strict";

const STATUSES = ["new", "posted", "approved", "false_alarm", "resolved"];
const STATUS_LABELS = {
  new: "New",
  posted: "Alert sent",
  approved: "Approved",
  false_alarm: "False alarm",
  resolved: "Resolved",
};

const state = {
  events: [],
  selectedId: null,
  seenIds: new Set(),
  firstLoad: true,
  clipAvailable: false,
};

const els = {
  apiState: document.querySelector("#api-state"),
  lastUpdate: document.querySelector("#last-update"),
  eventCount: document.querySelector("#event-count"),
  feedState: document.querySelector("#feed-state"),
  eventList: document.querySelector("#event-list"),
  clip: document.querySelector("#clip"),
  cameraTitle: document.querySelector("#camera-title"),
  cameraFrame: document.querySelector("#camera-frame"),
  cameraEmpty: document.querySelector("#camera-empty"),
  sourceLabel: document.querySelector("#source-label"),
  cameraSourceState: document.querySelector("#camera-source-state"),
  hazardStamp: document.querySelector("#hazard-stamp"),
  hazardTitle: document.querySelector("#hazard-title"),
  hazardDetail: document.querySelector("#hazard-detail"),
  hazardConfidence: document.querySelector("#hazard-confidence"),
  cameraCaption: document.querySelector("#camera-caption"),
  detailTitle: document.querySelector("#detail-title"),
  detailSubtitle: document.querySelector("#detail-subtitle"),
  detailStatus: document.querySelector("#detail-status"),
  detailEmpty: document.querySelector("#detail-empty"),
  detailGrid: document.querySelector("#detail-grid"),
  detailExplanation: document.querySelector("#detail-explanation"),
  detailZone: document.querySelector("#detail-zone"),
  detailConfidence: document.querySelector("#detail-confidence"),
  detailRule: document.querySelector("#detail-rule"),
  detailFix: document.querySelector("#detail-fix"),
  detailTimeline: document.querySelector("#detail-timeline"),
  metrics: document.querySelector("#metrics"),
  metricsList: document.querySelector("#metrics-list"),
};

function formatTime(value, withSeconds = true) {
  if (!value) return "Time unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat([], {
    hour: "2-digit",
    minute: "2-digit",
    second: withSeconds ? "2-digit" : undefined,
  }).format(date);
}

function readableZone(value) {
  return String(value || "Zone unavailable").replaceAll("_", " ").toUpperCase();
}

function statusClass(status) {
  return `status-${STATUSES.includes(status) ? status : "neutral"}`;
}

function confidence(value) {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "Unavailable";
}

function eventTitle(status) {
  if (status === "resolved") return "Exit route cleared";
  if (status === "false_alarm") return "Marked false alarm";
  if (status === "approved") return "Fix approved";
  return "Exit route blocked";
}

async function getJson(url, options = {}) {
  const response = await fetch(url, { cache: "no-store", ...options });
  if (!response.ok) throw new Error(`${url} returned ${response.status}`);
  return response.json();
}

function setApiState(online) {
  els.apiState.dataset.state = online ? "online" : "offline";
  els.apiState.lastElementChild.textContent = online ? "Event API online" : "Event API unavailable";
}

async function checkHealth() {
  try {
    const health = await getJson("/api/health");
    setApiState(health.ok === true);
    return health.ok === true;
  } catch (_error) {
    setApiState(false);
    return false;
  }
}

function makeStatusChip(status) {
  const chip = document.createElement("span");
  chip.className = `status-chip ${statusClass(status)}`;
  chip.textContent = STATUS_LABELS[status] || "Unknown";
  return chip;
}

function renderFeed(newIds) {
  els.eventList.replaceChildren();
  els.eventCount.textContent = `${state.events.length} ${state.events.length === 1 ? "event" : "events"}`;
  els.feedState.hidden = state.events.length > 0;
  if (!state.events.length) {
    els.feedState.textContent = "Watching. No hazards yet.";
    return;
  }

  for (const event of state.events) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "event-row";
    row.dataset.status = event.status;
    row.dataset.eventId = String(event.id);
    row.setAttribute("aria-current", String(event.id) === String(state.selectedId) ? "true" : "false");
    row.setAttribute("aria-label", `Event ${event.id}, ${eventTitle(event.status)}, ${readableZone(event.zone)}, ${STATUS_LABELS[event.status] || event.status}`);
    if (!state.firstLoad && newIds.has(String(event.id))) row.classList.add("event-new");

    const time = document.createElement("time");
    time.className = "event-time";
    time.dateTime = event.ts || "";
    time.textContent = formatTime(event.ts, false);

    const summary = document.createElement("div");
    summary.className = "event-summary";
    const title = document.createElement("strong");
    title.textContent = eventTitle(event.status);
    const zone = document.createElement("span");
    zone.textContent = readableZone(event.zone);
    summary.append(title, zone);
    if (event.disposition_by || event.disposition_ts) {
      const decision = document.createElement("span");
      decision.className = "decision";
      const actor = event.disposition_by ? ` by ${event.disposition_by}` : "";
      const at = event.disposition_ts ? ` at ${formatTime(event.disposition_ts)}` : "";
      decision.textContent = `${STATUS_LABELS[event.status] || event.status}${actor}${at}`;
      summary.append(decision);
    }

    const meta = document.createElement("div");
    meta.className = "event-meta";
    const score = document.createElement("span");
    score.className = "confidence";
    score.textContent = confidence(event.confidence);
    meta.append(score, makeStatusChip(event.status));

    row.append(time, summary, meta);
    row.addEventListener("click", () => selectEvent(event.id));
    els.eventList.append(row);
  }
}

function setImageFallback(image, label) {
  image.addEventListener("error", () => {
    image.hidden = true;
    if (!state.clipAvailable) {
      els.cameraEmpty.hidden = false;
      els.cameraEmpty.querySelector("p").textContent = "Evidence frame unavailable.";
      els.cameraEmpty.querySelector("span").textContent = "The event record remains available while the local file is checked.";
      els.sourceLabel.textContent = `${label} evidence unavailable`;
    }
  }, { once: true });
}

function renderCamera(event = state.events.find((item) => String(item.id) === String(state.selectedId)) || state.events[0]) {
  if (!event) {
    els.cameraFrame.hidden = true;
    els.cameraEmpty.hidden = false;
    els.cameraEmpty.querySelector("p").textContent = "Watching. No hazards yet.";
    els.cameraEmpty.querySelector("span").textContent = "Evidence appears here when the local model records an event.";
    els.hazardStamp.hidden = true;
    els.cameraTitle.textContent = "Exit route";
    els.cameraSourceState.textContent = state.clipAvailable ? "Recorded replay" : "Camera source";
    els.sourceLabel.textContent = state.clipAvailable ? "Recorded replay" : "Waiting for evidence";
    return;
  }

  const eventStatus = STATUS_LABELS[event.status] || event.status;
  els.cameraTitle.textContent = readableZone(event.zone);
  els.hazardStamp.hidden = false;
  els.hazardStamp.dataset.state = event.status;
  els.hazardTitle.textContent = eventTitle(event.status);
  els.hazardDetail.textContent = `Event ${event.id} · ${readableZone(event.zone)} · ${eventStatus}`;
  els.hazardConfidence.firstChild.nodeValue = confidence(event.confidence);
  if (state.clipAvailable) {
    els.clip.hidden = false;
    els.cameraFrame.hidden = true;
    els.cameraEmpty.hidden = true;
    els.cameraCaption.hidden = false;
    els.cameraSourceState.textContent = "Recorded replay";
    els.sourceLabel.textContent = "Primary evidence · Recorded replay";
  } else {
    els.cameraFrame.src = `/frames/${encodeURIComponent(event.id)}?v=${encodeURIComponent(event.ts || "")}`;
    els.cameraFrame.alt = `Evidence for blocked exit at ${readableZone(event.zone)}`;
    els.cameraFrame.hidden = false;
    els.cameraEmpty.hidden = true;
    els.cameraCaption.hidden = true;
    els.cameraSourceState.textContent = "Evidence frame";
    els.sourceLabel.textContent = `Primary evidence · Event ${event.id}`;
    setImageFallback(els.cameraFrame, "Selected");
  }
}

function addTimelineItem(label, timestamp, note) {
  const item = document.createElement("li");
  const title = document.createElement("strong");
  title.textContent = label;
  const time = document.createElement("time");
  time.dateTime = timestamp || "";
  time.textContent = formatTime(timestamp);
  item.append(title, time);
  if (note) item.append(document.createTextNode(` ${note}`));
  els.detailTimeline.append(item);
}

async function selectEvent(id) {
  state.selectedId = String(id);
  window.dispatchEvent(new CustomEvent("ssw:event-selected", { detail: { id: state.selectedId } }));
  renderFeed(new Set());
  try {
    const event = await getJson(`/api/events/${encodeURIComponent(id)}`);
    renderDetail(event);
    renderCamera(event);
  } catch (_error) {
    els.detailGrid.hidden = true;
    els.detailEmpty.hidden = false;
    els.detailEmpty.textContent = "The selected event could not be loaded. The console will retry on the next update.";
  }
}

function renderDetail(event) {
  els.detailEmpty.hidden = true;
  els.detailGrid.hidden = false;
  els.detailTitle.textContent = "Response record";
  els.detailSubtitle.textContent = `Event ${event.id} · ${readableZone(event.zone)}`;
  els.detailStatus.className = `module-state ${statusClass(event.status)}`;
  els.detailStatus.textContent = STATUS_LABELS[event.status] || "Unknown";
  els.detailExplanation.textContent = event.explanation || "No model observation recorded.";
  els.detailZone.textContent = readableZone(event.zone);
  els.detailConfidence.textContent = confidence(event.confidence);
  els.detailRule.textContent = event.rule || "No stored rule recorded.";
  els.detailFix.textContent = event.fix || "No proposed fix recorded.";
  els.detailTimeline.replaceChildren();
  addTimelineItem("Seen by local vision", event.ts);
  if (event.status !== "new") addTimelineItem("Alert sent", event.ts, "to the safety workflow");
  if (event.status === "approved" || event.status === "false_alarm" || event.status === "resolved") {
    const label = event.status === "approved" ? "Approved" : "Marked false alarm";
    if (event.status !== "resolved" || event.disposition_ts) {
      const resolvedLabel = event.status === "resolved" ? "Approved" : label;
      const actor = event.disposition_by ? `by ${event.disposition_by}` : "";
      addTimelineItem(resolvedLabel, event.disposition_ts, actor);
    }
  }
  if (event.status === "resolved") {
    addTimelineItem("Confirmed clear", event.resolved_ts, "by local vision");
  }
}

async function pollEvents() {
  const online = await checkHealth();
  if (!online) {
    if (!state.events.length) {
      els.feedState.hidden = false;
      els.feedState.textContent = "Event API unavailable. Retrying locally.";
    }
    return;
  }

  try {
    const lists = await Promise.all(STATUSES.map((status) => getJson(`/api/events?status=${status}`)));
    const merged = lists.flat().sort((a, b) => new Date(b.ts) - new Date(a.ts));
    const incomingIds = new Set(merged.map((event) => String(event.id)));
    const newIds = new Set([...incomingIds].filter((id) => !state.seenIds.has(id)));
    state.events = merged;
    state.seenIds = incomingIds;

    if (state.selectedId && !incomingIds.has(String(state.selectedId))) state.selectedId = null;
    if (!state.selectedId && merged.length) state.selectedId = String(merged[0].id);

    renderFeed(newIds);
    renderCamera();
    if (state.selectedId) await selectEvent(state.selectedId);

    els.lastUpdate.lastElementChild.textContent = formatTime(new Date().toISOString());
    state.firstLoad = false;
  } catch (_error) {
    setApiState(false);
  }
}

async function loadMetrics() {
  try {
    const numbers = await getJson("/numbers");
    const entries = Object.entries(numbers);
    if (!entries.length) return;
    els.metricsList.replaceChildren();
    for (const [key, value] of entries) {
      const block = document.createElement("div");
      block.className = "metric";
      const term = document.createElement("dt");
      term.textContent = key;
      const description = document.createElement("dd");
      description.textContent = typeof value === "object" ? JSON.stringify(value) : String(value);
      block.append(term, description);
      els.metricsList.append(block);
    }
    els.metrics.hidden = false;
  } catch (_error) {
    els.metrics.hidden = true;
  }
}

function setupClip() {
  els.clip.addEventListener("loadeddata", () => {
    state.clipAvailable = true;
    renderCamera();
  }, { once: true });
  els.clip.addEventListener("error", () => {
    state.clipAvailable = false;
    els.clip.hidden = true;
    renderCamera();
  }, { once: true });
}

setupClip();
loadMetrics();
pollEvents();
window.setInterval(pollEvents, 2000);
