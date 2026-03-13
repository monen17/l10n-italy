from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    doi_type = fields.Selection(
        selection=[
            ("in", "Issued from company"),
            ("out", "Received from customers"),
        ],
        compute="_compute_l10n_it_edi_doi_type",
    )

    @api.depends("move_type")
    def _compute_l10n_it_edi_doi_type(self):
        purchase_types = self.env["account.move"].get_purchase_types()
        sale_types = self.env["account.move"].get_sale_types()
        for move in self:
            if move.move_type in purchase_types:
                move.doi_type = "in"
            elif move.move_type in sale_types:
                move.doi_type = "out"
            else:
                move.doi_type = False

    def _compute_l10n_it_edi_doi_use(self):
        purchase_move_ids = self.filtered(lambda x: x.doi_type == "in")
        other_move_ids = self - purchase_move_ids
        super(AccountMove, other_move_ids)._compute_l10n_it_edi_doi_use()
        for move in purchase_move_ids:
            move.l10n_it_edi_doi_use = (
                move.l10n_it_edi_doi_id or move.country_code == "IT"
            )
        return  # W8110

    def _compute_l10n_it_edi_doi_amount(self):
        purchase_move_ids = self.filtered(lambda x: x.doi_type == "in")
        other_move_ids = self - purchase_move_ids
        super(AccountMove, other_move_ids)._compute_l10n_it_edi_doi_amount()
        for move in purchase_move_ids:
            tax = move.company_id.l10n_it_edi_doi_bill_tax_id
            if not tax or not move.l10n_it_edi_doi_id:
                move.l10n_it_edi_doi_amount = 0
                continue
            declaration_lines = move.invoice_line_ids.filtered(
                # The declaration tax cannot be used with other taxes on a single line
                # (checked in `_post`)
                lambda line, tax=tax: line.tax_ids.ids == tax.ids
            )
            move.l10n_it_edi_doi_amount = sum(declaration_lines.mapped("price_total"))
        return  # W8110

    def _compute_l10n_it_edi_doi_id(self):
        purchase_move_ids = self.filtered(lambda x: x.doi_type == "in")
        other_move_ids = self - purchase_move_ids
        super(AccountMove, other_move_ids)._compute_l10n_it_edi_doi_id()
        for move in purchase_move_ids:
            if not move.l10n_it_edi_doi_use or (
                move.state != "draft" and not move.l10n_it_edi_doi_id
            ):
                move.l10n_it_edi_doi_id = False
                continue

            partner = move.partner_id.commercial_partner_id
            validity_warnings = move.l10n_it_edi_doi_id._get_validity_warnings(
                move.company_id, partner, move.currency_id, move.l10n_it_edi_doi_date
            )
            if move.l10n_it_edi_doi_id and not validity_warnings:
                continue

            declaration = self.env[
                "l10n_it_edi_doi.declaration_of_intent"
            ]._fetch_valid_declaration_of_intent(
                move.company_id,
                partner,
                move.currency_id,
                move.l10n_it_edi_doi_date,
                doi_type="in",
            )
            move.l10n_it_edi_doi_id = declaration
        return  # W8110

    def _compute_l10n_it_edi_doi_warning(self):
        """Extend warning computation to include purchase invoices."""
        purchase_move_ids = self.filtered(lambda x: x.doi_type == "in")
        other_move_ids = self - purchase_move_ids
        super(AccountMove, other_move_ids)._compute_l10n_it_edi_doi_warning()

        for move in purchase_move_ids:
            move.l10n_it_edi_doi_warning = ""
            declaration = move.l10n_it_edi_doi_id

            show_warning = (
                declaration
                and move.is_purchase_document(include_receipts=False)
                and move.state != "cancel"
            )
            if not show_warning:
                continue

            declaration_invoiced = declaration.invoiced
            declaration_not_yet_invoiced = declaration.not_yet_invoiced

            if move.state != "posted":
                # Replicate what would happen when posting the invoice
                declaration_invoiced += move.l10n_it_edi_doi_amount
                # Update not_yet_invoiced for linked purchase orders
                linked_orders = self.env["purchase.order"]
                for invoice_line in move.invoice_line_ids:
                    for purchase_line in invoice_line.purchase_line_id:
                        order = purchase_line.order_id
                        if order.l10n_it_edi_doi_id == declaration:
                            linked_orders |= order
                for order in linked_orders:
                    not_yet_invoiced = order.l10n_it_edi_doi_not_yet_invoiced
                    # After posting, the order's not_yet_invoiced will be reduced
                    declaration_not_yet_invoiced -= not_yet_invoiced

            validity_warnings = declaration._get_validity_warnings(
                move.company_id,
                move.commercial_partner_id,
                move.currency_id,
                move.l10n_it_edi_doi_date,
                invoiced_amount=declaration_invoiced,
            )

            threshold_warning = declaration._build_threshold_warning_message(
                declaration_invoiced, declaration_not_yet_invoiced
            )

            move.l10n_it_edi_doi_warning = "{}\n\n{}".format(
                "\n".join(validity_warnings), threshold_warning
            ).strip()
        return  # W8110

    # Disabled automatic fiscal position assignment for purchase invoices
    #
    # @api.depends("l10n_it_edi_doi_id")
    # def _compute_fiscal_position_id(self):
    #     """Apply fiscal position automatically when DOI is selected."""
    #     super()._compute_fiscal_position_id()
    #     for move in self:
    #         declaration_fiscal_position = move.company_id.l10n_it_edi_doi_fiscal_position_id
    #         if declaration_fiscal_position and move.l10n_it_edi_doi_id:
    #             move.fiscal_position_id = declaration_fiscal_position
    #     return  # W8110

    def _post(self, soft=True):
        errors = []
        for move in self:
            declaration = move.l10n_it_edi_doi_id
            doi_bill_tax = move.company_id.l10n_it_edi_doi_bill_tax_id
            if not doi_bill_tax:
                continue
            declaration_lines = move.invoice_line_ids.filtered(
                lambda line, doi_bill_tax=doi_bill_tax: doi_bill_tax in line.tax_ids
            )
            if declaration_lines and not declaration:
                errors.append(
                    _(
                        "Given the tax %s is applied, there should be a "
                        "Declaration of Intent selected.",
                        doi_bill_tax.name,
                    )
                )
            if any(line.tax_ids != doi_bill_tax for line in declaration_lines):
                errors.append(
                    _(
                        "A line using tax %s should not contain any other taxes",
                        doi_bill_tax.name,
                    )
                )
        if errors:
            raise UserError("\n".join(errors))
        return super()._post(soft)
