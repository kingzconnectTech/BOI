# IQ Option Price Action Bot (Signal Only)

A strict, discipline-focused trading assistant based on Price Action, Support & Resistance, and Market Structure.

## 🎯 Strict Session Times (WAT - UTC+1)
This bot is configured to operate **ONLY** during:
- **London Session**: 09:00 – 12:00 WAT (08:00 - 11:00 UTC)
- **New York Session**: 14:00 – 17:00 WAT (13:00 - 16:00 UTC)

**Dead Zones (No Signals):**
- 12:01 – 13:59 WAT
- 17:01 – 08:59 WAT

## 💱 Recommended Pair Rotation
The bot automatically suggests pairs based on the active session:

**🟢 London Session**
1. EUR/USD
2. GBP/USD
3. USD/JPY (Backup)

**🟡 New York Session**
1. EUR/USD
2. USD/JPY
3. AUD/USD (Backup)

## 🚨 Early-Warning System
The bot provides 3 levels of alerts before a signal is generated:
1.  **Approaching**: Price is nearing a valid zone.
2.  **Zone Test**: Price touches the zone (Prepare on 1M).
3.  **Signal Imminent**: Rejection likely forming.
4.  **CONFIRMED SIGNAL**: Only when candle closes and all rules pass.

## ✅ Manual Execution Checklist
Included in the dashboard sidebar. You must verify:
-   Inside active session?
-   Zone tested 2-3 times (not broken)?
-   Slow approach (no huge momentum)?
-   Correct Pattern (Pin Bar/Engulfing/Double Rejection)?

## Features
-   **Dynamic S/R Zones**: Automatically detects valid Support & Resistance zones on 15M timeframe.
-   **Price Action Patterns**: Pin Bar, Engulfing, Double Rejection.
-   **Strict Filters**: ADX (Trend), ATR (Volatility), Session (London/NY), Signal Limits.
-   **Visualization**: Live dashboard with Charts, Zones, and Signals.

## Usage
Run the dashboard:
```bash
streamlit run app.py
```

## Disclaimer
This tool is for **educational and decision-support purposes only**. It does not execute trades. Market data is sourced from generic feeds (Yahoo Finance) and may differ slightly from IQ Option's proprietary feed. Always verify price action on your broker's terminal.
