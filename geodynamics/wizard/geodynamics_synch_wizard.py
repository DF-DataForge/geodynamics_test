# -*- coding: utf-8 -*-
# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class GeodynamicsSynchWizard(models.TransientModel):
    _name = 'geodynamics.synch.wizard'
    _description = 'Geodynamics Clocking Synchronization Wizard'

    date_from = fields.Date(string='Start Date', required=True, default=lambda self: fields.Date.today() - timedelta(days=7))
    date_to = fields.Date(string='End Date', required=True, default=fields.Date.today)

    def action_sync(self):
        """Synchronize clockings for the selected date range."""
        self.ensure_one()

        if self.date_from > self.date_to:
            raise UserError(_('Start Date must be before or equal to End Date.'))

        # Get the cron model to use the fetch method
        cron_model = self.env['geodynamics.cron']

        # Calculate number of days
        delta = self.date_to - self.date_from
        total_days = delta.days + 1

        synced_count = 0
        failed_days = []

        # Sync each day in the range
        current_date = self.date_from
        while current_date <= self.date_to:
            _logger.info('Syncing clockings for date: %s', current_date)
            try:
                result = cron_model.fetch_clockings_by_date(current_date)
                if result:
                    synced_count += 1
                else:
                    failed_days.append(current_date.strftime('%Y-%m-%d'))
            except Exception as e:
                _logger.exception('Failed to sync clockings for %s: %s', current_date, e)
                failed_days.append(current_date.strftime('%Y-%m-%d'))

            current_date += timedelta(days=1)

        # Prepare result message
        message = _('Synchronization completed!\n\n')
        message += _('Period: %s to %s\n') % (self.date_from, self.date_to)
        message += _('Total days: %d\n') % total_days
        message += _('Successfully synced: %d days\n') % synced_count

        if failed_days:
            message += _('\nFailed days (%d): %s') % (len(failed_days), ', '.join(failed_days))

        # Show result in a message dialog
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Synchronization Result'),
                'message': message,
                'type': 'success' if not failed_days else 'warning',
                'sticky': True,
            }
        }
# -*- coding: utf-8 -*-
from . import geodynamics_synch_wizard

