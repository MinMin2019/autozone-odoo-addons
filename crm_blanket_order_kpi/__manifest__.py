# Copyright 2026
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    "name": "Custom CRM Blanket Order KPI",
    "version": "18.0.1.0.0",
    "summary": "Opportunity as control tower for blanket-order contract KPIs",
    "author": "Autozone",
    "license": "AGPL-3",
    "category": "Autozone/Sales",
    "depends": [
        "sale_crm",
        "sale_blanket_order",
        "analytic",
        # Bridge only: hides backlog columns on contract-source quotations.
        # Drop this dep + views/sale_order_backlog_hide_views.xml if not used.
        "sale_service_remaining_qty",
        # Bridge only: hides the standard Project field on contract-source
        # quotations. Drop this dep + views/sale_order_project_hide_views.xml
        # if not used.
        "sale_project",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizard/create_blanket_order_views.xml",
        "views/sale_order_views.xml",
        "views/sale_order_backlog_hide_views.xml",
        "views/sale_order_project_hide_views.xml",
        "views/blanket_order_views.xml",
        "views/crm_lead_views.xml",
        "views/analysis_views.xml",
        "views/contract_timeline_report_views.xml",
        "report/contract_status_report.xml",
    ],
    "installable": True,
}
