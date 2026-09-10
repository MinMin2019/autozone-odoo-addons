# -*- coding: utf-8 -*-
{
    "name": "Autozone Master Data Approval",
    "summary": "Workflow อนุมัติข้อมูลหลัก (Vendor/Customer/Item) — ส่งแล้วล็อค, "
               "บล็อกทรานแซคชันของข้อมูลที่ยังไม่อนุมัติ",
    "version": "18.0.1.0.0",
    "category": "Autozone/Master Data",
    "author": "Autozone",
    "license": "LGPL-3",
    "depends": [
        "account",
        "sale_management",
        "purchase",
        "stock",
        "l10n_th_account_tax",
        "custom_access_role_builder",
    ],
    "data": [
        "security/mda_groups.xml",
        "security/ir.model.access.csv",
        "data/mail_activity_data.xml",
        "data/approval_type_data.xml",
        "views/approval_type_views.xml",
        "views/res_partner_views.xml",
        "views/product_template_views.xml",
        "wizard/reject_wizard_views.xml",
        "views/menus.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}
