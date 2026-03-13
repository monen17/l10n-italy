from odoo import models

from odoo.addons.account.models.chart_template import template


class AccountChartTemplate(models.AbstractModel):
    _inherit = "account.chart.template"

    @template("it", "account.tax")
    def _get_it_edi_doi_extension_account_tax(self):
        tax_data = self._parse_csv(
            "it", "account.tax", module="l10n_it_edi_doi_extension"
        )
        self._deref_account_tags("it", tax_data)
        return tax_data

    @template("it", "res.company")
    def _get_it_edi_doi_extension_res_company(self):
        return {
            self.env.company.id: {
                "l10n_it_edi_doi_bill_tax_id": "00dia",
            },
        }
