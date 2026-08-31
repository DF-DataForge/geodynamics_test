# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
from odoo import api, models, fields, _
from datetime import datetime, time, timedelta
import logging

_logger = logging.getLogger(__name__)

KM_PER_MILE = 1.609344

# Candidate keys for the total odometer / running-hours counters in the raw
# Geodynamics vehicle payload (checked top-level and one nested dict deep).
GD_TOTAL_KM_KEYS = (
    'Mileage', 'MileageKm', 'TotalMileage', 'CurrentMileage',
    'Odometer', 'OdometerValue', 'OdometerKm',
    'Kilometers', 'KilometerStand', 'Km',
)
GD_RUNNING_HOURS_KEYS = (
    'RunningHours', 'TotalRunningHours', 'CurrentRunningHours',
    'OperatingHours', 'EngineHours', 'Hours', 'Draaiuren',
)

# Candidate names for the counters returned by POST /api/v1/vehiclecounters
# (the 'Voertuig tellers' list in Geodynamics). Unlike the payload keys above
# these are free text chosen per Geodynamics instance and are locale-dependent,
# so they are matched case-insensitively. Override per database with the
# 'geodynamics.counter_name_km' / 'geodynamics.counter_name_hours' config
# parameters (comma-separated) when an instance uses its own naming.
GD_COUNTER_KM_NAMES = (
    'kilometers', 'kilometer', 'km', 'kilometerstand', 'kilometrage',
    'mileage', 'odometer', 'afstand', 'distance',
)
GD_COUNTER_HOURS_NAMES = (
    'draaiuren', 'draaiuur', 'motoruren', 'bedrijfsuren', 'uren',
    'running hours', 'runninghours', 'operating hours', 'engine hours',
    'hours', 'heures', 'heures moteur',
)


class FleetVehicleGd(models.Model):
    _inherit = 'fleet.vehicle'

    df_geodynamics_id = fields.Char(string='Geodynamics ID', index=True)
    df_geodynamics_last_sync = fields.Datetime(string='Last Geodynamics Sync')
    df_geodynamics_raw = fields.Json(string='Geodynamics Raw Data')
    df_gd_running_hours = fields.Float(string='Running Hours (Geodynamics)',
                                       help='Total running hours (draaiuren) reported by Geodynamics.')
    df_gd_odometer_last_sync = fields.Datetime(
        string='Last Odometer Sync',
        help='Last time the odometer was synchronized from Geodynamics. '
             'Used as the start of the next incremental mileage window.')

    @api.model
    def _gd_get_handler(self):
        """Return a configured GeodynamicsHandler, or None when credentials are missing."""
        from ..models.gdhandler import GeodynamicsHandler

        ICP = self.env['ir.config_parameter'].sudo()
        company = ICP.get_param('geodynamics.company')
        login = ICP.get_param('geodynamics.username')
        password = ICP.get_param('geodynamics.password')
        if not all([company, login, password]):
            return None
        return GeodynamicsHandler(login, password, company, self.env)

    @api.model
    def _gd_notify(self, message, kind='success', title=None):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title or _('Geodynamics'),
                'type': kind,
                'message': message,
                'sticky': False,
            },
        }

    # ------------------------------------------------------------------
    # Odometer sync (km + running hours from Geodynamics)
    # ------------------------------------------------------------------

    @api.model
    def _gd_extract_counter(self, payload, keys):
        """Extract a numeric counter from a raw Geodynamics vehicle payload.

        Tries the candidate keys on the top level, then one nested dict deep
        (some API payloads group counters under e.g. 'Counters' or 'Service').
        Returns float or None.
        """
        if not isinstance(payload, dict):
            return None

        def _from_dict(d, depth=0):
            for key in keys:
                if key in d and d[key] not in (None, False, ''):
                    try:
                        return float(d[key])
                    except (TypeError, ValueError):
                        continue
            if depth < 3:
                for sub in d.values():
                    if isinstance(sub, dict):
                        value = _from_dict(sub, depth + 1)
                        if value is not None:
                            return value
            return None

        return _from_dict(payload)

    @api.model
    def _gd_counter_names(self, param, defaults):
        """Candidate counter names for `param`, overridable per database."""
        raw = self.env['ir.config_parameter'].sudo().get_param(param)
        if raw:
            names = tuple(n.strip().lower() for n in raw.split(',') if n.strip())
            if names:
                return names
        return defaults

    @api.model
    def _gd_match_counter(self, counters, names):
        """Return the value of the first counter whose name matches `names`.

        Counter names come straight from the Geodynamics configuration
        ('Kilometers', 'Draaiuren', ...), so matching is case-insensitive:
        an exact name match wins, a substring match ('Draaiuren motor') is the
        fallback, and default template counters win over ad-hoc ones.

        Returns float or None.
        """
        exact, partial = [], []
        for counter in counters or []:
            if not isinstance(counter, dict):
                continue
            name = str(counter.get('CounterName') or '').strip().lower()
            value = counter.get('CounterValue')
            if not name or isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            if name in names:
                exact.append(counter)
            elif any(candidate in name for candidate in names):
                partial.append(counter)
        for bucket in (exact, partial):
            if not bucket:
                continue
            # A default template counter is the one Geodynamics itself shows first.
            bucket.sort(key=lambda c: not c.get('IsDefault'))
            return float(bucket[0]['CounterValue'])
        return None

    def _gd_log_odometer(self, km_value):
        """Log an odometer value (given in km) on fleet.vehicle.odometer.

        - Converts to miles when the vehicle's odometer unit is miles.
        - Updates today's record instead of creating duplicates.
        - Never writes a value lower than the last known odometer log
          (protects against manual corrections in Odoo).

        Returns True when a record was created/updated.
        """
        self.ensure_one()
        if not km_value or km_value <= 0:
            return False
        value = km_value / KM_PER_MILE if self.odometer_unit == 'miles' else km_value
        value = round(value, 2)

        Odometer = self.env['fleet.vehicle.odometer'].sudo()
        today = fields.Date.context_today(self)
        today_rec = Odometer.search([('vehicle_id', '=', self.id), ('date', '=', today)], limit=1)
        if today_rec:
            if value > today_rec.value:
                today_rec.write({'value': value})
                return True
            return False

        last = self._gd_last_odometer_record()
        if last and value <= last.value:
            _logger.info('[Geodynamics] Odometer sync %s: value %.2f <= last logged %.2f, skipping',
                         self.name, value, last.value)
            return False
        Odometer.create({'vehicle_id': self.id, 'date': today, 'value': value})
        return True

    def _gd_last_odometer_record(self):
        """Return the last odometer log with a real (positive) value.

        Zero-value records (e.g. an accidental manual '0,00' entry) are
        ignored: they carry no information and must not block the sync.
        """
        self.ensure_one()
        return self.env['fleet.vehicle.odometer'].sudo().search(
            [('vehicle_id', '=', self.id), ('value', '>', 0)],
            order='date desc, id desc', limit=1)

    def _gd_incremental_km(self, handler):
        """Fallback: derive an odometer value (km) from location/status data.

        Preferred: an absolute odometer counter found on the status Bars
        (matches the vehicle total shown in Geodynamics). Otherwise the km
        driven in the window is added to the last known odometer value.

        Returns a dict:
            {'km': float|None, 'hours': float|None, 'hours_absolute': bool,
             'ok': bool}
        `ok` is False only when the API call failed, so the sync window must
        not be advanced and the period is retried on the next run.
        """
        self.ensure_one()
        now = fields.Datetime.now()
        last = self._gd_last_odometer_record()
        last_km = None
        if last:
            last_km = last.value * KM_PER_MILE if self.odometer_unit == 'miles' else last.value

        if not last:
            # No real odometer value yet: always fetch the initial backfill window
            ICP = self.env['ir.config_parameter'].sudo()
            try:
                days_back = int(ICP.get_param('geodynamics.odometer_days_back', '30'))
            except (ValueError, TypeError):
                days_back = 30
            from_dt = now - timedelta(days=days_back)
        elif self.df_gd_odometer_last_sync:
            from_dt = self.df_gd_odometer_last_sync
        else:
            # Start after the day of the last (manual) log to avoid double counting
            from_dt = datetime.combine(last.date + timedelta(days=1), time.min)

        if from_dt >= now:
            return {'km': None, 'hours': None, 'hours_absolute': False, 'ok': True}

        result = handler.getResourceMileage(self.df_geodynamics_id, from_dt, now)
        if result.get('Error'):
            _logger.warning('[Geodynamics] Odometer sync %s: mileage fetch failed: %s',
                            self.name, result['Error'])
            return {'km': None, 'hours': None, 'hours_absolute': False, 'ok': False}

        # Absolute counters straight from the tracker data win
        odometer_km = result.get('odometer_km')
        abs_hours = result.get('running_hours')
        driven_km = result.get('total_km') or 0.0
        driven_hours = result.get('total_hours') or 0.0

        if odometer_km:
            km = odometer_km
        elif driven_km > 0:
            km = (last_km or 0.0) + driven_km
        else:
            km = None

        if abs_hours:
            return {'km': km, 'hours': abs_hours, 'hours_absolute': True, 'ok': True}
        return {'km': km, 'hours': driven_hours or None, 'hours_absolute': False, 'ok': True}

    def _gd_sync_odometer(self, handler, diagnostics=None):
        """Sync odometer (km) and running hours from Geodynamics for the
        vehicles in `self` that are linked via df_geodynamics_id.

        Sources, in order:
        1. The vehicle counters ('Voertuig tellers') from
           POST /api/v1/vehiclecounters — the same totals Geodynamics shows.
        2. A total km / running-hours counter in the vehicle payload of
           GET /api/v1/vehicle (stored in df_geodynamics_raw).
        3. Incremental MileageDriven from GET /api/v1/location/status.

        `diagnostics` is an optional dict filled with why the vehicle counters did
        not yield a value, so the caller can show it instead of only logging it.

        Returns (logged, skipped, fallback_used).
        """
        if diagnostics is None:
            diagnostics = {}
        vehicles = self.filtered('df_geodynamics_id')
        if not vehicles:
            return 0, 0, 0

        # 1. Vehicle counters: the totals Geodynamics itself shows under
        # 'Voertuig tellers'. One call covers the whole selection.
        counter_map = {}
        counters_result = handler.getVehicleCounters(vehicles.mapped('df_geodynamics_id'))
        if counters_result.get('Error'):
            _logger.warning('[Geodynamics] Odometer sync: getVehicleCounters failed (%s), '
                            'falling back to the vehicle payload and location/status',
                            counters_result['Error'])
            diagnostics['counter_error'] = counters_result['Error']
        else:
            counter_map = counters_result.get('Data') or {}
        km_names = self._gd_counter_names('geodynamics.counter_name_km', GD_COUNTER_KM_NAMES)
        hour_names = self._gd_counter_names('geodynamics.counter_name_hours', GD_COUNTER_HOURS_NAMES)

        gd_map = {}
        result = handler.getVehicles()
        if not result.get('Error'):
            data = result.get('Data', [])
            if isinstance(data, dict):
                data = data.get('Data', [])
            if not isinstance(data, list):
                data = [data]
            gd_map = {v.get('Id'): v for v in data if isinstance(v, dict) and v.get('Id')}
        else:
            _logger.warning('[Geodynamics] Odometer sync: getVehicles failed (%s), '
                            'falling back to location/status only', result.get('Error'))

        logged = skipped = fallback_used = counters_used = 0
        for veh in vehicles:
            now = fields.Datetime.now()
            km = None
            hours = None

            counters = counter_map.get(veh.df_geodynamics_id) or []
            if counters:
                km = self._gd_match_counter(counters, km_names)
                hours = self._gd_match_counter(counters, hour_names)
                if km is None:
                    names = [c.get('CounterName') for c in counters]
                    _logger.info('[Geodynamics] Odometer sync %s: no km counter among the vehicle '
                                 'counters; available names=%s', veh.name, names)
                    diagnostics.setdefault('unmatched', []).append((veh.name, names))
                else:
                    counters_used += 1
            elif 'counter_error' not in diagnostics:
                # The call succeeded but Geodynamics returned no counters for this vehicle.
                _logger.info('[Geodynamics] Odometer sync %s: Geodynamics returned no vehicle '
                             'counters (gd_id=%s)', veh.name, veh.df_geodynamics_id)
                diagnostics.setdefault('no_counters', []).append(veh.name)

            payload = gd_map.get(veh.df_geodynamics_id)
            if payload:
                veh.write({'df_geodynamics_raw': payload, 'df_geodynamics_last_sync': now})
                if km is None:
                    km = self._gd_extract_counter(payload, GD_TOTAL_KM_KEYS)
                if hours is None:
                    hours = self._gd_extract_counter(payload, GD_RUNNING_HOURS_KEYS)
                if km is None:
                    nested = {k: sorted(v.keys()) for k, v in payload.items() if isinstance(v, dict)}
                    _logger.info('[Geodynamics] Odometer sync %s: no total km counter in vehicle payload; '
                                 'top-level keys=%s nested=%s', veh.name, sorted(payload.keys()), nested)

            advance_window = True
            if km is None:
                fallback = veh._gd_incremental_km(handler)
                km = fallback['km']
                advance_window = fallback['ok']
                if km is not None:
                    fallback_used += 1
                if hours is None and fallback['hours']:
                    if fallback['hours_absolute']:
                        hours = fallback['hours']
                    else:
                        hours = (veh.df_gd_running_hours or 0.0) + fallback['hours']

            vals = {}
            if advance_window:
                vals['df_gd_odometer_last_sync'] = now
            if hours is not None:
                vals['df_gd_running_hours'] = round(hours, 2)
            if vals:
                veh.write(vals)

            if km is not None and veh._gd_log_odometer(km):
                logged += 1
                _logger.info('[Geodynamics] Odometer sync %s: logged %.2f km (gd_id=%s)',
                             veh.name, km, veh.df_geodynamics_id)
            else:
                skipped += 1

        _logger.info('[Geodynamics] Odometer sync complete: %d logged, %d skipped, '
                     '%d from vehicle counters, %d via location/status fallback',
                     logged, skipped, counters_used, fallback_used)
        return logged, skipped, fallback_used

    def action_gd_sync_odometer(self):
        """Sync odometer readings from Geodynamics for the selected vehicles."""
        handler = self._gd_get_handler()
        if handler is None:
            return self._gd_notify(
                _('Geodynamics API credentials are not configured. Go to Settings > Geodynamics.'),
                kind='danger')
        vehicles = self or self.search([('df_geodynamics_id', '!=', False)])
        linked = vehicles.filtered('df_geodynamics_id')
        if not linked:
            return self._gd_notify(
                _('None of the selected vehicles are linked to Geodynamics (missing Geodynamics ID).'),
                kind='warning')
        diagnostics = {}
        logged, skipped, fallback_used = linked._gd_sync_odometer(handler, diagnostics)
        message = _('Odometer sync: %d vehicle(s) updated, %d unchanged (%d computed from trip data).') \
            % (logged, skipped, fallback_used)

        # Without this the notification looks identical whether the counters were
        # read fine or the call was rejected, which makes the sync impossible to
        # diagnose from the interface.
        details = []
        if diagnostics.get('counter_error'):
            details.append(_('Vehicle counters could not be read: %s') % diagnostics['counter_error'])
        for name, counter_names in diagnostics.get('unmatched', []):
            details.append(_('%s: no kilometre counter matched. Counters in Geodynamics: %s')
                           % (name, ', '.join(str(n) for n in counter_names) or _('(none)')))
        if diagnostics.get('no_counters'):
            details.append(_('Geodynamics returned no counters for: %s')
                           % ', '.join(diagnostics['no_counters']))
        if details:
            message = '%s\n\n%s' % (message, '\n'.join(details))

        result = self._gd_notify(message, kind='warning' if details else 'success',
                                 title=_('Geodynamics Odometer Sync'))
        result['params']['sticky'] = bool(details)
        return result

    def action_gd_probe_counters(self):
        """Diagnostic: show the counters Geodynamics returns for this vehicle.

        Reports the counter names and values behind the odometer sync, or the
        reason the API did not return them. The full request/response is stored
        in the API log (Settings > Geodynamics).
        """
        self.ensure_one()
        handler = self._gd_get_handler()
        if handler is None:
            return self._gd_notify(
                _('Geodynamics API credentials are not configured. Go to Settings > Geodynamics.'),
                kind='danger')
        if not self.df_geodynamics_id:
            return self._gd_notify(_('This vehicle has no Geodynamics ID.'), kind='warning')

        result = handler.getVehicleCounters([self.df_geodynamics_id])
        if result.get('Error'):
            message = _('Vehicle counters could not be read: %s') % result['Error']
            kind = 'danger'
        else:
            counters = (result.get('Data') or {}).get(self.df_geodynamics_id) or []
            if not counters:
                message = _('Geodynamics returned no counters for this vehicle.')
                kind = 'warning'
            else:
                km = self._gd_match_counter(
                    counters, self._gd_counter_names('geodynamics.counter_name_km', GD_COUNTER_KM_NAMES))
                hours = self._gd_match_counter(
                    counters, self._gd_counter_names('geodynamics.counter_name_hours', GD_COUNTER_HOURS_NAMES))
                listing = ', '.join('%s = %s' % (c.get('CounterName'), c.get('CounterValue'))
                                    for c in counters)
                message = _('Counters in Geodynamics: %s.') % listing
                message += '\n'
                message += (_('Odometer: %s km.') % km) if km is not None \
                    else _('No counter matched as kilometres.')
                message += ' '
                message += (_('Running hours: %s.') % hours) if hours is not None \
                    else _('No counter matched as running hours.')
                kind = 'success' if km is not None else 'warning'

        params = self._gd_notify(message, kind=kind, title=_('Geodynamics Vehicle Counters'))
        params['params']['sticky'] = True
        return params

    @api.model
    def cron_gd_sync_odometer(self):
        """Daily cron: sync odometers for all linked vehicles.

        Only runs when 'Odometer Sync' is enabled in Settings
        (geodynamics.auto_sync_odometer).
        """
        ICP = self.env['ir.config_parameter'].sudo()
        if ICP.get_param('geodynamics.auto_sync_odometer', 'False').lower() not in ('true', '1', 'yes'):
            _logger.info('[Geodynamics] Odometer sync cron skipped: disabled in settings')
            return
        handler = self._gd_get_handler()
        if handler is None:
            _logger.warning('[Geodynamics] Odometer sync cron skipped: credentials not configured')
            return
        vehicles = self.search([('df_geodynamics_id', '!=', False)])
        vehicles._gd_sync_odometer(handler)

    def action_gd_export_to_geodynamics(self):
        """Export selected fleet vehicles to Geodynamics."""
        handler = self._gd_get_handler()
        if handler is None:
            return self._gd_notify(
                _('Geodynamics API credentials are not configured. Go to Settings > Geodynamics.'),
                kind='danger')

        ICP = self.env['ir.config_parameter'].sudo()
        match_by_plate = ICP.get_param(
            'geodynamics.match_fleet_by_plate', 'True').lower() in ('true', '1', 'yes')

        # Fetch GD vehicles for plate matching
        gd_vehicles = []
        if match_by_plate:
            result = handler.getVehicles()
            if not result.get('Error'):
                gd_vehicles = result.get('Data', [])
                if isinstance(gd_vehicles, dict):
                    gd_vehicles = gd_vehicles.get('Data', [])
                if not isinstance(gd_vehicles, list):
                    gd_vehicles = [gd_vehicles]

        export_scope = self
        _logger.info('[Geodynamics] Fleet vehicle export: %d selected', len(export_scope))

        # Match unlinked by license plate
        matched = 0
        if match_by_plate:
            for veh in export_scope.filtered(lambda v: not v.df_geodynamics_id):
                plate = (veh.license_plate or '').strip().upper().replace('-', '').replace(' ', '')
                if not plate:
                    continue
                for gd_veh in gd_vehicles:
                    gd_plate = (gd_veh.get('LicensePlate') or '').strip().upper().replace('-', '').replace(' ', '')
                    if gd_plate and gd_plate == plate:
                        veh.write({
                            'df_geodynamics_id': gd_veh.get('Id'),
                            'df_geodynamics_last_sync': fields.Datetime.now(),
                            'df_geodynamics_raw': gd_veh,
                        })
                        matched += 1
                        _logger.info('[Geodynamics] Fleet export: matched %s by plate=%s to gd_id=%s',
                                     veh.name, plate, gd_veh.get('Id'))
                        break

        # Update linked vehicles
        exported = 0
        for veh in export_scope.filtered(lambda v: v.df_geodynamics_id):
            vehicle_data = {
                'Id': veh.df_geodynamics_id,
                'Name': veh.name,
                'LicensePlate': veh.license_plate or '',
            }
            handler.updateVehicle(vehicle_data)
            exported += 1
            _logger.info('[Geodynamics] Fleet export: updated %s (gd_id=%s)', veh.name, veh.df_geodynamics_id)

        # Create new vehicles in GD
        gd_created = 0
        for veh in export_scope.filtered(lambda v: not v.df_geodynamics_id):
            vehicle_data = {
                'Name': veh.name,
                'LicensePlate': veh.license_plate or '',
            }
            _logger.info('[Geodynamics] Fleet export: creating GD vehicle for %s', veh.name)
            result = handler.createVehicle(vehicle_data)
            if result.get('Success') and result.get('Data'):
                gd_data = result['Data']
                new_gd_id = gd_data.get('Id') if isinstance(gd_data, dict) else None
                if new_gd_id:
                    veh.write({
                        'df_geodynamics_id': new_gd_id,
                        'df_geodynamics_last_sync': fields.Datetime.now(),
                        'df_geodynamics_raw': gd_data,
                    })
                    _logger.info('[Geodynamics] Fleet export: created %s with gd_id=%s', veh.name, new_gd_id)
                gd_created += 1
            else:
                _logger.warning('[Geodynamics] Fleet export: FAILED for %s: %s', veh.name, result)

        _logger.info('[Geodynamics] Fleet export complete: %d matched, %d updated, %d created', matched, exported, gd_created)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Geodynamics Fleet Export'),
                'type': 'success',
                'message': _('Fleet exported: %d matched by plate, %d updated, %d created in Geodynamics.') % (matched, exported, gd_created),
                'sticky': False,
            },
        }
