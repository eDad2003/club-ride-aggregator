/**
 * Club Ride Aggregator — Leaflet map
 *
 * Loads /api/map (GeoJSON FeatureCollection) and renders each route
 * as a coloured polyline. Clicking a sidebar item or a route on the
 * map pans to that route and opens a popup.
 */

// ── Colour palette — one per route, cycles on overflow ──────────────
const COLOURS = [
  "#4285f4", "#ea4335", "#34a853", "#fbbc04",
  "#9c27b0", "#00bcd4", "#ff5722", "#607d8b",
];

// ── Map init ─────────────────────────────────────────────────────────
const map = L.map("map").setView([40.0, -75.5], 10);  // adjust default centre

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 18,
  attribution: "© OpenStreetMap contributors",
}).addTo(map);

// ── State ─────────────────────────────────────────────────────────────
let activeLayer = null;
const routeLayers = {};   // ride_id → Leaflet polyline layer

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
      <div class="ride-meta">${date}${dist ? " · " + dist : ""}${ride.leader ? " · " + ride.leader : ""}</div>
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

    const coords = feature.geometry.coordinates.map(([lng, lat]) => [lat, lng]);
    const layer = L.polyline(coords, {
      color: colour,
      weight: 4,
      opacity: 0.75,
    }).addTo(map);

    const p = feature.properties || {};
    layer.bindPopup(`
      <strong>${p.title || p.name || "Route"}</strong><br>
      ${p.date ? new Date(p.date).toLocaleDateString() : ""}
      ${p.distance_km ? " · " + p.distance_km.toFixed(1) + " km" : ""}
      ${p.leader ? "<br>Leader: " + p.leader : ""}
    `);

    layer.on("click", () => {
      const sidebarEl = document.querySelector(`.ride-item[data-id="${rideId}"]`);
      if (sidebarEl) focusRide(rideId, sidebarEl, false);
    });

    if (rideId) routeLayers[rideId] = layer;
  });

  // Zoom to fit all routes
  const allLayers = Object.values(routeLayers);
  if (allLayers.length) {
    const group = L.featureGroup(allLayers);
    map.fitBounds(group.getBounds().pad(0.1));
  }
}

// ── Focus a ride ──────────────────────────────────────────────────────
function focusRide(rideId, sidebarEl, panMap = true) {
  // Deactivate previous
  document.querySelectorAll(".ride-item.active").forEach(el => el.classList.remove("active"));
  if (activeLayer) activeLayer.setStyle({ weight: 4, opacity: 0.75 });

  // Activate new
  sidebarEl.classList.add("active");
  sidebarEl.scrollIntoView({ block: "nearest" });

  const layer = routeLayers[rideId];
  if (!layer) return;

  layer.setStyle({ weight: 6, opacity: 1 });
  layer.openPopup();
  activeLayer = layer;

  if (panMap) map.fitBounds(layer.getBounds().pad(0.1));
}

// ── Boot ──────────────────────────────────────────────────────────────
loadMap().catch(err => {
  document.getElementById("ride-list").innerHTML =
    `<p style="padding:16px;color:#c00">Error loading rides: ${err.message}</p>`;
});
