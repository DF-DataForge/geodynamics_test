# -*- coding: utf-8 -*-
# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
from odoo.tests.common import TransactionCase

from ..models.fleet_vehicle import (
    GD_COUNTER_HOURS_NAMES, GD_COUNTER_KM_NAMES, GD_RUNNING_HOURS_KEYS, GD_TOTAL_KM_KEYS,
)


class FakeHandler:
    """Minimal stand-in for GeodynamicsHandler in odometer sync tests."""

    def __init__(self, vehicles=None, mileage=None, counters=None):
        self.vehicles = vehicles if vehicles is not None else []
        self.mileage = mileage or {'Success': True, 'total_km': 0.0, 'total_hours': 0.0, 'bars': 0,
                                   'odometer_km': None, 'running_hours': None}
        # {vehicle_gd_id: [{'CounterName': ..., 'CounterValue': ..., 'IsDefault': ...}]}
        self.counters = counters if counters is not None else {}
        self.counter_calls = []
        self.mileage_calls = []

    def getVehicles(self):
        return {'Success': True, 'Data': self.vehicles}

    def getVehicleCounters(self, vehicle_ids, defaults_only=False):
        self.counter_calls.append(list(vehicle_ids))
        if isinstance(self.counters, dict) and self.counters.get('Error'):
            return self.counters
        return {'Success': True,
                'Data': {vid: self.counters.get(vid, []) for vid in vehicle_ids if vid in self.counters}}

    def getResourceMileage(self, resource_id, from_dt, to_dt, raise_on_error=False):
        self.mileage_calls.append((resource_id, from_dt, to_dt))
        return self.mileage


class TestGdOdometerSync(TransactionCase):
    """Test odometer (km) logging from Geodynamics data."""

    def setUp(self):
        super().setUp()
        self.Vehicle = self.env['fleet.vehicle']
        self.Odometer = self.env['fleet.vehicle.odometer']
        brand = self.env['fleet.vehicle.model.brand'].create({'name': 'GD Test Brand'})
        model = self.env['fleet.vehicle.model'].create({'name': 'GD Test Model', 'brand_id': brand.id})
        self.vehicle = self.Vehicle.create({
            'model_id': model.id,
            'license_plate': '1-GDT-001',
            'df_geodynamics_id': 'gd-vehicle-guid-1',
        })

    # ------------------------------------------------------------------
    # Counter extraction from raw payload
    # ------------------------------------------------------------------

    def test_extract_counter_top_level(self):
        payload = {'Id': 'x', 'Mileage': 57107}
        self.assertEqual(self.Vehicle._gd_extract_counter(payload, GD_TOTAL_KM_KEYS), 57107.0)

    def test_extract_counter_nested(self):
        payload = {'Id': 'x', 'Counters': {'Odometer': '81614'}}
        self.assertEqual(self.Vehicle._gd_extract_counter(payload, GD_TOTAL_KM_KEYS), 81614.0)

    def test_extract_counter_running_hours(self):
        payload = {'Id': 'x', 'RunningHours': 1191.5}
        self.assertEqual(self.Vehicle._gd_extract_counter(payload, GD_RUNNING_HOURS_KEYS), 1191.5)

    def test_extract_counter_missing(self):
        self.assertIsNone(self.Vehicle._gd_extract_counter({'Id': 'x'}, GD_TOTAL_KM_KEYS))
        self.assertIsNone(self.Vehicle._gd_extract_counter(None, GD_TOTAL_KM_KEYS))
        self.assertIsNone(self.Vehicle._gd_extract_counter({'Mileage': 'n/a'}, GD_TOTAL_KM_KEYS))

    # ------------------------------------------------------------------
    # Odometer logging rules
    # ------------------------------------------------------------------

    def test_log_odometer_creates_record(self):
        self.assertTrue(self.vehicle._gd_log_odometer(57107.0))
        rec = self.Odometer.search([('vehicle_id', '=', self.vehicle.id)])
        self.assertEqual(len(rec), 1)
        self.assertEqual(rec.value, 57107.0)

    def test_log_odometer_updates_same_day(self):
        self.vehicle._gd_log_odometer(100.0)
        self.assertTrue(self.vehicle._gd_log_odometer(150.0))
        recs = self.Odometer.search([('vehicle_id', '=', self.vehicle.id)])
        self.assertEqual(len(recs), 1, 'Same-day sync must update, not duplicate')
        self.assertEqual(recs.value, 150.0)

    def test_log_odometer_never_decreases(self):
        self.vehicle._gd_log_odometer(200.0)
        self.assertFalse(self.vehicle._gd_log_odometer(180.0))
        recs = self.Odometer.search([('vehicle_id', '=', self.vehicle.id)])
        self.assertEqual(recs.value, 200.0)

    def test_log_odometer_ignores_zero(self):
        self.assertFalse(self.vehicle._gd_log_odometer(0.0))
        self.assertFalse(self.Odometer.search([('vehicle_id', '=', self.vehicle.id)]))

    # ------------------------------------------------------------------
    # Full sync
    # ------------------------------------------------------------------

    def test_sync_with_total_counter_in_payload(self):
        handler = FakeHandler(vehicles=[{
            'Id': 'gd-vehicle-guid-1',
            'Name': 'Voertuig 1',
            'Mileage': 57107,
            'RunningHours': 1191,
        }])
        logged, skipped, fallback = self.vehicle._gd_sync_odometer(handler)
        self.assertEqual((logged, skipped, fallback), (1, 0, 0))
        rec = self.Odometer.search([('vehicle_id', '=', self.vehicle.id)])
        self.assertEqual(rec.value, 57107.0)
        self.assertEqual(self.vehicle.df_gd_running_hours, 1191.0)
        self.assertTrue(self.vehicle.df_gd_odometer_last_sync)
        self.assertEqual(handler.mileage_calls, [], 'No fallback call expected when payload has a counter')

    def test_sync_fallback_to_trip_mileage(self):
        # Payload without any km counter -> incremental fallback via location/status
        handler = FakeHandler(
            vehicles=[{'Id': 'gd-vehicle-guid-1', 'Name': 'Voertuig 1'}],
            mileage={'Success': True, 'total_km': 42.5, 'total_hours': 1.25, 'bars': 3})
        logged, skipped, fallback = self.vehicle._gd_sync_odometer(handler)
        self.assertEqual((logged, skipped, fallback), (1, 0, 1))
        rec = self.Odometer.search([('vehicle_id', '=', self.vehicle.id)])
        self.assertEqual(rec.value, 42.5)
        self.assertEqual(self.vehicle.df_gd_running_hours, 1.25)
        self.assertEqual(len(handler.mileage_calls), 1)

    def test_sync_fallback_accumulates_on_last_value(self):
        self.vehicle._gd_log_odometer(1000.0)
        self.vehicle.df_gd_odometer_last_sync = False
        handler = FakeHandler(
            vehicles=[],
            mileage={'Success': True, 'total_km': 30.0, 'total_hours': 0.5, 'bars': 2})
        # Last log is today -> incremental window starts tomorrow -> nothing to add
        logged, skipped, fallback = self.vehicle._gd_sync_odometer(handler)
        self.assertEqual(logged, 0)
        rec = self.Odometer.search([('vehicle_id', '=', self.vehicle.id)])
        self.assertEqual(rec.value, 1000.0, 'Must not double count the day of the last manual log')

    def test_sync_skips_unlinked_vehicles(self):
        self.vehicle.df_geodynamics_id = False
        handler = FakeHandler()
        logged, skipped, fallback = self.vehicle._gd_sync_odometer(handler)
        self.assertEqual((logged, skipped, fallback), (0, 0, 0))

    def test_sync_manual_zero_record_does_not_block(self):
        """A manually created 0,00 odometer entry must not block the sync,
        and must be updated in place with the fetched value."""
        self.Odometer.create({'vehicle_id': self.vehicle.id, 'value': 0.0})
        handler = FakeHandler(
            vehicles=[{'Id': 'gd-vehicle-guid-1', 'Name': 'Voertuig 1'}],
            mileage={'Success': True, 'total_km': 42.5, 'total_hours': 1.25, 'bars': 3,
                     'odometer_km': None, 'running_hours': None})
        logged, skipped, fallback = self.vehicle._gd_sync_odometer(handler)
        self.assertEqual((logged, skipped, fallback), (1, 0, 1))
        self.assertEqual(len(handler.mileage_calls), 1,
                         'Zero-value record must not suppress the mileage fetch')
        recs = self.Odometer.search([('vehicle_id', '=', self.vehicle.id)])
        self.assertEqual(len(recs), 1, "Today's manual 0,00 record must be updated, not duplicated")
        self.assertEqual(recs.value, 42.5)

    def test_sync_absolute_odometer_from_status_bars(self):
        """When the status bars expose an absolute odometer counter, it is
        used directly so Odoo shows the same total as Geodynamics."""
        handler = FakeHandler(
            vehicles=[{'Id': 'gd-vehicle-guid-1', 'Name': 'Voertuig 1'}],
            mileage={'Success': True, 'total_km': 12.0, 'total_hours': 0.5, 'bars': 2,
                     'odometer_km': 57107.0, 'running_hours': 1191.0})
        logged, skipped, fallback = self.vehicle._gd_sync_odometer(handler)
        self.assertEqual((logged, skipped, fallback), (1, 0, 1))
        rec = self.Odometer.search([('vehicle_id', '=', self.vehicle.id)])
        self.assertEqual(rec.value, 57107.0, 'Absolute odometer must win over accumulated trip km')
        self.assertEqual(self.vehicle.df_gd_running_hours, 1191.0)

    def test_sync_api_error_does_not_advance_window(self):
        handler = FakeHandler(vehicles=[{'Id': 'gd-vehicle-guid-1'}],
                              mileage={'Error': 'HTTP 500'})
        logged, skipped, fallback = self.vehicle._gd_sync_odometer(handler)
        self.assertEqual((logged, skipped, fallback), (0, 1, 0))
        self.assertFalse(self.vehicle.df_gd_odometer_last_sync,
                         'Failed fetch must not advance the sync window')

    # ------------------------------------------------------------------
    # Vehicle counters (POST /api/v1/vehiclecounters)
    # ------------------------------------------------------------------

    def test_match_counter_by_name(self):
        counters = [
            {'CounterName': 'Draaiuren', 'CounterValue': 1191.57, 'IsDefault': True},
            {'CounterName': 'Kilometers', 'CounterValue': 57107.3, 'IsDefault': True},
        ]
        self.assertEqual(self.Vehicle._gd_match_counter(counters, GD_COUNTER_KM_NAMES), 57107.3)
        self.assertEqual(self.Vehicle._gd_match_counter(counters, GD_COUNTER_HOURS_NAMES), 1191.57)

    def test_match_counter_is_case_insensitive(self):
        counters = [{'CounterName': 'KILOMETERS', 'CounterValue': 10.0, 'IsDefault': True}]
        self.assertEqual(self.Vehicle._gd_match_counter(counters, GD_COUNTER_KM_NAMES), 10.0)

    def test_match_counter_falls_back_to_substring(self):
        counters = [{'CounterName': 'Draaiuren motor', 'CounterValue': 12.5, 'IsDefault': False}]
        self.assertEqual(self.Vehicle._gd_match_counter(counters, GD_COUNTER_HOURS_NAMES), 12.5)

    def test_match_counter_prefers_exact_over_substring(self):
        counters = [
            {'CounterName': 'Kilometers aanhangwagen', 'CounterValue': 10.0, 'IsDefault': False},
            {'CounterName': 'Kilometers', 'CounterValue': 500.0, 'IsDefault': False},
        ]
        self.assertEqual(self.Vehicle._gd_match_counter(counters, GD_COUNTER_KM_NAMES), 500.0)

    def test_match_counter_prefers_default_template(self):
        counters = [
            {'CounterName': 'Kilometers', 'CounterValue': 10.0, 'IsDefault': False},
            {'CounterName': 'Kilometers', 'CounterValue': 500.0, 'IsDefault': True},
        ]
        self.assertEqual(self.Vehicle._gd_match_counter(counters, GD_COUNTER_KM_NAMES), 500.0)

    def test_match_counter_ignores_unusable_values(self):
        self.assertIsNone(self.Vehicle._gd_match_counter(
            [{'CounterName': 'Kilometers', 'CounterValue': None, 'IsDefault': True}],
            GD_COUNTER_KM_NAMES))
        self.assertIsNone(self.Vehicle._gd_match_counter(
            [{'CounterName': 'Kilometers', 'CounterValue': '57107,3', 'IsDefault': True}],
            GD_COUNTER_KM_NAMES))
        self.assertIsNone(self.Vehicle._gd_match_counter([], GD_COUNTER_KM_NAMES))
        self.assertIsNone(self.Vehicle._gd_match_counter(
            [{'CounterName': 'Tankbeurten', 'CounterValue': 3, 'IsDefault': True}],
            GD_COUNTER_KM_NAMES))

    def test_counter_names_overridable_by_config_parameter(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'geodynamics.counter_name_km', 'Stand teller, Totaal KM')
        names = self.Vehicle._gd_counter_names('geodynamics.counter_name_km', GD_COUNTER_KM_NAMES)
        self.assertEqual(names, ('stand teller', 'totaal km'))
        counters = [{'CounterName': 'Stand teller', 'CounterValue': 99.0, 'IsDefault': True}]
        self.assertEqual(self.Vehicle._gd_match_counter(counters, names), 99.0)

    def test_counter_names_default_without_config_parameter(self):
        self.assertEqual(
            self.Vehicle._gd_counter_names('geodynamics.counter_name_km', GD_COUNTER_KM_NAMES),
            GD_COUNTER_KM_NAMES)

    def test_sync_uses_vehicle_counters_first(self):
        """The 'Voertuig tellers' totals win and make the fallbacks unnecessary."""
        handler = FakeHandler(
            vehicles=[{'Id': 'gd-vehicle-guid-1', 'Name': 'Voertuig 1'}],
            counters={'gd-vehicle-guid-1': [
                {'CounterName': 'Draaiuren', 'CounterValue': 1191.57, 'IsDefault': True},
                {'CounterName': 'Kilometers', 'CounterValue': 57107.3, 'IsDefault': True},
            ]})
        logged, skipped, fallback = self.vehicle._gd_sync_odometer(handler)
        self.assertEqual((logged, skipped, fallback), (1, 0, 0))
        rec = self.Odometer.search([('vehicle_id', '=', self.vehicle.id)])
        self.assertEqual(rec.value, 57107.3)
        self.assertEqual(self.vehicle.df_gd_running_hours, 1191.57)
        self.assertEqual(handler.counter_calls, [['gd-vehicle-guid-1']])
        self.assertEqual(handler.mileage_calls, [],
                         'No location/status fallback expected when a counter is available')

    def test_sync_counters_win_over_vehicle_payload(self):
        handler = FakeHandler(
            vehicles=[{'Id': 'gd-vehicle-guid-1', 'Mileage': 111, 'RunningHours': 22}],
            counters={'gd-vehicle-guid-1': [
                {'CounterName': 'Kilometers', 'CounterValue': 57107.3, 'IsDefault': True},
                {'CounterName': 'Draaiuren', 'CounterValue': 1191.57, 'IsDefault': True},
            ]})
        self.vehicle._gd_sync_odometer(handler)
        rec = self.Odometer.search([('vehicle_id', '=', self.vehicle.id)])
        self.assertEqual(rec.value, 57107.3)
        self.assertEqual(self.vehicle.df_gd_running_hours, 1191.57)

    def test_sync_counters_partial_falls_back_for_missing_km(self):
        """An hours-only counter set still leaves the km sourcing to the fallbacks."""
        handler = FakeHandler(
            vehicles=[{'Id': 'gd-vehicle-guid-1'}],
            counters={'gd-vehicle-guid-1': [
                {'CounterName': 'Draaiuren', 'CounterValue': 1191.57, 'IsDefault': True},
            ]},
            mileage={'Success': True, 'total_km': 42.5, 'total_hours': 1.25, 'bars': 3,
                     'odometer_km': None, 'running_hours': None})
        logged, skipped, fallback = self.vehicle._gd_sync_odometer(handler)
        self.assertEqual((logged, skipped, fallback), (1, 0, 1))
        rec = self.Odometer.search([('vehicle_id', '=', self.vehicle.id)])
        self.assertEqual(rec.value, 42.5)
        self.assertEqual(self.vehicle.df_gd_running_hours, 1191.57,
                         'The counter value must not be overwritten by the fallback')

    def test_sync_counter_error_falls_back(self):
        handler = FakeHandler(
            vehicles=[{'Id': 'gd-vehicle-guid-1', 'Mileage': 57107}],
            counters={'Error': 'HTTP 403'})
        logged, skipped, fallback = self.vehicle._gd_sync_odometer(handler)
        self.assertEqual((logged, skipped, fallback), (1, 0, 0))
        rec = self.Odometer.search([('vehicle_id', '=', self.vehicle.id)])
        self.assertEqual(rec.value, 57107.0, 'A counter failure must not break the sync')

    def test_sync_counters_for_other_vehicle_are_ignored(self):
        handler = FakeHandler(
            vehicles=[{'Id': 'gd-vehicle-guid-1'}],
            counters={'some-other-guid': [
                {'CounterName': 'Kilometers', 'CounterValue': 99999.0, 'IsDefault': True},
            ]})
        logged, skipped, fallback = self.vehicle._gd_sync_odometer(handler)
        self.assertEqual(logged, 0)
        self.assertFalse(self.Odometer.search([('vehicle_id', '=', self.vehicle.id)]))
