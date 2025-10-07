# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import requests
from requests.auth import HTTPBasicAuth

from odoo import fields, models, api
import json
from . import gdhandler
from .gdhandler import GeodynamicsHandler
import random


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    geodynamics_company = fields.Char(string='Geodynamics company', config_parameter='geodynamics.company')
    geodynamics_login = fields.Char(string='Geodynamics username', config_parameter='geodynamics.username')
    geodynamics_password = fields.Char(string='Geodynamics password', config_parameter='geodynamics.password')

    geodynamics_postcalcsource = fields.Selection(selection=[('timesheet','Timesheetevents'),('postcalculation', 'Postcalculationevents')],string='Bron nacalculatie',required=True,default='postcalculation', config_parameter='geodynamics.postcalcsource')

    geodynamics_warning_planning_overlap = fields.Boolean(string='Toon waarschuwing wanneer planningen overlappen', default=True, config_parameter='geodynamics.wapp')

    df_persones_gd_ids = fields.Many2many('hr.employee', string='Personen geodynamics',
                                                            compute='_wn_pers_gd')

    df_plan_directly = fields.Boolean(string='Plan rechtstreeks in naar Geodynamics bij wijzigen taak', config_parameter='geodynamics.plandirectly')

    def zetDemoAdressen(self):
        adresses = [
  {
    "street": "Rue de la Loi 42",
    "street2": "",
    "zip": "1040",
    "city": "Brussel",
    "country_id": 20
  },
  {
    "street": "Meir 15",
    "street2": "",
    "zip": "2000",
    "city": "Antwerpen",
    "country_id": 20
  },
  {
    "street": "Naamsestraat 84",
    "street2": "",
    "zip": "3000",
    "city": "Leuven",
    "country_id": 20
  },
  {
    "street": "Koningin Astridlaan 132",
    "street2": "",
    "zip": "9000",
    "city": "Gent",
    "country_id": 20
  },
  {
    "street": "Boulevard Tirou 67",
    "street2": "",
    "zip": "6000",
    "city": "Charleroi",
    "country_id": 20
  },
  {
    "street": "Luikersteenweg 101",
    "street2": "",
    "zip": "3500",
    "city": "Hasselt",
    "country_id": 20
  },
  {
    "street": "Chaussée de Mons 230",
    "street2": "",
    "zip": "1070",
    "city": "Anderlecht",
    "country_id": 20
  },
  {
    "street": "Zandstraat 9",
    "street2": "",
    "zip": "8000",
    "city": "Brugge",
    "country_id": 20
  },
  {
    "street": "Rue du Moulin 56",
    "street2": "",
    "zip": "5000",
    "city": "Namen",
    "country_id": 20
  },
  {
    "street": "Avenue des Champs 11",
    "street2": "",
    "zip": "1348",
    "city": "Louvain-la-Neuve",
    "country_id": 20
  }
]

        for r in self.env['res.partner'].search([]):
            random_int = random.randint(0, 9)
            randomAdress = adresses[random_int]
            r.write(randomAdress)

    def gd_get_handler(self):
        """Retrieve or create an instance of GeodynamicsHandler"""
        if 'gd_handler' not in self.env.context:
            if not self.geodynamics_login or not self.geodynamics_password or not self.geodynamics_company:
                raise ValueError("Geodynamics credentials are missing.")

            handler = GeodynamicsHandler(self.geodynamics_login, self.geodynamics_password, self.geodynamics_company, self.env)
            self = self.with_context(gd_handler=handler)  # Store in context
        return self.env.context['gd_handler']

    def gd_test_verbinding(self):
        """Test connection with Geodynamics"""
        if not self.geodynamics_login or not self.geodynamics_password or not self.geodynamics_company:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': "Error",
                    'type': 'danger',
                    'message': 'Login, password, and company are required to test the connection.',
                },
            }

        try:
            testRes = self.gd_get_handler().test()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': "Webservice Status",
                    'type': testRes[0],
                    'message': testRes[1]
                },
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': "Connection Error",
                    'type': 'danger',
                    'message': f"An error occurred: {str(e)}",
                },
            }

    def gd_fleet_to_odoo(self):
        handler = self.gd_get_handler()
        handler.loadFleetData()  # Assuming this method exists in GeodynamicsHandler

    def gd_erase_planningen(self):
        handler = self.gd_get_handler()
        print('hi')

    def gd_fetch_planningen(self):
        handler = self.gd_get_handler()
        handler.laadAllPlanning()

    def gd_poitype_to_odoo(self):
        handler = self.gd_get_handler()
        handler.laadPoiTypes()

    def _wn_pers_gd(self):
        for record in self:
            output = []

            for usr in self.env['hr.employee'].search([]):
                output.append(usr.id)

            record.df_persones_gd_ids = output




