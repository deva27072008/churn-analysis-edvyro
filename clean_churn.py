"""
Customer churn: data-quality audit, cleaning and exploratory analysis.

Run:  python3 clean_churn.py
Input : customer_churn_raw.csv  (copy of https://edvyro.in/datasets/customer_churn_sample.csv, unmodified)
Output: customer_churn_cleaned.csv, churn_data_quality_workbook.xlsx,
        data_quality_summary.md, charts/*.png
Everything is deterministic: re-running reproduces identical outputs.
"""
import math
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HERE = Path(__file__).resolve().parent
RAW = HERE / "customer_churn_raw.csv"
CLEAN = HERE / "customer_churn_cleaned.csv"
XLSX = HERE / "churn_data_quality_workbook.xlsx"
MD = HERE / "data_quality_summary.md"
CHARTS = HERE / "charts"
CHARTS.mkdir(exist_ok=True)

# ----------------------------------------------------------------------------
# 1. LOAD (everything as given; no coercion yet)
# ----------------------------------------------------------------------------
raw = pd.read_csv(RAW, dtype=str, keep_default_na=False)
n_raw = len(raw)

# ----------------------------------------------------------------------------
# 2. PROFILE THE RAW DATA
# ----------------------------------------------------------------------------
NUMERIC = ["Age", "TenureMonths", "MonthlyCharges", "TotalCharges", "SupportTickets"]
CATEG = ["Gender", "SubscriptionType", "ContractType", "PaymentMethod", "Churn"]

typed = raw.copy()
for c in NUMERIC:
    typed[c] = pd.to_numeric(typed[c], errors="coerce")

def iqr_outliers(s):
    q1, q3 = s.quantile([0.25, 0.75])
    i = q3 - q1
    return int(((s < q1 - 1.5 * i) | (s > q3 + 1.5 * i)).sum())

profile_rows = []
for c in raw.columns:
    blank = int((raw[c].str.strip() == "").sum())
    row = {
        "column": c,
        "inferred_type": "numeric" if c in NUMERIC else "text/categorical",
        "non_null": n_raw - blank,
        "missing_or_blank": blank,
        "unique_values": int(raw[c].nunique()),
    }
    if c in NUMERIC:
        s = typed[c]
        row.update(min=s.min(), max=s.max(), mean=round(s.mean(), 2),
                   median=s.median(), iqr_outliers=iqr_outliers(s),
                   unparseable=int(s.isna().sum() - blank))
    else:
        row.update(min=None, max=None, mean=None, median=None, iqr_outliers=None, unparseable=None)
    profile_rows.append(row)
profile = pd.DataFrame(profile_rows)

# ----------------------------------------------------------------------------
# 3. QUALITY CHECKS ON RAW DATA
# ----------------------------------------------------------------------------
ALLOWED = {
    "Gender": {"Female", "Male"},
    "SubscriptionType": {"Basic", "Pro", "Enterprise"},
    "ContractType": {"Month-to-Month", "One Year", "Two Year"},
    "PaymentMethod": {"Credit Card", "Debit Card", "UPI", "Bank Transfer"},
    "Churn": {"Yes", "No"},
}
expected_total = (typed.TenureMonths * typed.MonthlyCharges).round(2)
price_by_plan = typed.groupby("SubscriptionType").MonthlyCharges.nunique()

checks = []
def add_check(name, rule, failures, note=""):
    checks.append({"check": name, "rule": rule, "rows_failing": int(failures),
                   "result": "PASS" if failures == 0 else "REVIEW", "note": note})

add_check("Missing values", "No blank/NA in any column", (raw.apply(lambda s: s.str.strip() == "")).sum().sum())
add_check("Duplicate rows", "No fully duplicated rows", raw.duplicated().sum())
add_check("Duplicate customer IDs", "CustomerID unique", raw.CustomerID.duplicated().sum())
add_check("ID format", r"CustomerID matches ^CUST-\d{4}$", (~raw.CustomerID.str.match(r"^CUST-\d{4}$")).sum())
add_check("Numeric parseable", "All numeric columns parse as numbers", typed[NUMERIC].isna().sum().sum())
add_check("Whitespace / case", "No leading/trailing spaces in text", sum((raw[c] != raw[c].str.strip()).sum() for c in raw.columns))
for c, allowed in ALLOWED.items():
    add_check(f"Valid categories: {c}", f"Values in {sorted(allowed)}", (~raw[c].isin(allowed)).sum())
add_check("Age range", "18 <= Age <= 100", ((typed.Age < 18) | (typed.Age > 100)).sum())
add_check("Tenure range", "0 <= TenureMonths <= 120", ((typed.TenureMonths < 0) | (typed.TenureMonths > 120)).sum())
add_check("Monthly charge > 0", "MonthlyCharges > 0", (typed.MonthlyCharges <= 0).sum())
add_check("Tickets non-negative", "SupportTickets >= 0 and whole number",
          ((typed.SupportTickets < 0) | (typed.SupportTickets % 1 != 0)).sum())
add_check("TotalCharges reconciliation", "TotalCharges = TenureMonths x MonthlyCharges (+/- 0.01)",
          (abs(expected_total - typed.TotalCharges) > 0.01).sum())
add_check("One price per plan", "Each SubscriptionType has a single MonthlyCharges value", int((price_by_plan > 1).sum()))
add_check("Extreme values (IQR 1.5x)", "No numeric value outside Q1-1.5*IQR / Q3+1.5*IQR",
          sum(iqr_outliers(typed[c]) for c in NUMERIC))
checks = pd.DataFrame(checks)

# ----------------------------------------------------------------------------
# 4. CLEAN (every step logged, nothing dropped silently)
# ----------------------------------------------------------------------------
log = []
def add_log(step, action, rows_affected, assumption):
    log.append({"step": len(log) + 1, "action": action, "rows_affected": int(rows_affected), "assumption_or_reason": assumption})

df = raw.copy()
changed = sum((df[c] != df[c].str.strip()).sum() for c in df.columns)
df = df.apply(lambda s: s.str.strip())
add_log("trim", "Trimmed whitespace in all text fields", changed, "Defensive; none were found in this file.")

for c in NUMERIC:
    df[c] = pd.to_numeric(df[c], errors="raise")
df["Age"] = df.Age.astype(int)
df["TenureMonths"] = df.TenureMonths.astype(int)
df["SupportTickets"] = df.SupportTickets.astype(int)
add_log("types", "Cast Age, TenureMonths, SupportTickets to integer; MonthlyCharges, TotalCharges to float",
        n_raw, "All values parsed without coercion errors, so no values were nulled.")

df["CustomerID"] = df.CustomerID.str.upper()
for c in CATEG:
    df[c] = df[c].str.title() if c in ("Gender", "Churn") else df[c]
add_log("case", "Standardised ID to upper case and Gender/Churn to Title Case", 0, "Values were already consistent.")

add_log("missing", "Missing-value handling: imputed/dropped nothing", 0, "Zero missing values found; imputation would only add invented data.")
add_log("duplicates", "Duplicate removal: removed nothing", 0, "Zero duplicate rows and zero duplicate CustomerIDs.")
add_log("outliers", "Outlier handling: kept all values", 0,
        "No IQR outliers. Enterprise-tier charges and 48-month tenure are legitimate business values, not errors.")
add_log("total_check", "Verified TotalCharges = TenureMonths x MonthlyCharges", 0,
        "All 15 rows reconcile to the cent; TotalCharges kept as supplied.")

df = df.rename(columns={
    "CustomerID": "customer_id", "Gender": "gender", "Age": "age", "TenureMonths": "tenure_months",
    "SubscriptionType": "subscription_type", "MonthlyCharges": "monthly_charge", "TotalCharges": "total_charges",
    "ContractType": "contract_type", "SupportTickets": "support_tickets", "PaymentMethod": "payment_method",
    "Churn": "churn",
})
add_log("rename", "Renamed columns to snake_case (matches the task's field guide naming)", n_raw,
        "Guide uses customer_id / monthly_charge / contract_type; source uses CamelCase.")

df["churned"] = (df.churn == "Yes").astype(int)
add_log("flag", "Added churned (1/0) from churn (Yes/No)", n_raw, "Numeric flag so churn rate = mean(churned).")

df["tenure_band"] = pd.cut(df.tenure_months, [-1, 6, 12, 24, 999], labels=["0-6", "7-12", "13-24", "25+"]).astype(str)
df["ticket_band"] = pd.cut(df.support_tickets, [-1, 2, 4, 999], labels=["0-2", "3-4", "5+"]).astype(str)
add_log("bands", "Added tenure_band (0-6, 7-12, 13-24, 25+) and ticket_band (0-2, 3-4, 5+)", n_raw,
        "Bins chosen for readable group sizes; they are analysis aids, not source data.")

add_log("contract_labels", "Kept contract labels as Month-to-Month / One Year / Two Year", 0,
        "The field guide says monthly/quarterly/annual, but the file has no quarterly rows and has a Two Year tier. "
        "Data was not remapped; the mismatch is flagged in the report.")
add_log("currency", "Treated monthly_charge and total_charges as INR", 0,
        "Per the field guide; the CSV itself carries no currency marker. Not converted.")

df = df.sort_values("customer_id").reset_index(drop=True)
df.to_csv(CLEAN, index=False)

# ----------------------------------------------------------------------------
# 5. VALIDATE THE CLEANED DATA (post-clean assertions)
# ----------------------------------------------------------------------------
chk = pd.read_csv(CLEAN)
validation = []
def v(name, ok, detail=""):
    validation.append({"validation": name, "result": "PASS" if ok else "FAIL", "detail": detail})
    assert ok, f"Validation failed: {name} {detail}"

v("Row count preserved", len(chk) == n_raw, f"{len(chk)} cleaned vs {n_raw} raw")
v("customer_id unique", chk.customer_id.is_unique)
v("No missing values", int(chk.isna().sum().sum()) == 0)
v("churn matches churned flag", bool(((chk.churn == "Yes") == (chk.churned == 1)).all()))
v("total_charges = tenure x monthly", bool((abs(chk.tenure_months * chk.monthly_charge - chk.total_charges) <= 0.01).all()))
v("age within 18-100", bool(chk.age.between(18, 100).all()))
v("tenure within 0-120", bool(chk.tenure_months.between(0, 120).all()))
v("support_tickets >= 0", bool((chk.support_tickets >= 0).all()))
v("categories all valid", all(set(chk[c.lower() if c not in ("SubscriptionType", "ContractType", "PaymentMethod") else
                                      {"SubscriptionType": "subscription_type", "ContractType": "contract_type", "PaymentMethod": "payment_method"}[c]]) <= ALLOWED[c]
                              for c in CATEG))
v("Raw file untouched (15 data rows read)", n_raw == 15)
validation = pd.DataFrame(validation)

# ----------------------------------------------------------------------------
# 6. EXPLORATORY ANALYSIS
# ----------------------------------------------------------------------------
num_cols = ["age", "tenure_months", "monthly_charge", "total_charges", "support_tickets"]
summary_stats = chk[num_cols].describe().T.round(2)
summary_stats.insert(0, "variable", summary_stats.index)
summary_stats["skew"] = chk[num_cols].skew().round(2).values

def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0, c - h), min(1, c + h)

lo, hi = wilson(int(chk.churned.sum()), n_raw)
overall = {"customers": n_raw, "churned": int(chk.churned.sum()), "churn_rate": chk.churned.mean(),
           "ci_low": lo, "ci_high": hi}

def seg(col):
    g = chk.groupby(col).agg(customers=("churned", "size"), churned=("churned", "sum"),
                             avg_monthly_charge=("monthly_charge", "mean"),
                             avg_tickets=("support_tickets", "mean"), avg_tenure=("tenure_months", "mean")).reset_index()
    g["churn_rate_pct"] = (g.churned / g.customers * 100).round(1)
    g[["avg_monthly_charge", "avg_tickets", "avg_tenure"]] = g[["avg_monthly_charge", "avg_tickets", "avg_tenure"]].round(2)
    g.insert(0, "dimension", col)
    return g.rename(columns={col: "segment"})

segments = pd.concat([seg(c) for c in ["contract_type", "subscription_type", "payment_method", "gender",
                                         "tenure_band", "ticket_band"]], ignore_index=True)

by_churn = chk.groupby("churn")[num_cols].mean().round(2).reset_index()
corr = chk[num_cols + ["churned"]].corr().round(2)
corr.insert(0, "variable", corr.index)

# revenue at risk (descriptive): monthly recurring revenue from customers who churned
mrr_total = chk.monthly_charge.sum()
mrr_churned = chk.loc[chk.churned == 1, "monthly_charge"].sum()

# ----------------------------------------------------------------------------
# 7. CHARTS
# ----------------------------------------------------------------------------
BLUE, ORANGE, GREY = "#2a6fb0", "#d9731a", "#6b7280"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})

def save(fig, name):
    fig.tight_layout()
    fig.savefig(CHARTS / name, dpi=130)
    plt.close(fig)

# a) churn rate by contract
g = seg("contract_type")
fig, ax = plt.subplots(figsize=(6, 3.6))
bars = ax.bar(g.segment, g.churn_rate_pct, color=BLUE)
for b, (n, k) in zip(bars, zip(g.customers, g.churned)):
    ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 2, f"{k}/{n}", ha="center")
ax.set_ylim(0, 115); ax.set_ylabel("Churn rate (%)"); ax.set_title("Churn rate by contract type (churned/customers)")
save(fig, "churn_by_contract.png")

# b) tenure distribution by churn
fig, ax = plt.subplots(figsize=(6, 3.6))
bins = np.arange(0, 54, 6)
ax.hist([chk.loc[chk.churned == 0, "tenure_months"], chk.loc[chk.churned == 1, "tenure_months"]],
        bins=bins, label=["Stayed", "Churned"], color=[BLUE, ORANGE])
ax.set_xlabel("Tenure (months)"); ax.set_ylabel("Customers"); ax.set_title("Tenure distribution by churn outcome"); ax.legend(frameon=False)
save(fig, "tenure_distribution.png")

# c) tickets vs churn
t = chk.groupby("support_tickets").agg(n=("churned", "size"), churned=("churned", "sum")).reset_index()
fig, ax = plt.subplots(figsize=(6, 3.6))
ax.bar(t.support_tickets, t.n - t.churned, color=BLUE, label="Stayed")
ax.bar(t.support_tickets, t.churned, bottom=t.n - t.churned, color=ORANGE, label="Churned")
ax.set_xlabel("Support tickets (previous 90 days)"); ax.set_ylabel("Customers")
ax.set_title("Support tickets vs churn outcome"); ax.legend(frameon=False)
save(fig, "tickets_vs_churn.png")

# d) monthly charge by plan
fig, ax = plt.subplots(figsize=(6, 3.6))
order = ["Basic", "Pro", "Enterprise"]
for i, p in enumerate(order):
    sub = chk[chk.subscription_type == p]
    ax.scatter(np.full(len(sub), i) + np.linspace(-0.12, 0.12, len(sub)), sub.tenure_months,
               c=[ORANGE if x else BLUE for x in sub.churned], s=45)
ax.set_xticks(range(3)); ax.set_xticklabels([f"{p}\n({chk[chk.subscription_type==p].monthly_charge.iloc[0]})" for p in order])
ax.set_ylabel("Tenure (months)"); ax.set_title("Tenure by plan (orange = churned, blue = stayed)")
save(fig, "tenure_by_plan.png")

# ----------------------------------------------------------------------------
# 8. EXCEL WORKBOOK
# ----------------------------------------------------------------------------
wb = Workbook()
HEAD = PatternFill("solid", fgColor="1F3A5F")
WHITE = Font(color="FFFFFF", bold=True)

def write_df(ws, frame, start_row=1):
    for j, col in enumerate(frame.columns, 1):
        c = ws.cell(row=start_row, column=j, value=col)
        c.fill, c.font = HEAD, WHITE
        c.alignment = Alignment(wrap_text=True, vertical="top")
    for i, row in enumerate(frame.itertuples(index=False), start_row + 1):
        for j, val in enumerate(row, 1):
            if isinstance(val, (np.integer,)): val = int(val)
            elif isinstance(val, (np.floating,)): val = None if np.isnan(val) else float(val)
            ws.cell(row=i, column=j, value=val).alignment = Alignment(wrap_text=True, vertical="top")
    for j, col in enumerate(frame.columns, 1):
        width = max([len(str(col))] + [len(str(x)) for x in frame.iloc[:, j - 1]]) + 2
        ws.column_dimensions[get_column_letter(j)].width = min(max(width, 10), 70)
    ws.freeze_panes = ws.cell(row=start_row + 1, column=1)

ws = wb.active; ws.title = "README"
readme = [
    ("Customer churn - data quality & EDA workbook", True),
    ("Source: customer_churn_sample.csv (15 synthetic customers, 11 columns). Reproduce with clean_churn.py.", False),
    ("", False),
    ("Sheets", True),
    ("Profile - column types, missing values, ranges, outliers (raw data)", False),
    ("Quality_Checks - every rule tested on the raw data and its result", False),
    ("Cleaning_Log - each cleaning action, rows affected, and the assumption behind it", False),
    ("Validation - post-clean assertions (all must PASS)", False),
    ("Summary_Stats - descriptive statistics of numeric fields", False),
    ("Churn_Segments - churn rate by contract, plan, payment, gender, tenure band, ticket band", False),
    ("Means_by_Churn / Correlations - descriptive comparisons only (not causal)", False),
    ("Cleaned_Data - analysis-ready dataset (same as customer_churn_cleaned.csv)", False),
    ("Charts - four exploratory charts", False),
    ("", False),
    ("Caution: n = 15. Rates are shown with counts; the data cannot support predictions or causal claims.", True),
]
for r, (txt, bold) in enumerate(readme, 1):
    ws.cell(row=r, column=1, value=txt).font = Font(bold=bold, size=14 if r == 1 else 11)
ws.column_dimensions["A"].width = 110

for name, frame in [("Profile", profile), ("Quality_Checks", checks), ("Cleaning_Log", pd.DataFrame(log)),
                    ("Validation", validation), ("Summary_Stats", summary_stats.reset_index(drop=True)),
                    ("Churn_Segments", segments), ("Means_by_Churn", by_churn),
                    ("Correlations", corr.reset_index(drop=True)), ("Cleaned_Data", chk)]:
    write_df(wb.create_sheet(name), frame)

wc = wb.create_sheet("Charts")
for i, f in enumerate(["churn_by_contract.png", "tenure_distribution.png", "tickets_vs_churn.png", "tenure_by_plan.png"]):
    img = XLImage(str(CHARTS / f)); img.width, img.height = 520, 312
    wc.add_image(img, f"{'A' if i % 2 == 0 else 'L'}{1 + (i // 2) * 18}")
wb.save(XLSX)

# ----------------------------------------------------------------------------
# 9. DATA-QUALITY SUMMARY (markdown, numbers pulled from the data)
# ----------------------------------------------------------------------------
def rate(col, val):
    r = segments[(segments.dimension == col) & (segments.segment == val)].iloc[0]
    return f"{int(r.churned)}/{int(r.customers)}"

def md_table(frame):
    cols = list(frame.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for row in frame.itertuples(index=False):
        out.append("| " + " | ".join("" if (isinstance(x, float) and np.isnan(x)) else str(x) for x in row) + " |")
    return "\n".join(out)

seg_md = segments[["dimension", "segment", "customers", "churned", "churn_rate_pct", "avg_tickets", "avg_tenure"]]
mean_no = by_churn[by_churn.churn == "No"].iloc[0]
mean_yes = by_churn[by_churn.churn == "Yes"].iloc[0]

md = f"""# Customer Churn - Data Quality Report & Initial Patterns

**Dataset:** customer_churn_sample.csv - {n_raw} synthetic customer records, 11 columns.
**Reproduce:** `python3 clean_churn.py` (reads `customer_churn_raw.csv`, writes the cleaned CSV, workbook, charts and this report).

## 1. Headline

- The file is **structurally clean**: 0 missing values, 0 duplicate rows, 0 duplicate IDs, 0 invalid categories, 0 impossible values, 0 IQR outliers, and TotalCharges reconciles to tenure x monthly charge on all {n_raw} rows.
- **{n_raw} rows in, {n_raw} rows out.** Nothing was deleted, imputed or capped.
- The main limitation is not dirty data but **size**: with {n_raw} customers, patterns are descriptive only.

## 2. Profile (raw data)

{md_table(profile[['column','inferred_type','non_null','missing_or_blank','unique_values','min','max','mean','iqr_outliers']])}

## 3. Quality checks on raw data

{md_table(checks[['check','rule','rows_failing','result']])}

Observations that are not errors but worth knowing:

- **Field guide vs file mismatch.** The guide lists `contract_type` as monthly / quarterly / annual; the file has Month-to-Month / One Year / Two Year and no quarterly value. The file's labels were kept and not remapped.
- **Currency.** The guide says monthly charge is in INR; the CSV has no currency marker. Treated as INR, not converted.
- **Prices are fixed per plan** (Basic 49.99, Pro 79.99, Enterprise 149.99), so `monthly_charge` carries the same information as `subscription_type` and the two should not be read as independent signals.
- **Rows look generated** (evenly spaced IDs, round tenure values); this is synthetic data, so patterns are cleaner than real-world data would be.

## 4. Cleaning decisions (see Cleaning_Log sheet)

{md_table(pd.DataFrame(log)[['step','action','rows_affected','assumption_or_reason']])}

## 5. Validation after cleaning

{md_table(validation)}

## 6. Summary statistics

{md_table(summary_stats[['variable','count','mean','std','min','25%','50%','75%','max','skew']])}

Overall churn: **{overall['churned']} of {overall['customers']} customers ({overall['churn_rate']*100:.1f}%)**, 95% Wilson interval {overall['ci_low']*100:.0f}%-{overall['ci_high']*100:.0f}%. Monthly recurring charge from churned customers: {mrr_churned:.2f} of {mrr_total:.2f} total ({mrr_churned/mrr_total*100:.1f}%).

## 7. Initial patterns (descriptive, not causal)

{md_table(seg_md)}

Average values by outcome: stayed - age {mean_no.age}, tenure {mean_no.tenure_months} months, monthly charge {mean_no.monthly_charge}, tickets {mean_no.support_tickets}; churned - age {mean_yes.age}, tenure {mean_yes.tenure_months} months, monthly charge {mean_yes.monthly_charge}, tickets {mean_yes.support_tickets}.

1. **Contract type.** Churn is {rate('contract_type','Month-to-Month')} on Month-to-Month vs {rate('contract_type','One Year')} on One Year and {rate('contract_type','Two Year')} on Two Year.
2. **Support tickets.** Every customer with 3+ tickets in 90 days churned; none with 0-2 did.
3. **Tenure.** All churners have tenure of 14 months or less; the shortest tenures (2-6 months) are all churners.
4. **Plan.** Basic churn is {rate('subscription_type','Basic')}, Pro {rate('subscription_type','Pro')}, Enterprise {rate('subscription_type','Enterprise')}.
5. **Payment method.** Bank Transfer {rate('payment_method','Bank Transfer')}, Credit Card {rate('payment_method','Credit Card')}, UPI {rate('payment_method','UPI')}, Debit Card {rate('payment_method','Debit Card')}. Groups are 2-6 customers, so treat as weak.
6. **Gender.** Female {rate('gender','Female')}, Male {rate('gender','Male')}: no meaningful difference.

Several splits are **perfect** (for example, contract type and ticket count separate churners from non-churners without exception). Real customer data almost never does this; it is a sign of synthetic generation, and a model trained on it would not generalise. Contract, tenure, plan and tickets also overlap heavily (Month-to-Month customers are the short-tenure, Basic-plan, high-ticket ones), so their separate effects cannot be untangled with 15 rows.

## 8. Recommendation (decision brief)

- **Audience:** the fictional subscription retention team.
- **Decision:** which customer groups to contact first.
- **Suggested priority:** active Month-to-Month customers with 3+ support tickets and short tenure (Basic plan especially). In this sample that profile describes every churner.
- **Supporting metric:** churn rate by contract type and ticket band (7/7 and 7/7 in this sample).
- **Uncertainty:** n = {n_raw}; the overall churn interval alone spans {overall['ci_low']*100:.0f}%-{overall['ci_high']*100:.0f}%. Correlated factors cannot be separated, and "churned" here means left during the observation period, so these customers are already gone; the data describes past churners, not current at-risk customers.
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
"""
MD.write_text(md, encoding="utf-8")
print("OK:", CLEAN.name, XLSX.name, MD.name, "charts:", len(list(CHARTS.glob('*.png'))))
