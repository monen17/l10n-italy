from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class L10nItEdiDoiPlafondYear(models.Model):
    _name = "l10n_it_edi_doi.plafond.year"
    _description = "Annual Plafond for Declarations of Intent"
    _order = "year desc, company_id"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(
        string="Name",
        compute="_compute_name",
        store=True,
    )

    year = fields.Integer(
        string="Year (stored)",
        required=True,
        default=lambda self: fields.Date.today().year,
        tracking=True,
    )

    year_display = fields.Char(
        string="Year",
        compute="_compute_year_display",
        inverse="_inverse_year_display",
        store=False,
        help="Year in YYYY format (e.g., 2025)",
    )

    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Currency",
        related="company_id.currency_id",
        store=True,
    )

    plafond_total = fields.Monetary(
        string="Total Plafond (AdE)",
        required=True,
        tracking=True,
        help="Total amount assigned by Agenzia delle Entrate for this year",
    )

    plafond_assigned = fields.Monetary(
        string="Total Assigned",
        compute="_compute_plafond_usage",
        store=True,
        help="Sum of thresholds assigned to DOIs with specific threshold",
    )

    plafond_used = fields.Monetary(
        string="Total Used",
        compute="_compute_plafond_usage",
        store=True,
        help="Sum of invoiced amounts from all DOIs linked to this plafond",
    )

    plafond_available = fields.Monetary(
        string="Available",
        compute="_compute_plafond_usage",
        store=True,
        help="Total plafond minus used amount",
    )

    usage_percentage = fields.Float(
        string="Usage %",
        compute="_compute_plafond_usage",
        store=True,
    )

    declaration_ids = fields.One2many(
        comodel_name="l10n_it_edi_doi.declaration_of_intent",
        inverse_name="plafond_id",
        string="Declarations of Intent",
    )

    # Computed field for all invoices linked to this plafond through DOIs
    invoice_ids = fields.Many2many(
        comodel_name="account.move",
        string="Purchase Invoices",
        compute="_compute_invoice_ids",
        store=False,
    )

    invoice_count = fields.Integer(
        string="Invoice Count",
        compute="_compute_invoice_ids",
        store=False,
    )

    active = fields.Boolean(
        string="Active",
        default=True,
    )

    note = fields.Text(
        string="Notes",
    )

    _sql_constraints = [
        (
            "year_company_unique",
            "unique(year, company_id)",
            "A plafond already exists for this year and company!",
        ),
        (
            "plafond_total_positive",
            "CHECK(plafond_total > 0)",
            "The total plafond must be greater than zero!",
        ),
    ]

    def _compute_invoice_ids(self):
        """Compute all purchase invoices linked to this plafond through DOIs."""
        for rec in self:
            # Get all invoices from all DOIs linked to this plafond
            invoices = rec.declaration_ids.mapped("invoice_ids").filtered(
                lambda inv: inv.move_type in ("in_invoice", "in_refund")
            )
            rec.invoice_ids = invoices
            rec.invoice_count = len(invoices)

    @api.depends("year")
    def _compute_year_display(self):
        """Convert integer year to string for display."""
        for rec in self:
            rec.year_display = str(rec.year) if rec.year else ""

    def _inverse_year_display(self):
        """Convert string year to integer for storage."""
        for rec in self:
            if rec.year_display:
                try:
                    year_int = int(rec.year_display)
                    if 2000 <= year_int <= 2100:
                        rec.year = year_int
                    else:
                        raise ValidationError(_("Year must be between 2000 and 2100."))
                except ValueError:
                    raise ValidationError(
                        _("Year must be a 4-digit number (e.g., 2025).")
                    )

    @api.depends("year", "company_id")
    def _compute_name(self):
        for rec in self:
            company_name = rec.company_id.name or ""
            rec.name = _(
                "Plafond %(year)s - %(company)s", year=rec.year, company=company_name
            )

    @api.depends(
        "plafond_total",
        "declaration_ids.threshold",
        "declaration_ids.invoiced",
        "declaration_ids.state",
        "declaration_ids.type",
    )
    def _compute_plafond_usage(self):
        for rec in self:
            # Only consider DOIs of type "in" (issued from company) that are not cancelled
            active_dois = rec.declaration_ids.filtered(
                lambda d: d.state not in ["revoked", "terminated"] and d.type == "in"
            )

            # Sum of thresholds for DOIs with specific threshold
            rec.plafond_assigned = sum(
                active_dois.filtered(lambda d: d.threshold > 0).mapped("threshold")
            )

            # Sum of all invoiced amounts
            rec.plafond_used = sum(active_dois.mapped("invoiced"))

            # Available = Total - Used
            rec.plafond_available = rec.plafond_total - rec.plafond_used

            # Usage percentage
            if rec.plafond_total > 0:
                rec.usage_percentage = (rec.plafond_used / rec.plafond_total) * 100
            else:
                rec.usage_percentage = 0.0

    @api.constrains("plafond_total", "declaration_ids")
    def _check_plafond_not_exceeded(self):
        """Check that assigned thresholds don't exceed total plafond."""
        for rec in self:
            if rec.plafond_assigned > rec.plafond_total:
                raise ValidationError(
                    _(
                        "The sum of assigned thresholds (%(assigned)s) exceeds "
                        "the total plafond (%(total)s)!",
                        assigned=rec.plafond_assigned,
                        total=rec.plafond_total,
                    )
                )

    def action_open_declarations(self):
        """Open declarations linked to this plafond."""
        self.ensure_one()
        return {
            "name": _("Declarations of Intent - %s", self.name),
            "type": "ir.actions.act_window",
            "res_model": "l10n_it_edi_doi.declaration_of_intent",
            "domain": [("plafond_id", "=", self.id)],
            "views": [(False, "list"), (False, "form")],
            "context": {
                "default_plafond_id": self.id,
                "default_type": "in",
            },
        }

    def action_open_invoices(self):
        """Open all purchase invoices linked to this plafond through DOIs."""
        self.ensure_one()
        return {
            "name": _("Purchase Invoices - %s", self.name),
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "domain": [("id", "in", self.invoice_ids.ids)],
            "views": [(False, "list"), (False, "form")],
            "context": {
                "default_move_type": "in_invoice",
                "search_default_posted": 1,
            },
        }
