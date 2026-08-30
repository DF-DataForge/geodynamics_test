# -*- coding: utf-8 -*-
# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
from odoo import http
from odoo.http import request
from datetime import datetime, timedelta
import json


class GeodynamicsAPI(http.Controller):

    @http.route('/api/geodynamics/employee/daily_summary', type='http', auth='user', methods=['GET'], csrf=False)
    def get_employee_daily_summary(self, start_date=None, end_date=None, **kwargs):
        """
        HTTP GET version of the daily summary API for easier testing.
        Access via: /api/geodynamics/employee/daily_summary?start_date=2024-01-01&end_date=2024-01-31
        """
        result = self._get_daily_summary(start_date, end_date)
        return request.make_response(
            json.dumps(result, indent=2, ensure_ascii=False),
            headers=[
                ('Content-Type', 'application/json'),
                ('Access-Control-Allow-Origin', '*')
            ]
        )

    @http.route('/api/geodynamics/employee/profile', type='http', auth='user', methods=['GET'], csrf=False)
    def get_employee_profile(self, **kwargs):
        """
        Get current user and employee profile information.
        Access via: /api/geodynamics/employee/profile
        """
        try:
            user = request.env.user

            # Find the employee linked to the current user
            # For portal users, the link is through partner_id (work_contact_id)
            # For internal users, the link is through user_id or user_partner_id
            employee = request.env['hr.employee'].sudo().search([
                '|', '|',
                ('user_id', '=', user.id),
                ('user_partner_id', '=', user.partner_id.id),
                ('work_contact_id', '=', user.partner_id.id)
            ], limit=1)

            if not employee:
                result = {
                    'success': False,
                    'error': 'No employee found for the current user'
                }
            else:
                result = {
                    'success': True,
                    'user': {
                        'id': user.id,
                        'name': user.name,
                        'login': user.login,
                        'email': user.partner_id.email or user.login,
                        'partner_id': user.partner_id.id,
                    },
                    'employee': {
                        'id': employee.id,
                        'name': employee.name,
                        'work_email': employee.work_email or '',
                        'work_phone': employee.work_phone or '',
                        'mobile_phone': employee.mobile or '',
                        'job_title': employee.job_title or '',
                        'department': employee.department_id.name if employee.department_id else '',
                        'geodynamics_id': employee.df_geodynamics_id or '',
                    }
                }

            return request.make_response(
                json.dumps(result, indent=2, ensure_ascii=False),
                headers=[
                    ('Content-Type', 'application/json'),
                    ('Access-Control-Allow-Origin', '*')
                ]
            )

        except Exception as e:
            result = {
                'success': False,
                'error': str(e)
            }
            return request.make_response(
                json.dumps(result, indent=2, ensure_ascii=False),
                headers=[
                    ('Content-Type', 'application/json'),
                    ('Access-Control-Allow-Origin', '*')
                ]
            )

    def _get_daily_summary(self, start_date=None, end_date=None):
        """
        Internal method to get daily summary data.
        """
        try:
            # Get the current user
            user = request.env.user

            # Find the employee linked to the current user
            # For portal users, the link is through partner_id (work_contact_id)
            # For internal users, the link is through user_id or user_partner_id
            employee = request.env['hr.employee'].sudo().search([
                '|', '|',
                ('user_id', '=', user.id),
                ('user_partner_id', '=', user.partner_id.id),
                ('work_contact_id', '=', user.partner_id.id)
            ], limit=1)

            if not employee:
                return {
                    'success': False,
                    'error': 'No employee found for the current user'
                }

            # Parse dates
            if not end_date:
                end_date_dt = datetime.now().date()
            else:
                try:
                    end_date_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
                except ValueError:
                    return {
                        'success': False,
                        'error': 'Invalid end_date format. Use YYYY-MM-DD'
                    }

            if not start_date:
                start_date_dt = end_date_dt - timedelta(days=30)
            else:
                try:
                    start_date_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
                except ValueError:
                    return {
                        'success': False,
                        'error': 'Invalid start_date format. Use YYYY-MM-DD'
                    }

            # Convert to datetime for filtering
            start_datetime = datetime.combine(start_date_dt, datetime.min.time())
            end_datetime = datetime.combine(end_date_dt, datetime.max.time())

            # Fetch clocking records for this employee
            clocking_records = request.env['geodynamics.clocking'].sudo().search([
                ('employee_id', '=', employee.id),
                ('date_local', '>=', start_datetime),
                ('date_local', '<=', end_datetime)
            ], order='date_local asc')

            # Group by date and calculate totals
            daily_data = {}

            for clocking in clocking_records:
                if not clocking.date_local:
                    continue

                date_key = clocking.date_local.date().strftime('%Y-%m-%d')

                if date_key not in daily_data:
                    daily_data[date_key] = {
                        'date': date_key,
                        'total_hours': 0.0,
                        'worked_total': 0.0,
                        'hours_driving_total': 0.0,
                        'hours_pause': 0.0,
                        'total_km_driven': 0.0,
                    }

                hours = clocking.movement_time_hours or 0.0
                distance = clocking.movement_distance or 0.0

                # Add to total hours
                daily_data[date_key]['total_hours'] += hours
                daily_data[date_key]['total_km_driven'] += distance

                # Categorize by type_label
                type_label = (clocking.type_label or '').lower()

                # Movement Drive = driving time
                if 'drive' in type_label or 'driving' in type_label or 'rijden' in type_label:
                    daily_data[date_key]['hours_driving_total'] += hours
                # Pause/Break = pause time
                elif 'pause' in type_label or 'break' in type_label or 'pauze' in type_label:
                    daily_data[date_key]['hours_pause'] += hours
                # Everything else = worked time
                else:
                    daily_data[date_key]['worked_total'] += hours

            # Convert to list and round values
            result = []
            for date_key in sorted(daily_data.keys()):
                data = daily_data[date_key]
                result.append({
                    'date': data['date'],
                    'total_hours': round(data['total_hours'], 2),
                    'worked_total': round(data['worked_total'], 2),
                    'hours_driving_total': round(data['hours_driving_total'], 2),
                    'hours_pause': round(data['hours_pause'], 2),
                    'total_km_driven': round(data['total_km_driven'], 2),
                })

            return {
                'success': True,
                'employee_id': employee.id,
                'employee_name': employee.name,
                'data': result
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

