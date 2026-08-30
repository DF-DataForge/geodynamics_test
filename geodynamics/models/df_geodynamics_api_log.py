# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
from odoo import models, fields, api, _
import json
import base64
import logging

_logger = logging.getLogger(__name__)


class GeodynamicsApiLog(models.Model):
    _name = 'df.geodynamics.api.log'
    _description = 'Geodynamics API Log'
    _order = 'create_date desc'

    df_name = fields.Char(string='Endpoint', required=True, index=True)
    df_method = fields.Selection([
        ('GET', 'GET'),
        ('POST', 'POST'),
        ('PUT', 'PUT'),
        ('DELETE', 'DELETE'),
        ('LOG', 'LOG'),
    ], string='HTTP Method', required=True)
    df_url = fields.Char(string='Full URL')
    df_request_payload = fields.Json(string='Request Payload')
    df_response_payload = fields.Json(string='Response Payload')
    df_response_status = fields.Integer(string='HTTP Status Code')
    df_success = fields.Boolean(string='Success', compute='_compute_success', store=True)
    df_duration_ms = fields.Integer(string='Duration (ms)')
    df_error_message = fields.Text(string='Error Message')
    df_user_id = fields.Many2one('res.users', string='Triggered By', default=lambda self: self.env.uid)
    df_request_payload_text = fields.Text(string='Request Payload Text', compute='_compute_payload_text')
    df_response_payload_text = fields.Text(string='Response Payload Text', compute='_compute_payload_text')

    @api.depends('df_request_payload', 'df_response_payload')
    def _compute_payload_text(self):
        for rec in self:
            rec.df_request_payload_text = json.dumps(rec.df_request_payload, indent=2, ensure_ascii=False) if rec.df_request_payload else ''
            rec.df_response_payload_text = json.dumps(rec.df_response_payload, indent=2, ensure_ascii=False) if rec.df_response_payload else ''

    @api.depends('df_response_status')
    def _compute_success(self):
        for rec in self:
            rec.df_success = rec.df_response_status == 200 if rec.df_response_status else False

    @api.model
    def cleanup_old_logs(self, days=None):
        """Remove API logs older than the configured retention period."""
        if days is None:
            days = int(self.env['ir.config_parameter'].sudo().get_param(
                'geodynamics.api_log_retention_days', '30'))
        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(days=days)
        old_logs = self.search([('create_date', '<', cutoff.strftime('%Y-%m-%d'))])
        count = len(old_logs)
        old_logs.unlink()
        _logger.info('[Geodynamics] Cleaned up %d old API log entries (older than %d days)', count, days)
        return count

    def action_view_json(self):
        """Open the request + response payloads as formatted JSON in a new tab."""
        self.ensure_one()
        content = json.dumps({
            'endpoint': self.df_name,
            'method': self.df_method,
            'url': self.df_url,
            'status': self.df_response_status,
            'request_payload': self.df_request_payload,
            'response_payload': self.df_response_payload,
        }, indent=2, ensure_ascii=False)
        attachment = self.env['ir.attachment'].create({
            'name': 'geodynamics_api_log_%s.json' % self.id,
            'type': 'binary',
            'datas': base64.b64encode(content.encode('utf-8')),
            'mimetype': 'application/json',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=false' % attachment.id,
            'target': 'new',
        }

    def action_export_xml(self):
        """Export selected log entries as a single XML file for debugging."""
        from xml.etree.ElementTree import Element, SubElement, tostring
        from xml.dom.minidom import parseString

        root = Element('geodynamics_logs')
        for rec in self.sorted(key=lambda r: r.create_date):
            entry = SubElement(root, 'entry', id=str(rec.id))
            SubElement(entry, 'created').text = str(rec.create_date)
            SubElement(entry, 'method').text = rec.df_method or ''
            SubElement(entry, 'endpoint').text = rec.df_name or ''
            SubElement(entry, 'url').text = rec.df_url or ''
            SubElement(entry, 'status').text = str(rec.df_response_status)
            SubElement(entry, 'success').text = str(rec.df_success)
            SubElement(entry, 'duration_ms').text = str(rec.df_duration_ms)
            SubElement(entry, 'triggered_by').text = rec.df_user_id.name if rec.df_user_id else ''
            SubElement(entry, 'request_payload').text = json.dumps(
                rec.df_request_payload, indent=2, ensure_ascii=False) if rec.df_request_payload else ''
            SubElement(entry, 'response_payload').text = json.dumps(
                rec.df_response_payload, indent=2, ensure_ascii=False) if rec.df_response_payload else ''
            if rec.df_error_message:
                SubElement(entry, 'error_message').text = rec.df_error_message

        xml_str = parseString(tostring(root, encoding='unicode')).toprettyxml(indent='  ')
        attachment = self.env['ir.attachment'].create({
            'name': 'geodynamics_logs.xml',
            'type': 'binary',
            'datas': base64.b64encode(xml_str.encode('utf-8')),
            'mimetype': 'application/xml',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }
