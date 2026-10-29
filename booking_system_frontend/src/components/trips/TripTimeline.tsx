import { parseISO } from 'date-fns';
import { Plane, Clock } from 'lucide-react';
import type { ItinerarySearchResult } from '../../types';
import { Card, Button } from '../common';
import { formatCurrency, formatDate } from '../../utils/formatters';

interface TripTimelineProps {
  trip: ItinerarySearchResult;
  onBook: (trip: ItinerarySearchResult) => void;
  isBooking?: boolean;
}

const formatMinutes = (totalMinutes: number): string => {
  const hours = Math.floor(totalMinutes / 60);
  const minutes = Math.round(totalMinutes % 60);
  return `${hours}h ${minutes}m`;
};

const layoverMinutes = (arrival: string, departure: string): number =>
  (parseISO(departure).getTime() - parseISO(arrival).getTime()) / 60000;

export const TripTimeline = ({ trip, onBook, isBooking = false }: TripTimelineProps) => {
  return (
    <Card className="space-y-3">
      <div className="flex items-center justify-between text-sm text-star-white/70">
        <span>
          {trip.legs.length} leg{trip.legs.length !== 1 ? 's' : ''}
        </span>
        <span>Total travel time: {formatMinutes(trip.total_duration_minutes)}</span>
      </div>

      {trip.legs.map((leg, index) => (
        <div key={leg.flight_id}>
          {index > 0 && (
            <div className="flex items-center gap-2 my-2 text-sm text-yellow-300">
              <Clock size={14} />
              <span className="px-2 py-0.5 rounded-full bg-yellow-500/10 border border-yellow-500/30">
                Layover at {leg.origin}:{' '}
                {formatMinutes(layoverMinutes(trip.legs[index - 1].arrival_time, leg.departure_time))}
              </span>
            </div>
          )}
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <Plane className="text-cosmic-purple" size={20} />
              <div>
                <div className="font-semibold text-star-white">
                  {leg.origin} → {leg.destination}
                </div>
                <div className="text-sm text-star-white/70">
                  {formatDate(leg.departure_time)} – {formatDate(leg.arrival_time)}
                </div>
              </div>
            </div>
            <div className="text-star-white font-medium">{formatCurrency(leg.economy_price)}</div>
          </div>
        </div>
      ))}

      <div className="flex items-center justify-between pt-3 border-t border-white/10">
        <div>
          <span className="text-star-white/70">Total price: </span>
          <span className="text-xl font-bold text-star-white">{formatCurrency(trip.total_price)}</span>
        </div>
        <Button onClick={() => onBook(trip)} isLoading={isBooking} disabled={isBooking}>
          Book trip
        </Button>
      </div>
    </Card>
  );
};
