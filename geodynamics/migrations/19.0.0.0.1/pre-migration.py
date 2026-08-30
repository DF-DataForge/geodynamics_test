# Copyright 2025-2026 Data Forge (https://www.data-forge.be)
# License OPL-1 (Odoo Proprietary License v1.0) - See LICENSE file for full details.
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info("[Geodynamics] Pre-migration to 19.0.0.0.1: start")
    if not version:
        return

    # Rename legacy camelCase columns to snake_case (preserve data)
    aal_col_renames = {
        'df_starttime': 'df_start_time',
        'df_endtime': 'df_end_time',
    }
    for old_col, new_col in aal_col_renames.items():
        cr.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'account_analytic_line' AND column_name = %s
        """, (old_col,))
        if cr.fetchone():
            cr.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'account_analytic_line' AND column_name = %s
            """, (new_col,))
            if not cr.fetchone():
                cr.execute(f'ALTER TABLE account_analytic_line RENAME COLUMN "{old_col}" TO "{new_col}"')
                _logger.info("[Geodynamics] Renamed column account_analytic_line.%s -> %s", old_col, new_col)
            else:
                cr.execute(f'ALTER TABLE account_analytic_line DROP COLUMN IF EXISTS "{old_col}"')
                _logger.info("[Geodynamics] Dropped duplicate legacy column: %s", old_col)

    # Rename 'decription' to 'description' in df_geodynamics_planning if exists
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'df_geodynamics_planning'
        AND column_name = 'decription'
    """)
    if cr.fetchone():
        cr.execute('ALTER TABLE df_geodynamics_planning RENAME COLUMN decription TO description')
        _logger.info("[Geodynamics] Renamed column decription -> description")

    # Rename fields on account_analytic_line to df_ prefix
    aal_renames = {
        'timesheet_type': 'df_timesheet_type',
        'gd_purchase_cost': 'df_gd_purchase_cost',
        'gd_employer_cost': 'df_gd_employer_cost',
        'gd_backoffice_cost': 'df_gd_backoffice_cost',
        'gd_total_cost': 'df_gd_total_cost',
        'gd_sales_price': 'df_gd_sales_price',
        'gd_margin': 'df_gd_margin',
        'gd_margin_percentage': 'df_gd_margin_percentage',
    }
    for old_col, new_col in aal_renames.items():
        cr.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'account_analytic_line' AND column_name = %s
        """, (old_col,))
        if cr.fetchone():
            cr.execute(f'ALTER TABLE account_analytic_line RENAME COLUMN "{old_col}" TO "{new_col}"')
            _logger.info("[Geodynamics] Renamed column account_analytic_line.%s -> %s", old_col, new_col)

    # Rename employee_ids M2M relation table for project.task if auto-generated name exists
    cr.execute("""
        SELECT tablename FROM pg_tables
        WHERE tablename = 'project_task_hr_employee_rel'
    """)
    if cr.fetchone():
        # Check if new name already exists
        cr.execute("SELECT tablename FROM pg_tables WHERE tablename = 'project_task_df_employee_ids_rel'")
        if not cr.fetchone():
            cr.execute('ALTER TABLE project_task_hr_employee_rel RENAME TO project_task_df_employee_ids_rel')
            _logger.info("[Geodynamics] Renamed M2M table project_task_hr_employee_rel -> project_task_df_employee_ids_rel")

    # Rename M2M columns to match explicit field definition (task_id, employee_id)
    cr.execute("SELECT tablename FROM pg_tables WHERE tablename = 'project_task_df_employee_ids_rel'")
    if cr.fetchone():
        cr.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'project_task_df_employee_ids_rel' AND column_name = 'project_task_id'
        """)
        if cr.fetchone():
            cr.execute('ALTER TABLE project_task_df_employee_ids_rel RENAME COLUMN project_task_id TO task_id')
            _logger.info("[Geodynamics] Renamed M2M column project_task_id -> task_id")
        cr.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'project_task_df_employee_ids_rel' AND column_name = 'hr_employee_id'
        """)
        if cr.fetchone():
            cr.execute('ALTER TABLE project_task_df_employee_ids_rel RENAME COLUMN hr_employee_id TO employee_id')
            _logger.info("[Geodynamics] Renamed M2M column hr_employee_id -> employee_id")

    _logger.info("[Geodynamics] Pre-migration to 19.0.0.0.1: done")
