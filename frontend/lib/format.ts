// Display helpers. They only format numbers already reported or calculated by the backend;
// no arithmetic on financial values happens in the browser (hard rule 3).

export const METRIC_NAMES: Record<string, string> = {
  revenue_from_operations: "Revenue from operations",
  other_income: "Other income",
  total_income: "Total income",
  finance_costs: "Finance costs",
  depreciation_amortisation: "Depreciation and amortisation",
  profit_before_tax: "Profit before tax",
  total_tax_expense: "Total tax expense",
  profit_after_tax: "Profit after tax",
  eps_basic: "EPS, basic",
  eps_diluted: "EPS, diluted",
  net_cash_from_operating_activities: "Operating cash flow",
  equity_share_capital: "Equity share capital",
  other_equity: "Other equity",
  non_controlling_interest: "Non-controlling interest",
  total_equity: "Total equity",
  borrowings_non_current: "Borrowings, non-current",
  borrowings_current: "Borrowings, current",
  deferred_payment_liabilities_non_current: "Deferred payment liabilities, non-current",
  deferred_payment_liabilities_current: "Deferred payment liabilities, current",
  cash_and_cash_equivalents: "Cash and cash equivalents",
  total_assets: "Total assets",
  ebitda: "EBITDA",
  adjusted_ebitda: "Adjusted EBITDA (excl. other income)",
  ebitda_margin_pct: "EBITDA margin",
  adjusted_ebitda_margin_pct: "Adjusted EBITDA margin",
  pat_margin_pct: "PAT margin",
  return_on_equity_pct: "Return on equity (average equity)",
  return_on_net_worth_pct: "Return on net worth (closing)",
  total_debt: "Total debt (borrowings)",
  debt_to_equity: "Debt to equity (borrowings)",
  total_debt_incl_deferred_payments: "Total debt incl. deferred payments",
  debt_to_equity_incl_deferred_payments: "Debt to equity incl. deferred payments",
};

export const FIELD_NAMES: Record<string, string> = {
  fresh_issue_amount: "Fresh issue",
  fresh_issue_shares: "Fresh issue, shares",
  offer_for_sale_amount: "Offer for sale",
  offer_for_sale_shares: "Offer for sale, shares",
  total_issue_amount: "Total issue size",
  total_issue_shares: "Total issue, shares",
  face_value: "Face value",
  price_band: "Price band",
  anchor_bid_date: "Anchor investor bidding",
  bid_open_date: "Bid opens",
  bid_close_date: "Bid closes",
};

export const CATEGORY_NAMES: Record<string, string> = {
  financial: "Financial",
  operational: "Operational",
  legal: "Legal",
  regulatory: "Regulatory",
  customer_concentration: "Customer concentration",
  industry: "Industry",
  uncategorised: "Not categorised",
};

export function metricName(metric: string): string {
  return METRIC_NAMES[metric] ?? metric.replaceAll("_", " ");
}

/** International digit grouping (1,234,567.89), as RHPs print ₹ million figures.
 *  Negatives in brackets, as in the prospectus. Keeps the printed decimals. */
export function formatNumber(value: string, unit: string): string {
  const negative = value.startsWith("-");
  const [whole, fraction] = value.replace("-", "").split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  // Decimals exactly as stored: "1250.00" stays 1,250.00, "1468853" stays whole.
  // Ratios arrive already rounded to 2 places by the backend.
  const decimals = fraction ?? "";
  const text = decimals ? `${grouped}.${decimals}` : grouped;
  const suffix = unit === "%" ? "%" : unit === "x" ? "x" : "";
  return negative ? `(${text}${suffix})` : `${text}${suffix}`;
}

export function unitCaption(unit: string): string {
  if (unit.startsWith("INR ")) return `₹ ${unit.slice(4)}`;
  return unit;
}

/** Order periods: balance-sheet dates and flow periods, newest first. */
export function periodSortKey(period: string): string {
  const fy = period.match(/^FY(\d{4})$/);
  if (fy) return `${fy[1]}-03-31`;
  const part = period.match(/(\d{4}-\d{2}-\d{2})/);
  return part ? part[1] : period;
}

export function sortPeriods(periods: string[]): string[] {
  return [...new Set(periods)].sort((a, b) => periodSortKey(b).localeCompare(periodSortKey(a)));
}

export function periodName(period: string): string {
  const fy = period.match(/^FY(\d{4})$/);
  if (fy) return `FY${fy[1]}`;
  const part = period.match(/^(\d+)M ended (\d{4})-(\d{2})-(\d{2})$/);
  if (part) return `${part[1]}M to ${monthYear(part[2], part[3])}`;
  const asAt = period.match(/^as at (\d{4})-(\d{2})-(\d{2})$/);
  if (asAt) return `${monthYear(asAt[1], asAt[2])}`;
  return period;
}

function monthYear(year: string, month: string): string {
  const names = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
  ];
  return `${names[Number(month) - 1]} ${year}`;
}

export function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-");
  if (!d) return iso;
  return `${Number(d)} ${monthYear(y, m)}`;
}
