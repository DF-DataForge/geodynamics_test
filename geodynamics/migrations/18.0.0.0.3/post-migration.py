# -*- coding: utf-8 -*-
# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
from odoo import api, SUPERUSER_ID
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info("Migration {version}: start.".format(version=version))
    if not version:
        return
    # Detect legacy columns: lowercase (df_starttime/df_endtime) or camelCase (df_startTime/df_endTime)
    cr.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_name = 'account_analytic_line'
           AND column_name IN ('df_starttime', 'df_endtime', 'df_startTime', 'df_endTime')
        """
    )
    cols = {r[0] for r in cr.fetchall()}

    start_src = None
    end_src = None
    if 'df_starttime' in cols:
        start_src = 'df_starttime'
    elif 'df_startTime' in cols:
        start_src = 'df_startTime'
    if 'df_endtime' in cols:
        end_src = 'df_endtime'
    elif 'df_endTime' in cols:
        end_src = 'df_endTime'

    if not start_src and not end_src:
        _logger.info("[Geodynamics] Migration 18.0.0.0.3: no legacy columns found; nothing to migrate.")
        return

    set_parts = []
    where_parts = []
    if start_src:
        set_parts.append(f'df_start_time = COALESCE(df_start_time, "{start_src}"::timestamp)')
        where_parts.append(f'"{start_src}" IS NOT NULL')
    if end_src:
        set_parts.append(f'df_end_time   = COALESCE(df_end_time,   "{end_src}"::timestamp)')
        where_parts.append(f'"{end_src}" IS NOT NULL')

    set_sql = ",\n               ".join(set_parts)
    where_sql = " OR ".join(where_parts)

    query = f"""
        UPDATE account_analytic_line
           SET {set_sql}
         WHERE ({where_sql})
          AND (df_start_time IS NULL OR df_end_time IS NULL)
    """
    cr.execute(query)
    _logger.info("[Geodynamics] Migration 18.0.0.0.3: updated %s timesheet rows from legacy columns.", cr.rowcount)

