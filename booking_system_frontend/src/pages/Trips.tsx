import { useState, useEffect, useCallback, useRef } from 'react';
import type { ErrorResponse, Itinerary, ItinerarySearchResult } from '../types';
import { Button, LoadingSpinner } from '../components/common';
import { TripTimeline } from '../components/trips/TripTimeline';
import { TripCard } from '../components/trips/TripCard';
import { UserIdentification } from '../components/user/UserIdentification';
import {
  searchItineraries,
  createItinerary,
  confirmItinerary,
  getUserItineraries,
  isErrorResponse,
} from '../services/api';
import { useUser } from '../hooks/useUserContext';
import toast from 'react-hot-toast';
import { motion } from 'framer-motion';

const inputClasses =
  'w-full px-4 py-3 bg-white/5 border border-white/10 rounded-lg text-star-white placeholder-star-white/50 focus:outline-none focus:ring-2 focus:ring-cosmic-purple';

export const Trips = () => {
  const { user } = useUser();
  const [origin, setOrigin] = useState('');
  const [destination, setDestination] = useState('');
  const [date, setDate] = useState('');
  const [results, setResults] = useState<ItinerarySearchResult[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [bookingTrip, setBookingTrip] = useState<ItinerarySearchResult | null>(null);
  const [isBooking, setIsBooking] = useState(false);
  const [showUserModal, setShowUserModal] = useState(false);
  const identifiedRef = useRef(false);
  const [myTrips, setMyTrips] = useState<Itinerary[]>([]);
  const [isLoadingTrips, setIsLoadingTrips] = useState(false);

  const loadMyTrips = useCallback(async () => {
    if (!user) {
      setMyTrips([]);
      return;
    }
    setIsLoadingTrips(true);
    try {
      const trips = await getUserItineraries(user.user_id);
      setMyTrips(trips.filter((trip) => trip.status === 'confirmed'));
    } catch (err) {
      const error = err as ErrorResponse;
      toast.error(error.details || error.error || 'Failed to load your trips');
    } finally {
      setIsLoadingTrips(false);
    }
  }, [user]);

  useEffect(() => {
    loadMyTrips();
  }, [loadMyTrips]);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!origin.trim() || !destination.trim() || !date) {
      toast.error('Please enter an origin, destination and date');
      return;
    }
    setIsSearching(true);
    try {
      setResults(await searchItineraries(origin.trim(), destination.trim(), date));
    } catch (err) {
      const error = err as ErrorResponse;
      toast.error(error.details || error.error || 'Search failed');
    } finally {
      setIsSearching(false);
    }
  };

  const bookTrip = async (trip: ItinerarySearchResult, userId: number, name: string) => {
    setIsBooking(true);
    try {
      const held = await createItinerary({
        user_id: userId,
        name,
        flight_ids: trip.legs.map((leg) => leg.flight_id),
      });
      if (isErrorResponse(held)) {
        toast.error(held.details || held.error);
        return;
      }
      const confirmed = await confirmItinerary(held.itinerary_id);
      if (isErrorResponse(confirmed)) {
        toast.error(confirmed.details || confirmed.error);
        return;
      }
      toast.success('Trip booked!');
      await loadMyTrips();
    } catch (err) {
      // FastAPI wraps ErrorResponse in { detail: ... }
      const error = err as ErrorResponse & { detail?: ErrorResponse };
      const body = error.detail ?? error;
      toast.error(body.details || body.error || 'Failed to book trip');
    } finally {
      setIsBooking(false);
      setBookingTrip(null);
    }
  };

  const handleBook = (trip: ItinerarySearchResult) => {
    if (!user) {
      identifiedRef.current = false;
      setBookingTrip(trip);
      setShowUserModal(true);
      return;
    }
    bookTrip(trip, user.user_id, user.name);
  };

  // The modal calls setUser before onSuccess; the effect below books the
  // pending trip once the modal has closed and the new user is available.
  const handleUserIdentified = () => {
    identifiedRef.current = true;
    setShowUserModal(false);
  };

  const handleUserModalClose = () => {
    setShowUserModal(false);
    if (!identifiedRef.current) setBookingTrip(null);
  };

  useEffect(() => {
    if (user && bookingTrip && !showUserModal && !isBooking) {
      bookTrip(bookingTrip, user.user_id, user.name);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, showUserModal]);

  return (
    <div className="space-y-8">
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="text-center">
        <h1 className="text-4xl md:text-5xl font-bold text-star-white mb-4">
          Multi-leg <span className="bg-cosmic-gradient bg-clip-text text-transparent">Trips</span>
        </h1>
        <p className="text-star-white/70 text-lg">
          Connect up to three flights into one journey, booked in a single step
        </p>
      </motion.div>

      <form onSubmit={handleSearch} className="glass-card p-6 grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
        <label className="text-sm text-star-white/70">
          Origin
          <input
            type="text"
            value={origin}
            onChange={(e) => setOrigin(e.target.value)}
            placeholder="Earth"
            className={inputClasses}
          />
        </label>
        <label className="text-sm text-star-white/70">
          Destination
          <input
            type="text"
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
            placeholder="Europa"
            className={inputClasses}
          />
        </label>
        <label className="text-sm text-star-white/70">
          Date
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className={inputClasses} />
        </label>
        <Button type="submit" isLoading={isSearching} disabled={isSearching}>
          Search
        </Button>
      </form>

      {isSearching ? (
        <LoadingSpinner size="lg" text="Searching trips..." />
      ) : results === null ? null : results.length === 0 ? (
        <p className="text-center py-8 text-star-white/70 text-lg">
          No itineraries found for those inputs
        </p>
      ) : (
        <div className="space-y-4">
          {results.map((trip) => (
            <TripTimeline
              key={trip.legs.map((leg) => leg.flight_id).join('-')}
              trip={trip}
              onBook={handleBook}
              isBooking={isBooking}
            />
          ))}
        </div>
      )}

      {user && (
        <section className="space-y-4">
          <h2 className="text-2xl font-bold text-star-white">My trips</h2>
          {isLoadingTrips ? (
            <LoadingSpinner text="Loading your trips..." />
          ) : myTrips.length === 0 ? (
            <p className="text-star-white/70">No trips booked yet</p>
          ) : (
            myTrips.map((trip) => <TripCard key={trip.itinerary_id} trip={trip} />)
          )}
        </section>
      )}

      <UserIdentification
        isOpen={showUserModal}
        onClose={handleUserModalClose}
        onSuccess={handleUserIdentified}
      />
    </div>
  );
};
