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

// ── Load data ─────────────────────────────────────────────────────────
async function loadMap() {
  const [mapResp, ridesResp] = await Promise.all([
    fetch("/api/map"),
    fetch("/api/rides"),
  ]);

  const geojson = await mapResp.json();
  const rides   = await ridesResp.json();

  renderSidebar(rides, geojson);
  renderRoutes(geojson);
}

// ── Sidebar ───────────────────────────────────────────────────────────
function renderSidebar(rides, geojson) {
  const resolvedIds = new Set(
    geojson.features.map(f => f.properties?.id).filter(Boolean)
  );

  // Date range subtitle
  const dates = rides
    .map(r => r.date ? new Date(r.date) : null)
    .filter(Boolean)
    .sort((a, b) => a - b);

  if (dates.length) {
    const fmt = d => d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    const earliest = dates[0];
    const latest   = dates[dates.length - 1];
    const subtitle = earliest.toDateString() === latest.toDateString()
      ? fmt(earliest)
      : `${fmt(earliest)} – ${fmt(latest)}`;
    document.getElementById("date-range").textContent = subtitle;
  }

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
    const dist = ride.distance_km ? `${ride.distance_km.toFixed(1)} km` : "";

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
    const dist      = p.distance_km ? ` · ${p.distance_km.toFixed(1)} km` : "";
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
