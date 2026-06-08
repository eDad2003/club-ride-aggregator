/**
 * Club Ride Aggregator — Leaflet map
 */

// Red is reserved for the selected route — excluded from the palette
const COLOURS = [
  "#4285f4", "#34a853", "#fbbc04",
  "#9c27b0", "#00bcd4", "#ff5722", "#607d8b", "#795548",
];
const SELECTED_COLOUR = "#e53935";

// ── Map init ─────────────────────────────────────────────────────────
const map = L.map("map").setView([39.97, -75.6], 11);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 18,
  attribution: "© OpenStreetMap contributors",
}).addTo(map);

// ── State ─────────────────────────────────────────────────────────────
let activeLayer    = null;
let activeColour   = null;
const routeLayers  = {};   // ride_id → { layer, colour }
let allRides       = [];
let allGeojson     = null;

// ── Load data ─────────────────────────────────────────────────────────
async function loadMap() {
  const [mapResp, ridesResp] = await Promise.all([
    fetch("/api/map"),
    fetch("/api/rides"),
  ]);

  allGeojson = await mapResp.json();
  allRides   = await ridesResp.json();

  renderSidebar(allRides, allGeojson);
  renderRoutes(allGeojson);
  initRangeSelector();
}

// ── Sidebar ───────────────────────────────────────────────────────────
function renderSidebar(rides, geojson) {
  const resolvedIds = new Set(
    geojson.features.map(f => f.properties?.id).filter(Boolean)
  );

  const list = document.getElementById("ride-list");
  list.innerHTML = "";

  if (!rides.length) {
    list.innerHTML = '<p style="padding:16px;color:#666">No rides yet — run the scraper first.</p>';
    return;
  }

  rides.forEach(ride => {
    const hasRoute = resolvedIds.has(ride.id);
    const el = document.createElement("div");
    el.className = "ride-item" + (hasRoute ? "" : " no-route");
    el.dataset.id = ride.id;

    const date = ride.date ? new Date(ride.date).toLocaleDateString() : "—";
    const dist = ride.distance_mi ? `${ride.distance_mi.toFixed(1)} mi` : "";

    el.innerHTML = `
      <div class="ride-title">${ride.title}</div>
      <div class="ride-meta">${date}${dist ? " · " + dist : ""}${ride.pace ? " · " + ride.pace : ""}</div>
    `;

    if (hasRoute) {
      el.addEventListener("click", () => focusRide(ride.id, el));
    }

    list.appendChild(el);
  });
}

// ── Range selector ────────────────────────────────────────────────────
function initRangeSelector() {
  const maxDateStr = allRides
    .map(r => r.date?.slice(0, 10))
    .filter(Boolean)
    .sort()
    .at(-1);

  if (!maxDateStr) return;

  applyRange(weekRange(maxDateStr));

  document.querySelectorAll(".range-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".range-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const mode = btn.dataset.range;
      if (mode === "custom") {
        document.getElementById("custom-range").style.display = "flex";
      } else {
        document.getElementById("custom-range").style.display = "none";
        applyRange(mode === "week" ? weekRange(maxDateStr) : monthRange(maxDateStr));
      }
    });
  });

  document.getElementById("apply-range").addEventListener("click", () => {
    const from = document.getElementById("from-date").value;
    const to   = document.getElementById("to-date").value;
    if (from && to) applyRange({ from, to });
  });
}

function weekRange(maxDateStr) {
  const d = new Date(maxDateStr + "T12:00:00");
  d.setDate(d.getDate() - 6);
  return { from: d.toISOString().slice(0, 10), to: maxDateStr };
}

function monthRange(maxDateStr) {
  const d = new Date(maxDateStr + "T12:00:00");
  d.setDate(d.getDate() - 30);
  return { from: d.toISOString().slice(0, 10), to: maxDateStr };
}

function applyRange({ from, to }) {
  const fmt = s => new Date(s + "T12:00:00").toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
  });
  document.getElementById("date-range").textContent =
    from === to ? fmt(from) : `${fmt(from)} – ${fmt(to)}`;

  // Filter sidebar items
  document.querySelectorAll(".ride-item[data-id]").forEach(el => {
    const ride = allRides.find(r => r.id === el.dataset.id);
    const d = ride?.date?.slice(0, 10);
    el.style.display = (!d || (d >= from && d <= to)) ? "" : "none";
  });

  // Filter map layers
  Object.entries(routeLayers).forEach(([rideId, entry]) => {
    const ride = allRides.find(r => r.id === rideId);
    const d = ride?.date?.slice(0, 10);
    const inRange = d && d >= from && d <= to;

    if (inRange) {
      if (!map.hasLayer(entry.layer)) entry.layer.addTo(map);
    } else {
      if (map.hasLayer(entry.layer)) map.removeLayer(entry.layer);
    }
  });

  // Deselect active ride if it was filtered out
  if (activeLayer && !map.hasLayer(activeLayer)) {
    document.querySelectorAll(".ride-item.active").forEach(el => el.classList.remove("active"));
    activeLayer.setStyle({ color: activeColour, weight: 4, opacity: 0.75 });
    activeLayer = null;
    activeColour = null;
  }
}

// ── Route polylines ───────────────────────────────────────────────────
function renderRoutes(geojson) {
  geojson.features.forEach((feature, idx) => {
    if (feature.geometry?.type !== "LineString") return;

    const colour = COLOURS[idx % COLOURS.length];
    const rideId = feature.properties?.id;
    const p      = feature.properties || {};

    const coords = feature.geometry.coordinates.map(([lng, lat]) => [lat, lng]);
    const layer  = L.polyline(coords, {
      color:   colour,
      weight:  4,
      opacity: 0.75,
    }).addTo(map);

    const rwgpsId  = p.rwgps_id
                  || (p.rwgps_url ? p.rwgps_url.match(/(\d+)\/?$/)?.[1] : null);
    const rwgpsUrl = p.rwgps_url
                  || (rwgpsId ? `https://ridewithgps.com/routes/${rwgpsId}` : null);

    const date      = p.date ? new Date(p.date).toLocaleDateString() : "";
    const dist      = p.distance_mi ? ` · ${p.distance_mi.toFixed(1)} mi` : "";
    const pace      = p.pace ? ` · ${p.pace}` : "";
    const rwgpsLink = rwgpsUrl
      ? `<br><a href="${rwgpsUrl}" target="_blank" rel="noopener"
              style="color:#4285f4;font-size:12px;">View on RideWithGPS ↗</a>`
      : "";

    layer.bindPopup(`
      <strong style="font-size:13px;">${p.title || p.name || "Route"}</strong><br>
      <span style="color:#666;font-size:12px;">${date}${dist}${pace}</span>
      ${rwgpsLink}
    `, { maxWidth: 300 });

    layer.on("click", () => {
      const sidebarEl = document.querySelector(`.ride-item[data-id="${rideId}"]`);
      if (sidebarEl) focusRide(rideId, sidebarEl, false);
    });

    if (rideId) routeLayers[rideId] = { layer, colour };
  });

  // Zoom to fit all routes
  const allLayers = Object.values(routeLayers).map(e => e.layer);
  if (allLayers.length) {
    const group = L.featureGroup(allLayers);
    map.fitBounds(group.getBounds().pad(0.1));
  }
}

// ── Focus a ride ──────────────────────────────────────────────────────
function focusRide(rideId, sidebarEl, panMap = true) {
  // Deactivate previous
  document.querySelectorAll(".ride-item.active").forEach(el => el.classList.remove("active"));
  if (activeLayer) {
    activeLayer.setStyle({ color: activeColour, weight: 4, opacity: 0.75 });
  }

  // Activate new
  sidebarEl.classList.add("active");
  sidebarEl.scrollIntoView({ block: "nearest" });

  const entry = routeLayers[rideId];
  if (!entry) return;

  // Store original colour so we can restore it on deselect
  activeLayer  = entry.layer;
  activeColour = entry.colour;

  entry.layer.setStyle({ color: SELECTED_COLOUR, weight: 6, opacity: 1 });
  entry.layer.bringToFront();
  entry.layer.openPopup();

  if (panMap) map.fitBounds(entry.layer.getBounds().pad(0.1));
}

// ── Boot ──────────────────────────────────────────────────────────────
loadMap().catch(err => {
  document.getElementById("ride-list").innerHTML =
    `<p style="padding:16px;color:#c00">Error loading rides: ${err.message}</p>`;
});
