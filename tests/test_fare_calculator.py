"""Run with: python -m unittest discover tests"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.flight import FlightOffer
from tools.fare_calculator import FareCalculator


def offer(oid, fare, legs, ts="2026-11-25T10:00:00Z"):
    return FlightOffer.create(
        offer_id=oid, airline="IndiGo", airline_code="6E", flight_number=legs[0],
        origin="PNQ", destination="DPS", departure_time="", arrival_time="",
        duration="", duration_minutes=0, stops=len(legs) - 1, layovers=[],
        cabin="Economy", baggage="", base_fare=fare, tax_fees=0,
        observation_timestamp=ts, segments=[{"flight_number": f} for f in legs],
    )


class ArbitrateOffersTest(unittest.TestCase):

    def test_trips_sharing_only_first_leg_are_all_kept(self):
        a = offer("a", 24000, ["6E 672", "6E 1613"])
        b = offer("b", 21000, ["6E 672", "6E 1605"])
        kept, conflicts = FareCalculator.arbitrate_offers([a, b])
        self.assertEqual({o.offer_id for o in kept}, {"a", "b"})
        self.assertEqual(conflicts, [])

    def test_same_trip_same_timestamp_keeps_cheapest(self):
        a = offer("a", 24000, ["6E 672", "6E 1613"])
        b = offer("b", 23352, ["6E 672", "6E 1613"])
        kept, _ = FareCalculator.arbitrate_offers([a, b])
        self.assertEqual([o.offer_id for o in kept], ["b"])

    def test_same_flight_from_two_sources_keeps_newest(self):
        old = offer("old", 21000, ["FL-101"], ts="2026-10-29T08:00:00Z")
        new = offer("new", 23800, ["FL-101"], ts="2026-10-29T09:15:00Z")
        kept, conflicts = FareCalculator.arbitrate_offers([old, new])
        self.assertEqual([o.offer_id for o in kept], ["new"])
        self.assertEqual(len(conflicts), 1)


if __name__ == "__main__":
    unittest.main()
