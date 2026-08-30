# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from ..models.gdhandler import GeodynamicsHandler
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class GeodynamicsImportWizard(models.TransientModel):
    _name = 'df.geodynamics.import.wizard'
    _description = 'Geodynamics Import/Export Wizard'

    df_import_type = fields.Selection([
        ('employees', 'Employees'),
        ('fleet', 'Fleet / Vehicles'),
        ('pois', 'Points of Interest'),
        ('checkins', 'Checkin at Work'),
    ], string='Import Type', required=True, default='employees')

    df_direction = fields.Selection([
        ('import', 'Import from Geodynamics'),
        ('export', 'Export to Geodynamics'),
        ('sync', 'Bidirectional Sync'),
    ], string='Direction', required=True, default='import')

    df_match_by_email = fields.Boolean(string='Match by Email', default=True)

    df_date_from = fields.Date(string='Date From', default=lambda self: fields.Date.today())
    df_date_to = fields.Date(string='Date To', default=lambda self: fields.Date.today())

    def _get_handler(self):
        company = self.env['ir.config_parameter'].sudo().get_param('geodynamics.company')
        login = self.env['ir.config_parameter'].sudo().get_param('geodynamics.username')
        password = self.env['ir.config_parameter'].sudo().get_param('geodynamics.password')
        if not all([company, login, password]):
            raise UserError(_('Geodynamics API credentials are not configured. Go to Settings > Geodynamics.'))
        return GeodynamicsHandler(login, password, company, self.env)

    def action_execute(self):
        self.ensure_one()
        if self.df_import_type == 'employees':
            return self._sync_employees()
        elif self.df_import_type == 'fleet':
            return self._import_fleet()
        elif self.df_import_type == 'pois':
            return self._import_pois()
        elif self.df_import_type == 'checkins':
            return self._import_checkins()

    def _notify(self, message, msg_type='success'):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Geodynamics Import'),
                'type': msg_type,
                'message': message,
                'sticky': False,
            },
        }

    def _sync_employees(self, employee_ids=None):
        _logger.info('[Geodynamics] ===== EMPLOYEE SYNC STARTED (direction=%s, selected=%s) =====',
                     self.df_direction, len(employee_ids) if employee_ids else 'ALL')
        handler = self._get_handler()
        result = handler.getUsers()
        _logger.info('[Geodynamics] getUsers result keys: %s', list(result.keys()))
        if 'Error' in result:
            _logger.error('[Geodynamics] Employee import failed: %s', result['Error'])
            return self._notify(result['Error'], 'danger')

        gd_users = result.get('Data', [])
        _logger.info('[Geodynamics] result.get("Data") type=%s', type(gd_users).__name__)
        if isinstance(gd_users, dict):
            _logger.info('[Geodynamics] Data is a dict with keys=%s — unwrapping nested Data list', list(gd_users.keys()))
            gd_users = gd_users.get('Data', [])
            _logger.info('[Geodynamics] After unwrap: type=%s, len=%s', type(gd_users).__name__, len(gd_users) if isinstance(gd_users, list) else 'N/A')
        if not isinstance(gd_users, list):
            _logger.warning('[Geodynamics] gd_users is not a list (type=%s), wrapping in list', type(gd_users).__name__)
            gd_users = [gd_users]

        _logger.info('[Geodynamics] Total users from API: %d', len(gd_users))
        for i, u in enumerate(gd_users):
            if isinstance(u, dict):
                _logger.info('[Geodynamics]   API user %d: Id=%s, Name=%r, Email=%r', i + 1, u.get('Id'), u.get('Name'), u.get('Email'))
            else:
                _logger.warning('[Geodynamics]   API user %d: unexpected type %s — value: %s', i + 1, type(u).__name__, u)

        created = 0
        updated = 0
        Employee = self.env['hr.employee'].sudo()

        # Log existing employees for debugging
        all_employees = Employee.search([])
        _logger.info('[Geodynamics] Existing employees in Odoo: %d', len(all_employees))
        for emp in all_employees:
            _logger.info('[Geodynamics]   Odoo employee: id=%d, name=%r, work_email=%r, private_email=%r, gd_id=%s, user_email=%r',
                         emp.id, emp.name, emp.work_email or '', emp.private_email or '',
                         emp.df_geodynamics_id or 'None',
                         emp.user_id.email if emp.user_id else '')

        for idx, gd_user in enumerate(gd_users):
            if not isinstance(gd_user, dict):
                _logger.warning('[Geodynamics] Skipping user %d: not a dict (type=%s)', idx + 1, type(gd_user).__name__)
                continue

            gd_id = gd_user.get('Id')
            email = gd_user.get('Email', '').strip().lower() if gd_user.get('Email') else ''
            raw_name = gd_user.get('Name')
            raw_first = gd_user.get('FirstName')
            raw_last = gd_user.get('LastName')
            name = raw_name or (raw_first or '') + ' ' + (raw_last or '')
            _logger.info('[Geodynamics] --- Processing user %d/%d: Id=%s, Name=%r, Email=%r, resolved_name=%r ---',
                         idx + 1, len(gd_users), gd_id, raw_name, email, name.strip())

            # Try to match existing employee
            employee = False
            if gd_id:
                employee = Employee.search([('df_geodynamics_id', '=', gd_id)], limit=1)
                _logger.info('[Geodynamics] User %d: search by gd_id=%s -> %s',
                             idx + 1, gd_id, '%s (id=%d)' % (employee.name, employee.id) if employee else 'NO MATCH')
            if not employee and self.df_match_by_email and email:
                # Match by work_email or private email or linked user email
                employee = Employee.search([
                    '|', '|',
                    ('work_email', '=ilike', email),
                    ('private_email', '=ilike', email),
                    ('user_id.email', '=ilike', email),
                ], limit=1)
                _logger.info('[Geodynamics] User %d: search by email=%s -> %s',
                             idx + 1, email, '%s (id=%d)' % (employee.name, employee.id) if employee else 'NO MATCH')
            elif not employee and not self.df_match_by_email and email:
                _logger.info('[Geodynamics] User %d: email matching disabled, skipping email search for %s', idx + 1, email)

            if not employee and not email:
                _logger.info('[Geodynamics] User %d: no gd_id match and no email to search by', idx + 1)

            if employee:
                vals = {
                    'df_geodynamics_id': gd_id,
                    'df_geodynamics_last_sync': fields.Datetime.now(),
                    'df_geodynamics_raw': gd_user,
                }
                if not employee.work_email and email:
                    vals['work_email'] = email
                employee.write(vals)
                updated += 1
                _logger.info('[Geodynamics] User %d: UPDATED existing employee %s (id=%d)', idx + 1, employee.name, employee.id)
            else:
                final_name = name.strip() or f'GD User {gd_id}'
                vals = {
                    'name': final_name,
                    'df_geodynamics_id': gd_id,
                    'df_geodynamics_last_sync': fields.Datetime.now(),
                    'df_geodynamics_raw': gd_user,
                }
                if email:
                    vals['work_email'] = email
                _logger.info('[Geodynamics] User %d: CREATING new employee with vals=%s', idx + 1, vals)
                Employee.create(vals)
                created += 1

        _logger.info('[Geodynamics] ===== IMPORT COMPLETE: %d created, %d updated, %d from API =====', created, updated, len(gd_users))

        # Export: push employees with GD IDs to Geodynamics
        if self.df_direction in ('export', 'sync'):
            # When called with specific employees, only export those
            if employee_ids:
                export_scope = employee_ids
                _logger.info('[Geodynamics] Export: scoped to %d selected employees: %s',
                             len(export_scope), export_scope.mapped('name'))
            else:
                export_scope = Employee.search([])
                _logger.info('[Geodynamics] Export: all %d employees', len(export_scope))

            # First, match unlinked employees by email against Geodynamics users
            matched = 0
            unlinked = export_scope.filtered(lambda e: not e.df_geodynamics_id)
            if not self.df_match_by_email:
                _logger.info('[Geodynamics] Export: email matching disabled, skipping email match for %d unlinked employees', len(unlinked))
                unlinked = Employee  # empty recordset, skip the loop
            for emp in unlinked:
                emp_emails = [e.strip().lower() for e in [
                    emp.work_email or '',
                    emp.private_email or '',
                    emp.user_id.email if emp.user_id else '',
                ] if e and e.strip()]
                if not emp_emails:
                    continue
                for gd_user in gd_users:
                    gd_email = (gd_user.get('Email') or '').strip().lower()
                    if gd_email and gd_email in emp_emails:
                        emp.write({
                            'df_geodynamics_id': gd_user.get('Id'),
                            'df_geodynamics_last_sync': fields.Datetime.now(),
                            'df_geodynamics_raw': gd_user,
                        })
                        if not emp.work_email:
                            emp.work_email = gd_email
                        matched += 1
                        _logger.info('[Geodynamics] Export: matched unlinked employee %s (id=%d) to GD user by email=%s',
                                     emp.name, emp.id, gd_email)
                        break

            # Update existing linked employees in Geodynamics
            exported = 0
            for emp in export_scope.filtered(lambda e: e.df_geodynamics_id):
                user_data = {
                    'Id': emp.df_geodynamics_id,
                    'Name': emp.name,
                    'Email': emp.work_email or '',
                }
                handler.updateUser(user_data)
                exported += 1
                _logger.info('[Geodynamics] Export: updated employee %s (id=%d, gd_id=%s)', emp.name, emp.id, emp.df_geodynamics_id)

            # Create new users in Geodynamics for employees that are still unlinked
            gd_created = 0
            still_unlinked = export_scope.filtered(lambda e: not e.df_geodynamics_id)
            _logger.info('[Geodynamics] Export: %d employees still without Geodynamics ID, will create in GD', len(still_unlinked))
            for emp in still_unlinked:
                user_data = {
                    'Name': emp.name,
                    'Email': emp.work_email or '',
                }
                _logger.info('[Geodynamics] Export: creating new GD user for employee %s (id=%d), data=%s', emp.name, emp.id, user_data)
                result = handler.createUser(user_data)
                _logger.info('[Geodynamics] Export: createUser response for %s: keys=%s, data=%s',
                             emp.name, list(result.keys()), result)
                if result.get('Success') and result.get('Data'):
                    gd_data = result['Data']
                    # Handle nested response: API may return {"PagingFilter":..., "Data": {...}} or just the user dict
                    if isinstance(gd_data, dict) and 'Data' in gd_data and 'Id' not in gd_data:
                        gd_data = gd_data['Data']
                        _logger.info('[Geodynamics] Export: unwrapped nested Data for %s: %s', emp.name, gd_data)
                    # Handle list response
                    if isinstance(gd_data, list) and gd_data:
                        gd_data = gd_data[0]
                        _logger.info('[Geodynamics] Export: took first item from list for %s: %s', emp.name, gd_data)
                    new_gd_id = gd_data.get('Id') if isinstance(gd_data, dict) else None
                    if new_gd_id:
                        emp.write({
                            'df_geodynamics_id': new_gd_id,
                            'df_geodynamics_last_sync': fields.Datetime.now(),
                            'df_geodynamics_raw': gd_data,
                        })
                        _logger.info('[Geodynamics] Export: created GD user for %s with gd_id=%s', emp.name, new_gd_id)
                    else:
                        _logger.warning('[Geodynamics] Export: created GD user for %s but no Id in response. gd_data type=%s, value=%s',
                                        emp.name, type(gd_data).__name__, gd_data)
                    gd_created += 1
                elif result.get('Error'):
                    _logger.warning('[Geodynamics] Export: FAILED to create GD user for %s: %s', emp.name, result['Error'])
                else:
                    _logger.warning('[Geodynamics] Export: FAILED to create GD user for %s: %s', emp.name, result)

            _logger.info('[Geodynamics] ===== EXPORT COMPLETE: %d matched by email, %d updated, %d created in GD =====', matched, exported, gd_created)
            return self._notify(
                _('Employees synced: %d imported, %d updated, %d matched by email, %d exported, %d created in Geodynamics.') % (created, updated, matched, exported, gd_created))

        return self._notify(_('Employees imported: %d created, %d updated.') % (created, updated))

    def _import_fleet(self):
        _logger.info('[Geodynamics] ===== FLEET IMPORT STARTED =====')
        handler = self._get_handler()
        result = handler.getVehicles()
        _logger.info('[Geodynamics] getVehicles result keys: %s', list(result.keys()))
        if 'Error' in result:
            _logger.error('[Geodynamics] Fleet import failed: %s', result['Error'])
            return self._notify(result['Error'], 'danger')

        vehicles = result.get('Data', [])
        _logger.info('[Geodynamics] Fleet import: result.get("Data") type=%s', type(vehicles).__name__)
        # API may return a flat list or a dict with nested Data
        if isinstance(vehicles, dict):
            _logger.info('[Geodynamics] Fleet import: Data is a dict with keys=%s — unwrapping', list(vehicles.keys()))
            vehicles = vehicles.get('Data', [])
            _logger.info('[Geodynamics] Fleet import: after unwrap type=%s', type(vehicles).__name__)
        if not isinstance(vehicles, list):
            _logger.warning('[Geodynamics] Fleet import: vehicles is not a list (type=%s), wrapping', type(vehicles).__name__)
            vehicles = [vehicles]

        _logger.info('[Geodynamics] Fleet import: %d vehicle(s) from API', len(vehicles))
        for i, v in enumerate(vehicles):
            if isinstance(v, dict):
                _logger.info('[Geodynamics]   API vehicle %d: Id=%s, Name=%r, LicensePlate=%r, Code=%r',
                             i + 1, v.get('Id'), v.get('Name'), v.get('LicensePlate'), v.get('Code'))
            else:
                _logger.warning('[Geodynamics]   API vehicle %d: unexpected type %s — value: %s', i + 1, type(v).__name__, v)

        # Import into df.geodynamics.vehicle
        GdVehicle = self.env['df.geodynamics.vehicle'].sudo()
        created = 0
        updated = 0
        fleet_created = 0

        # Also import into fleet.vehicle if fleet module is installed
        FleetVehicle = None
        try:
            FleetVehicle = self.env['fleet.vehicle'].sudo()
            _logger.info('[Geodynamics] Fleet import: fleet.vehicle model available')
        except Exception:
            _logger.info('[Geodynamics] Fleet import: fleet.vehicle model not available, skipping fleet import')

        for idx, v in enumerate(vehicles):
            if not isinstance(v, dict):
                _logger.warning('[Geodynamics] Fleet import: skipping vehicle %d: not a dict', idx + 1)
                continue

            gd_id = v.get('Id', '')
            name = v.get('Name', '')
            code = (v.get('Code') or '').strip() or None
            license_plate = v.get('LicensePlate') or ''

            _logger.info('[Geodynamics] --- Processing vehicle %d/%d: Id=%s, Name=%r, Plate=%r, Code=%r ---',
                         idx + 1, len(vehicles), gd_id, name, license_plate, code)

            if not gd_id:
                _logger.warning('[Geodynamics] Fleet import: skipping vehicle without Id')
                continue

            # Import into df.geodynamics.vehicle
            existing = GdVehicle.search([('df_geodynamics_id', '=', gd_id)], limit=1)
            if not existing and code:
                existing = GdVehicle.search([('df_code', '=', code)], limit=1)
            _logger.info('[Geodynamics] Vehicle %d: GD vehicle search -> %s',
                         idx + 1, '%s (id=%d)' % (existing.df_name, existing.id) if existing else 'NO MATCH')

            vals = {
                'df_name': name or code or gd_id,
                'df_code': code,
                'df_license_plate': license_plate,
                'df_brand': v.get('Brand', ''),
                'df_model_name': v.get('Model', ''),
                'df_vehicle_type': str(v.get('Category', '')),
                'df_geodynamics_id': gd_id,
                'df_raw_payload': v,
                'df_last_sync_date': fields.Datetime.now(),
            }
            if existing:
                existing.write(vals)
                updated += 1
                _logger.info('[Geodynamics] Vehicle %d: UPDATED GD vehicle %s (id=%d)', idx + 1, name, existing.id)
            else:
                GdVehicle.create(vals)
                created += 1
                _logger.info('[Geodynamics] Vehicle %d: CREATED GD vehicle %s', idx + 1, name)

            # Also sync to fleet.vehicle
            if FleetVehicle is not None:
                fleet_veh = FleetVehicle.search([('df_geodynamics_id', '=', gd_id)], limit=1)
                if not fleet_veh and license_plate:
                    fleet_veh = FleetVehicle.search([('license_plate', '=ilike', license_plate)], limit=1)
                _logger.info('[Geodynamics] Vehicle %d: fleet.vehicle search -> %s',
                             idx + 1, '%s (id=%d)' % (fleet_veh.name, fleet_veh.id) if fleet_veh else 'NO MATCH')
                if fleet_veh:
                    fleet_veh.write({
                        'df_geodynamics_id': gd_id,
                        'df_geodynamics_last_sync': fields.Datetime.now(),
                        'df_geodynamics_raw': v,
                    })
                    _logger.info('[Geodynamics] Vehicle %d: UPDATED fleet.vehicle %s (id=%d)', idx + 1, fleet_veh.name, fleet_veh.id)
                else:
                    # Create new fleet.vehicle — need a model_id (required field)
                    try:
                        FleetModel = self.env['fleet.vehicle.model'].sudo()
                        FleetBrand = self.env['fleet.vehicle.model.brand'].sudo()

                        # Find or create a brand and model from the GD vehicle name
                        gd_brand_name = 'Geodynamics'
                        gd_model_name = name or gd_id
                        brand = FleetBrand.search([('name', '=ilike', gd_brand_name)], limit=1)
                        if not brand:
                            brand = FleetBrand.create({'name': gd_brand_name})
                        fleet_model = FleetModel.search([('name', '=ilike', gd_model_name), ('brand_id', '=', brand.id)], limit=1)
                        if not fleet_model:
                            fleet_model = FleetModel.create({'name': gd_model_name, 'brand_id': brand.id})

                        fleet_vals = {
                            'model_id': fleet_model.id,
                            'license_plate': license_plate or False,
                            'df_geodynamics_id': gd_id,
                            'df_geodynamics_last_sync': fields.Datetime.now(),
                            'df_geodynamics_raw': v,
                        }
                        new_fleet_veh = FleetVehicle.create(fleet_vals)
                        fleet_created += 1
                        _logger.info('[Geodynamics] Vehicle %d: CREATED fleet.vehicle %s (id=%d, model=%s)',
                                     idx + 1, new_fleet_veh.name, new_fleet_veh.id, fleet_model.name)
                    except Exception as e:
                        _logger.warning('[Geodynamics] Vehicle %d: FAILED to create fleet.vehicle for %s: %s', idx + 1, name, e)

        _logger.info('[Geodynamics] ===== FLEET IMPORT COMPLETE: %d created, %d updated in GD vehicles, %d created in fleet =====', created, updated, fleet_created)
        return self._notify(_('Fleet imported: %d created, %d updated, %d fleet vehicles created.') % (created, updated, fleet_created))

    def _export_fleet(self, vehicle_ids=None):
        """Export vehicles to Geodynamics.

        vehicle_ids can be fleet.vehicle or df.geodynamics.vehicle recordsets.
        When called from Settings (no vehicle_ids), exports fleet.vehicle records.
        """
        _logger.info('[Geodynamics] ===== FLEET EXPORT STARTED =====')
        handler = self._get_handler()
        match_by_plate = self.env['ir.config_parameter'].sudo().get_param(
            'geodynamics.match_fleet_by_plate', 'True').lower() in ('true', '1', 'yes')

        FleetVehicle = self.env['fleet.vehicle'].sudo()

        # Fetch GD vehicles for matching
        gd_vehicles = []
        if match_by_plate:
            result = handler.getVehicles()
            if not result.get('Error'):
                gd_vehicles = result.get('Data', [])
                if isinstance(gd_vehicles, dict):
                    gd_vehicles = gd_vehicles.get('Data', [])
                if not isinstance(gd_vehicles, list):
                    gd_vehicles = [gd_vehicles]
            _logger.info('[Geodynamics] Fleet export: fetched %d GD vehicles for license plate matching', len(gd_vehicles))

        # Determine scope — always work with fleet.vehicle
        if vehicle_ids and vehicle_ids._name == 'fleet.vehicle':
            export_scope = vehicle_ids
            _logger.info('[Geodynamics] Fleet export: scoped to %d selected fleet vehicles', len(export_scope))
        elif vehicle_ids and vehicle_ids._name == 'df.geodynamics.vehicle':
            export_scope = vehicle_ids
            _logger.info('[Geodynamics] Fleet export: scoped to %d selected GD vehicles', len(export_scope))
        else:
            export_scope = FleetVehicle.search([])
            _logger.info('[Geodynamics] Fleet export: all %d fleet vehicles', len(export_scope))

        is_fleet = export_scope._name == 'fleet.vehicle' if export_scope else True

        # Helper to get fields from either model
        def _get_name(veh):
            return veh.name if is_fleet else veh.df_name
        def _get_plate(veh):
            return veh.license_plate if is_fleet else (veh.df_license_plate or '')
        def _get_gd_id(veh):
            return veh.df_geodynamics_id

        for veh in export_scope:
            _logger.info('[Geodynamics] Fleet export: vehicle %s, name=%r, plate=%r, gd_id=%s',
                         veh._name, _get_name(veh), _get_plate(veh), _get_gd_id(veh) or 'None')

        # Match unlinked vehicles by license plate
        matched = 0
        if match_by_plate:
            for veh in export_scope.filtered(lambda v: not v.df_geodynamics_id):
                plate = (_get_plate(veh) or '').strip().upper().replace('-', '').replace(' ', '')
                if not plate:
                    continue
                for gd_veh in gd_vehicles:
                    gd_plate = (gd_veh.get('LicensePlate') or '').strip().upper().replace('-', '').replace(' ', '')
                    if gd_plate and gd_plate == plate:
                        veh.write({
                            'df_geodynamics_id': gd_veh.get('Id'),
                        })
                        if is_fleet:
                            veh.write({
                                'df_geodynamics_last_sync': fields.Datetime.now(),
                                'df_geodynamics_raw': gd_veh,
                            })
                        else:
                            veh.write({
                                'df_last_sync_date': fields.Datetime.now(),
                                'df_raw_payload': gd_veh,
                            })
                        matched += 1
                        _logger.info('[Geodynamics] Fleet export: matched %s by plate=%s to gd_id=%s',
                                     _get_name(veh), plate, gd_veh.get('Id'))
                        break

        # Update existing linked vehicles
        exported = 0
        for veh in export_scope.filtered(lambda v: v.df_geodynamics_id):
            vehicle_data = {
                'Id': veh.df_geodynamics_id,
                'Name': _get_name(veh),
                'LicensePlate': _get_plate(veh) or '',
            }
            handler.updateVehicle(vehicle_data)
            exported += 1
            _logger.info('[Geodynamics] Fleet export: updated %s (gd_id=%s)', _get_name(veh), veh.df_geodynamics_id)

        # Create new vehicles in Geodynamics for unlinked ones
        gd_created = 0
        for veh in export_scope.filtered(lambda v: not v.df_geodynamics_id):
            vehicle_data = {
                'Name': _get_name(veh),
                'LicensePlate': _get_plate(veh) or '',
            }
            _logger.info('[Geodynamics] Fleet export: creating GD vehicle for %s, data=%s', _get_name(veh), vehicle_data)
            result = handler.createVehicle(vehicle_data)
            _logger.info('[Geodynamics] Fleet export: createVehicle response: %s', result)
            if result.get('Success') and result.get('Data'):
                gd_data = result['Data']
                new_gd_id = gd_data.get('Id') if isinstance(gd_data, dict) else None
                if new_gd_id:
                    write_vals = {'df_geodynamics_id': new_gd_id}
                    if is_fleet:
                        write_vals.update({
                            'df_geodynamics_last_sync': fields.Datetime.now(),
                            'df_geodynamics_raw': gd_data,
                        })
                    else:
                        write_vals.update({
                            'df_last_sync_date': fields.Datetime.now(),
                            'df_raw_payload': gd_data,
                        })
                    veh.write(write_vals)
                    _logger.info('[Geodynamics] Fleet export: created %s with gd_id=%s', _get_name(veh), new_gd_id)
                gd_created += 1
            else:
                _logger.warning('[Geodynamics] Fleet export: FAILED for %s: %s', _get_name(veh), result)

        _logger.info('[Geodynamics] ===== FLEET EXPORT COMPLETE: %d matched, %d updated, %d created =====', matched, exported, gd_created)
        return self._notify(
            _('Fleet exported: %d matched by plate, %d updated, %d created in Geodynamics.') % (matched, exported, gd_created))

    def _import_pois(self):
        _logger.info('[Geodynamics] ===== POI IMPORT STARTED =====')
        handler = self._get_handler()
        result = handler.getPois()
        if 'Error' in result:
            _logger.error('[Geodynamics] POI import failed: %s', result['Error'])
            return self._notify(result['Error'], 'danger')

        pois = result.get('Data', [])
        # Handle wrapped response
        if isinstance(pois, dict):
            _logger.info('[Geodynamics] POI import: Data is dict with keys=%s, unwrapping', list(pois.keys()))
            pois = pois.get('Data', [])
        if not isinstance(pois, list):
            pois = [pois]

        _logger.info('[Geodynamics] POI import: %d POI(s) from API', len(pois))
        for i, p in enumerate(pois):
            if isinstance(p, dict):
                _logger.info('[Geodynamics]   API POI %d: Id=%s, Name=%r, Street=%r, City=%r',
                             i + 1, p.get('Id'), p.get('Name'), p.get('Street'), p.get('City'))

        Partner = self.env['res.partner'].sudo()
        created = 0
        updated = 0

        for idx, poi in enumerate(pois):
            if not isinstance(poi, dict):
                continue

            poi_id = poi.get('Id', '')
            poi_name = poi.get('Name', '')

            if not poi_id:
                _logger.warning('[Geodynamics] POI %d: skipping, no Id', idx + 1)
                continue

            _logger.info('[Geodynamics] --- Processing POI %d/%d: Id=%s, Name=%r ---', idx + 1, len(pois), poi_id, poi_name)

            # Try to match by POI ID first, then by name
            partner = Partner.search([('df_geodynamics_poi_id', '=', poi_id)], limit=1)
            if not partner and poi_name:
                partner = Partner.search([('name', '=ilike', poi_name)], limit=1)
            _logger.info('[Geodynamics] POI %d: partner search -> %s',
                         idx + 1, '%s (id=%d)' % (partner.name, partner.id) if partner else 'NO MATCH')

            # Extract POI data — API uses MarkerLat/MarkerLon for coordinates
            lat = poi.get('MarkerLat') or poi.get('Latitude') or poi.get('Lat') or 0.0
            lng = poi.get('MarkerLon') or poi.get('Longitude') or poi.get('Lng') or poi.get('Lon') or 0.0
            poi_type = ''
            if isinstance(poi.get('PoiType'), dict):
                poi_type = poi['PoiType'].get('Name', '')
            elif poi.get('PoiType'):
                poi_type = str(poi['PoiType'])

            # Build address fields
            street_parts = []
            if poi.get('Street'):
                street_parts.append(poi['Street'])
            if poi.get('HouseNumber'):
                street_parts.append(str(poi['HouseNumber']))
            street = ' '.join(street_parts) if street_parts else False
            city = poi.get('City') or False
            zip_code = poi.get('PostalCode') or poi.get('ZipCode') or False

            poi_vals = {
                'df_geodynamics_poi_id': poi_id,
                'df_geodynamics_poi_name': poi_name,
                'df_geodynamics_poi_type': poi_type,
                'partner_latitude': float(lat) if lat else 0.0,
                'partner_longitude': float(lng) if lng else 0.0,
                'df_geodynamics_poi_raw': poi,
                'df_geodynamics_poi_last_sync': fields.Datetime.now(),
            }

            if partner:
                partner.write(poi_vals)
                # Update address fields only if they're empty on the partner
                if street and not partner.street:
                    partner.street = street
                if city and not partner.city:
                    partner.city = city
                if zip_code and not partner.zip:
                    partner.zip = zip_code
                updated += 1
                _logger.info('[Geodynamics] POI %d: UPDATED partner %s (id=%d)', idx + 1, partner.name, partner.id)
            else:
                # Create new partner from POI
                create_vals = poi_vals.copy()
                create_vals['name'] = poi_name or poi_id
                create_vals['is_company'] = True
                if street:
                    create_vals['street'] = street
                if city:
                    create_vals['city'] = city
                if zip_code:
                    create_vals['zip'] = zip_code
                new_partner = Partner.create(create_vals)
                created += 1
                _logger.info('[Geodynamics] POI %d: CREATED partner %s (id=%d)', idx + 1, new_partner.name, new_partner.id)

        _logger.info('[Geodynamics] ===== POI IMPORT COMPLETE: %d created, %d updated =====', created, updated)
        return self._notify(_('POIs imported: %d created, %d updated.') % (created, updated))

    def _import_checkins(self):
        handler = self._get_handler()
        employees = self.env['hr.employee'].sudo().search([('df_geodynamics_id', '!=', False)])
        Checkin = self.env['df.geodynamics.checkin'].sudo()

        from_dt = datetime.combine(self.df_date_from, datetime.min.time())
        to_dt = datetime.combine(self.df_date_to, datetime.max.time().replace(microsecond=0))

        created = 0
        for emp in employees:
            result = handler.getCheckins(emp.df_geodynamics_id, from_dt, to_dt)
            if 'Error' in result:
                continue
            checkins = result.get('Data', [])
            for ci in checkins:
                start_raw = ci.get('start', {})
                gd_id = start_raw.get('Id', '')
                if gd_id and Checkin.search([('df_geodynamics_id', '=', gd_id)], limit=1):
                    continue

                pois = ci.get('pois')
                site_name = ''
                site_address = ''
                if isinstance(pois, list) and pois:
                    first_poi = pois[0] if isinstance(pois[0], dict) else {}
                    site_name = first_poi.get('Name', '')
                    site_address = first_poi.get('Street', '')

                start_time = handler._parse_input_dt(ci.get('start_time')) if ci.get('start_time') else False
                stop_time = handler._parse_input_dt(ci.get('stop_time')) if ci.get('stop_time') else False

                vals = {
                    'df_employee_id': emp.id,
                    'df_checkin_time': start_time,
                    'df_checkout_time': stop_time,
                    'df_construction_site': site_name,
                    'df_site_address': site_address,
                    'df_geodynamics_id': gd_id or False,
                    'df_status': 'checked_out' if stop_time else 'checked_in',
                    'df_raw_payload': ci,
                }
                Checkin.create(vals)
                created += 1

        return self._notify(_('Checkins imported: %d records created.') % created)
