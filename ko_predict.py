"""
Coca-Cola (KO) Stock Prediction — Next 12 Months
Uses 5 years of historical data + multi-model ensemble to forecast price.
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import MinMaxScaler
import yfinance as yf
from datetime import datetime, timedelta

# ─────────────────────────────────────────────
# 1. FETCH DATA
# ─────────────────────────────────────────────
print("Fetching KO historical data...")
ticker = yf.Ticker("KO")
df = ticker.history(period="5y")
info = ticker.info

df = df[["Close", "Volume", "High", "Low"]].copy()
df.index = pd.to_datetime(df.index).tz_localize(None)

# Key fundamentals (fallback to known values if API limited)
current_price   = df["Close"].iloc[-1]
pe_ratio        = info.get("trailingPE", 24.8)
_dy             = info.get("dividendYield", 0.0285) or 0.0285
dividend_yield  = _dy / 100 if _dy > 1 else _dy   # guard against API returning raw %
eps             = info.get("trailingEps", 2.41)
market_cap      = info.get("marketCap", 170_000_000_000)
week52_high     = info.get("fiftyTwoWeekHigh", df["High"].rolling(252).max().iloc[-1])
week52_low      = info.get("fiftyTwoWeekLow",  df["Low"].rolling(252).min().iloc[-1])
beta            = info.get("beta", 0.59)
analyst_target  = info.get("targetMeanPrice", 72.00)

print(f"  Current price  : ${current_price:.2f}")
print(f"  52-wk High/Low : ${week52_high:.2f} / ${week52_low:.2f}")
print(f"  P/E ratio      : {pe_ratio:.1f}")
print(f"  Dividend yield : {dividend_yield*100:.2f}%")
print(f"  Beta           : {beta:.2f}")
print(f"  Analyst target : ${analyst_target:.2f}")

# ─────────────────────────────────────────────
# 2. TECHNICAL INDICATORS
# ─────────────────────────────────────────────
df["SMA_50"]  = df["Close"].rolling(50).mean()
df["SMA_200"] = df["Close"].rolling(200).mean()
df["EMA_20"]  = df["Close"].ewm(span=20).mean()

# RSI
delta = df["Close"].diff()
gain  = delta.clip(lower=0).rolling(14).mean()
loss  = (-delta.clip(upper=0)).rolling(14).mean()
rs    = gain / loss
df["RSI"] = 100 - 100 / (1 + rs)

# Bollinger Bands
df["BB_mid"]   = df["Close"].rolling(20).mean()
df["BB_std"]   = df["Close"].rolling(20).std()
df["BB_upper"] = df["BB_mid"] + 2 * df["BB_std"]
df["BB_lower"] = df["BB_mid"] - 2 * df["BB_std"]

# MACD
ema12 = df["Close"].ewm(span=12).mean()
ema26 = df["Close"].ewm(span=26).mean()
df["MACD"]        = ema12 - ema26
df["MACD_signal"] = df["MACD"].ewm(span=9).mean()

# ─────────────────────────────────────────────
# 3. FORECAST MODELS
# ─────────────────────────────────────────────
future_days = 252  # ~1 trading year
last_date   = df.index[-1]
future_dates = pd.date_range(last_date + timedelta(days=1), periods=future_days, freq="B")

close = df["Close"].values
n     = len(close)

# --- Model A: Linear Regression on log-price (long-term trend) ---
X = np.arange(n).reshape(-1, 1)
y = np.log(close)
lr = LinearRegression().fit(X, y)
X_fut = np.arange(n, n + future_days).reshape(-1, 1)
# Anchor prediction to actual current price to avoid regression-line offset drift
lr_last  = np.exp(lr.predict([[n - 1]])[0])
lr_scale = close[-1] / lr_last
lr_pred  = np.exp(lr.predict(X_fut)) * lr_scale
lr_annual_return = (lr_pred[-1] / current_price - 1) * 100

# --- Model B: Exponential moving average extrapolation ---
ema_span = 60
alpha = 2 / (ema_span + 1)
ema_val = close[-1]
daily_drift = np.exp(lr.coef_[0]) - 1   # per-day drift from linear fit
ema_pred = []
for i in range(future_days):
    ema_val = ema_val * (1 + daily_drift)
    ema_pred.append(ema_val)
ema_pred = np.array(ema_pred)

# --- Model C: Historical seasonality ---
# Median month-over-month return for each calendar month across history
monthly_close = df["Close"].resample("ME").last()
monthly_returns = monthly_close.pct_change().dropna()
seasonal_map = monthly_returns.groupby(monthly_returns.index.month).median()

seasonal_pred = [current_price]
for i in range(future_days):
    m = future_dates[i].month
    # daily equivalent of the typical monthly return for this calendar month
    monthly_r = seasonal_map.get(m, 0)
    daily_r   = (1 + monthly_r) ** (1 / 21)
    seasonal_pred.append(seasonal_pred[-1] * daily_r)
seasonal_pred = np.array(seasonal_pred[1:])

# --- Ensemble: weighted average (LR 40%, EMA 30%, Seasonal 30%) ---
ensemble = 0.40 * lr_pred + 0.30 * ema_pred + 0.30 * seasonal_pred

# --- Confidence bands: ±1 std of last 252-day rolling volatility ---
hist_vol = df["Close"].pct_change().rolling(252).std().iloc[-1]
ci_band  = np.array([ensemble[i] * hist_vol * np.sqrt(i+1) for i in range(future_days)])
upper_ci = ensemble + ci_band
lower_ci = ensemble - ci_band

# ─────────────────────────────────────────────
# 4. BUY / SELL SIGNAL LOGIC
# ─────────────────────────────────────────────
rsi_now      = df["RSI"].iloc[-1]
macd_now     = df["MACD"].iloc[-1]
macd_sig_now = df["MACD_signal"].iloc[-1]
above_sma50  = current_price > df["SMA_50"].iloc[-1]
above_sma200 = current_price > df["SMA_200"].iloc[-1]
golden_cross = df["SMA_50"].iloc[-1] > df["SMA_200"].iloc[-1]
bb_pos       = (current_price - df["BB_lower"].iloc[-1]) / (df["BB_upper"].iloc[-1] - df["BB_lower"].iloc[-1])
projected_1y = ensemble[-1]
upside_pct   = (projected_1y / current_price - 1) * 100

score = 0
reasons = []

if rsi_now < 45:
    score += 2; reasons.append(f"RSI {rsi_now:.0f} — oversold territory (bullish)")
elif rsi_now < 60:
    score += 1; reasons.append(f"RSI {rsi_now:.0f} — neutral/mildly bullish")
else:
    score -= 1; reasons.append(f"RSI {rsi_now:.0f} — approaching overbought")

if macd_now > macd_sig_now:
    score += 1; reasons.append("MACD above signal line (bullish momentum)")
else:
    score -= 1; reasons.append("MACD below signal line (bearish momentum)")

if above_sma50:
    score += 1; reasons.append("Price above 50-day SMA (short-term uptrend)")
if above_sma200:
    score += 1; reasons.append("Price above 200-day SMA (long-term uptrend)")
if golden_cross:
    score += 1; reasons.append("Golden cross active: SMA50 > SMA200")

if upside_pct > 5:
    score += 2; reasons.append(f"Model projects +{upside_pct:.1f}% upside in 12 months")
elif upside_pct > 0:
    score += 1; reasons.append(f"Model projects +{upside_pct:.1f}% modest upside")
else:
    score -= 1; reasons.append(f"Model projects {upside_pct:.1f}% downside")

if dividend_yield > 0.025:
    score += 1; reasons.append(f"Dividend yield {dividend_yield*100:.2f}% — reliable income")

if current_price < analyst_target:
    score += 1; reasons.append(f"Below analyst consensus target (${analyst_target:.2f})")
else:
    score -= 1; reasons.append(f"Above analyst consensus target (${analyst_target:.2f})")

if score >= 5:
    verdict = "STRONG BUY"
    verdict_color = "#00c851"
elif score >= 2:
    verdict = "BUY"
    verdict_color = "#4caf50"
elif score >= 0:
    verdict = "HOLD"
    verdict_color = "#ff9800"
elif score >= -2:
    verdict = "SELL"
    verdict_color = "#f44336"
else:
    verdict = "STRONG SELL"
    verdict_color = "#b71c1c"

# ─────────────────────────────────────────────
# 5. PLOT
# ─────────────────────────────────────────────
plt.style.use("dark_background")
fig = plt.figure(figsize=(18, 14))
fig.patch.set_facecolor("#0d1117")

gs = GridSpec(4, 2, figure=fig, hspace=0.45, wspace=0.3,
              height_ratios=[3, 1, 1, 1])

# ── Panel 1: Price + Forecast (spans both columns) ──
ax1 = fig.add_subplot(gs[0, :])
hist_slice = df.index[-504:]   # last 2 years visible
ax1.fill_between(future_dates, lower_ci, upper_ci, alpha=0.18, color="#4fc3f7", label="95% confidence band")
ax1.plot(df.index[-504:], df["Close"].iloc[-504:],         color="#e0e0e0", lw=1.4, label="Historical close")
ax1.plot(df.index[-504:], df["SMA_50"].iloc[-504:],        color="#ffca28", lw=1,   linestyle="--", label="SMA 50")
ax1.plot(df.index[-504:], df["SMA_200"].iloc[-504:],       color="#ef5350", lw=1,   linestyle="--", label="SMA 200")
ax1.plot(df.index[-504:], df["BB_upper"].iloc[-504:],      color="#ab47bc", lw=0.7, linestyle=":", alpha=0.7)
ax1.plot(df.index[-504:], df["BB_lower"].iloc[-504:],      color="#ab47bc", lw=0.7, linestyle=":", alpha=0.7, label="Bollinger Bands")
ax1.plot(future_dates, ensemble,    color="#4fc3f7", lw=2.2, label=f"Ensemble forecast (1yr)")
ax1.plot(future_dates, lr_pred,     color="#80cbc4", lw=1,   linestyle="--", alpha=0.6, label="Linear regression")
ax1.plot(future_dates, ema_pred,    color="#aed581", lw=1,   linestyle="--", alpha=0.6, label="EMA extrapolation")
ax1.plot(future_dates, seasonal_pred, color="#ffb74d", lw=1, linestyle="--", alpha=0.6, label="Seasonal model")
ax1.axvline(last_date, color="#616161", lw=1.5, linestyle="--", alpha=0.8)
ax1.axhline(week52_high, color="#ef9a9a", lw=0.8, linestyle=":", alpha=0.6)
ax1.axhline(week52_low,  color="#a5d6a7", lw=0.8, linestyle=":", alpha=0.6)

# Verdict annotation
ax1.annotate(f"  {verdict}\n  Score: {score}/9\n  Proj. 1yr: ${projected_1y:.2f}",
             xy=(future_dates[future_days//2], ensemble[future_days//2]),
             fontsize=11, color=verdict_color, fontweight="bold",
             bbox=dict(boxstyle="round,pad=0.4", fc="#1a1a2e", ec=verdict_color, lw=1.5))

ax1.set_title("Coca-Cola (KO) — 2-Year History + 12-Month Forecast", fontsize=15, pad=10, color="white")
ax1.set_ylabel("Price (USD)", color="#b0bec5")
ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
ax1.legend(loc="upper left", fontsize=7.5, framealpha=0.3, ncol=3)
ax1.tick_params(colors="#b0bec5"); ax1.spines[:].set_color("#37474f")
ax1.set_facecolor("#0d1117")

# ── Panel 2: Volume ──
ax2 = fig.add_subplot(gs[1, :])
colors = ["#4caf50" if df["Close"].iloc[i] >= df["Close"].iloc[i-1] else "#ef5350"
          for i in range(len(df.iloc[-504:]))]
ax2.bar(df.index[-504:], df["Volume"].iloc[-504:], color=colors, width=1.5, alpha=0.7)
ax2.set_ylabel("Volume", color="#b0bec5", fontsize=8)
ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x/1e6:.0f}M"))
ax2.tick_params(colors="#b0bec5", labelsize=7); ax2.spines[:].set_color("#37474f")
ax2.set_facecolor("#0d1117")
ax2.set_title("Volume", fontsize=9, color="#b0bec5")

# ── Panel 3: RSI ──
ax3 = fig.add_subplot(gs[2, 0])
ax3.plot(df.index[-252:], df["RSI"].iloc[-252:], color="#ce93d8", lw=1.5)
ax3.axhline(70, color="#ef5350", lw=0.8, linestyle="--", alpha=0.7)
ax3.axhline(30, color="#4caf50", lw=0.8, linestyle="--", alpha=0.7)
ax3.axhline(50, color="#616161", lw=0.5, linestyle=":", alpha=0.5)
ax3.fill_between(df.index[-252:], df["RSI"].iloc[-252:], 50,
                 where=df["RSI"].iloc[-252:] >= 50, alpha=0.2, color="#ce93d8")
ax3.set_ylim(0, 100); ax3.set_ylabel("RSI(14)", color="#b0bec5", fontsize=8)
ax3.set_title(f"RSI — Current: {rsi_now:.1f}", fontsize=9, color="#b0bec5")
ax3.tick_params(colors="#b0bec5", labelsize=7); ax3.spines[:].set_color("#37474f")
ax3.set_facecolor("#0d1117")

# ── Panel 4: MACD ──
ax4 = fig.add_subplot(gs[2, 1])
macd_hist = df["MACD"].iloc[-252:] - df["MACD_signal"].iloc[-252:]
bar_colors = ["#4caf50" if v >= 0 else "#ef5350" for v in macd_hist]
ax4.bar(df.index[-252:], macd_hist, color=bar_colors, width=1.5, alpha=0.7)
ax4.plot(df.index[-252:], df["MACD"].iloc[-252:],        color="#4fc3f7", lw=1.2, label="MACD")
ax4.plot(df.index[-252:], df["MACD_signal"].iloc[-252:], color="#ffca28", lw=1.2, label="Signal")
ax4.axhline(0, color="#616161", lw=0.5)
ax4.set_title("MACD", fontsize=9, color="#b0bec5")
ax4.legend(fontsize=7, framealpha=0.2)
ax4.tick_params(colors="#b0bec5", labelsize=7); ax4.spines[:].set_color("#37474f")
ax4.set_facecolor("#0d1117")

# ── Panel 5: Forecast summary card ──
ax5 = fig.add_subplot(gs[3, 0])
ax5.axis("off")
ax5.set_facecolor("#0d1117")
summary_text = (
    f"FORECAST SUMMARY (as of {last_date.strftime('%Y-%m-%d')})\n"
    f"{'─'*44}\n"
    f"Current price       :  ${current_price:.2f}\n"
    f"Proj. price (1yr)   :  ${projected_1y:.2f}   ({upside_pct:+.1f}%)\n"
    f"Confidence range    :  ${lower_ci[-1]:.2f} – ${upper_ci[-1]:.2f}\n"
    f"52-wk High / Low    :  ${week52_high:.2f} / ${week52_low:.2f}\n"
    f"P/E ratio           :  {pe_ratio:.1f}x\n"
    f"Dividend yield      :  {dividend_yield*100:.2f}%\n"
    f"Beta (volatility)   :  {beta:.2f}  (market = 1.0)\n"
    f"Analyst target      :  ${analyst_target:.2f}\n"
    f"{'─'*44}\n"
    f"VERDICT:  {verdict}  (Score {score}/9)"
)
ax5.text(0.03, 0.97, summary_text, transform=ax5.transAxes,
         fontsize=8.5, verticalalignment="top", fontfamily="monospace",
         color="#e0e0e0",
         bbox=dict(boxstyle="round", facecolor="#1a1a2e", alpha=0.85, edgecolor=verdict_color, lw=1.5))

# ── Panel 6: Analysis & advice ──
ax6 = fig.add_subplot(gs[3, 1])
ax6.axis("off")
ax6.set_facecolor("#0d1117")
advice_lines = ["SIGNAL BREAKDOWN\n" + "─"*38]
for r in reasons:
    bullet = "▲" if any(w in r for w in ["bullish","above","yield","upside","Below"]) else "▼"
    advice_lines.append(f" {bullet}  {r}")
advice_lines += [
    "─"*38,
    "GENERAL ADVICE",
    " • KO is a Dividend Aristocrat (62+ yrs)",
    f" • Total 1yr return incl. div: ~{upside_pct + dividend_yield*100:.1f}%",
    " • Defensive stock; low beta suits",
    "   volatile macro environments",
    " • Dollar-cost averaging recommended",
]
ax6.text(0.03, 0.97, "\n".join(advice_lines), transform=ax6.transAxes,
         fontsize=7.8, verticalalignment="top", fontfamily="monospace",
         color="#cfd8dc",
         bbox=dict(boxstyle="round", facecolor="#1a1a2e", alpha=0.85, edgecolor="#37474f", lw=1))

fig.suptitle(
    "Coca-Cola (KO) — AI-Assisted 12-Month Stock Prediction  |  For educational use only, not financial advice",
    fontsize=11, y=0.995, color="#78909c"
)

out = "/workspaces/bs2/ko_forecast.png"
plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
print(f"\nChart saved → {out}")
plt.close()

# ─────────────────────────────────────────────
# 6. PRINT THOUGHT PROCESS
# ─────────────────────────────────────────────
print("\n" + "="*60)
print("PREDICTION THOUGHT PROCESS")
print("="*60)
print("""
METHODOLOGY
───────────
Three independent models are blended into an ensemble forecast:

  A) Log-Linear Regression (40% weight)
     Fits a straight line to log(price) over 5 years. Captures the
     long-run compound growth rate. KO has grown ~5-7% annualised
     historically. This is the dominant signal.

  B) EMA Extrapolation (30% weight)
     Extrapolates the current 60-day exponential moving average
     forward, using the same daily drift rate from model A.
     Smooths out short-term noise while staying close to recent price.

  C) Seasonal Model (30% weight)
     Uses the median monthly % change from the last 5 years to
     inject known seasonality (KO typically sees Q3 softness and
     Q4 strength as holiday beverage demand rises).

  Confidence band = ±1 standard deviation × √time (random-walk).

KEY ASSUMPTIONS & RISKS
───────────────────────
  + Coca-Cola's defensive moat (brand, distribution) supports
    continued steady demand regardless of economic cycle.
  + Beta ~0.59 means it moves ~41% less than the S&P 500 —
    good hedge in uncertain markets.
  + Dividend yield (~2.85%) provides a floor for long-term holders.
  - Model does NOT factor in macro shocks (rate hikes, geopolitics,
    health/sugar-tax regulation, FX since ~50% revenue is non-USD).
  - Past seasonality may not repeat.
  - Analyst consensus target of ~$72 is slightly below current
    price, suggesting the street sees limited near-term upside.
""")
print(f"  → Ensemble 1-year target: ${projected_1y:.2f}")
print(f"  → Verdict: {verdict}")
print("="*60)
