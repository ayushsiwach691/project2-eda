"""
DecodeLabs | Data Analytics | Project 2: Exploratory Data Analysis (EDA)
Dataset : data/ABC.xlsx  (E-commerce orders, 1,200 rows x 14 columns)

Follows the IPO framework from the project kit:
    INPUT   -> load + data-quality "forensics"
    PROCESS -> descriptive statistics, outliers, trends, correlation
    OUTPUT  -> charts/, outputs/*.csv and key findings (see README.md)

Run:  python eda_analysis.py
"""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats

BASE = Path(__file__).parent
CHARTS, OUT = BASE / "charts", BASE / "outputs"
CHARTS.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

# ---- chart style: "cut the noise, highlight the insight" ----
GREY, ACCENT, ALERT = "#B8BEC6", "#1F77B4", "#D62728"
sns.set_theme(style="whitegrid")
plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False,
                     "figure.dpi": 120, "axes.titleweight": "bold"})


def save(name):
    plt.tight_layout()
    plt.savefig(CHARTS / name, bbox_inches="tight")
    plt.close()


# =====================================================================
# 1. INPUT - load data & data-quality checks
# =====================================================================
df = pd.read_excel(BASE / "data" / "ABC.xlsx")
print("Shape:", df.shape)

quality = pd.DataFrame({
    "dtype": df.dtypes.astype(str),
    "missing": df.isna().sum(),
    "missing_%": (df.isna().mean() * 100).round(2),
    "unique": df.nunique(),
})
quality.to_csv(OUT / "01_data_quality.csv")
print("\n--- Data quality ---\n", quality)
print("Duplicate rows:", df.duplicated().sum())
print("Duplicate OrderID:", df.OrderID.duplicated().sum())
print("Duplicate TrackingNumber:", df.TrackingNumber.duplicated().sum())

# Integrity check: TotalPrice should equal Quantity * UnitPrice
mismatch = (df.Quantity * df.UnitPrice - df.TotalPrice).abs().gt(0.01).sum()
print("TotalPrice != Quantity*UnitPrice rows:", mismatch)

# CouponCode NaN means "no coupon used" (not a data error) -> label it
df["CouponCode"] = df["CouponCode"].fillna("No Coupon")

# Feature engineering for time analysis
df["Year"] = df.Date.dt.year
df["Month"] = df.Date.dt.month
df["YearMonth"] = df.Date.dt.to_period("M").dt.to_timestamp()

# =====================================================================
# 2. PROCESS - descriptive statistics
# =====================================================================
num_cols = ["Quantity", "UnitPrice", "ItemsInCart", "TotalPrice"]
desc = df[num_cols].describe().T
desc["median"] = df[num_cols].median()
desc["skewness"] = df[num_cols].skew()
desc = desc[["count", "mean", "median", "std", "min", "25%", "50%", "75%", "max", "skewness"]]
desc.round(2).to_csv(OUT / "02_summary_statistics.csv")
print("\n--- Summary statistics ---\n", desc.round(2))

# Category counts
for col in ["Product", "PaymentMethod", "OrderStatus", "CouponCode", "ReferralSource"]:
    df[col].value_counts().rename("count").to_frame().assign(
        pct=lambda d: (d["count"] / len(df) * 100).round(1)
    ).to_csv(OUT / f"03_counts_{col}.csv")

# Product performance
product = df.groupby("Product").TotalPrice.agg(
    orders="count", revenue="sum", mean_order_value="mean", median_order_value="median"
).round(2).sort_values("revenue", ascending=False)
product.to_csv(OUT / "04_product_performance.csv")
print("\n--- Product performance ---\n", product)

# Order status (revenue at risk)
status = df.groupby("OrderStatus").TotalPrice.agg(orders="count", revenue="sum").round(2)
status["orders_%"] = (status.orders / status.orders.sum() * 100).round(1)
status["revenue_%"] = (status.revenue / status.revenue.sum() * 100).round(1)
status.to_csv(OUT / "05_order_status.csv")
print("\n--- Order status ---\n", status)

# Channel & payment
for col, fn in [("ReferralSource", "06_referral_source.csv"),
                ("PaymentMethod", "07_payment_method.csv"),
                ("CouponCode", "08_coupon.csv")]:
    df.groupby(col).TotalPrice.agg(orders="count", revenue="sum", mean_order_value="mean") \
        .round(2).sort_values("revenue", ascending=False).to_csv(OUT / fn)

# =====================================================================
# 3. OUTLIERS - IQR (robust) vs Z-score
# =====================================================================
def iqr_bounds(s):
    q1, q3 = s.quantile([0.25, 0.75])
    iqr = q3 - q1
    return q1 - 1.5 * iqr, q3 + 1.5 * iqr


rows = []
for c in num_cols:
    lo, hi = iqr_bounds(df[c])
    z = (df[c] - df[c].mean()) / df[c].std()
    rows.append({"column": c, "IQR_lower": round(lo, 2), "IQR_upper": round(hi, 2),
                 "IQR_outliers": int(((df[c] < lo) | (df[c] > hi)).sum()),
                 "Z>3_outliers": int((z.abs() > 3).sum())})
outlier_summary = pd.DataFrame(rows)
outlier_summary.to_csv(OUT / "09_outlier_summary.csv", index=False)
print("\n--- Outlier summary ---\n", outlier_summary)

lo, hi = iqr_bounds(df.TotalPrice)
tp_outliers = df[(df.TotalPrice < lo) | (df.TotalPrice > hi)].sort_values("TotalPrice", ascending=False)
tp_outliers.drop(columns=["YearMonth"]).to_csv(OUT / "10_totalprice_outliers.csv", index=False)
print(f"\nTotalPrice IQR upper fence = {hi:.2f}; outliers = {len(tp_outliers)}")

# Tiny-price check (possible data-entry issue?)
print("Orders with UnitPrice < 50:", (df.UnitPrice < 50).sum(), "| min UnitPrice:", df.UnitPrice.min())

# =====================================================================
# 4. TRENDS
# =====================================================================
monthly = df.groupby("YearMonth").agg(orders=("OrderID", "count"),
                                       revenue=("TotalPrice", "sum"),
                                       aov=("TotalPrice", "mean"))
monthly.round(2).to_csv(OUT / "11_monthly_trend.csv")

# Fair year-over-year view: data ends 30-Jun-2025, so compare Jan-Jun only
h1 = df[df.Month <= 6].groupby("Year").agg(orders=("OrderID", "count"),
                                           revenue=("TotalPrice", "sum"),
                                           aov=("TotalPrice", "mean")).round(2)
h1["revenue_yoy_%"] = (h1.revenue.pct_change() * 100).round(1)
h1["orders_yoy_%"] = (h1.orders.pct_change() * 100).round(1)
h1["aov_yoy_%"] = (h1.aov.pct_change() * 100).round(1)
h1.to_csv(OUT / "12_h1_year_over_year.csv")
print("\n--- Jan-Jun like-for-like comparison ---\n", h1)

# Seasonality must be normalised: Jan-Jun has 3 years of data, Jul-Dec only 2
years_seen = df.groupby("Month").Year.nunique()
season = (df.groupby("Month").TotalPrice.sum() / years_seen).rename("avg_revenue_per_year")
season.round(2).to_csv(OUT / "13_seasonality_avg_per_year.csv")
print("\n--- Seasonality (avg revenue per year of data) ---\n", season.round(0))

# ---- Chart 1: distributions (shape of the evidence) ----
fig, ax = plt.subplots(1, 2, figsize=(11, 4))
sns.histplot(df.TotalPrice, bins=35, color=ACCENT, ax=ax[0])
ax[0].axvline(df.TotalPrice.mean(), color=ALERT, ls="--", label=f"Mean {df.TotalPrice.mean():,.0f}")
ax[0].axvline(df.TotalPrice.median(), color="black", ls="-", label=f"Median {df.TotalPrice.median():,.0f}")
ax[0].set(title="Order value is right-skewed: mean > median", xlabel="TotalPrice", ylabel="Orders")
ax[0].legend()
sns.histplot(df.UnitPrice, bins=35, color=GREY, ax=ax[1])
ax[1].set(title="Unit price is roughly uniform (11 - 700)", xlabel="UnitPrice", ylabel="Orders")
save("01_distributions.png")

# ---- Chart 2: boxplot of TotalPrice (outliers) ----
plt.figure(figsize=(9, 3))
sns.boxplot(x=df.TotalPrice, color=GREY, flierprops=dict(markerfacecolor=ALERT, markeredgecolor=ALERT))
plt.title(f"Only {len(tp_outliers)} of 1,200 orders are IQR outliers (> {hi:,.0f})")
plt.xlabel("TotalPrice")
save("02_boxplot_totalprice.png")

# ---- Chart 3: Product revenue ----
p = product.sort_values("revenue")
top3 = set(product.head(3).index)
plt.figure(figsize=(8, 4.5))
plt.barh(p.index, p.revenue, color=[ACCENT if k in top3 else GREY for k in p.index])
for i, v in enumerate(p.revenue):
    plt.text(v, i, f" {v/1000:,.0f}k", va="center")
plt.title("Top 3 products by revenue (blue); Phone trails")
plt.xlabel("Total revenue")
save("03_revenue_by_product.png")

# ---- Chart 4: Order status (revenue at risk) ----
s = status.revenue.sort_values()
plt.figure(figsize=(8, 4))
plt.barh(s.index, s.values, color=[ALERT if k in ("Cancelled", "Returned") else GREY for k in s.index])
for i, (k, v) in enumerate(s.items()):
    plt.text(v, i, f" {v/1000:,.0f}k ({status.loc[k, 'revenue_%']}%)", va="center")
at_risk = status.loc[["Cancelled", "Returned"], "revenue_%"].sum()
plt.title(f"{at_risk:.0f}% of order value is Cancelled or Returned")
plt.xlabel("Revenue")
plt.xlim(0, s.max() * 1.25)
save("04_order_status.png")

# ---- Chart 5: Monthly trend ----
fig, ax = plt.subplots(figsize=(11, 4))
ax.plot(monthly.index, monthly.revenue, color=ACCENT, marker="o", ms=3)
ax.set(title="Monthly revenue, Jan 2023 - Jun 2025", ylabel="Revenue", xlabel="")
peak = monthly.revenue.idxmax()
ax.annotate(f"Peak: {peak:%b %Y}", (peak, monthly.revenue.max()),
            xytext=(10, 8), textcoords="offset points", color=ALERT)
save("05_monthly_revenue.png")

# ---- Chart 6: like-for-like H1 comparison ----
fig, ax = plt.subplots(1, 2, figsize=(10, 4))
ax[0].bar(h1.index.astype(str), h1.revenue, color=[GREY, GREY, ACCENT])
ax[0].set(title="Jan-Jun revenue falls every year", ylabel="Revenue")
ax[1].bar(h1.index.astype(str), h1.aov, color=[GREY, GREY, ACCENT])
ax[1].set(title="Jan-Jun avg order value falls every year", ylabel="Avg order value")
for a, col in zip(ax, ["revenue", "aov"]):
    for i, v in enumerate(h1[col]):
        a.text(i, v, f"{v:,.0f}", ha="center", va="bottom")
save("06_h1_year_over_year.png")

# ---- Chart 7: seasonality (normalised) ----
plt.figure(figsize=(10, 4))
plt.bar(season.index, season.values, color=[ALERT if m == season.idxmax() else GREY for m in season.index])
plt.xticks(range(1, 13), ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
plt.title("Seasonality (avg revenue per year of data): June is the only real peak")
plt.ylabel("Avg revenue per year")
save("07_seasonality_normalised.png")

# ---- Chart 8: channels ----
ref = df.groupby("ReferralSource").TotalPrice.agg(["sum", "mean"]).sort_values("sum")
fig, ax = plt.subplots(1, 2, figsize=(11, 4))
ax[0].barh(ref.index, ref["sum"], color=GREY)
ax[0].set(title="Revenue by referral source", xlabel="Revenue")
ax[1].barh(ref.index, ref["mean"], color=GREY)
ax[1].set(title="Avg order value by referral source", xlabel="Avg order value")
save("08_referral_source.png")

# =====================================================================
# 5. CORRELATION
# =====================================================================
corr = df[num_cols].corr(method="pearson")
corr.round(3).to_csv(OUT / "14_correlation_matrix.csv")
print("\n--- Pearson correlation ---\n", corr.round(3))

plt.figure(figsize=(6, 5))
sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm", vmin=-1, vmax=1, square=True)
plt.title("Correlation matrix (Pearson r)")
save("09_correlation_heatmap.png")

rng = np.random.default_rng(1)
fig, ax = plt.subplots(1, 2, figsize=(11, 4))
ax[0].scatter(df.Quantity + rng.uniform(-.15, .15, len(df)),
              df.ItemsInCart + rng.uniform(-.15, .15, len(df)),
              s=8, color=ACCENT, alpha=.5)
ax[0].set(title="ItemsInCart is never below Quantity", xlabel="Quantity (jittered)", ylabel="ItemsInCart")
ax[1].scatter(df.UnitPrice, df.TotalPrice, s=8, color=ACCENT, alpha=.5)
ax[1].set(title="TotalPrice vs UnitPrice (r = %.2f)" % corr.loc["UnitPrice", "TotalPrice"],
          xlabel="UnitPrice", ylabel="TotalPrice")
save("10_scatter_relationships.png")

# =====================================================================
# 6. Are the category differences real? (Chi-square tests)
# =====================================================================
tests = []
for col in ["Product", "PaymentMethod", "ReferralSource", "CouponCode"]:
    chi2, pval, _, _ = stats.chi2_contingency(pd.crosstab(df[col], df.OrderStatus))
    tests.append({"variable": col, "vs": "OrderStatus", "chi2": round(chi2, 2),
                  "p_value": round(pval, 4), "significant_at_0.05": bool(pval < 0.05)})
tests = pd.DataFrame(tests)
tests.to_csv(OUT / "15_chi_square_tests.csv", index=False)
print("\n--- Chi-square: is OrderStatus related to these variables? ---\n", tests)

ret = df.assign(Returned=df.OrderStatus.eq("Returned")).groupby("PaymentMethod").Returned.mean().mul(100).round(1)
print("\nReturn rate % by payment method:\n", ret)

rep = df.CustomerID.value_counts()
print("\nCustomers:", len(rep), "| repeat customers:", (rep > 1).sum())

print("\nTotal revenue (all statuses): %.2f | AOV mean %.2f | median %.2f" %
      (df.TotalPrice.sum(), df.TotalPrice.mean(), df.TotalPrice.median()))
print("Done. Charts ->", CHARTS, "| Tables ->", OUT)
