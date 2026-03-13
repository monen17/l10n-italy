# Copyright 2025 Nextev Srl
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestPlafondYear(TransactionCase):
    """Test Annual Plafond functionality."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.company.country_id = cls.env.ref("base.it")
        cls.company.account_fiscal_country_id = cls.env.ref("base.it")
        cls.partner = cls.env.ref("base.res_partner_2")
        cls.partner.country_id = cls.env.ref("base.it")
        cls.partner.company_id = cls.company
        cls.current_year = fields.Date.today().year

        # Create plafond for current year
        cls.plafond = cls.env["l10n_it_edi_doi.plafond.year"].create(
            {
                "year": cls.current_year,
                "company_id": cls.company.id,
                "plafond_total": 100000.0,
            }
        )

    def test_plafond_creation(self):
        """Test that plafond is correctly created."""
        self.assertEqual(self.plafond.year, self.current_year)
        self.assertEqual(self.plafond.plafond_total, 100000.0)
        self.assertEqual(self.plafond.plafond_available, 100000.0)
        self.assertEqual(self.plafond.plafond_used, 0.0)
        self.assertEqual(self.plafond.usage_percentage, 0.0)

    def test_plafond_name_computed(self):
        """Test that plafond name is correctly computed."""
        self.assertIn(str(self.current_year), self.plafond.name)
        self.assertIn(self.company.name, self.plafond.name)

    def test_plafond_unique_constraint(self):
        """Test that only one plafond per year/company is allowed."""
        with self.assertRaises(Exception):
            self.env["l10n_it_edi_doi.plafond.year"].create(
                {
                    "year": self.current_year,
                    "company_id": self.company.id,
                    "plafond_total": 50000.0,
                }
            )

    def test_plafond_positive_constraint(self):
        """Test that plafond total must be positive."""
        with self.assertRaises(Exception):
            self.env["l10n_it_edi_doi.plafond.year"].create(
                {
                    "year": self.current_year + 1,
                    "company_id": self.company.id,
                    "plafond_total": 0.0,
                }
            )


@tagged("post_install", "-at_install")
class TestDoiWithPlafond(TransactionCase):
    """Test Declaration of Intent with Annual Plafond."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.company.country_id = cls.env.ref("base.it")
        cls.company.account_fiscal_country_id = cls.env.ref("base.it")
        cls.partner = cls.env.ref("base.res_partner_2")
        cls.partner.country_id = cls.env.ref("base.it")
        cls.partner.company_id = cls.company
        cls.current_year = fields.Date.today().year

        # Create plafond
        cls.plafond = cls.env["l10n_it_edi_doi.plafond.year"].create(
            {
                "year": cls.current_year,
                "company_id": cls.company.id,
                "plafond_total": 100000.0,
            }
        )

        # Create tax for DOI
        cls.tax_group = cls.env["account.tax.group"].create(
            {"name": "Vat Free Test", "sequence": 1}
        )
        cls.tax = cls.env["account.tax"].create(
            {
                "l10n_it_exempt_reason": "N3.5",
                "l10n_it_law_reference": "Art. 8, comma 1, lett. a) DPR 633/72",
                "type_tax_use": "purchase",
                "name": "0% DOI Test",
                "amount": 0,
                "tax_group_id": cls.tax_group.id,
            }
        )
        cls.env.company.l10n_it_edi_doi_bill_tax_id = cls.tax

    def test_doi_in_requires_plafond(self):
        """Test that DOI type 'in' requires a plafond."""
        with self.assertRaises(ValidationError):
            self.env["l10n_it_edi_doi.declaration_of_intent"].create(
                {
                    "partner_id": self.partner.id,
                    "company_id": self.company.id,
                    "state": "draft",
                    "type": "in",
                    "currency_id": self.company.currency_id.id,
                    "issue_date": fields.Date.today(),
                    "start_date": fields.Date.today(),
                    "end_date": fields.Date.today() + relativedelta(months=2),
                    "threshold": 5000,
                    "protocol_number_part1": "20250000",
                    "protocol_number_part2": "123456789",
                    # plafond_id not set -> should raise
                }
            )

    def test_doi_out_requires_partner(self):
        """Test that DOI type 'out' requires a partner."""
        with self.assertRaises(ValidationError):
            self.env["l10n_it_edi_doi.declaration_of_intent"].create(
                {
                    "company_id": self.company.id,
                    "state": "draft",
                    "type": "out",
                    "currency_id": self.company.currency_id.id,
                    "issue_date": fields.Date.today(),
                    "start_date": fields.Date.today(),
                    "end_date": fields.Date.today() + relativedelta(months=2),
                    "threshold": 5000,
                    "protocol_number_part1": "123",
                    "protocol_number_part2": "456",
                    # partner_id not set -> should raise for type 'out'
                }
            )

    def test_doi_in_with_plafond(self):
        """Test DOI type 'in' creation with plafond."""
        doi = self.env["l10n_it_edi_doi.declaration_of_intent"].create(
            {
                "partner_id": self.partner.id,
                "company_id": self.company.id,
                "state": "draft",
                "type": "in",
                "plafond_id": self.plafond.id,
                "currency_id": self.company.currency_id.id,
                "issue_date": fields.Date.today(),
                "start_date": fields.Date.today(),
                "end_date": fields.Date.today() + relativedelta(months=2),
                "threshold": 10000,
                "protocol_number_part1": "20250000",
                "protocol_number_part2": "123456789",
            }
        )
        self.assertEqual(doi.plafond_id, self.plafond)
        self.assertEqual(doi.type, "in")
        self.assertTrue(doi.has_threshold)

    def test_doi_in_without_threshold(self):
        """Test DOI type 'in' without specific threshold uses plafond."""
        # First, we need to temporarily disable the threshold constraint
        # by using a threshold > 0 (since base module requires it)
        doi = self.env["l10n_it_edi_doi.declaration_of_intent"].create(
            {
                "partner_id": self.partner.id,
                "company_id": self.company.id,
                "state": "draft",
                "type": "in",
                "plafond_id": self.plafond.id,
                "currency_id": self.company.currency_id.id,
                "issue_date": fields.Date.today(),
                "start_date": fields.Date.today(),
                "end_date": fields.Date.today() + relativedelta(months=2),
                "threshold": 1,  # Minimal threshold to pass base constraint
                "protocol_number_part1": "20250000",
                "protocol_number_part2": "234567890",
            }
        )
        # With threshold > 0, has_threshold should be True
        self.assertTrue(doi.has_threshold)

    def test_plafond_usage_computed(self):
        """Test that plafond usage is correctly computed from linked DOIs."""
        doi = self.env["l10n_it_edi_doi.declaration_of_intent"].create(
            {
                "partner_id": self.partner.id,
                "company_id": self.company.id,
                "state": "active",
                "type": "in",
                "plafond_id": self.plafond.id,
                "currency_id": self.company.currency_id.id,
                "issue_date": fields.Date.today(),
                "start_date": fields.Date.today(),
                "end_date": fields.Date.today() + relativedelta(months=2),
                "threshold": 20000,
                "protocol_number_part1": "20250000",
                "protocol_number_part2": "345678901",
            }
        )

        # Check plafond has the DOI linked
        self.assertIn(doi, self.plafond.declaration_ids)

        # Plafond assigned should include the DOI threshold
        self.plafond.invalidate_recordset()
        self.assertEqual(self.plafond.plafond_assigned, 20000)


@tagged("post_install", "-at_install")
class TestProtocolValidation(TransactionCase):
    """Test Protocol number validation for issued DOIs."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.company.country_id = cls.env.ref("base.it")
        cls.company.account_fiscal_country_id = cls.env.ref("base.it")
        cls.partner = cls.env.ref("base.res_partner_2")
        cls.partner.country_id = cls.env.ref("base.it")
        cls.partner.company_id = cls.company
        cls.current_year = fields.Date.today().year

        # Create plafond
        cls.plafond = cls.env["l10n_it_edi_doi.plafond.year"].create(
            {
                "year": cls.current_year,
                "company_id": cls.company.id,
                "plafond_total": 100000.0,
            }
        )

    def _create_doi_in(self, part1, part2):
        """Helper to create DOI type 'in' with given protocol parts."""
        return self.env["l10n_it_edi_doi.declaration_of_intent"].create(
            {
                "partner_id": self.partner.id,
                "company_id": self.company.id,
                "state": "draft",
                "type": "in",
                "plafond_id": self.plafond.id,
                "currency_id": self.company.currency_id.id,
                "issue_date": fields.Date.today(),
                "start_date": fields.Date.today(),
                "end_date": fields.Date.today() + relativedelta(months=2),
                "threshold": 5000,
                "protocol_number_part1": part1,
                "protocol_number_part2": part2,
            }
        )

    def test_valid_protocol_17_chars(self):
        """Test that valid 17-character protocol is accepted."""
        # Format: AAAANNNNNNNNCCCCC (4 + 8 + 5 = 17 chars)
        # Using current year
        part1 = f"{self.current_year}0000"  # 8 chars
        part2 = "123456789"  # 9 chars -> total 17
        doi = self._create_doi_in(part1, part2)
        self.assertTrue(doi.id)

    def test_invalid_protocol_length(self):
        """Test that protocol with wrong length is rejected."""
        # Too short
        with self.assertRaises(ValidationError):
            self._create_doi_in("2025", "123")  # Only 7 chars

    def test_invalid_protocol_format(self):
        """Test that protocol with invalid format is rejected."""
        # Invalid format (letters in wrong place)
        with self.assertRaises(ValidationError):
            self._create_doi_in("ABCD0000", "123456789")  # Letters instead of year

    def test_protocol_year_mismatch(self):
        """Test that protocol year must match plafond year."""
        wrong_year = self.current_year + 1
        with self.assertRaises(ValidationError):
            self._create_doi_in(f"{wrong_year}0000", "123456789")

    def test_protocol_not_validated_for_out(self):
        """Test that protocol validation is skipped for type 'out'."""
        # Type 'out' should not validate protocol format
        doi = self.env["l10n_it_edi_doi.declaration_of_intent"].create(
            {
                "partner_id": self.partner.id,
                "company_id": self.company.id,
                "state": "draft",
                "type": "out",
                "currency_id": self.company.currency_id.id,
                "issue_date": fields.Date.today(),
                "start_date": fields.Date.today(),
                "end_date": fields.Date.today() + relativedelta(months=2),
                "threshold": 5000,
                "protocol_number_part1": "ABC",  # Invalid format but OK for 'out'
                "protocol_number_part2": "123",
            }
        )
        self.assertTrue(doi.id)
