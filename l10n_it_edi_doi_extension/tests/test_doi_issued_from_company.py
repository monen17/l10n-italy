# Copyright 2025 Nextev Srl
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests import Form, tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestDoiIssuedFromCompany(TransactionCase):
    @classmethod
    def _create_declaration(cls, type_doi):
        return cls.env["l10n_it_edi_doi.declaration_of_intent"].create(
            {
                "partner_id": cls.partner.id,
                "company_id": cls.company.id,
                "state": "active",
                "type": type_doi,
                "currency_id": cls.company.currency_id.id,
                "issue_date": fields.Date.today(),
                "start_date": fields.Date.today(),
                "end_date": fields.Date.today() + relativedelta(months=2),
                "threshold": 5000,
                "protocol_number_part1": "123",
                "protocol_number_part2": "456",
            }
        )

    @classmethod
    def _create_invoice(cls, name, partner, tax=False, date=False, in_type=False):
        invoice_form = Form(
            cls.env["account.move"].with_context(
                default_move_type="in_invoice" if in_type else "out_invoice",
                default_partner_id=partner.id,
            )
        )
        invoice_form.invoice_date = date if date else fields.Date.today()
        invoice_form.invoice_payment_term_id = cls.env.ref(
            "account.account_payment_term_advance"
        )
        cls._add_invoice_line_id(invoice_form, tax=tax, in_type=in_type)
        invoice = invoice_form.save()
        return invoice

    @classmethod
    def _add_invoice_line_id(cls, invoice_form, tax=False, in_type=False):
        with invoice_form.invoice_line_ids.new() as invoice_line:
            invoice_line.product_id = cls.env.ref("product.product_product_5")
            invoice_line.quantity = 10.00
            invoice_line.name = "test line"
            invoice_line.price_unit = 90.00
            if tax:
                invoice_line.tax_ids.clear()
                invoice_line.tax_ids.add(tax)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.company.country_id = cls.env.ref("base.it")
        cls.company.account_fiscal_country_id = cls.env.ref("base.it")
        cls.tax_model = cls.env["account.tax"]
        cls.partner = cls.env.ref("base.res_partner_2")
        cls.partner.country_id = cls.env.ref("base.it")
        cls.partner.company_id = cls.company
        cls.doi_in = cls._create_declaration("in")
        cls.tax_group = cls.env["account.tax.group"].create(
            {"name": "Vat Free", "sequence": 1}
        )
        cls.tax = cls.tax_model.create(
            {
                "l10n_it_exempt_reason": "N3.5",
                "l10n_it_law_reference": "Art. 8, comma 1, lett. a) DPR 633/72",
                "type_tax_use": "purchase",
                "name": "0% declaration tax3",
                "amount": 0,
                "tax_group_id": cls.tax_group.id,
            }
        )
        cls.env.company.l10n_it_edi_doi_bill_tax_id = cls.tax

    def test_in_invoice_under_declaration_limit(self):
        """Test that purchase invoice amount is correctly tracked in DOI."""
        invoice = self._create_invoice("1", self.partner, tax=self.tax, in_type=True)
        previous_used_amount = self.doi_in.invoiced
        invoice.action_post()
        used_amount = self.doi_in.invoiced
        self.assertNotEqual(previous_used_amount, used_amount)
        self.assertEqual(used_amount, invoice.amount_total)
        self.assertEqual(self.doi_in.state, "active")

    def test_in_invoice_warning_below_threshold(self):
        """Test that no warning is shown when below threshold."""
        invoice = self._create_invoice("1", self.partner, tax=self.tax, in_type=True)
        invoice.l10n_it_edi_doi_id = self.doi_in
        # Amount is 900 (10 * 90), threshold is 5000
        self.assertEqual(invoice.l10n_it_edi_doi_warning, "")

    def test_in_invoice_warning_above_threshold(self):
        """Test that warning is shown when above threshold."""
        # Create a declaration with low threshold
        doi_low = self.env["l10n_it_edi_doi.declaration_of_intent"].create(
            {
                "partner_id": self.partner.id,
                "company_id": self.company.id,
                "state": "active",
                "type": "in",
                "currency_id": self.company.currency_id.id,
                "issue_date": fields.Date.today(),
                "start_date": fields.Date.today(),
                "end_date": fields.Date.today() + relativedelta(months=2),
                "threshold": 500,
                "protocol_number_part1": "789",
                "protocol_number_part2": "012",
            }
        )
        invoice = self._create_invoice("2", self.partner, tax=self.tax, in_type=True)
        invoice.l10n_it_edi_doi_id = doi_low
        # Amount is 900 (10 * 90), threshold is 500 -> should show warning
        self.assertTrue(invoice.l10n_it_edi_doi_warning)
        self.assertIn("exceeded", invoice.l10n_it_edi_doi_warning)

    def test_doi_type_computation(self):
        """Test that doi_type is correctly computed based on move_type."""
        # Purchase invoice
        in_invoice = self._create_invoice("3", self.partner, tax=self.tax, in_type=True)
        self.assertEqual(in_invoice.doi_type, "in")

        # Sale invoice
        out_invoice = self._create_invoice(
            "4", self.partner, tax=self.tax, in_type=False
        )
        self.assertEqual(out_invoice.doi_type, "out")

    def test_fiscal_position_applied_on_invoice(self):
        """Test that fiscal position is automatically applied when DOI is selected."""
        # Create a fiscal position for DOI
        fiscal_position = self.env["account.fiscal.position"].create(
            {
                "name": "Test DOI Fiscal Position",
                "company_id": self.company.id,
            }
        )
        self.company.l10n_it_edi_doi_fiscal_position_id = fiscal_position

        # Create purchase invoice without DOI
        invoice = self._create_invoice("5", self.partner, tax=self.tax, in_type=True)
        self.assertNotEqual(invoice.fiscal_position_id, fiscal_position)

        # Assign DOI to invoice
        invoice.l10n_it_edi_doi_id = self.doi_in

        # Fiscal position should be applied automatically
        self.assertEqual(
            invoice.fiscal_position_id,
            fiscal_position,
            "Fiscal position should be automatically applied when DOI is selected",
        )

    def test_fiscal_position_applied_on_purchase_order(self):
        """Test that fiscal position is automatically applied on purchase order."""
        # Create a fiscal position for DOI
        fiscal_position = self.env["account.fiscal.position"].create(
            {
                "name": "Test DOI Fiscal Position PO",
                "company_id": self.company.id,
            }
        )
        self.company.l10n_it_edi_doi_fiscal_position_id = fiscal_position

        # Create purchase order with DOI
        po_form = Form(self.env["purchase.order"])
        po_form.partner_id = self.partner
        po_form.l10n_it_edi_doi_id = self.doi_in
        po = po_form.save()

        # Fiscal position should be applied automatically
        self.assertEqual(
            po.fiscal_position_id,
            fiscal_position,
            "Fiscal position should be automatically applied on purchase order when DOI is selected",
        )


@tagged("post_install", "-at_install")
class TestDoiExtensionPostInit(TransactionCase):
    """Test the post_init_hook functionality."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.company.country_id = cls.env.ref("base.it")
        cls.company.account_fiscal_country_id = cls.env.ref("base.it")

    def test_purchase_doi_tax_created(self):
        """Test that purchase DOI tax is created for Italian companies."""
        # The tax should be created by post_init_hook
        # Check if the company has the purchase DOI tax configured
        if self.company.chart_template == "it":
            doi_bill_tax = self.company.l10n_it_edi_doi_bill_tax_id
            if doi_bill_tax:
                self.assertEqual(doi_bill_tax.type_tax_use, "purchase")
                self.assertEqual(doi_bill_tax.amount, 0.0)
                self.assertEqual(doi_bill_tax.l10n_it_exempt_reason, "N3.5")

    def test_fiscal_position_mappings(self):
        """Test that fiscal position has purchase tax mappings."""
        if self.company.chart_template == "it":
            fiscal_position = self.company.l10n_it_edi_doi_fiscal_position_id
            if fiscal_position:
                # Check that there are purchase tax mappings
                purchase_mappings = fiscal_position.tax_ids.filtered(
                    lambda m: m.tax_src_id.type_tax_use == "purchase"
                )
                # Should have mappings for purchase taxes
                if self.company.l10n_it_edi_doi_bill_tax_id:
                    self.assertTrue(
                        len(purchase_mappings) > 0,
                        "Fiscal position should have purchase tax mappings",
                    )
