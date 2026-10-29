import { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import type { Itinerary } from '../../types';
import { Card } from '../common';
import { formatCurrency, formatDate } from '../../utils/formatters';

interface TripCardProps {
  trip: Itinerary;
}

export const TripCard = ({ trip }: TripCardProps) => {
  const [expanded, setExpanded] = useState(false);
  const legs = [...trip.legs].sort((a, b) => a.leg_order - b.leg_order);
  const first = legs[0]?.flight;
  const last = legs[legs.length - 1]?.flight;

  if (!first || !last) return null;

  return (
    <Card className="space-y-3">
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        aria-expanded={expanded}
        className="w-full text-left flex items-center justify-between gap-4"
      >
        <div>
          <div className="text-lg font-bold text-star-white">
            {first.origin} → {last.destination}
          </div>
          <div className="text-sm text-star-white/70">
            {formatDate(first.departure_time)} – {formatDate(last.arrival_time)}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-star-white font-medium">{formatCurrency(trip.total_price)}</span>
          <span className="px-2 py-0.5 rounded-full text-xs bg-white/10 text-star-white capitalize">
            {trip.status}
          </span>
          {expanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
        </div>
      </button>

      {expanded && (
        <ul className="space-y-2 pt-3 border-t border-white/10">
          {legs.map((leg) => (
            <li key={leg.leg_id} className="text-sm text-star-white/80">
              <span className="font-semibold text-star-white">Flight #{leg.flight_id}</span>:{' '}
              {leg.flight.origin} → {leg.flight.destination} ·{' '}
              {formatDate(leg.flight.departure_time)} – {formatDate(leg.flight.arrival_time)}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
};
