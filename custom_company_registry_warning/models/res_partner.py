from odoo import api, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.depends("vat", "company_id", "company_registry")
    def _compute_same_vat_partner_id(self):
        super()._compute_same_vat_partner_id()
        # company_registry holds the Thai tax branch code (00000 = head
        # office), which is legitimately shared by many partners — only warn
        # when the Tax ID matches as well.
        Partner = self.with_context(active_test=False).sudo()
        for partner in self:
            if not partner.same_company_registry_partner_id:
                continue
            if not partner.vat:
                partner.same_company_registry_partner_id = False
                continue
            partner_id = partner._origin.id
            domain = [
                ("company_registry", "=", partner.company_registry),
                ("vat", "=", partner.vat),
                ("company_id", "in", [False, partner.company_id.id]),
            ]
            if partner_id:
                domain += [("id", "!=", partner_id), "!", ("id", "child_of", partner_id)]
            partner.same_company_registry_partner_id = Partner.search(domain, limit=1)
