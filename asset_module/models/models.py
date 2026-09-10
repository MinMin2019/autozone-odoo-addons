# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountAssetImageExtension(models.Model):  
    _name = 'account.asset'
    _inherit = ['account.asset', 'image.mixin']
    _description = 'Account Asset with Image (image.mixin)'
    
    # New fields
    x_asset_barcode = fields.Char(string='Barcode')
    x_asset_description = fields.Text(string='Description')
    x_asset_repository = fields.Char(string='Repository')
    x_asset_serial = fields.Char(string='Serial Number')
    x_asset_brand = fields.Char(string='Brand')
    x_asset_model = fields.Char(string='Model')
    x_asset_warranty_expiry_date = fields.Date(string='Warranty Expiry Date')
    
    x_asset_cost = fields.Float(string='Asset Cost')
    x_purchase_date = fields.Date(string='Purchase Date')
    
    x_class_id = fields.Many2one(
        comodel_name='account.analytic.account',  # เชื่อมโยงไปหา Analytic Account
        string='Class',
        help="Custom classification linked to Analytic Account"
    )
    x_location_id = fields.Many2one(
        comodel_name='stock.location',  # เชื่อมโยงไปหา Analytic Account
        string='Asset Location',
        help="Custom classification linked to Stock Location"
    )
    
   