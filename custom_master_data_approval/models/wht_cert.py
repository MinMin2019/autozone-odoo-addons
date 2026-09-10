from odoo import models


class WithholdingTaxCert(models.Model):
    _inherit = "withholding.tax.cert"

    def action_done(self):
        Check = self.env["az.approval.type"]
        for cert in self:
            if cert.partner_id:
                Check.check_partners(
                    cert.partner_id, "ออกหนังสือรับรองหัก ณ ที่จ่าย %s"
                    % (cert.display_name))
        return super().action_done()
