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
        if self.gd_login != None and self.gd_company != None and self.gd_password != None:
            self.auth = HTTPBasicAuth(str(self.gd_login) + '|' + str(self.gd_company), str(self.gd_password))

    def test(self):

        response = requests.get(self.baseUrl + '/user', auth=self.auth)

        #print(response)
        #print(response.text)

        if response.status_code != 200:
            return ['danger', 'Fout bij verbinden']
        else:
            return ['success', 'Verbinding gelukt']

    def loadFleetData(self):
        print('load fleet data')
        for r in self.env['sale.order'].search([]):
            print(r.id)

    def createPlanning(self, userId, fromDateTime, toDateTime, activityNumber, nPoiId=None):
        url = 'https://api.intellitracer.be/api/v3/planning'

        sJson = {'UserId':userId, 'FromDateUtc':self.convert_to_utc(fromDateTime), 'ToDateUtc':self.convert_to_utc(toDateTime), 'ActivityNumber':activityNumber, 'Description':activityNumber}

        if nPoiId != None:
            sJson['PoiId'] = nPoiId

        print(json.dumps(sJson))

        self.deletePlanningUser(userId, fromDateTime, toDateTime)

        response = requests.put(url, json=sJson, auth=self.auth)
        self.sleep()

        if response.status_code != 200:
            print('Request failed with status code: ' + str(response.status_code))
            print(response)
            print(response.text)
        else:
            sOutputJson = response.json()
            return sOutputJson["Data"]["Id"]

    def createPlanningByTask(self, sTask):
        for usr in sTask.df_assignees_with_geodynamics_ids:
            sNaam = sTask.df_gd_name
            print(sNaam)
            sId = self.createPlanning(usr.df_geodynamics_id, sTask.planned_date_start, sTask.date_deadline, sNaam)
            print(sId)

            sValues = {'start_datetime':sTask.planned_date_start, 'end_datetime':sTask.date_deadline, 'id_geodynamics':sId,
                       'user_id_geodynamics':usr.df_geodynamics_id, 'user_id':usr.id, 'task_id':sTask.id, 'activitynumber':sNaam}
            self.env['df.geodynamics.planning'].create(sValues)

    def removePlanning_emp(self, taskId, empId):
        pls = self.env['df.geodynamics.planning'].search([('task_id','=',taskId),('employee_id','=',empId)])

        for p in pls:
            self.removePlanning(p.id_geodynamics)
            p.unlink()

    def removePlanning_task(self, sTask):
        pls = self.env['df.geodynamics.planning'].search([('task_id', '=', sTask.id)])

        for p in pls:
            self.removePlanning(p.id_geodynamics)
            p.unlink()

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
        workday_start_hour = 6
        workday_end_hour = 15
        results = []

        print(start_datetime)
        print(end_datetime)

        current_day = start_datetime.date()
        last_day = end_datetime.date()

        while current_day <= last_day:
            if self.isWeekendOrHoliday(current_day):
                current_day += timedelta(days=1)
                continue

            is_start_day = current_day == start_datetime.date()
            is_end_day = current_day == end_datetime.date()

            day_start = datetime.combine(current_day, datetime.min.time()).replace(hour=workday_start_hour)
            default_day_end = datetime.combine(current_day, datetime.min.time()).replace(hour=workday_end_hour)

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
        print(periodItems)

    def createPlanningByTaskWn(self, sTask):
        nAmount = 0

        self.removePlanning_task(sTask)

        for usr in sTask.employee_ids:
            if usr.df_geodynamics_id == False:
                continue
            sNaam = sTask.df_gd_name
            print(sNaam)

            self.removePlanning_emp(sTask.id, usr.id)

            if sTask.partner_id.df_geodynamics_poi_id != False:
                poiId = sTask.partner_id.df_geodynamics_poi_id
            else:
                sTask.partner_id.sync_poi_geodynamics()
                poiId = sTask.partner_id.df_geodynamics_poi_id

            periodItems = self.split_into_workdays(sTask.planned_date_start, sTask.date_deadline)

            print('Period items: ')
            print(periodItems)

            if periodItems == []:
                raise ValidationError('No periods. There must be a period within the working days.')

            for p in periodItems:
                try:
                    sId = self.createPlanning(usr.df_geodynamics_id, p[0], p[1], sNaam, poiId)
                    print(sId)

                    sValues = {'start_datetime':p[0], 'end_datetime':p[1], 'id_geodynamics':sId,
                               'user_id_geodynamics':usr.df_geodynamics_id, 'employee_id':usr.id, 'task_id':sTask.id, 'activitynumber':sNaam}
                    self.env['df.geodynamics.planning'].create(sValues)
                    nAmount = nAmount + 1
                except:
                    _logger.error('Error while adding planning: ' + str(sId))
                    raise ValidationError('Error while adding planning')

        return nAmount

    def laadPostcalc(self, userId, ddate):
        url = 'https://api.intellitracer.be/api/v2/postcalculation/export'

        sJson = {'UserIds': [userId], 'AllUsers':False, 'Mode':0, 'GroupCostcenterByActivity':False, 'DateUtc':self.convert_to_utc(ddate),
                 'IncludeTimesheet:':False, 'IncludeTimesheetEvents':True, 'IncludeTimeValidation':False,
                 'IncludePostCalculationLog':False, 'IncludeLossCostcenter':False}

        print(sJson)

        response = requests.post(url, json=sJson, auth=self.auth)
        self.sleep()

        if response.status_code != 200:
            print('Request failed with status code: ' + str(response.status_code))
            #print(response)
            #print(response.text)
        else:
            print('Success')
            #print(response.text)
            return response.json()

    def deletePlanning(self, sRecord):
        totalDeletions = 0
        allWn = []
        for s in sRecord.employee_ids:
            allWn.append(s.id)

        print(allWn)

        for r in self.env['df.geodynamics.planning'].search([('task_id','=',sRecord.id)]):
            if r.employee_id.id not in allWn:
                self.removePlanning(r.id_geodynamics)
                r.unlink()
                totalDeletions = totalDeletions + 1

        return totalDeletions

    def deletePlanning2(self, sRecord):
        totalDeletions = 0

        planIds = [sRecord.id]

        for p in planIds:
            for r in self.env['df.geodynamics.planning'].search([('task_id','=',p.id)]):
                    self.removePlanning(r.id_geodynamics)
                    r.unlink()

        return totalDeletions

    def deletePlanning3(self, pId):

        for r in self.env['df.geodynamics.planning'].search([('id','=',pId)]):
            self.removePlanning(r.id_geodynamics)
            r.unlink()

    def deletePlanningUser(self, userId, fromDateTime, toDateTime):
        url = 'https://api.intellitracer.be/api/v1/byuseriddaterange'

        params = {'userId':userId, 'fromDate':self.convert_to_utc(fromDateTime), 'toDate':self.convert_to_utc(toDateTime)}

        response = requests.delete(url, params=params, auth=self.auth)
        self.sleep()

        print(f"Status Code= {response.status_code}")
        print(f"Response: {response.text}")
        print(self.auth)
        print(response.text)

    def removePlanning(self, planningId):
        url = 'https://api.intellitracer.be/api/v2/planning/' + planningId

        response = requests.delete(url, auth=self.auth)
        self.sleep()

        print(f"Status Code= {response.status_code}")
        print(f"Response: {response.text}")
        print(self.auth)
        print(response.text)

    def laadAllPlanning(self):
        start_date = datetime(2025, 1, 1)  # January 1, 2025
        end_date = datetime(2025, 9, 30)  # December 31, 2030

        jump_days = 30

        for r in self.env['hr.employee'].search([('df_geodynamics_id','!=',False)]):
            current_date = start_date

            while current_date <= end_date:

                to_date = current_date + timedelta(days=jump_days)

                self.laadPlanning(r.df_geodynamics_id, current_date, to_date)

                current_date = current_date + timedelta(days=jump_days)

    def laadPoiTypes(self):
        url = 'https://api.intellitracer.be/api/v1/poitype'

        response = requests.get(url, auth=self.auth)
        self.sleep()

        responseJson = response.json()

        for r in responseJson:
            curR = self.env['df.geodynamics.poitype'].search([('id_geodynamics','=',r['Id'])])

            if not curR:
                self.env['df.geodynamics.poitype'].create({'id_geodynamics':r['Id'], 'Name':r['Name']})

    def laadPlanning(self, userId, fromDate, toDate):
        url = 'https://api.intellitracer.be/api/v1/byuseriddaterange'

        params = {'userId':userId, 'fromDate':self.convert_to_utc(fromDate), 'toDate':self.convert_to_utc(toDate)}

        response = requests.get(url, params=params, auth=self.auth)
        self.sleep()

        print(f"Status Code= {response.status_code}")
        print(f"Response: {response.text}")
        print(self.auth)
        print(response.text)
        print(response.url)

        response_json = response.json()
        if response_json:
            for r in response_json:
                sValues = {'start_datetime':self.convert_to_datetime(r['FromDate']), 'end_datetime':self.convert_to_datetime(r['ToDate']), 'id_geodynamics':r['Id'], 'user_id_geodynamics':r['User']['Id']}
                print(sValues)
                self.env['df.geodynamics.planning'].create(sValues)


    def convert_to_utc(self, dt):
        return dt.strftime('%Y-%m-%dT%H:%M:%S')

    def convert_to_datetime(self, date_string):
        return datetime.strptime(date_string, "%Y-%m-%dT%H:%M:%S")

    def sleep(self):
        time.sleep(0.1)

    def addPoi(self, sContact):
        url = 'https://api.intellitracer.be/api/v1/poi'

        defaultPoitypes = self.env['df.geodynamics.poitype'].search([])

        defPoiType = defaultPoitypes[0]

        poiData = {'Name':sContact.name, 'PoiType':{'Id':defPoiType.id_geodynamics}, 'Street':sContact.street, 'City':sContact.city, 'PostalCode':sContact.zip, 'Priority':'-', 'ReverseGeocoding':False}

        filtered_dict = {key: value for key, value in poiData.items() if value is not False}

        print(poiData)
        print(url)
        print(filtered_dict)

        data = {
            "Name": "Work",
            "Code": "012345",
            "PoiType": {
                "Id": "7515a948-0039-4c4f-8ade-a70705030ad6"
            },
            "IsAssetLocation": False,
            "Street": "Dumolinlaan",
            "HouseNumber": "9",
            "City": "Kortrijk",
            "Submunicipality": "Kortrijk",
            "PostalCode": "8500",
            "Country": 0,
            "Priority": "0",
            "Description": "Work",
            "MarkerLon": 3.145219,
            "MarkerLat": 50.81309,
            "IsLambert72": False,
            "Radius": 0.03,
            "ReverseGeocoding": False
        }

        response = requests.put(url, json=poiData, auth=self.auth)

        print("Request URL: %s", response.request.url)
        print("Request Headers: %s", response.request.headers)
        print("Request Body: %s", response.request.body)

        _logger.info("Request URL: %s", response.request.url)
        _logger.info("Request Headers: %s", response.request.headers)
        _logger.info("Request Body: %s", response.request.body)

        if response.status_code != 200:
            print('Request failed with status code: ' + str(response.status_code))
            print(response)
            print(response.text)
            print(response.url)
            _logger.debug('Error occured: ' + response.text)
            sOutput = response.json()
            return {'Error':sOutput[0]['Message']}
        else:
            sOutput = response.json()
            return {'Succes':sOutput}






