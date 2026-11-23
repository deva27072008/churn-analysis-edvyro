# Customer Churn - Data Quality Report & Initial Patterns

**Dataset:** customer_churn_sample.csv - 15 synthetic customer records, 11 columns.
**Reproduce:** `python3 clean_churn.py` (reads `customer_churn_raw.csv`, writes the cleaned CSV, workbook, charts and this report).

## 1. Headline

- The file is **structurally clean**: 0 missing values, 0 duplicate rows, 0 duplicate IDs, 0 invalid categories, 0 impossible values, 0 IQR outliers, and TotalCharges reconciles to tenure x monthly charge on all 15 rows.
- **15 rows in, 15 rows out.** Nothing was deleted, imputed or capped.
- The main limitation is not dirty data but **size**: with 15 customers, patterns are descriptive only.

## 2. Profile (raw data)

| column | inferred_type | non_null | missing_or_blank | unique_values | min | max | mean | iqr_outliers |
|---|---|---|---|---|---|---|---|---|
| CustomerID | text/categorical | 15 | 0 | 15 |  |  |  |  |
| Gender | text/categorical | 15 | 0 | 2 |  |  |  |  |
| Age | numeric | 15 | 0 | 15 | 23.0 | 60.0 | 39.07 | 0.0 |
| TenureMonths | numeric | 15 | 0 | 15 | 2.0 | 48.0 | 18.8 | 0.0 |
| SubscriptionType | text/categorical | 15 | 0 | 3 |  |  |  |  |
| MonthlyCharges | numeric | 15 | 0 | 3 | 49.99 | 149.99 | 84.66 | 0.0 |
| TotalCharges | numeric | 15 | 0 | 15 | 99.98 | 7199.52 | 2088.48 | 0.0 |
| ContractType | text/categorical | 15 | 0 | 3 |  |  |  |  |
| SupportTickets | numeric | 15 | 0 | 7 | 0.0 | 6.0 | 2.53 | 0.0 |
| PaymentMethod | text/categorical | 15 | 0 | 4 |  |  |  |  |
| Churn | text/categorical | 15 | 0 | 2 |  |  |  |  |

## 3. Quality checks on raw data

| check | rule | rows_failing | result |
|---|---|---|---|
| Missing values | No blank/NA in any column | 0 | PASS |
| Duplicate rows | No fully duplicated rows | 0 | PASS |
| Duplicate customer IDs | CustomerID unique | 0 | PASS |
| ID format | CustomerID matches ^CUST-\d{4}$ | 0 | PASS |
| Numeric parseable | All numeric columns parse as numbers | 0 | PASS |
| Whitespace / case | No leading/trailing spaces in text | 0 | PASS |
| Valid categories: Gender | Values in ['Female', 'Male'] | 0 | PASS |
| Valid categories: SubscriptionType | Values in ['Basic', 'Enterprise', 'Pro'] | 0 | PASS |
| Valid categories: ContractType | Values in ['Month-to-Month', 'One Year', 'Two Year'] | 0 | PASS |
| Valid categories: PaymentMethod | Values in ['Bank Transfer', 'Credit Card', 'Debit Card', 'UPI'] | 0 | PASS |
| Valid categories: Churn | Values in ['No', 'Yes'] | 0 | PASS |
| Age range | 18 <= Age <= 100 | 0 | PASS |
| Tenure range | 0 <= TenureMonths <= 120 | 0 | PASS |
| Monthly charge > 0 | MonthlyCharges > 0 | 0 | PASS |
| Tickets non-negative | SupportTickets >= 0 and whole number | 0 | PASS |
| TotalCharges reconciliation | TotalCharges = TenureMonths x MonthlyCharges (+/- 0.01) | 0 | PASS |
| One price per plan | Each SubscriptionType has a single MonthlyCharges value | 0 | PASS |
| Extreme values (IQR 1.5x) | No numeric value outside Q1-1.5*IQR / Q3+1.5*IQR | 0 | PASS |

Observations that are not errors but worth knowing:

- **Field guide vs file mismatch.** The guide lists `contract_type` as monthly / quarterly / annual; the file has Month-to-Month / One Year / Two Year and no quarterly value. The file's labels were kept and not remapped.
- **Currency.** The guide says monthly charge is in INR; the CSV has no currency marker. Treated as INR, not converted.
- **Prices are fixed per plan** (Basic 49.99, Pro 79.99, Enterprise 149.99), so `monthly_charge` carries the same information as `subscription_type` and the two should not be read as independent signals.
- **Rows look generated** (evenly spaced IDs, round tenure values); this is synthetic data, so patterns are cleaner than real-world data would be.

## 4. Cleaning decisions (see Cleaning_Log sheet)

| step | action | rows_affected | assumption_or_reason |
|---|---|---|---|
| 1 | Trimmed whitespace in all text fields | 0 | Defensive; none were found in this file. |
| 2 | Cast Age, TenureMonths, SupportTickets to integer; MonthlyCharges, TotalCharges to float | 15 | All values parsed without coercion errors, so no values were nulled. |
| 3 | Standardised ID to upper case and Gender/Churn to Title Case | 0 | Values were already consistent. |
| 4 | Missing-value handling: imputed/dropped nothing | 0 | Zero missing values found; imputation would only add invented data. |
| 5 | Duplicate removal: removed nothing | 0 | Zero duplicate rows and zero duplicate CustomerIDs. |
| 6 | Outlier handling: kept all values | 0 | No IQR outliers. Enterprise-tier charges and 48-month tenure are legitimate business values, not errors. |
| 7 | Verified TotalCharges = TenureMonths x MonthlyCharges | 0 | All 15 rows reconcile to the cent; TotalCharges kept as supplied. |
| 8 | Renamed columns to snake_case (matches the task's field guide naming) | 15 | Guide uses customer_id / monthly_charge / contract_type; source uses CamelCase. |
| 9 | Added churned (1/0) from churn (Yes/No) | 15 | Numeric flag so churn rate = mean(churned). |
| 10 | Added tenure_band (0-6, 7-12, 13-24, 25+) and ticket_band (0-2, 3-4, 5+) | 15 | Bins chosen for readable group sizes; they are analysis aids, not source data. |
| 11 | Kept contract labels as Month-to-Month / One Year / Two Year | 0 | The field guide says monthly/quarterly/annual, but the file has no quarterly rows and has a Two Year tier. Data was not remapped; the mismatch is flagged in the report. |
| 12 | Treated monthly_charge and total_charges as INR | 0 | Per the field guide; the CSV itself carries no currency marker. Not converted. |

## 5. Validation after cleaning

| validation | result | detail |
|---|---|---|
| Row count preserved | PASS | 15 cleaned vs 15 raw |
| customer_id unique | PASS |  |
| No missing values | PASS |  |
| churn matches churned flag | PASS |  |
| total_charges = tenure x monthly | PASS |  |
| age within 18-100 | PASS |  |
| tenure within 0-120 | PASS |  |
| support_tickets >= 0 | PASS |  |
| categories all valid | PASS |  |
| Raw file untouched (15 data rows read) | PASS |  |

## 6. Summary statistics

| variable | count | mean | std | min | 25% | 50% | 75% | max | skew |
|---|---|---|---|---|---|---|---|---|---|
| age | 15.0 | 39.07 | 11.39 | 23.0 | 30.0 | 38.0 | 47.0 | 60.0 | 0.37 |
| tenure_months | 15.0 | 18.8 | 14.33 | 2.0 | 7.0 | 15.0 | 27.0 | 48.0 | 0.71 |
| monthly_charge | 15.0 | 84.66 | 42.74 | 49.99 | 49.99 | 79.99 | 114.99 | 149.99 | 0.87 |
| total_charges | 15.0 | 2088.48 | 2407.37 | 99.98 | 449.91 | 1099.78 | 3209.73 | 7199.52 | 1.21 |
| support_tickets | 15.0 | 2.53 | 1.92 | 0.0 | 1.0 | 2.0 | 4.0 | 6.0 | 0.36 |

Overall churn: **7 of 15 customers (46.7%)**, 95% Wilson interval 25%-70%. Monthly recurring charge from churned customers: 409.93 of 1269.85 total (32.3%).

## 7. Initial patterns (descriptive, not causal)

| dimension | segment | customers | churned | churn_rate_pct | avg_tickets | avg_tenure |
|---|---|---|---|---|---|---|
| contract_type | Month-to-Month | 7 | 7 | 100.0 | 4.29 | 7.0 |
| contract_type | One Year | 4 | 0 | 0.0 | 1.5 | 19.75 |
| contract_type | Two Year | 4 | 0 | 0.0 | 0.5 | 38.5 |
| subscription_type | Basic | 7 | 5 | 71.4 | 3.71 | 9.57 |
| subscription_type | Enterprise | 4 | 0 | 0.0 | 0.5 | 38.5 |
| subscription_type | Pro | 4 | 2 | 50.0 | 2.5 | 15.25 |
| payment_method | Bank Transfer | 3 | 0 | 0.0 | 1.0 | 31.33 |
| payment_method | Credit Card | 6 | 2 | 33.3 | 2.0 | 22.67 |
| payment_method | Debit Card | 2 | 2 | 100.0 | 3.5 | 11.0 |
| payment_method | UPI | 4 | 3 | 75.0 | 4.0 | 7.5 |
| gender | Female | 8 | 4 | 50.0 | 2.75 | 17.0 |
| gender | Male | 7 | 3 | 42.9 | 2.29 | 20.86 |
| tenure_band | 0-6 | 4 | 4 | 100.0 | 5.0 | 3.75 |
| tenure_band | 13-24 | 5 | 1 | 20.0 | 1.8 | 18.6 |
| tenure_band | 25+ | 4 | 0 | 0.0 | 0.5 | 38.5 |
| tenure_band | 7-12 | 2 | 2 | 100.0 | 3.5 | 10.0 |
| ticket_band | 0-2 | 8 | 0 | 0.0 | 1.0 | 29.12 |
| ticket_band | 3-4 | 4 | 4 | 100.0 | 3.5 | 9.5 |
| ticket_band | 5+ | 3 | 3 | 100.0 | 5.33 | 3.67 |

Average values by outcome: stayed - age 46.62, tenure 29.12 months, monthly charge 107.49, tickets 1.0; churned - age 30.43, tenure 7.0 months, monthly charge 58.56, tickets 4.29.

1. **Contract type.** Churn is 7/7 on Month-to-Month vs 0/4 on One Year and 0/4 on Two Year.
2. **Support tickets.** Every customer with 3+ tickets in 90 days churned; none with 0-2 did.
3. **Tenure.** All churners have tenure of 14 months or less; the shortest tenures (2-6 months) are all churners.
4. **Plan.** Basic churn is 5/7, Pro 2/4, Enterprise 0/4.
5. **Payment method.** Bank Transfer 0/3, Credit Card 2/6, UPI 3/4, Debit Card 2/2. Groups are 2-6 customers, so treat as weak.
6. **Gender.** Female 4/8, Male 3/7: no meaningful difference.

Several splits are **perfect** (for example, contract type and ticket count separate churners from non-churners without exception). Real customer data almost never does this; it is a sign of synthetic generation, and a model trained on it would not generalise. Contract, tenure, plan and tickets also overlap heavily (Month-to-Month customers are the short-tenure, Basic-plan, high-ticket ones), so their separate effects cannot be untangled with 15 rows.

## 8. Recommendation (decision brief)

- **Audience:** the fictional subscription retention team.
- **Decision:** which customer groups to contact first.
- **Suggested priority:** active Month-to-Month customers with 3+ support tickets and short tenure (Basic plan especially). In this sample that profile describes every churner.
- **Supporting metric:** churn rate by contract type and ticket band (7/7 and 7/7 in this sample).
- **Uncertainty:** n = 15; the overall churn interval alone spans 25%-70%. Correlated factors cannot be separated, and "churned" here means left during the observation period, so these customers are already gone; the data describes past churners, not current at-risk customers.
- **Next measurement:** score the current active base on contract type and ticket count, contact a test group, hold out a comparable control group, and compare 90-day retention. That is the only way to learn whether outreach, rather than the profile itself, changes the outcome.

## 9. Files

| File | Purpose |
|---|---|
| customer_churn_raw.csv | Unmodified source data |
| clean_churn.py | Reproducible cleaning + analysis script |
| customer_churn_cleaned.csv | Analysis-ready dataset (adds `churned`, `tenure_band`, `ticket_band`) |
| churn_data_quality_workbook.xlsx | Profile, checks, cleaning log, validation, stats, segments, charts |
| data_quality_summary.md | This report |
| charts/ | Four PNG charts |
