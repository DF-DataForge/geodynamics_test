# -*- coding: utf-8 -*-
# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
from odoo.tests.common import TransactionCase

from ..models.fleet_vehicle import GD_TOTAL_KM_KEYS, GD_RUNNING_HOURS_KEYS


class FakeHandler:
    """Minimal stand-in for GeodynamicsHandler in odometer sync tests."""

    def __init__(self, vehicles=None, mileage=None):
        self.vehicles = vehicles if vehicles is not None else []
        self.mileage = mileage or {'Success': True, 'total_km': 0.0, 'total_hours': 0.0, 'bars': 0,
                                   'odometer_km': None, 'running_hours': None}
        self.mileage_calls = []

    def getVehicles(self):
        return {'Success': True, 'Data': self.vehicles}

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
