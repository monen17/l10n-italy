# 18.0.1.1.0 (2025-12-28)

- [ADD] Automatic creation of purchase DOI tax during module installation
  - New tax `00dia` (0% E Acq) for purchase invoices with DOI
  - Fiscal position mappings for all Italian purchase taxes (22%, 10%, 5%, 4%)
  - Automatic company configuration with the new purchase tax
- [ADD] Threshold warning for purchase invoices
  - Extended `_compute_l10n_it_edi_doi_warning` to show warnings on vendor bills
  - Consistent behavior with sales invoices from base module

# 18.0.1.0.0

- Start of the history.
