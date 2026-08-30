# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase


class TestWoonWerkVehicleFiltering(TransactionCase):
    """Test woon-werk calculation with vehicle code filtering."""

    def setUp(self):
        super(TestWoonWerkVehicleFiltering, self).setUp()
        self.cron = self.env['geodynamics.cron']
        self.config_param = self.env['ir.config_parameter'].sudo()

    def test_get_woon_werk_vehicle_codes_empty(self):
        """Test that empty config returns empty set (all vehicles allowed)."""
        self.config_param.set_param('geodynamics.woon_werk_vehicle_codes', '')
        codes = self.cron._get_woon_werk_vehicle_codes()
        self.assertEqual(codes, set(), "Empty config should return empty set")

    def test_get_woon_werk_vehicle_codes_single(self):
        """Test single vehicle code configuration."""
        self.config_param.set_param('geodynamics.woon_werk_vehicle_codes', 'AUTO')
        codes = self.cron._get_woon_werk_vehicle_codes()
        self.assertEqual(codes, {'AUTO'}, "Should return set with single code")

    def test_get_woon_werk_vehicle_codes_multiple(self):
        """Test multiple vehicle codes configuration."""
        self.config_param.set_param('geodynamics.woon_werk_vehicle_codes', 'AUTO,MOTO,VRACHT')
        codes = self.cron._get_woon_werk_vehicle_codes()
        self.assertEqual(codes, {'AUTO', 'MOTO', 'VRACHT'}, "Should return set with all codes")

    def test_get_woon_werk_vehicle_codes_whitespace(self):
        """Test that whitespace is stripped and codes are uppercased."""
        self.config_param.set_param('geodynamics.woon_werk_vehicle_codes', ' auto , moto , vracht ')
        codes = self.cron._get_woon_werk_vehicle_codes()
        self.assertEqual(codes, {'AUTO', 'MOTO', 'VRACHT'}, "Should strip whitespace and uppercase")

    def test_get_woon_werk_vehicle_codes_empty_entries(self):
        """Test that empty entries are filtered out."""
        self.config_param.set_param('geodynamics.woon_werk_vehicle_codes', 'AUTO,,MOTO, ,VRACHT')
        codes = self.cron._get_woon_werk_vehicle_codes()
        self.assertEqual(codes, {'AUTO', 'MOTO', 'VRACHT'}, "Should filter empty entries")

    def test_is_vehicle_allowed_no_config(self):
        """Test that all vehicles are allowed when no config is set."""
        self.config_param.set_param('geodynamics.woon_werk_vehicle_codes', '')
        vehicle_data = {'Code': 'AUTO', 'Id': 123}
        self.assertTrue(
            self.cron._is_vehicle_allowed_for_woon_werk(vehicle_data),
            "All vehicles should be allowed when no config"
        )

    def test_is_vehicle_allowed_matching_code(self):
        """Test that vehicle with matching code is allowed."""
        self.config_param.set_param('geodynamics.woon_werk_vehicle_codes', 'AUTO,MOTO')
        vehicle_data = {'Code': 'AUTO', 'Id': 123}
        self.assertTrue(
            self.cron._is_vehicle_allowed_for_woon_werk(vehicle_data),
            "Vehicle with matching code should be allowed"
        )

    def test_is_vehicle_allowed_non_matching_code(self):
        """Test that vehicle with non-matching code is not allowed."""
        self.config_param.set_param('geodynamics.woon_werk_vehicle_codes', 'AUTO,MOTO')
        vehicle_data = {'Code': 'VRACHT', 'Id': 123}
        self.assertFalse(
            self.cron._is_vehicle_allowed_for_woon_werk(vehicle_data),
            "Vehicle with non-matching code should not be allowed"
        )

    def test_is_vehicle_allowed_case_insensitive(self):
        """Test that code matching is case-insensitive."""
        self.config_param.set_param('geodynamics.woon_werk_vehicle_codes', 'AUTO,MOTO')
        vehicle_data = {'Code': 'auto', 'Id': 123}
        self.assertTrue(
            self.cron._is_vehicle_allowed_for_woon_werk(vehicle_data),
            "Code matching should be case-insensitive"
        )

    def test_is_vehicle_allowed_no_code(self):
        """Test that vehicle without code is not allowed when codes are configured."""
        self.config_param.set_param('geodynamics.woon_werk_vehicle_codes', 'AUTO,MOTO')
        vehicle_data = {'Id': 123}
        self.assertFalse(
            self.cron._is_vehicle_allowed_for_woon_werk(vehicle_data),
            "Vehicle without code should not be allowed"
        )

    def test_is_vehicle_allowed_empty_code(self):
        """Test that vehicle with empty code is not allowed when codes are configured."""
        self.config_param.set_param('geodynamics.woon_werk_vehicle_codes', 'AUTO,MOTO')
        vehicle_data = {'Code': '', 'Id': 123}
        self.assertFalse(
            self.cron._is_vehicle_allowed_for_woon_werk(vehicle_data),
            "Vehicle with empty code should not be allowed"
        )

    def test_is_vehicle_allowed_none_vehicle(self):
        """Test that None vehicle data is not allowed."""
        self.config_param.set_param('geodynamics.woon_werk_vehicle_codes', 'AUTO,MOTO')
        self.assertFalse(
            self.cron._is_vehicle_allowed_for_woon_werk(None),
            "None vehicle should not be allowed"
        )

    def test_is_vehicle_allowed_invalid_vehicle_type(self):
        """Test that invalid vehicle data type is not allowed."""
        self.config_param.set_param('geodynamics.woon_werk_vehicle_codes', 'AUTO,MOTO')
        self.assertFalse(
            self.cron._is_vehicle_allowed_for_woon_werk("invalid"),
            "Invalid vehicle type should not be allowed"
        )

    def test_is_vehicle_allowed_whitespace_in_code(self):
        """Test that whitespace in vehicle code is handled correctly."""
        self.config_param.set_param('geodynamics.woon_werk_vehicle_codes', 'AUTO,MOTO')
        vehicle_data = {'Code': ' AUTO ', 'Id': 123}
        self.assertTrue(
            self.cron._is_vehicle_allowed_for_woon_werk(vehicle_data),
            "Whitespace in vehicle code should be stripped"
        )

