# -*- coding: utf-8 -*-
# from odoo import http


# class Geodynamics(http.Controller):
#     @http.route('/geodynamics/geodynamics', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/geodynamics/geodynamics/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('geodynamics.listing', {
#             'root': '/geodynamics/geodynamics',
#             'objects': http.request.env['geodynamics.geodynamics'].search([]),
#         })

#     @http.route('/geodynamics/geodynamics/objects/<model("geodynamics.geodynamics"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('geodynamics.object', {
#             'object': obj
#         })

