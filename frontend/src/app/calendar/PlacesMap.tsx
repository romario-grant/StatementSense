"use client";

import { useState, useCallback } from "react";
import { APIProvider, Map, AdvancedMarker, InfoWindow } from "@vis.gl/react-google-maps";
import { MapPin, Star, ExternalLink, Phone } from "lucide-react";

interface MarkerData {
  place_id: string;
  name: string;
  address: string;
  lat: number;
  lng: number;
  rating?: number | null;
  rating_count?: number | null;
  price_level?: string | null;
  phone?: string | null;
  website?: string | null;
  google_maps_url: string;
  opening_hours?: string[] | null;
}

interface PlacesMapProps {
  center: { lat: number; lng: number } | null;
  markers: MarkerData[];
  destination: string;
  subscriptionName?: string;
}

const MAP_ID = "calendarsense-map";

export default function PlacesMap({
  center,
  markers,
  destination,
  subscriptionName,
}: PlacesMapProps) {
  const [activeMarker, setActiveMarker] = useState<string | null>(null);

  const apiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;

  const handleMarkerClick = useCallback((placeId: string) => {
    setActiveMarker((prev) => (prev === placeId ? null : placeId));
  }, []);

  if (!apiKey) {
    return (
      <div className="rounded-xl bg-white/5 border border-white/10 p-6 text-center text-white/50 text-sm">
        <MapPin size={24} className="mx-auto mb-2 opacity-50" />
        <p>Map unavailable — Google Maps API key not configured.</p>
      </div>
    );
  }

  if (!center || markers.length === 0) {
    return (
      <div className="rounded-xl bg-white/5 border border-white/10 p-6 text-center text-white/50 text-sm">
        <MapPin size={24} className="mx-auto mb-2 opacity-50" />
        <p>No alternatives found to display on the map.</p>
      </div>
    );
  }

  return (
    <div className="rounded-2xl overflow-hidden border border-white/10 bg-[#05080c] shadow-xl">
      {/* Map Header */}
      <div className="bg-[#05080c] px-4 py-3 flex items-center justify-between border-b border-white/10">
        <div className="flex items-center gap-2">
          <MapPin size={16} className="text-yellow-400" />
          <span className="text-sm font-medium text-white">
            {subscriptionName ? `Alternatives for ${subscriptionName}` : "Nearby Alternatives"}
          </span>
        </div>
        <span className="text-xs text-white/50">{markers.length} found in {destination}</span>
      </div>

      {/* Map Container */}
      <APIProvider apiKey={apiKey}>
        <div className="overflow-hidden" style={{ height: "320px", width: "100%" }}>
          <Map
            defaultCenter={center}
            defaultZoom={13}
            mapId={MAP_ID}
            gestureHandling="cooperative"
            disableDefaultUI={false}
            clickableIcons={false}
            colorScheme="DARK"
          >
            {markers.map((marker) => (
              <AdvancedMarker
                key={marker.place_id}
                position={{ lat: marker.lat, lng: marker.lng }}
                onClick={() => handleMarkerClick(marker.place_id)}
                title={marker.name}
              />
            ))}

            {/* Info Window for active marker */}
            {activeMarker && (() => {
              const marker = markers.find((m) => m.place_id === activeMarker);
              if (!marker) return null;
              return (
                <InfoWindow
                  position={{ lat: marker.lat, lng: marker.lng }}
                  onCloseClick={() => setActiveMarker(null)}
                  headerDisabled
                >
                  <div className="p-1 max-w-[240px]" style={{ fontFamily: "var(--font-geist-sans), system-ui, sans-serif" }}>
                    <h4 className="font-semibold text-sm text-gray-900 mb-1 leading-tight">
                      {marker.name}
                    </h4>
                    <p className="text-xs text-gray-500 mb-2 leading-snug">
                      {marker.address}
                    </p>

                    {/* Rating */}
                    {marker.rating && (
                      <div className="flex items-center gap-1 mb-2">
                        <Star size={12} className="text-yellow-500 fill-yellow-500" />
                        <span className="text-xs font-medium text-gray-700">
                          {marker.rating.toFixed(1)}
                        </span>
                        {marker.rating_count && (
                          <span className="text-xs text-gray-400">
                            ({marker.rating_count.toLocaleString()})
                          </span>
                        )}
                        {marker.price_level && (
                          <span className="text-xs text-gray-400 ml-1">
                            · {marker.price_level}
                          </span>
                        )}
                      </div>
                    )}

                    {/* Phone */}
                    {marker.phone && (
                      <div className="flex items-center gap-1 text-xs text-gray-500 mb-2">
                        <Phone size={10} />
                        <span>{marker.phone}</span>
                      </div>
                    )}

                    {/* Action Links */}
                    <div className="flex gap-2 mt-1">
                      {marker.google_maps_url && (
                        <a
                          href={marker.google_maps_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 font-medium no-underline"
                        >
                          <ExternalLink size={10} />
                          Google Maps
                        </a>
                      )}
                      {marker.website && (
                        <a
                          href={marker.website}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 font-medium no-underline"
                        >
                          <ExternalLink size={10} />
                          Website
                        </a>
                      )}
                    </div>
                  </div>
                </InfoWindow>
              );
            })()}
          </Map>
        </div>
      </APIProvider>

      {/* Places List (below map) */}
      <div className="bg-[#05080c] divide-y divide-white/5">
        {markers.map((marker) => (
          <button
            key={marker.place_id}
            onClick={() => handleMarkerClick(marker.place_id)}
            className={`w-full flex items-center gap-3 px-4 py-3 text-left bg-transparent border-none cursor-pointer transition-colors hover:bg-white/5 ${activeMarker === marker.place_id ? "bg-white/10" : ""}`}
          >
            <div className="w-8 h-8 rounded-full bg-yellow-400/10 flex items-center justify-center shrink-0">
              <MapPin size={14} className="text-yellow-400" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-white truncate">{marker.name}</p>
              <p className="text-xs text-white/40 truncate">{marker.address}</p>
            </div>
            {marker.rating && (
              <div className="flex items-center gap-1 shrink-0">
                <Star size={10} className="text-yellow-400 fill-yellow-400" />
                <span className="text-xs text-white/70">{marker.rating.toFixed(1)}</span>
              </div>
            )}
            {marker.google_maps_url && (
              <a
                href={marker.google_maps_url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="text-white/30 hover:text-white/70 transition-colors shrink-0"
              >
                <ExternalLink size={14} />
              </a>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
