# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
import requests
from requests.auth import HTTPBasicAuth
import pytz
import json
import time
from datetime import datetime, timedelta
import logging
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

class GeodynamicsHandler:
    def __init__(self, gd_login, gd_password, gd_company, environ):
        self.gd_login = gd_login
        self.gd_password = gd_password
        self.gd_company = gd_company
        self.env = environ

        self.baseUrl = 'https://api.intellitracer.be/api/v2'
        if self.gd_login is not None and self.gd_company is not None and self.gd_password is not None:
            self.auth = HTTPBasicAuth(str(self.gd_login) + '|' + str(self.gd_company), str(self.gd_password))

    def _is_logging_enabled(self):
        """Check if API logging is enabled in settings."""
        try:
            return self.env['ir.config_parameter'].sudo().get_param(
                'geodynamics.enable_api_logging', 'True').lower() in ('true', '1', 'yes')
        except Exception:
            return True

    def _api_request(self, method, url, params=None, json_body=None, timeout=30):
        """Wrapper for HTTP requests with automatic API logging.

        Returns the requests.Response object, or None on network errors.
        """
        import time as _time
        from urllib.parse import urlencode
        start = _time.time()
        response = None
        error = None

        # Build full URL with query params for logging (Postman-friendly)
        full_url = url
        if params:
            full_url = f'{url}?{urlencode(params)}'

        try:
            http_method = getattr(requests, method.lower())
            kwargs = {'auth': self.auth, 'timeout': timeout}
            if params:
                kwargs['params'] = params
            if json_body is not None:
                kwargs['json'] = json_body
            response = http_method(url, **kwargs)
        except Exception as e:
            error = e
            _logger.error('[Geodynamics] %s %s — network/connection error: %s', method.upper(), full_url, e)
        finally:
            duration_ms = int((_time.time() - start) * 1000)
            is_error = error or (response is not None and response.status_code != 200)
            if is_error:
                body_snippet = ''
                if response is not None:
                    try:
                        body_snippet = response.text[:500]
                    except Exception:
                        pass
                _logger.error(
                    '[Geodynamics] API ERROR — %s %s — Status: %s — Body: %s — JSON sent: %s',
                    method.upper(), full_url,
                    response.status_code if response else 'N/A',
                    body_snippet or '(empty)',
                    json_body or '(none)')
            if self._is_logging_enabled():
                try:
                    resp_payload = None
                    if response is not None:
                        try:
                            resp_payload = response.json()
                        except Exception:
                            resp_text = ''
                            try:
                                resp_text = response.text[:2000]
                            except Exception:
                                pass
                            if resp_text:
                                resp_payload = {'_raw_response': resp_text}
                    endpoint = url.split('/')[-1].split('?')[0] or url
                    status_code = 0
                    if response is not None:
                        status_code = response.status_code
                    error_msg = None
                    if error:
                        error_msg = str(error)
                    elif response is not None and response.status_code != 200:
                        try:
                            error_msg = response.text[:2000]
                        except Exception:
                            error_msg = f'HTTP {response.status_code}'
                    self.env['df.geodynamics.api.log'].sudo().create({
                        'df_name': endpoint,
                        'df_method': method.upper(),
                        'df_url': full_url,
                        'df_request_payload': json_body or params,
                        'df_response_payload': resp_payload,
                        'df_response_status': status_code,
                        'df_duration_ms': duration_ms,
                        'df_error_message': error_msg,
                    })
                except Exception as log_err:
                    _logger.warning('[Geodynamics] Failed to log API request: %s', log_err)
        self.sleep()
        return response

    def test(self):
        response = self._api_request('GET', self.baseUrl + '/user')

        if response is None:
            return ['danger', 'Verbindingsfout: kon de server niet bereiken']
        if response.status_code != 200:
            return ['danger', f'Fout bij verbinden (HTTP {response.status_code})']
        return ['success', 'Verbinding gelukt']

    # ----- New API methods -----

    def _error_result(self, method_name, url, response):
        """Build a detailed error dict and log it."""
        if response is None:
            _logger.error('[Geodynamics] %s failed: no response (connection error) — URL: %s',
                          method_name, url)
            return {'Error': f'Connection error: could not reach {url}. Check server logs for details.'}
        body = ''
        try:
            body = response.text[:500]
        except Exception:
            pass
        _logger.error('[Geodynamics] %s failed: HTTP %s — URL: %s — Response: %s',
                      method_name, response.status_code, url, body)
        return {'Error': f'Failed with HTTP {response.status_code}: {body}'}

    def getUsers(self):
        """GET /api/v2/user — Fetch all Geodynamics users."""
        url = f'{self.baseUrl}/user'
        response = self._api_request('GET', url)
        if response is None or response.status_code != 200:
            return self._error_result('getUsers', url, response)
        data = response.json()
        _logger.info('[Geodynamics] getUsers: response type=%s', type(data).__name__)
        if isinstance(data, list):
            _logger.info('[Geodynamics] getUsers: %d users returned', len(data))
            if data:
                _logger.info('[Geodynamics] getUsers: first user keys=%s, data=%s', list(data[0].keys()) if isinstance(data[0], dict) else 'N/A', data[0])
        elif isinstance(data, dict):
            _logger.info('[Geodynamics] getUsers: response keys=%s', list(data.keys()))
            inner = data.get('Data') or data.get('data') or data.get('Users') or data.get('users') or data.get('Result') or data.get('result')
            if inner and isinstance(inner, list) and inner:
                _logger.info('[Geodynamics] getUsers: nested list found with %d items, first item keys=%s', len(inner), list(inner[0].keys()) if isinstance(inner[0], dict) else 'N/A')
        return {'Success': True, 'Data': data}

    def createUser(self, user_data):
        """PUT /api/v2/user — Create user in Geodynamics."""
        url = f'{self.baseUrl}/user'
        response = self._api_request('PUT', url, json_body=user_data)
        if response is None or response.status_code != 200:
            return self._error_result('createUser', url, response)
        return {'Success': True, 'Data': response.json()}

    def updateUser(self, user_data):
        """POST /api/v2/user — Update user in Geodynamics."""
        url = f'{self.baseUrl}/user'
        response = self._api_request('POST', url, json_body=user_data)
        if response is None or response.status_code != 200:
            return self._error_result('updateUser', url, response)
        return {'Success': True, 'Data': response.json()}

    def getVehicles(self):
        """Fetch all vehicles from Geodynamics via /api/v1/vehicle."""
        url = 'https://api.intellitracer.be/api/v1/vehicle'
        response = self._api_request('GET', url)
        if response is None or response.status_code != 200:
            return self._error_result('getVehicles', url, response)
        data = response.json()
        _logger.info('[Geodynamics] getVehicles: response type=%s, count=%s',
                     type(data).__name__, len(data) if isinstance(data, list) else 'N/A')
        return {'Success': True, 'Data': data}

    def getVehicleCounters(self, vehicle_ids, defaults_only=False):
        """POST /api/v1/vehiclecounters — current counters per vehicle.

        These are the counters shown under "Voertuig tellers" in Geodynamics
        (e.g. 'Kilometers', 'Draaiuren'). Per the API documentation they are
        calculated up to the vehicle's last tracking report.

        The counter *names* are free text and locale-dependent, so the caller
        decides which counter is the odometer and which the running hours.

        Args:
            vehicle_ids (list[str]): Vehicle GUIDs (df_geodynamics_id).
            defaults_only (bool): Only return the default template counters.

        Returns (dict):
            On success: {'Success': True, 'Data': {vehicle_id: [counter, ...]}}
                        where counter is {'Id', 'CounterName', 'CounterValue', 'IsDefault'}
            On error:   {'Error': msg}
        """
        ids = [vid for vid in (vehicle_ids or []) if vid]
        if not ids:
            return {'Success': True, 'Data': {}}

        url = 'https://api.intellitracer.be/api/v1/vehiclecounters'
        params = {'defaultsOnly': 'true' if defaults_only else 'false'}
        counters = {}
        # The endpoint takes a list of vehicles; chunk so a large fleet does not
        # end up in one oversized request.
        for start in range(0, len(ids), 100):
            chunk = ids[start:start + 100]
            response = self._api_request('POST', url, params=params, json_body=chunk, timeout=60)
            if response is None or response.status_code != 200:
                if response is not None and response.status_code == 403:
                    # Documented response for this endpoint when the account lacks the
                    # privilege; it comes back with an empty body, so spell it out here.
                    message = ("HTTP 403: this Geodynamics API account may not read vehicle "
                               "counters. Ask GeoDynamics to grant it the "
                               "'Api: vehicle counters' privilege.")
                    _logger.error('[Geodynamics] getVehicleCounters: %s — URL: %s', message, url)
                    return {'Error': message}
                return self._error_result('getVehicleCounters', url, response)
            try:
                data = response.json()
            except ValueError:
                return {'Error': 'getVehicleCounters: response was not valid JSON'}
            if isinstance(data, dict):
                data = data.get('Data') or []
            if not isinstance(data, list):
                data = [data]
            for item in data:
                if not isinstance(item, dict):
                    continue
                vehicle = item.get('Vehicle') or {}
                vehicle_id = vehicle.get('Id') if isinstance(vehicle, dict) else None
                if not vehicle_id:
                    continue
                rows = item.get('VehicleCounterData') or []
                counters[vehicle_id] = [r for r in rows if isinstance(r, dict)]

        _logger.info('[Geodynamics] getVehicleCounters: %d of %d vehicle(s) returned counters %s',
                     len(counters), len(ids),
                     {vid: [r.get('CounterName') for r in rows] for vid, rows in counters.items()})
        return {'Success': True, 'Data': counters}

    def createVehicle(self, vehicle_data):
        """PUT /api/v1/vehicle — Create vehicle in Geodynamics."""
        url = 'https://api.intellitracer.be/api/v1/vehicle'
        response = self._api_request('PUT', url, json_body=vehicle_data)
        if response is None or response.status_code != 200:
            return self._error_result('createVehicle', url, response)
        return {'Success': True, 'Data': response.json()}

    def updateVehicle(self, vehicle_data):
        """POST /api/v1/vehicle — Update vehicle in Geodynamics."""
        url = 'https://api.intellitracer.be/api/v1/vehicle'
        response = self._api_request('POST', url, json_body=vehicle_data)
        if response is None or response.status_code != 200:
            return self._error_result('updateVehicle', url, response)
        return {'Success': True, 'Data': response.json()}

    def getAbsenceTypes(self):
        """GET /api/v2/absencetype — Fetch all absence types."""
        url = f'{self.baseUrl}/absencetype'
        response = self._api_request('GET', url)
        if response is None or response.status_code != 200:
            return self._error_result('getAbsenceTypes', url, response)
        data = response.json()
        _logger.info('[Geodynamics] getAbsenceTypes: %s items',
                     len(data) if isinstance(data, list) else type(data).__name__)
        return {'Success': True, 'Data': data}

    def createAbsenceType(self, absence_data):
        """PUT /api/v2/absencetype — Create absence type in Geodynamics."""
        url = f'{self.baseUrl}/absencetype'
        response = self._api_request('PUT', url, json_body=absence_data)
        if response is None or response.status_code != 200:
            return self._error_result('createAbsenceType', url, response)
        return {'Success': True, 'Data': response.json()}

    def updateAbsenceType(self, absence_data):
        """POST /api/v2/absencetype — Update absence type in Geodynamics."""
        url = f'{self.baseUrl}/absencetype'
        response = self._api_request('POST', url, json_body=absence_data)
        if response is None or response.status_code != 200:
            return self._error_result('updateAbsenceType', url, response)
        return {'Success': True, 'Data': response.json()}

    def getAbsences(self, fromDateTime, toDateTime, userIds=None):
        """POST /api/v2/absence/user/list — Fetch absences for users in a date range.
        Automatically chunks into 30-day windows to avoid API period-too-large errors."""
        url = f'{self.baseUrl}/absence/user/list'
        from_dt = self._parse_input_dt(fromDateTime)
        to_dt = self._parse_input_dt(toDateTime)
        tz = pytz.timezone('Europe/Brussels')
        if from_dt.tzinfo is None:
            from_dt = tz.localize(from_dt)
        if to_dt.tzinfo is None:
            to_dt = tz.localize(to_dt)

        chunks = []
        chunk_start = from_dt
        while chunk_start < to_dt:
            chunk_end = min(chunk_start + timedelta(days=30), to_dt)
            chunks.append((chunk_start, chunk_end))
            chunk_start = chunk_end + timedelta(seconds=1)

        all_data = []
        total_pages = 0
        for chunk_from, chunk_to in chunks:
            json_body = {
                'FromDate': chunk_from.isoformat(),
                'ToDate': chunk_to.isoformat(),
                'UserIds': userIds or [],
            }
            page = 1
            while True:
                params = {'page': page}
                response = self._api_request('POST', url, params=params, json_body=json_body, timeout=120)
                if response is None or response.status_code != 200:
                    if page == 1 and len(chunks) == 1:
                        return self._error_result('getAbsences', url, response)
                    _logger.warning('[Geodynamics] getAbsences chunk %s→%s page %d failed, skipping',
                                    chunk_from.isoformat(), chunk_to.isoformat(), page)
                    break
                data = response.json()
                if isinstance(data, dict):
                    items = data.get('Data', [])
                    if isinstance(items, list):
                        all_data.extend(items)
                    paging = data.get('PagingFilter', {})
                    if not paging.get('Links', {}).get('Next'):
                        break
                elif isinstance(data, list):
                    if not data:
                        break
                    all_data.extend(data)
                else:
                    break
                page += 1
            total_pages += page
        _logger.info('[Geodynamics] getAbsences: %d user entries fetched (%d chunks, %d total pages)',
                     len(all_data), len(chunks), total_pages)
        return {'Success': True, 'Data': all_data}

    def getPois(self):
        """GET /api/v1/poi — Fetch all POIs."""
        url = 'https://api.intellitracer.be/api/v1/poi'
        response = self._api_request('GET', url)
        if response is None or response.status_code != 200:
            return self._error_result('getPois', url, response)
        data = response.json()
        _logger.info('[Geodynamics] getPois: response type=%s, count=%s',
                     type(data).__name__, len(data) if isinstance(data, list) else 'N/A')
        if isinstance(data, list) and data:
            _logger.info('[Geodynamics] getPois: first POI keys=%s', list(data[0].keys()) if isinstance(data[0], dict) else 'N/A')
        return {'Success': True, 'Data': data}

    def getCheckins(self, userId, fromDateTime, toDateTime):
        """Fetch check-in at work records by filtering clockings for work start/stop types."""
        result = self.getClockingsByUserDateRange(userId, fromDateTime, toDateTime)
        if 'Error' in result:
            return result
        clockings = result.get('Data', [])
        if not isinstance(clockings, list):
            clockings = [clockings]
        # Filter for Start work (1) and Stop work (2) to build check-in pairs
        work_events = [c for c in clockings if isinstance(c, dict) and c.get('Type') in (1, 2)]
        work_events.sort(key=lambda c: c.get('DateTimeLocal', '') or c.get('DateTimeUtc', ''))
        checkins = []
        current_start = None
        for evt in work_events:
            if evt.get('Type') == 1:
                current_start = evt
            elif evt.get('Type') == 2 and current_start:
                checkins.append({
                    'start': current_start,
                    'stop': evt,
                    'start_time': current_start.get('DateTimeLocal') or current_start.get('DateTimeUtc'),
                    'stop_time': evt.get('DateTimeLocal') or evt.get('DateTimeUtc'),
                    'pois': current_start.get('Pois') or evt.get('Pois'),
                    'user': current_start.get('User') or evt.get('User'),
                })
                current_start = None
        return {'Success': True, 'Data': checkins, 'Count': len(checkins)}

    def createPlanning(self, userId, fromDateTime, toDateTime, activityNumber, nPoiId=None, description=None):
        url = 'https://api.intellitracer.be/api/v3/planning'

        # ActivityNumber carries the unique key (task name + id); Description stays the
        # human-readable task name when one is provided.
        sJson = {'UserId':userId, 'FromDateUtc':self.convert_to_utc(fromDateTime), 'ToDateUtc':self.convert_to_utc(toDateTime), 'ActivityNumber':activityNumber, 'Description': description if description is not None else activityNumber}

        if nPoiId is not None:
            sJson['PoiId'] = nPoiId

        self.deletePlanningUser(userId, fromDateTime, toDateTime)

        response = self._api_request('PUT', url, json_body=sJson)

        if response is None or response.status_code != 200:
            _logger.info('Request failed with status code: %s', response.status_code if response else 'N/A')
        else:
            sOutputJson = response.json()
            return sOutputJson["Data"]["Id"]

    def createPlanningByTask(self, sTask):
        for usr in sTask.df_assignees_with_geodynamics_ids:
            sNaam = sTask.df_gd_name
            _logger.info('df_gd_name: %s',sNaam)
            sId = self.createPlanning(usr.df_geodynamics_id, sTask.planned_date_start, sTask.date_deadline, sNaam, description=sTask.name)
            _logger.info('sId after createPlanning: %s', sId)

            sValues = {'start_datetime':sTask.planned_date_start, 'end_datetime':sTask.date_deadline, 'id_geodynamics':sId,
                       'user_id_geodynamics':usr.df_geodynamics_id, 'user_id':usr.id, 'task_id':sTask.id, 'activitynumber':sNaam, 'description':sTask.name}
            self.env['df.geodynamics.planning'].create(sValues)

    def removePlanning_emp(self, taskId, empId):
        pls = self.env['df.geodynamics.planning'].search([('task_id','=',taskId),('employee_id','=',empId)])
        pls.unlink()

    def removePlanning_task(self, sTask):
        pls = self.env['df.geodynamics.planning'].search([('task_id', '=', sTask.id)])
        pls.unlink()

    def isWeekendOrHoliday(self, date):
        # Weekend check
        if date.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
            return True
        # Add any custom holiday logic here
        holidays = [
            datetime(2025, 12, 25).date(),  # Just as an example: X-mas
        ]
        return date in holidays

    def split_into_workdays(self, start_datetime, end_datetime):
        # Read workday hours from settings (float, e.g. 6.5 = 06:30) — these are LOCAL times
        try:
            ws = float(self.env['ir.config_parameter'].sudo().get_param('geodynamics.workday_start', '6.0'))
            we = float(self.env['ir.config_parameter'].sudo().get_param('geodynamics.workday_end', '15.0'))
        except (ValueError, TypeError):
            ws, we = 6.0, 15.0
        workday_start_hour, workday_start_min = int(ws), int((ws % 1) * 60)
        workday_end_hour, workday_end_min = int(we), int((we % 1) * 60)

        # Get user timezone to convert local workday hours to UTC
        user_tz_name = self.env.user.tz or self.env.context.get('tz') or 'Europe/Brussels'
        try:
            user_tz = pytz.timezone(user_tz_name)
        except Exception:
            user_tz = pytz.timezone('Europe/Brussels')

        results = []

        _logger.info(start_datetime)
        _logger.info(end_datetime)

        current_day = start_datetime.date()
        last_day = end_datetime.date()

        while current_day <= last_day:
            if self.isWeekendOrHoliday(current_day):
                current_day += timedelta(days=1)
                continue

            is_start_day = current_day == start_datetime.date()
            is_end_day = current_day == end_datetime.date()

            # Create local times then convert to UTC (naive) for Odoo storage
            local_start = user_tz.localize(datetime.combine(current_day, datetime.min.time()).replace(
                hour=workday_start_hour, minute=workday_start_min))
            local_end = user_tz.localize(datetime.combine(current_day, datetime.min.time()).replace(
                hour=workday_end_hour, minute=workday_end_min))
            day_start = local_start.astimezone(pytz.utc).replace(tzinfo=None)
            default_day_end = local_end.astimezone(pytz.utc).replace(tzinfo=None)

            period_start = max(start_datetime, day_start) if is_start_day else day_start
            period_end = end_datetime if is_end_day else default_day_end

            if period_start < period_end:
                results.append((period_start, period_end))

            current_day += timedelta(days=1)

        return results

    def subtract_two_hours(self, dt):
        if dt:
            return dt - timedelta(hours=2)
        return dt

    def testPeriods(self, sTask):
        periodItems = self.split_into_workdays(sTask.planned_date_start, sTask.date_deadline)
        _logger.info(periodItems)

    def createPlanningByTaskWn(self, sTask):
        nAmount = 0

        self.removePlanning_task(sTask)

        for usr in sTask.df_employee_ids:
            if usr.df_geodynamics_id == False:
                continue
            sNaam = sTask.df_gd_name
            _logger.info(sNaam)

            self.removePlanning_emp(sTask.id, usr.id)
            # use partner_shipping_id if available, otherwise use task's partner
            partner_id = False
            if hasattr(sTask, 'sale_line_id') and sTask.sale_line_id and sTask.sale_line_id.order_id.partner_shipping_id:
                partner_id = sTask.sale_line_id.order_id.partner_shipping_id
            else:
                partner_id = sTask.partner_id

            if partner_id.df_geodynamics_poi_id != False:
                poiId = partner_id.df_geodynamics_poi_id
            else:
                partner_id.sync_poi_geodynamics()
                poiId = partner_id.df_geodynamics_poi_id

            periodItems = self.split_into_workdays(sTask.planned_date_start, sTask.date_deadline)

            _logger.info('Period items: ')
            _logger.info(periodItems)

            if periodItems == []:
                raise ValidationError('No periods. There must be a period within the working days.')

            sId = None
            for p in periodItems:
                try:
                    sId = self.createPlanning(usr.df_geodynamics_id, p[0], p[1], sNaam, poiId, description=sTask.name)
                    _logger.info(sId)

                    sValues = {'start_datetime':p[0], 'end_datetime':p[1], 'id_geodynamics':sId,
                               'user_id_geodynamics':usr.df_geodynamics_id, 'employee_id':usr.id, 'task_id':sTask.id, 'activitynumber':sNaam, 'description':sTask.name}
                    self.env['df.geodynamics.planning'].create(sValues)
                    nAmount = nAmount + 1
                except:
                    _logger.error('Error while adding planning: ' + str(sId))
                    raise ValidationError('Error while adding planning')

        return nAmount

    def laadPostcalc(self, userId, ddate):
        url = 'https://api.intellitracer.be/api/v2/postcalculation/export'

        sJson = {'UserIds': [userId], 'AllUsers':False, 'Mode':0, 'GroupCostcenterByActivity':False, 'DateUtc':self.convert_to_utc(ddate),
                 'IncludeTimesheet':False, 'IncludeTimesheetEvents':True, 'IncludeTimeValidation':False,
                 'IncludePostCalculationLog':False, 'IncludeLossCostcenter':False}

        _logger.info('[Geodynamics][Postcalc] API request postcalculation/export UserId=%s DateUtc=%s', userId, sJson.get('DateUtc'))
        if self.env['ir.config_parameter'].sudo().get_param('geodynamics.verbose_logging', 'False').lower() in ('true', '1', 'yes'):
            _logger.info('[Geodynamics][Postcalc][VERBOSE] request body: %s', sJson)

        response = self._api_request('POST', url, json_body=sJson)

        if response is None or response.status_code != 200:
            _logger.info('[Geodynamics][Postcalc] API request failed with status code: %s', response.status_code if response else 'N/A')
            return {}
        else:
            result = response.json()
            try:
                data_list = result.get('Data') if isinstance(result, dict) else None
                _logger.info('[Geodynamics][Postcalc] API response: Success=%s, %s data entr(ies)',
                             result.get('Success') if isinstance(result, dict) else 'n/a',
                             len(data_list) if isinstance(data_list, list) else 'n/a')
            except Exception:
                pass
            return result

    def deletePlanning(self, sRecord):
        totalDeletions = 0
        allWn = []
        for s in sRecord.df_employee_ids:
            allWn.append(s.id)

        _logger.info(allWn)

        to_delete = self.env['df.geodynamics.planning']
        for r in self.env['df.geodynamics.planning'].search([('task_id','=',sRecord.id)]):
            if r.employee_id.id not in allWn:
                to_delete |= r
                totalDeletions = totalDeletions + 1
        to_delete.unlink()

        return totalDeletions

    def deletePlanning2(self, sRecord):
        totalDeletions = 0

        planIds = [sRecord.id]

        for p in planIds:
            records = self.env['df.geodynamics.planning'].search([('task_id','=',p.id)])
            totalDeletions += len(records)
            records.unlink()

        return totalDeletions

    def deletePlanning3(self, pId):
        self.env['df.geodynamics.planning'].search([('id','=',pId)]).unlink()

    def deletePlanningUser(self, userId, fromDateTime, toDateTime):
        url = 'https://api.intellitracer.be/api/v1/byuseriddaterange'

        params = {'userId':userId, 'fromDate':self.convert_to_utc(fromDateTime), 'toDate':self.convert_to_utc(toDateTime)}

        self._api_request('DELETE', url, params=params)

    def removePlanning(self, planningId):
        url = 'https://api.intellitracer.be/api/v2/planning/' + planningId

        self._api_request('DELETE', url)

    def laadAllPlanning(self):
        """Fetch all planning from Geodynamics for all employees.

        Uses configurable sync_days_back setting to determine the date range.
        Fetches in 30-day chunks (API limit) per employee.
        Deduplicates by Geodynamics ID to avoid creating duplicate records.
        """
        # Use planning_from_date setting if set, otherwise fall back to sync_days_back
        from_date_str = self.env['ir.config_parameter'].sudo().get_param('geodynamics.planning_from_date')
        if from_date_str:
            try:
                start_date = datetime.strptime(from_date_str, '%Y-%m-%d')
            except (ValueError, TypeError):
                start_date = datetime.now() - timedelta(days=90)
        else:
            sync_days = 90
            try:
                sync_days = int(self.env['ir.config_parameter'].sudo().get_param('geodynamics.sync_days_back', '90'))
            except (ValueError, TypeError):
                pass
            start_date = datetime.now() - timedelta(days=sync_days)
        end_date = datetime.now() + timedelta(days=30)
        chunk_days = 30  # API max period

        employees = self.env['hr.employee'].search([('df_geodynamics_id', '!=', False)])
        Planning = self.env['df.geodynamics.planning']

        total_days = (end_date - start_date).days
        total_chunks = max(1, total_days // chunk_days + 1) * len(employees)
        _logger.info('[Geodynamics] Loading planning for %d employees from %s to %s (in %d-day chunks, ~%d API calls)',
                     len(employees), start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), chunk_days, total_chunks)

        total_created = 0
        total_updated = 0

        for emp_idx, emp in enumerate(employees):
            _logger.info('[Geodynamics] Fetching planning for employee %d/%d: %s (gd_id=%s)',
                         emp_idx + 1, len(employees), emp.name, emp.df_geodynamics_id)
            # Fetch in chunks to respect API period limit
            chunk_start = start_date
            while chunk_start < end_date:
                chunk_end = min(chunk_start + timedelta(days=chunk_days), end_date)

                plannings = self._fetch_planning_for_user(emp.df_geodynamics_id, chunk_start, chunk_end)
                chunk_start = chunk_end

                if not plannings:
                    continue

                for p in plannings:
                    gd_id = p.get('Id')
                    if not gd_id:
                        continue

                    from_dt = self.convert_to_datetime(p['FromDate']) if p.get('FromDate') else False
                    to_dt = self.convert_to_datetime(p['ToDate']) if p.get('ToDate') else False
                    activity = p.get('ActivityNumber') or p.get('Description') or ''

                    if not from_dt or not to_dt:
                        continue

                    vals = {
                        'start_datetime': from_dt,
                        'end_datetime': to_dt,
                        'id_geodynamics': gd_id,
                        'user_id_geodynamics': emp.df_geodynamics_id,
                        'employee_id': emp.id,
                        'activitynumber': activity,
                        'description': p.get('Description') or '',
                    }

                    existing = Planning.search([('id_geodynamics', '=', gd_id)], limit=1)
                    if existing:
                        existing.write(vals)
                        total_updated += 1
                    else:
                        Planning.create(vals)
                        total_created += 1

        _logger.info('[Geodynamics] Planning load complete: %d created, %d updated', total_created, total_updated)
        return total_created, total_updated

    def _fetch_planning_for_user(self, userId, fromDate, toDate):
        """Fetch planning records for a single user in a date range."""
        url = 'https://api.intellitracer.be/api/v1/byuseriddaterange'
        params = {
            'userId': userId,
            'fromDate': self.convert_to_utc(fromDate),
            'toDate': self.convert_to_utc(toDate),
        }
        response = self._api_request('GET', url, params=params)
        if response is None or response.status_code != 200:
            _logger.warning('[Geodynamics] Failed to fetch planning for user %s: status=%s',
                           userId, response.status_code if response else 'None')
            return []
        data = response.json()
        if not isinstance(data, list):
            data = [data] if data else []
        return data

    def laadPoiTypes(self):
        url = 'https://api.intellitracer.be/api/v1/poitype'

        response = self._api_request('GET', url)
        if response is None or response.status_code != 200:
            return

        responseJson = response.json()

        for r in responseJson:
            curR = self.env['df.geodynamics.poitype'].search([('id_geodynamics','=',r['Id'])])

            if not curR:
                self.env['df.geodynamics.poitype'].create({'id_geodynamics':r['Id'], 'Name':r['Name']})

    def laadPlanning(self, userId, fromDate, toDate):
        """Fetch and store planning for a single user — uses _fetch_planning_for_user."""
        Planning = self.env['df.geodynamics.planning']
        plannings = self._fetch_planning_for_user(userId, fromDate, toDate)

        emp = self.env['hr.employee'].search([('df_geodynamics_id', '=', userId)], limit=1)

        for p in plannings:
            gd_id = p.get('Id')
            if not gd_id:
                continue

            from_dt = self.convert_to_datetime(p['FromDate']) if p.get('FromDate') else False
            to_dt = self.convert_to_datetime(p['ToDate']) if p.get('ToDate') else False
            if not from_dt or not to_dt:
                continue

            existing = Planning.search([('id_geodynamics', '=', gd_id)], limit=1)
            if existing:
                continue

            vals = {
                'start_datetime': from_dt,
                'end_datetime': to_dt,
                'id_geodynamics': gd_id,
                'user_id_geodynamics': p.get('User', {}).get('Id') or userId,
                'employee_id': emp.id if emp else False,
                'activitynumber': p.get('ActivityNumber') or p.get('Description') or '',
                'description': p.get('Description') or '',
            }
            Planning.create(vals)


    def convert_to_utc(self, dt):
        return dt.strftime('%Y-%m-%dT%H:%M:%S')

    def convert_to_datetime(self, date_string):
        return datetime.strptime(date_string, "%Y-%m-%dT%H:%M:%S")

    def sleep(self):
        time.sleep(0.1)

    def _build_poi_data(self, sContact):
        """Build POI data dict from a contact record."""
        defaultPoitypes = self.env['df.geodynamics.poitype'].search([])
        defPoiType = defaultPoitypes[0] if defaultPoitypes else None
        name = sContact.name
        if (not name or name.strip() == '') and sContact.parent_id:
            name = sContact.parent_id.name

        poiData = {
            'Name': name,
            'Street': sContact.street,
            'HouseNumber': '',
            'City': sContact.city,
            'PostalCode': sContact.zip,
            'Priority': '-',
            'ReverseGeocoding': True,
        }
        if defPoiType:
            poiData['PoiType'] = {'Id': defPoiType.id_geodynamics}
        # Remove False/None values
        return {key: value for key, value in poiData.items() if value is not None and value is not False}

    def addPoi(self, sContact):
        """Create a new POI in Geodynamics from a contact."""
        poiData = self._build_poi_data(sContact)
        _logger.info("addPoi: creating POI from contact: %s", poiData)
        return self.addPoiData(poiData)

    def updatePoi(self, sContact):
        """Update an existing POI in Geodynamics from a contact."""
        poiData = self._build_poi_data(sContact)
        poiData['Id'] = sContact.df_geodynamics_poi_id
        _logger.info("updatePoi: updating POI %s from contact: %s", sContact.df_geodynamics_poi_id, poiData)
        return self.updatePoiData(poiData)


    def addPoiFromTask(self, sTask):
        """Add POI using task object"""
        # Check if task has project_id - required condition
        if not sTask.project_id:
            _logger.info(f"Task {sTask.id} has no project_id, skipping POI creation")
            return {'Error': 'Task must have a project_id to create POI'}

        defaultPoitypes = self.env['df.geodynamics.poitype'].search([])
        if not defaultPoitypes:
            _logger.error("No POI types found in system")
            return {'Error': 'No POI types available'}

        defPoiType = defaultPoitypes[0]

        # Base POI data with task information
        # name must to max 50 char and if task name longer than 50, it will be append to Code
        task_name = sTask.name.replace(' - ','-').replace(" + ","+")
        task_name = task_name if len(task_name) <= 50 else task_name[:47] + '...'
        code = "{}-[{}]".format(sTask.name if len(sTask.name) <= 500 else sTask.name[:490], str(sTask.id))
        poiData = {
            'Name': task_name,
            'Code': code,
            'Description': f"https://{self.env['ir.config_parameter'].sudo().get_param('web.base.url')}/web#id={sTask.id}&model=project.task&view_type=form",
            'PoiType': {'Id': defPoiType.id_geodynamics},
            'Priority': '-',
            'ReverseGeocoding': False
        }

        # Add partner address information if available
        if sTask.sale_line_id and sTask.sale_line_id.order_id.partner_shipping_id:
            partner = sTask.sale_line_id.order_id.partner_shipping_id
            poiData.update({
                'Street': partner.street,
                'City': partner.city,
                'PostalCode': partner.zip,
            })
        elif sTask.project_id.partner_id:
            partner = sTask.project_id.partner_id
            poiData.update({
                'Street': partner.street,
                'City': partner.city,
                'PostalCode': partner.zip,
            })
            _logger.info(f"Added partner address info for task {sTask.id}: {partner.name}")
        else:
            _logger.info(f"Task {sTask.id} project has no partner, creating POI without address")

        # Remove False values
        filtered_dict = {key: value for key, value in poiData.items() if value is not False}

        _logger.info(f"Creating POI from task {sTask.id}: {filtered_dict}")

        return self.addPoiData(filtered_dict)

    def addPoiData(self, poiData):
        """Add POI using raw poiData dictionary"""
        url = 'https://api.intellitracer.be/api/v1/poi'

        response = self._api_request('PUT', url, json_body=poiData)

        if response is None or response.status_code != 200:
            if response is not None:
                try:
                    sOutput = response.json()
                    if isinstance(sOutput, list) and sOutput and 'Message' in sOutput[0]:
                        return {"Error": f"Error occurred: {sOutput[0]['Message']}"}
                except Exception:
                    pass
            return {'Error': 'Request failed with status code: ' + str(response.status_code if response else 'None')}
        else:
            return {'Success': response.json()}

    def updatePoiData(self, poiData):
        """Update existing POI using raw poiData dictionary (POST)"""
        url = 'https://api.intellitracer.be/api/v1/poi'

        _logger.info("updatePoiData: %s", poiData)
        response = self._api_request('POST', url, json_body=poiData)

        if response is None or response.status_code != 200:
            _logger.error('updatePoiData failed: status=%s', response.status_code if response else 'None')
            if response is not None:
                try:
                    sOutput = response.json()
                    if isinstance(sOutput, list) and sOutput and 'Message' in sOutput[0]:
                        return {"Error": f"Error occurred: {sOutput[0]['Message']}"}
                except Exception:
                    pass
            return {'Error': 'Request failed with status code: ' + str(response.status_code if response else 'None')}
        return {'Success': response.json()}

    def deletePoi(self, poiId):
        """Delete POI using POI ID"""
        url = 'https://api.intellitracer.be/api/v1/poi'

        response = self._api_request('DELETE', url, json_body={'Id': poiId})

        if response is None or response.status_code != 200:
            if response is not None:
                try:
                    sOutput = response.json()
                    if isinstance(sOutput, list) and sOutput and 'Message' in sOutput[0]:
                        return {"Error": f"Error deleting POI: {sOutput[0]['Message']}"}
                except Exception:
                    pass
            return {'Error': f'Failed to delete POI with status code: {response.status_code if response else "None"}'}
        else:
            return {'Success': 'POI deleted successfully'}

    def _parse_input_dt(self, value):
        """Parse incoming datetime input which is expected to be a string in
        format '%Y-%m-%d %H:%M:%S' or '%Y-%m-%dT%H:%M:%S' (or already a datetime). Return datetime.
        Raise ValidationError on invalid format.
        """
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            s = value.strip()
            # Normalize trailing Z to +00:00 for fromisoformat attempts
            try_formats = ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f')
            for fmt in try_formats:
                try:
                    return datetime.strptime(s[:26], fmt)
                except ValueError:
                    continue
            # Last resort: fromisoformat with Z handling
            try:
                iso_candidate = s.replace('Z', '+00:00')
                dt = datetime.fromisoformat(iso_candidate)
                # If timezone-aware, normalize to naive in same wall time (we only need a point-in-time here)
                return dt.replace(tzinfo=None)
            except Exception:
                pass
            raise ValidationError(
                "Datetime value must be a string in format 'YYYY-MM-DD HH:MM:SS' or 'YYYY-MM-DDTHH:MM:SS'"
            )
        raise ValidationError("Datetime value must be datetime or string in format 'YYYY-MM-DD HH:MM:SS' or 'YYYY-MM-DDTHH:MM:SS'")

    def _parse_input_date(self, value):
        """Parse incoming date input; accept datetime.date, datetime, or string 'YYYY-MM-DD'. Return a date.
        Raise ValidationError on invalid format.
        """
        if hasattr(value, 'date') and isinstance(value, datetime):
            return value.date()
        # datetime.date duck typing: has attributes year, month, day and strftime
        if hasattr(value, 'year') and hasattr(value, 'month') and hasattr(value, 'day') and hasattr(value, 'strftime') and not isinstance(value, str):
            return value
        if isinstance(value, str):
            try:
                return datetime.strptime(value, '%Y-%m-%d').date()
            except ValueError:
                raise ValidationError("Date value must be a string in format 'YYYY-MM-DD' (e.g., 2025-10-24)")
        raise ValidationError("Date value must be date/datetime or string in format 'YYYY-MM-DD'")

    CLOCKING_TYPE_MAP = {
        1: 'Start work',
        2: 'Stop work',
        3: 'Start activity',
        4: 'Stop activity',
        5: 'Start break',
        6: 'Stop break',
        12: 'Start movement driver',
        13: 'Start movement passenger',
        14: 'Stop movement',
        19: 'Start travel time',
        20: 'Stop travel time'
    }

    def _annotate_clocking_records(self, records):
        """Attach human-readable TypeLabel to each clocking dict if possible."""
        if isinstance(records, list):
            for rec in records:
                if isinstance(rec, dict) and 'Type' in rec:
                    t = rec.get('Type')
                    rec['TypeLabel'] = self.CLOCKING_TYPE_MAP.get(t, f'Unknown ({t})')
        elif isinstance(records, dict) and 'Type' in records:
            t = records.get('Type')
            records['TypeLabel'] = self.CLOCKING_TYPE_MAP.get(t, f'Unknown ({t})')
        return records

    def getClockingsByUserDateRange(self, userId, fromDateTime, toDateTime, raise_on_error=False):
        """Fetch clocking (time registration) data for a given Geodynamics user within a date range.

        Params:
            userId (str): Geodynamics user GUID (e.g. '00000000-0000-0000-0000-000000000000').
            fromDateTime (str|datetime): Start datetime as string in '%Y-%m-%d %H:%M:%S'.
            toDateTime (str|datetime): End datetime as string in '%Y-%m-%d %H:%M:%S'.
            raise_on_error (bool): If True, raise ValidationError on HTTP / parsing error; else return dict with Error.

        Returns:
            dict: { 'Success': True, 'Data': <list clockings>, 'Count': n } OR { 'Error': 'message', 'Status': <status_code> }
        """
        if not (userId and fromDateTime and toDateTime):
            return {'Error': 'Missing required parameters userId/fromDateTime/toDateTime'}

        # Parse (now required string) date inputs (generic, not field-based)
        try:
            from_dt = self._parse_input_dt(fromDateTime)
            to_dt = self._parse_input_dt(toDateTime)
        except ValidationError as ve:
            if raise_on_error:
                raise
            return {'Error': str(ve)}

        url = 'https://api.intellitracer.be/api/v1/Clocking_GetByUserIdDateRange'
        params = {
            'userId': userId,
            'fromDate': self.convert_to_utc(from_dt),
            'toDate': self.convert_to_utc(to_dt)
        }
        response = self._api_request('GET', url, params=params, timeout=30)

        if response is None:
            msg = 'Clocking API request failed: no response'
            if raise_on_error:
                raise ValidationError(msg)
            return {'Error': msg}

        if response.status_code != 200:
            msg = f'Clocking API request failed with status {response.status_code}'
            if raise_on_error:
                raise ValidationError(msg)
            return {'Error': msg, 'Status': response.status_code}

        try:
            data = response.json()
        except ValueError:
            msg = 'Invalid JSON in clocking response'
            if raise_on_error:
                raise ValidationError(msg)
            return {'Error': msg, 'Status': response.status_code}

        if isinstance(data, dict) and 'Data' in data:
            records = data['Data']
        else:
            records = data

        records = self._annotate_clocking_records(records)

        _logger.info('[Geodynamics] Retrieved %d clocking entries for user %s', len(records) if isinstance(records, list) else 1, userId)
        durations = self.compute_clocking_activity_durations(records)
        return {'Success': True, 'Data': records, 'Count': len(records) if isinstance(records, list) else 1, 'Durations': durations}

    def getClockingsByDateRange(self, fromDateTime, toDateTime, includeClockingsWithoutUser=False, raise_on_error=False):
        """Fetch clocking entries within a date range (no user filter).

        Endpoint:
            https://api.intellitracer.be/api/v1/clocking_getbydaterange

        Query Params:
            fromDate (UTC, ISO w/o timezone) - required
            toDate (UTC, ISO w/o timezone) - required
            includeClockingsWithoutUser (bool) - include entries not tied to a user

        Args:
            fromDateTime (str|datetime): Start datetime as string in '%Y-%m-%d %H:%M:%S' or datetime
            toDateTime (str|datetime): End datetime as string in '%Y-%m-%d %H:%M:%S' or datetime
            includeClockingsWithoutUser (bool): Whether to include clockings that have no user mapping
            raise_on_error (bool): Raise ValidationError instead of returning an error dict

        Returns (dict):
            On success: {'Success': True, 'Data': <list|dict>, 'Count': n}
            On error: {'Error': msg, 'Status': <http_status>?}
        """
        if not (fromDateTime and toDateTime):
            return {'Error': 'Missing required parameters fromDateTime/toDateTime'}

        # Parse date inputs
        try:
            from_dt = self._parse_input_dt(fromDateTime)
            to_dt = self._parse_input_dt(toDateTime)
        except ValidationError as ve:
            if raise_on_error:
                raise
            return {'Error': str(ve)}

        url = 'https://api.intellitracer.be/api/v1/clocking_getbydaterange'
        params = {
            'fromDate': self.convert_to_utc(from_dt),
            'toDate': self.convert_to_utc(to_dt),
            'includeClockingsWithoutUser': 'true' if includeClockingsWithoutUser else 'false'
        }

        response = self._api_request('GET', url, params=params, timeout=30)

        if response is None:
            msg = 'Clocking range API request failed: no response'
            if raise_on_error:
                raise ValidationError(msg)
            return {'Error': msg}

        if response.status_code != 200:
            msg = f'Clocking range API request failed with status {response.status_code}'
            if raise_on_error:
                raise ValidationError(msg)
            return {'Error': msg, 'Status': response.status_code}

        try:
            data = response.json()
        except ValueError:
            msg = 'Invalid JSON in clocking range response'
            if raise_on_error:
                raise ValidationError(msg)
            return {'Error': msg, 'Status': response.status_code}

        if isinstance(data, dict) and 'Data' in data:
            records = data['Data']
        else:
            records = data

        records = self._annotate_clocking_records(records)
        count = len(records) if isinstance(records, list) else 1
        _logger.info('[Geodynamics] Retrieved %d clocking (range) entries', count)
        return {'Success': True, 'Data': records, 'Count': count}

    ACTIVITY_START_TYPES = {1, 3, 12, 19}
    ACTIVITY_END_TYPES = {2, 4, 5, 6, 14, 20}

    def _extract_clock_dt(self, rec):
        """Try to extract a datetime object from a clocking record.
        Priority order now:
          1. DateTimeLocal (converted to UTC naive if tz provided)
          2. Other known datetime keys (Date, DateTime, ClockingDate, ClockingDateUtc, Timestamp, Time)
        Supports ISO8601 with timezone offsets (e.g. 2025-10-05T08:30:00+02:00 or Z).
        """
        if not isinstance(rec, dict):
            return None
        # Priority: DateTimeLocal
        dt_local = rec.get('DateTimeLocal')
        if dt_local:
            if isinstance(dt_local, datetime):
                dt = dt_local
            else:
                dt = None
                if isinstance(dt_local, str):
                    iso_candidate = dt_local.strip()
                    try:
                        # normalize Z to +00:00 for fromisoformat
                        iso_candidate_norm = iso_candidate.replace('Z', '+00:00')
                        dt = datetime.fromisoformat(iso_candidate_norm)
                    except Exception:
                        # fallback to existing patterns
                        for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f'):
                            try:
                                dt = datetime.strptime(iso_candidate[:26], fmt)
                                break
                            except ValueError:
                                continue
                if dt:
                    # If timezone-aware, convert to UTC then make naive for internal consistency
                    if dt.tzinfo:
                        dt = dt.astimezone(pytz.UTC).replace(tzinfo=None)
                    return dt
        # Fallback candidates (legacy)
        candidates = [
            rec.get('Date'), rec.get('DateTime'), rec.get('ClockingDate'),
            rec.get('ClockingDateUtc'), rec.get('Timestamp'), rec.get('Time')
        ]
        for val in candidates:
            if not val:
                continue
            if isinstance(val, datetime):
                return val if not val.tzinfo else val.astimezone(pytz.UTC).replace(tzinfo=None)
            if isinstance(val, str):
                for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f'):
                    try:
                        dt = datetime.strptime(val[:26], fmt)
                        return dt
                    except ValueError:
                        continue
                # try ISO with timezone as last resort
                try:
                    iso_candidate_norm = val.replace('Z', '+00:00')
                    dt_iso = datetime.fromisoformat(iso_candidate_norm)
                    if dt_iso.tzinfo:
                        dt_iso = dt_iso.astimezone(pytz.UTC).replace(tzinfo=None)
                    return dt_iso
                except Exception:
                    pass
        return None

    def compute_clocking_activity_durations(self, clockings):
        """Compute active duration (minutes & hours) from raw clocking records.

        Rules:
          Start activity types: 1,3,12,19
          End activity types:   2,4,5,6,14,20
          Each start opens a period until the next end; unmatched starts at end are ignored.
        Returns dict with intervals and totals.
        """
        if not clockings:
            return {'intervals': [], 'total_minutes': 0, 'total_hours': 0.0}
        # Normalize & sort
        norm = []
        for rec in clockings if isinstance(clockings, list) else [clockings]:
            dt = self._extract_clock_dt(rec)
            if not dt:
                continue
            t = rec.get('Type')
            norm.append({'dt': dt, 'Type': t, 'TypeLabel': rec.get('TypeLabel')})
        norm.sort(key=lambda x: x['dt'])

        intervals = []
        current_start = None
        current_start_type = None
        for item in norm:
            t = item['Type']
            if t in self.ACTIVITY_START_TYPES:
                # If there is an open start without end, we discard and start anew
                # If start is same day, ignore (avoid duplicates)
                if current_start and current_start.date() == item['dt'].date():
                    continue
                current_start = item['dt']
                current_start_type = t
            elif t in self.ACTIVITY_END_TYPES and current_start:
                if item['dt'] > current_start:
                    delta = item['dt'] - current_start
                    minutes = int(delta.total_seconds() // 60)
                    if minutes > 0:
                        intervals.append({
                            'start': current_start,
                            'end': item['dt'],
                            'minutes': minutes,
                            'hours': round(minutes / 60.0, 2),
                            'started_type': current_start_type,
                            'ended_type': t,
                        })
                # reset after end
                current_start = None
                current_start_type = None
        total_minutes = sum(i['minutes'] for i in intervals)
        return {
            'intervals': intervals,
            'total_minutes': total_minutes,
            'total_hours': round(total_minutes / 60.0, 2)
        }

    def getLocationsByResourcesAndDate(self, resource_ids, day=None, raise_on_error=False, from_day=None, to_day=None):
        """Fetch location positions for a list of resources for a given date or date range.

        Endpoint:
            POST https://api.intellitracer.be/api/v1/location/position?from=<fromDate>&to=<toDate>
            Body: JSON array of resource GUIDs ["...","..."]

        Args:
            resource_ids (list[str]): List of resource GUID strings.
            day (str|date|datetime, optional): Single day ('YYYY-MM-DD') to query 00:00:00..23:59:59.
            raise_on_error (bool): If True, raise ValidationError on error; else return {'Error': msg, ...}.
            from_day (str|date|datetime, optional): Start day of range ('YYYY-MM-DD').
            to_day (str|date|datetime, optional): End day of range ('YYYY-MM-DD').

        Behavior:
            - If from_day and to_day are provided, use the date range [from_day 00:00:00, to_day 23:59:59].
            - Else if day is provided, query that full day.
            - Else return an error for missing date inputs.

        Returns (dict):
            On success: {'Success': True, 'Data': <list>, 'Count': n}
            On error:   {'Error': msg, 'Status': <http_status>?}
        """
        if not resource_ids or not isinstance(resource_ids, (list, tuple)):
            return {'Error': 'resource_ids must be a non-empty list'}

        try:
            if from_day is not None and to_day is not None:
                from_date = self._parse_input_date(from_day)
                to_date = self._parse_input_date(to_day)
                # normalize order if swapped
                if from_date > to_date:
                    _logger.warning('[Geodynamics] from_day > to_day; swapping values: %s > %s', from_date, to_date)
                    from_date, to_date = to_date, from_date
                from_dt = datetime.combine(from_date, datetime.min.time())
                to_dt = datetime.combine(to_date, datetime.min.time()).replace(hour=23, minute=59, second=59)
            elif day is not None:
                day_date = self._parse_input_date(day)
                from_dt = datetime.combine(day_date, datetime.min.time())
                to_dt = from_dt.replace(hour=23, minute=59, second=59)
            else:
                return {'Error': 'Missing date input: provide either day, or from_day and to_day'}
        except ValidationError as ve:
            if raise_on_error:
                raise
            return {'Error': str(ve)}

        url = 'https://api.intellitracer.be/api/v1/location/position'
        params = {
            'from': self.convert_to_utc(from_dt),
            'to': self.convert_to_utc(to_dt),
        }

        response = self._api_request('POST', url, params=params, json_body=list(resource_ids), timeout=60)

        if response is None:
            msg = 'Location API request failed: no response'
            if raise_on_error:
                raise ValidationError(msg)
            return {'Error': msg}

        if response.status_code != 200:
            msg = f'Location API request failed with status {response.status_code}'
            if raise_on_error:
                raise ValidationError(msg)
            return {'Error': msg, 'Status': response.status_code}

        try:
            data = response.json()
        except ValueError:
            msg = 'Invalid JSON in location response'
            if raise_on_error:
                raise ValidationError(msg)
            return {'Error': msg, 'Status': response.status_code}

        records = data.get('Data') if isinstance(data, dict) and 'Data' in data else data
        count = len(records) if isinstance(records, list) else (1 if records else 0)

        _logger.info('[Geodynamics] Retrieved %d location resource entries for range %s -> %s', count, from_dt.date().isoformat(), to_dt.date().isoformat())
        return {'Success': True, 'Data': records, 'Count': count}

    def getLocationStatus(self, resource_id, fromDateTime, toDateTime, raise_on_error=False):
        """Fetch location status timeline for a resource within a datetime range.

        Endpoint:
            GET https://api.intellitracer.be/api/v1/location/status?resourceId=<id>&from=<fromDate>&to=<toDate>

        Args:
            resource_id (str): Resource GUID.
            fromDateTime (str|datetime): Start datetime ('%Y-%m-%d %H:%M:%S' or datetime).
            toDateTime (str|datetime): End datetime ('%Y-%m-%d %H:%M:%S' or datetime).
            raise_on_error (bool): If True, raise ValidationError on error; else return {'Error': msg, ...}.

        Returns (dict):
            On success: {'Success': True, 'Data': <dict|list>, 'Count': <int>}
            On error:   {'Error': msg, 'Status': <http_status>?}
        """
        if not resource_id:
            return {'Error': 'Missing required parameter: resource_id'}
        if not (fromDateTime and toDateTime):
            return {'Error': 'Missing required parameters fromDateTime/toDateTime'}

        try:
            from_dt = self._parse_input_dt(fromDateTime)
            to_dt = self._parse_input_dt(toDateTime)
        except ValidationError as ve:
            if raise_on_error:
                raise
            return {'Error': str(ve)}

        if from_dt > to_dt:
            _logger.warning('[Geodynamics] getLocationStatus: from > to; swapping values: %s > %s', from_dt, to_dt)
            from_dt, to_dt = to_dt, from_dt

        url = 'https://api.intellitracer.be/api/v1/location/status'
        params = {
            'resourceId': resource_id,
            'from': self.convert_to_utc(from_dt),
            'to': self.convert_to_utc(to_dt),
        }
        response = self._api_request('GET', url, params=params, timeout=60)

        if response is None:
            msg = 'Location status API request failed: no response'
            if raise_on_error:
                raise ValidationError(msg)
            return {'Error': msg}

        if response.status_code != 200:
            msg = f'Location status API request failed with status {response.status_code}'
            if raise_on_error:
                raise ValidationError(msg)
            return {'Error': msg, 'Status': response.status_code}

        try:
            data = response.json()
        except ValueError:
            msg = 'Invalid JSON in location status response'
            if raise_on_error:
                raise ValidationError(msg)
            return {'Error': msg, 'Status': response.status_code}

        count = 0
        if isinstance(data, dict):
            results = data.get('StatusResults')
            if isinstance(results, list):
                count = len(results)
            else:
                count = 1 if data else 0
        elif isinstance(data, list):
            count = len(data)
        else:
            count = 1 if data else 0

        _logger.info('[Geodynamics] Retrieved location status for resource %s: count=%d', resource_id, count)
        return {'Success': True, 'Data': data, 'Count': count}

    def _extract_status_bars(self, data):
        """Normalize a location/status response payload into a flat list of Bar dicts."""
        results = []
        if isinstance(data, dict):
            res_list = data.get('StatusResults')
            if isinstance(res_list, list):
                results = res_list
            elif 'Bars' in data:
                results = [data]
        elif isinstance(data, list):
            results = data
        bars = []
        for res_item in results:
            if not isinstance(res_item, dict):
                continue
            item_bars = res_item.get('Bars')
            if isinstance(item_bars, list):
                bars.extend(b for b in item_bars if isinstance(b, dict))
        return bars

    # Keys that hold an ABSOLUTE odometer / running-hours counter on a
    # location/status Bar or StatusResult item (deliberately excludes the
    # delta fields MileageDriven / HoursDriven).
    STATUS_ODOMETER_KEYS = (
        'MileageStop', 'MileageEnd', 'StopMileage', 'EndMileage',
        'MileageStart', 'StartMileage', 'OdometerStop', 'OdometerStart',
        'Odometer', 'TotalMileage', 'CurrentMileage', 'Kilometers',
    )
    STATUS_RUNNING_HOURS_KEYS = (
        'RunningHoursStop', 'RunningHoursEnd', 'RunningHoursStart',
        'RunningHours', 'TotalRunningHours', 'CurrentRunningHours',
        'OperatingHours', 'EngineHours',
    )

    @staticmethod
    def _max_counter(record, keys, current):
        """Return max(current, highest numeric value among keys in record)."""
        for key in keys:
            val = record.get(key)
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                continue
            if current is None or float(val) > current:
                current = float(val)
        return current

    def getResourceMileage(self, resource_id, fromDateTime, toDateTime, raise_on_error=False):
        """Total kilometers driven and driving time for a resource (vehicle) in a period.

        Fetches GET /api/v1/location/status in 30-day chunks and sums the
        `MileageDriven` of every Bar, plus the Bar durations (Start..Stop).
        Additionally scans Bars and StatusResult items for absolute odometer /
        running-hours counters (e.g. MileageStop) and reports the highest value
        found, which corresponds to the vehicle's total as shown in Geodynamics.

        Returns (dict):
            On success: {'Success': True, 'total_km': float, 'total_hours': float,
                         'bars': <nr of bars counted>,
                         'odometer_km': float|None, 'running_hours': float|None}
            On error:   {'Error': msg}
        """
        if not resource_id:
            return {'Error': 'Missing required parameter: resource_id'}
        try:
            from_dt = self._parse_input_dt(fromDateTime)
            to_dt = self._parse_input_dt(toDateTime)
        except ValidationError as ve:
            if raise_on_error:
                raise
            return {'Error': str(ve)}
        if from_dt >= to_dt:
            return {'Success': True, 'total_km': 0.0, 'total_hours': 0.0, 'bars': 0,
                    'odometer_km': None, 'running_hours': None}

        total_km = 0.0
        total_minutes = 0.0
        bars_counted = 0
        odometer_km = None
        running_hours = None
        sample_logged = False
        chunk_start = from_dt
        first_chunk = True
        while chunk_start < to_dt:
            chunk_end = min(chunk_start + timedelta(days=30), to_dt)
            res = self.getLocationStatus(resource_id, chunk_start, chunk_end, raise_on_error=raise_on_error)
            if res.get('Error'):
                if first_chunk:
                    return res
                _logger.warning('[Geodynamics] getResourceMileage: chunk %s -> %s failed for %s: %s',
                                chunk_start, chunk_end, resource_id, res.get('Error'))
                chunk_start = chunk_end
                first_chunk = False
                continue
            data = res.get('Data')
            # Scan StatusResult items themselves for absolute counters too
            if isinstance(data, dict) and isinstance(data.get('StatusResults'), list):
                for res_item in data['StatusResults']:
                    if isinstance(res_item, dict):
                        odometer_km = self._max_counter(res_item, self.STATUS_ODOMETER_KEYS, odometer_km)
                        running_hours = self._max_counter(res_item, self.STATUS_RUNNING_HOURS_KEYS, running_hours)
            for bar in self._extract_status_bars(data):
                if not sample_logged:
                    _logger.info('[Geodynamics] getResourceMileage: sample Bar keys for %s: %s',
                                 resource_id, sorted(bar.keys()))
                    sample_logged = True
                odometer_km = self._max_counter(bar, self.STATUS_ODOMETER_KEYS, odometer_km)
                running_hours = self._max_counter(bar, self.STATUS_RUNNING_HOURS_KEYS, running_hours)
                mileage = bar.get('MileageDriven')
                if not isinstance(mileage, (int, float)):
                    continue
                total_km += float(mileage)
                bars_counted += 1
                try:
                    bar_start = self._parse_input_dt(bar['Start']) if bar.get('Start') else None
                    bar_stop = self._parse_input_dt(bar['Stop']) if bar.get('Stop') else None
                    if bar_start and bar_stop and bar_stop > bar_start:
                        total_minutes += (bar_stop - bar_start).total_seconds() / 60.0
                except Exception:
                    pass
            chunk_start = chunk_end
            first_chunk = False

        _logger.info('[Geodynamics] getResourceMileage: resource=%s %s -> %s: %.2f km, %.2f h over %d bars, '
                     'odometer=%s, running_hours=%s',
                     resource_id, from_dt, to_dt, total_km, total_minutes / 60.0, bars_counted,
                     odometer_km, running_hours)
        return {
            'Success': True,
            'total_km': round(total_km, 2),
            'total_hours': round(total_minutes / 60.0, 2),
            'bars': bars_counted,
            'odometer_km': round(odometer_km, 2) if odometer_km is not None else None,
            'running_hours': round(running_hours, 2) if running_hours is not None else None,
        }
