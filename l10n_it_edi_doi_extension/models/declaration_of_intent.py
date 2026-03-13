import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class L10nItDeclarationOfIntent(models.Model):
    _inherit = "l10n_it_edi_doi.declaration_of_intent"

    purchase_order_ids = fields.One2many(
        "purchase.order",
        "l10n_it_edi_doi_id",
        string="Purchase / Rfq Orders",
        copy=False,
        readonly=True,
    )

    type = fields.Selection(
        [("in", "Issued from company"), ("out", "Received from customers")],
        required=True,
        default="out",
        tracking=True,
    )

    # Link to annual plafond (only for type "in")
    plafond_id = fields.Many2one(
        comodel_name="l10n_it_edi_doi.plafond.year",
        string="Annual Plafond",
        tracking=True,
        domain="[('company_id', '=', company_id)]",
        help="Annual plafond assigned by Agenzia delle Entrate. "
        "Required for issued declarations (type 'in').",
    )

    # Computed field to check if DOI has a specific threshold or uses plafond
    has_threshold = fields.Boolean(
        string="Has Specific Threshold",
        compute="_compute_has_threshold",
        store=True,
        help="If True, this DOI has a specific threshold. "
        "If False, it uses the total plafond without individual limit.",
    )

    # Plafond available (for DOIs without threshold, shows plafond available)
    plafond_available = fields.Monetary(
        string="Plafond Available",
        compute="_compute_plafond_available",
        store=True,
        help="Available amount from annual plafond (for DOIs without specific threshold)",
    )

    # Override partner_id to make it optional for type "in"
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Partner",
        index=True,
        required=False,  # Will be enforced by constraint for type "out"
        domain="['|', ('is_company', '=', True), ('parent_id', '=', False)]",
    )

    @api.depends("threshold")
    def _compute_has_threshold(self):
        for rec in self:
            rec.has_threshold = rec.threshold > 0

    @api.depends("plafond_id.plafond_available", "type", "has_threshold")
    def _compute_plafond_available(self):
        for rec in self:
            if rec.type == "in" and rec.plafond_id and not rec.has_threshold:
                rec.plafond_available = rec.plafond_id.plafond_available
            else:
                rec.plafond_available = 0.0

    @api.constrains("type", "partner_id")
    def _check_partner_required_for_out(self):
        """Partner is required for received declarations (type 'out')."""
        for rec in self:
            if rec.type == "out" and not rec.partner_id:
                raise ValidationError(
                    _(
                        "Partner is required for received declarations "
                        "(type 'Received from customers')."
                    )
                )

    @api.constrains("type", "plafond_id")
    def _check_plafond_required_for_in(self):
        """Plafond is required for issued declarations (type 'in')."""
        for rec in self:
            if rec.type == "in" and not rec.plafond_id:
                raise ValidationError(
                    _(
                        "Annual Plafond is required for issued declarations "
                        "(type 'Issued from company')."
                    )
                )

    @api.constrains("protocol_number_part1", "protocol_number_part2")
    def _check_protocol_format(self):
        """
        Validate AdE protocol format for issued declarations.

        The full protocol (part1 + part2) should be 17 characters:
        - AAAA: Year (4 digits)
        - NNNNNNNN: Sequential number (8 digits)
        - CCCCC: Last 5 chars of company fiscal code (5 alphanumeric)

        Format: AAAANNNNNNNNCCCCC (17 characters total)
        """
        for rec in self:
            if rec.type != "in":
                # Skip validation for received declarations
                continue

            part1 = (rec.protocol_number_part1 or "").strip()
            part2 = (rec.protocol_number_part2 or "").strip()

            if not part1 or not part2:
                continue

            # Combine parts for full protocol
            full_protocol = part1 + part2

            # Check total length (17 characters)
            if len(full_protocol) != 17:
                raise ValidationError(
                    _(
                        "The protocol number must be exactly 17 characters.\n"
                        "Current: %(current)s (%(length)s characters)\n\n"
                        "Format: AAAANNNNNNNNCCCCC\n"
                        "- AAAA: Year (4 digits)\n"
                        "- NNNNNNNN: Sequential (8 digits)\n"
                        "- CCCCC: Last 5 chars of fiscal code",
                        current=full_protocol,
                        length=len(full_protocol),
                    )
                )

            # Check format: 4 digits + 8 digits + 5 alphanumeric
            pattern = r"^(\d{4})(\d{8})([A-Z0-9]{5})$"
            match = re.match(pattern, full_protocol.upper())

            if not match:
                raise ValidationError(
                    _(
                        "The protocol '%(protocol)s' does not match AdE format.\n\n"
                        "Required format: AAAANNNNNNNNCCCCC\n"
                        "- AAAA: Year (4 digits)\n"
                        "- NNNNNNNN: Sequential number (8 digits)\n"
                        "- CCCCC: Last 5 characters of company fiscal code\n\n"
                        "Example: 20250000123456789",
                        protocol=full_protocol,
                    )
                )

            # Extract and validate year
            protocol_year = int(match.group(1))

            # Check year matches plafond year
            if rec.plafond_id and protocol_year != rec.plafond_id.year:
                raise ValidationError(
                    _(
                        "The year in protocol (%(protocol_year)s) does not match "
                        "the plafond year (%(plafond_year)s).",
                        protocol_year=protocol_year,
                        plafond_year=rec.plafond_id.year,
                    )
                )

    @api.onchange("type")
    def _onchange_type_clear_plafond(self):
        """Clear plafond when switching to type 'out'."""
        if self.type == "out":
            self.plafond_id = False

    @api.onchange("plafond_id")
    def _onchange_plafond_set_dates(self):
        """Suggest dates based on plafond year."""
        if self.plafond_id and not self.start_date:
            year = self.plafond_id.year
            self.start_date = fields.Date.today().replace(year=year, month=1, day=1)
            self.end_date = fields.Date.today().replace(year=year, month=12, day=31)

    def _fetch_valid_declaration_of_intent(
        self, company, partner, currency, date, doi_type="out"
    ):
        res = super()._fetch_valid_declaration_of_intent(
            company, partner, currency, date
        )
        if not res or res.type == doi_type:
            return res
        # Same domain as in the original, with the addition of 'type'
        domain = [
            ("state", "=", "active"),
            ("company_id", "=", company.id),
            ("currency_id", "=", currency.id),
            ("partner_id", "=", partner.commercial_partner_id.id),
            ("start_date", "<=", date),
            ("end_date", ">=", date),
            ("remaining", ">", 0),
            ("type", "=", doi_type),
        ]
        return self.search(domain, limit=1)

    @api.depends(
        "purchase_order_ids",
        "purchase_order_ids.state",
        "purchase_order_ids.l10n_it_edi_doi_not_yet_invoiced",
    )
    def _compute_not_yet_invoiced(self):
        received_doi = self.filtered(lambda r: r.type == "out")
        issued_doi = self - received_doi
        super(L10nItDeclarationOfIntent, received_doi)._compute_not_yet_invoiced()
        for declaration in issued_doi:
            relevant_orders = declaration.purchase_order_ids.filtered(
                lambda order: order.state == "purchase"
            )
            declaration.not_yet_invoiced = sum(
                relevant_orders.mapped("l10n_it_edi_doi_not_yet_invoiced")
            )
        return  # W8110

    @api.ondelete(at_uninstall=False)
    def _unlink_except_linked_to_purchase_document(self):
        if self.purchase_order_ids:
            raise UserError(
                _(
                    "You cannot delete Declarations of Intents that "
                    "are already used on at least one Purchase Order."
                )
            )
