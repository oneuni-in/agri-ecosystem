"use client";

import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef } from "react";

export interface MapPin {
  id: string;
  slug: string;
  name: string;
  lat: number;
  lng: number;
}

/**
 * MapLibre only (D24 DO-NOT: no Google Maps JS). Raster OSM tiles keep the
 * style self-contained — swap the tile URL for a paid provider before real
 * traffic (OSM tile policy). Pins are DOM Markers, not GL symbol layers:
 * covers() pages cap the list at 20 cards, so pin count never reaches
 * clustering territory, and DOM pins are click-syncable + testable
 * (NON-NEGOTIABLE 3). Same-coordinate pins get a tiny deterministic spread
 * so none are unreachable.
 */
const OSM_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

const PIN_CLASS =
  "block h-7 w-7 cursor-pointer rounded-full border-2 border-card bg-brand-deep shadow-md";
const PIN_SELECTED_CLASS =
  "block h-7 w-7 cursor-pointer rounded-full border-2 border-card bg-accent shadow-md";

function spread(pins: MapPin[]): MapPin[] {
  const seen = new Map<string, number>();
  return pins.map((pin) => {
    const key = `${pin.lat.toFixed(4)}:${pin.lng.toFixed(4)}`;
    const n = seen.get(key) ?? 0;
    seen.set(key, n + 1);
    return n === 0 ? pin : { ...pin, lat: pin.lat + n * 0.0004, lng: pin.lng + n * 0.0004 };
  });
}

export default function VendorMap({
  cards,
  selectedId,
  onSelect,
}: {
  cards: MapPin[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<globalThis.Map<string, maplibregl.Marker>>(new globalThis.Map());
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: OSM_STYLE,
      attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }));
    const pins = spread(cards);
    const bounds = new maplibregl.LngLatBounds();
    for (const pin of pins) {
      const el = document.createElement("button");
      el.type = "button";
      el.setAttribute("data-testid", `map-pin-${pin.slug}`);
      el.setAttribute("data-pin-id", pin.id);
      el.setAttribute("aria-label", pin.name);
      el.className = PIN_CLASS;
      el.addEventListener("click", (event) => {
        event.stopPropagation();
        onSelectRef.current(pin.id);
      });
      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([pin.lng, pin.lat])
        .addTo(map);
      markersRef.current.set(pin.id, marker);
      bounds.extend([pin.lng, pin.lat]);
    }
    if (!bounds.isEmpty()) map.fitBounds(bounds, { padding: 48, maxZoom: 14 });
    mapRef.current = map;
    return () => {
      markersRef.current.clear();
      map.remove();
      mapRef.current = null;
    };
    // cards are stable for a given SSR page load — init once.
  }, []);

  useEffect(() => {
    for (const [id, marker] of markersRef.current) {
      const el = marker.getElement();
      const selected = id === selectedId;
      el.className = selected ? PIN_SELECTED_CLASS : PIN_CLASS;
      el.setAttribute("data-selected", String(selected));
    }
    if (selectedId) {
      const marker = markersRef.current.get(selectedId);
      if (marker && mapRef.current) {
        mapRef.current.flyTo({ center: marker.getLngLat(), zoom: 13 });
      }
    }
  }, [selectedId]);

  return (
    <div
      ref={containerRef}
      data-testid="vendor-map"
      className="h-[320px] w-full overflow-hidden rounded-card border border-line"
    />
  );
}
