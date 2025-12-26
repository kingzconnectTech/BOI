import streamlit as st
import time
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    # Fallback if module is missing
    def st_autorefresh(interval, key):
        time.sleep(interval / 1000)
        st.rerun()

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import pytz

import config
from data_feed import DataFeed
from indicators import calculate_indicators
# from strategy import SupportResistanceEngine, SignalGenerator # Old Strategy
from strategy_trend import TrendPullbackStrategy # New Strategy

# Page Config
st.set_page_config(page_title="IQ Option Trend Bot", layout="wide", page_icon="📈")

# Initialize Session State
if 'data_feed' not in st.session_state:
    st.session_state.data_feed = DataFeed()

# Strategy Initialization with Stale Check
if 'strategy' not in st.session_state:
    st.session_state.strategy = TrendPullbackStrategy()
else:
    # Check if the instance matches the current version
    current_version = getattr(TrendPullbackStrategy, 'VERSION', 'UNKNOWN')
    instance_version = getattr(st.session_state.strategy, 'VERSION', 'OLD')
    
    if instance_version != current_version:
        st.session_state.strategy = TrendPullbackStrategy()
        st.toast("Strategy reset to Clean Slate!", icon="🧹")

if 'signals' not in st.session_state:
    st.session_state.signals = []
if 'last_update' not in st.session_state:
    st.session_state.last_update = None

# Sidebar
st.sidebar.title("Configuration")

# IQ Option Connection
with st.sidebar.expander("🔐 IQ Option Login (Optional)"):
    st.caption("Connect for Real-Time Data (Replaces Yahoo Finance)")
    iq_email = st.text_input("Email")
    iq_password = st.text_input("Password", type="password")
    account_type = st.radio("Account Type", ["PRACTICE", "REAL"], horizontal=True)
    
    if st.button("Connect IQ Option"):
        if iq_email and iq_password:
            success, msg = st.session_state.data_feed.connect_iq(iq_email, iq_password, account_type)
            if success:
                st.success(msg)
            else:
                st.error(msg)
        else:
            st.warning("Enter credentials.")

if st.session_state.data_feed.is_connected:
    st.sidebar.success("✅ IQ Option Connected")
else:
    st.sidebar.info("☁️ Using Yahoo Finance (Delayed)")

# Determine Session & Pairs
current_utc = datetime.now(pytz.utc).time()

# OTC Session Check (User Defined Windows)
current_utc = datetime.now(pytz.utc).time()

# Window 1: 00:00 - 03:00 UTC
is_otc_w1 = config.OTC_WINDOW_1_START <= current_utc <= config.OTC_WINDOW_1_END

# Window 2: 18:00 - 21:00 UTC
is_otc_w2 = config.OTC_WINDOW_2_START <= current_utc <= config.OTC_WINDOW_2_END

is_otc = is_otc_w1 or is_otc_w2

# Live Sessions (Legacy/Reference)
is_london = config.SESSION_LONDON_START <= current_utc <= config.SESSION_LONDON_END
is_ny = config.SESSION_NY_START <= current_utc <= config.SESSION_NY_END
is_ny_cont = config.SESSION_NY_CONT_START <= current_utc <= config.SESSION_NY_CONT_END

session_name = "OFF-HOURS"
session_status = "❌ NO TRADE"
recommended_pairs = []

if is_otc:
    if is_otc_w1:
        session_name = "OTC WINDOW 1 (00-03 UTC)"
    else:
        session_name = "OTC WINDOW 2 (18-21 UTC)"
    
    session_status = "✅ PRIME OTC TIME"
    recommended_pairs = config.PAIRS_OTC
elif is_london:
    session_name = "LONDON SESSION"
    session_status = "⚠️ LIVE (CAUTION)"
    recommended_pairs = config.PAIRS_LONDON
elif is_ny:
    session_name = "NEW YORK SESSION"
    session_status = "✅ BEST LIVE MARKET"
    recommended_pairs = config.PAIRS_NY
elif is_ny_cont:
    session_name = "NY CONTINUATION"
    session_status = "⚠️ LIVE (CAUTION)"
    recommended_pairs = config.PAIRS_NY

# Sidebar Status
st.sidebar.markdown(f"### 🛡️ Daily Decision: {session_status}")
st.sidebar.caption(f"Session: {session_name}")

if "NO TRADE" in session_status:
    st.sidebar.error("⛔ Market Chop / Avoid. Wait for next window.")
elif "CAUTION" in session_status:
    st.sidebar.warning("⚠️ Trade with caution. Check Trend & News.")
elif "BEST" in session_status:
    st.sidebar.success("✅ Prime Trading Window.")

# Asset Selection
pair_options = recommended_pairs if recommended_pairs else config.PAIRS_LONDON + config.PAIRS_NY + config.PAIRS_OTC
symbol = st.sidebar.selectbox("Select Asset", pair_options)

st.sidebar.markdown("---")

# Daily Decision Matrix (Manual Checks)
with st.sidebar.expander("✅ Pre-Trade Checklist (MANDATORY)", expanded=True):
    st.markdown("**1. News & Structure**")
    check_news = st.checkbox("No High-Impact News (NFP/CPI/FOMC)?", value=False)
    check_structure = st.checkbox("Clean Trend / No Chop?", value=False)
    
    st.markdown("**2. Personal State**")
    check_state = st.checkbox("Not Emotional / Tired?", value=False)
    
    st.markdown("**3. Daily Limit**")
    check_loss = st.checkbox("Not stopped out (Max 2 losses)?", value=True)

    can_trade = check_news and check_structure and check_state and check_loss
    
    # Store decision in session state for update_data() to access
    st.session_state.can_trade = can_trade
    
    if not can_trade:
        st.sidebar.error("⛔ DO NOT TRADE")
    else:
        st.sidebar.success("✅ GOOD TO TRADE")

# Manual Execution Checklist (Legacy - kept for reference or removed? User updated framework replaces it partially but user said 'STEP 5: Daily Decision Matrix')
# Let's keep the specific trade checklist but minimize it
with st.sidebar.expander("📋 Trade Execution Checklist", expanded=False):
    st.markdown("""
    **1. Session Confirmation**
    - [ ] Inside London/NY?
    - [ ] No Red Folder News?
    
    **2. Zone Validation**
    - [ ] Tested 2-3 times?
    - [ ] No clean break?
    
    **3. Price Arrival**
    - [ ] Slow entry (no huge momentum)?
    - [ ] Wicks forming?
    
    **4. Entry Pattern**
    - [ ] Pin Bar / Engulfing / Dbl Reject?
    - [ ] Wick >= 2x Body?
    
    **5. Execution**
    - [ ] CALL @ Support / PUT @ Resistance
    - [ ] Expiry: 1-3 min
    """)

# Auto-Trading Settings
with st.sidebar.expander("⚡ Auto-Execution", expanded=False):
    enable_auto_trading = st.checkbox("Enable Auto-Trading", value=False, help="Automatically place trades on signal.")
    trade_amount = st.number_input("Trade Amount ($)", min_value=1.0, value=1.0, step=1.0)
    trade_mode = st.selectbox("Execution Type", ["AUTO", "DIGITAL", "BINARY"], index=0, help="AUTO tries Binary then Digital. DIGITAL forces Digital Options (Reliable for Normal Pairs).")
    
    if enable_auto_trading and not st.session_state.data_feed.is_connected:
        st.error("⚠️ Connect IQ Option first!")
    
    if enable_auto_trading and not can_trade:
        st.error("⛔ Daily Decision: DO NOT TRADE. Disable Auto.")

    if st.button("Reset Session Stats"):
        st.session_state.strategy.signals_this_session = 0
        st.session_state.strategy.consecutive_losses = 0
        st.success("Session stats reset!")

    # Asset Check Tool
    st.markdown("---")
    if st.button("🔍 Check Asset Status"):
        if st.session_state.data_feed.is_connected:
            with st.spinner(f"Checking {symbol} on IQ Option..."):
                status = st.session_state.data_feed.check_asset_open(symbol)
                st.write(f"**Asset:** {symbol}")
                st.write(f"**Binary (Turbo):** {'✅ OPEN' if status['binary'] else '❌ CLOSED'}")
                st.write(f"**Digital:** {'✅ OPEN' if status['digital'] else '❌ CLOSED'}")
                st.caption(f"Reason: {status.get('reason', '')}")
                
                if not status['binary'] and not status['digital']:
                    st.error("Asset appears closed on IQ Option. Try another pair or OTC.")
                elif status['digital'] and not status['binary']:
                    st.warning("Only Digital Options available. Use 'DIGITAL' mode.")
        else:
            st.error("Connect to IQ Option first.")

auto_refresh = st.sidebar.checkbox("Auto Refresh (60s)", value=False)
if auto_refresh:
    st_autorefresh(interval=60 * 1000, key="data_refresh")

# Main UI
st.title("🎯 IQ Option Price Action Bot")

# Session Status Display
session_name = "CLOSED 🔴"
if is_london:
    session_name = "LONDON 🟢"
elif is_ny:
    session_name = "NEW YORK 🟡"

st.markdown(f"**Session:** {session_name} | **Asset:** {symbol} | **Mode:** {'Auto-Refresh' if auto_refresh else 'Manual'}")
st.caption(f"Current System Time (UTC): {current_utc.strftime('%H:%M:%S')} | WAT (Your Time): {(datetime.now(pytz.utc) + timedelta(hours=1)).strftime('%H:%M:%S')}")

# Placeholders
metrics_ph = st.empty()
chart_ph = st.empty()
signals_ph = st.empty()

def update_data():
    display_data = None
    
    # Progress Bar
    progress_text = "Scanning market..."
    my_bar = st.progress(0, text=progress_text)
    total_pairs = len(pair_options)
    
    # Sound Alert Logic
    if 'sound_queue' not in st.session_state:
        st.session_state.sound_queue = []

    for i, ticker in enumerate(pair_options):
        # Update progress
        my_bar.progress((i + 1) / total_pairs, text=f"Scanning {ticker}...")
        
        # 1. Fetch Data
        # OPTIMIZATION: Reduce fetch size to avoid hanging. 
        # We only need enough for EMA 50 + some lookback. 1 day is plenty for 1m data.
        df_ticker = st.session_state.data_feed.fetch_data(symbol=ticker, period="1d", interval="1m")
        
        if df_ticker is None or df_ticker.empty:
            continue

        # 2. Calculate Indicators on 1m
        df_ticker = calculate_indicators(df_ticker)

        # 3. Detect Zones
        zones = st.session_state.strategy.detect_zones(df_ticker)
        
        # 4b. Update Outcomes
        st.session_state.strategy.update_outcomes(df_ticker, st.session_state.signals, current_asset=ticker)

        # 4c. Check Early Warnings (Alerts)
        # We only show toasts for high priority alerts to avoid spamming
        alerts = st.session_state.strategy.check_early_warnings(df_ticker)
        if alerts:
            for alert in alerts:
                if alert.get('level') == 'IMMINENT':
                    st.toast(f"[{ticker}] {alert['message']}", icon="⏳")
                elif alert.get('level') == 'TEST' and ticker == symbol:
                    st.toast(f"[{ticker}] {alert['message']}", icon="🔔")

        # 5. Check for Signal
        market_mode = st.session_state.strategy.detect_market_mode(df_ticker, -1)
        signal = st.session_state.strategy.analyze_1m(df_ticker, symbol=ticker)
        
        if signal:
            # Avoid duplicates: Check if we already have this signal for this asset at this time
            existing = [s for s in st.session_state.signals if s['asset'] == ticker and s['time'] == signal['time']]
            
            if not existing:
                st.session_state.signals.append(signal)
                st.toast(f"🚨 SIGNAL: {signal['type']} {signal['asset']}!", icon="🔔")
                
                # Queue sound
                st.session_state.sound_queue.append("notification")
                
                # --- AUTO EXECUTION ---
                if enable_auto_trading:
                    can_trade_status = st.session_state.get('can_trade', False)
                    
                    if not st.session_state.data_feed.is_connected:
                         st.error(f"⚠️ Auto-Trade Skipped ({ticker}): IQ Option NOT Connected!")
                    elif not can_trade_status:
                         st.error(f"⛔ Auto-Trade Skipped ({ticker}): Daily Decision Checks Failed! Check Sidebar.")
                    else:
                        st.info(f"⚡ Executing Auto-Trade: {signal['type']} {ticker} ${trade_amount} ({trade_mode})...")
                        success, msg = st.session_state.data_feed.execute_trade(
                            symbol=signal['asset'],
                            action=signal['type'],
                            amount=trade_amount,
                            duration=config.EXPIRY_MINUTES,
                            trade_mode=trade_mode
                        )
                        
                        # Find the signal we just added (last one)
                        sig_idx = -1
                        # Double check we are updating the right one (though append makes it last)
                        if st.session_state.signals[-1]['asset'] == ticker:
                            if success:
                                st.success(f"✅ Trade Placed: {msg}")
                                st.toast(f"💸 Auto-Trade Executed: {msg}", icon="✅")
                                st.session_state.signals[sig_idx]['status'] = 'EXECUTED'
                                st.session_state.signals[sig_idx]['execution_msg'] = msg
                                st.session_state.sound_queue.append("money") # Cha-ching sound
                            else:
                                st.error(f"❌ Trade Failed: {msg}")
                                st.session_state.signals[sig_idx]['status'] = 'FAILED'
                                st.session_state.signals[sig_idx]['execution_msg'] = msg
        
        # 6. Save data if it's the selected symbol (for visualization)
        if ticker == symbol:
            display_data = (df_ticker, zones, market_mode)

    # Cleanup
    my_bar.empty()
    st.session_state.last_update = datetime.now()
    
    return display_data

def plot_chart(df, zones, signals, symbol):
    # Slice for better visibility (last 100 candles)
    plot_df = df.tail(100)
    
    # Create Subplots: Row 1 = Price, Row 2 = RSI
    fig = make_subplots(
        rows=2, cols=1, 
        shared_xaxes=True, 
        vertical_spacing=0.05, 
        row_heights=[0.7, 0.3],
        subplot_titles=(f"{symbol} - {config.ENTRY_TIMEFRAME}", "RSI (14)")
    )
    
    # --- ROW 1: Price & EMAs ---
    
    # Candlestick
    fig.add_trace(go.Candlestick(
        x=plot_df.index,
        open=plot_df['open'],
        high=plot_df['high'],
        low=plot_df['low'],
        close=plot_df['close'],
        name="Price"
    ), row=1, col=1)
    
    # Add OTC Indicators: EMA 20 & EMA 50
    if 'ema_fast' in plot_df.columns:
        fig.add_trace(go.Scatter(
            x=plot_df.index, 
            y=plot_df['ema_fast'], 
            line=dict(color='cyan', width=2), 
            name=f"EMA {config.EMA_FAST_PERIOD}"
        ), row=1, col=1)
        
    if 'ema_slow' in plot_df.columns:
        fig.add_trace(go.Scatter(
            x=plot_df.index, 
            y=plot_df['ema_slow'], 
            line=dict(color='orange', width=2), 
            name=f"EMA {config.EMA_SLOW_PERIOD}"
        ), row=1, col=1)

    # Draw Zones
    future_time = plot_df.index[-1] + timedelta(minutes=10)
    
    for zone in zones:
        color = "rgba(0, 255, 0, 0.2)" if zone['type'] == 'support' else "rgba(255, 0, 0, 0.2)"
        thickness = 0.0005 # fallback
        y0 = zone['price'] - thickness/2
        y1 = zone['price'] + thickness/2
        
        start_t = plot_df.index[0] 
        
        fig.add_shape(
            type="rect",
            x0=start_t,
            x1=future_time,
            y0=y0,
            y1=y1,
            fillcolor=color,
            line=dict(width=0),
            layer="below",
            row=1, col=1
        )

    # Plot Signals
    for sig in signals:
        if sig.get('asset') != symbol: continue
        if sig['time'] in plot_df.index:
            y_val = sig['price']
            marker = "triangle-up" if sig['type'] == "CALL" else "triangle-down"
            color = "green" if sig['type'] == "CALL" else "red"
            
            fig.add_trace(go.Scatter(
                x=[sig['time']],
                y=[y_val],
                mode='markers',
                marker=dict(symbol=marker, size=15, color=color),
                name=f"Signal {sig['type']}"
            ), row=1, col=1)

    # --- ROW 2: RSI ---
    if 'rsi' in plot_df.columns:
        fig.add_trace(go.Scatter(
            x=plot_df.index,
            y=plot_df['rsi'],
            line=dict(color='purple', width=2),
            name="RSI"
        ), row=2, col=1)
        
        # RSI Lines
        # Standard 30/70
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1, annotation_text="Overbought")
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1, annotation_text="Oversold")
        
        # Strategy Zone (40-60)
        fig.add_hrect(y0=40, y1=60, fillcolor="rgba(100, 100, 255, 0.1)", layer="below", line_width=0, row=2, col=1)
        fig.add_hline(y=50, line_dash="dot", line_color="gray", row=2, col=1)

    fig.update_layout(
        xaxis_rangeslider_visible=False,
        height=700,
        template="plotly_dark",
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    
    return fig

def play_sound(sound_type):
    # Simple HTML5 Audio Player
    # Note: Autoplay policies might block this without user interaction first.
    sound_urls = {
        "notification": "https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3",
        "money": "https://assets.mixkit.co/active_storage/sfx/2000/2000-preview.mp3"
    }
    
    url = sound_urls.get(sound_type, sound_urls["notification"])
    
    # JavaScript to play sound
    js_code = f"""
        <audio autoplay style="display:none;">
            <source src="{url}" type="audio/mpeg">
        </audio>
        <script>
            var audio = new Audio("{url}");
            audio.play().catch(function(error) {{
                console.log("Audio play failed: " + error);
            }});
        </script>
    """
    st.markdown(js_code, unsafe_allow_html=True)

# Run Loop
if st.button("Refresh Now") or auto_refresh:
    data_res = update_data()
    
    # Process Sound Queue
    if 'sound_queue' in st.session_state and st.session_state.sound_queue:
        # Play the last sound added (to avoid spamming multiple sounds at once)
        # or play all? Let's play the most important one.
        # Priority: Money > Notification
        
        sounds = st.session_state.sound_queue
        if "money" in sounds:
            play_sound("money")
        elif "notification" in sounds:
            play_sound("notification")
            
        # Clear queue
        st.session_state.sound_queue = []
    
    if data_res:
        df_1m, zones, market_mode = data_res
        
        # Metrics
        c1, c2, c3, c4 = metrics_ph.columns(4)
        c1.metric("Market Mode", market_mode, delta="Trend" if market_mode == "TREND" else "Range", delta_color="normal")
        c2.metric("Active Zones", len(zones))
        c3.metric("Signals (Session)", len(st.session_state.signals))
        
        # Display Last Price with Status (Forming/Closed)
        last_price = df_1m['close'].iloc[-1]
        last_time = df_1m.index[-1]
        current_time_utc = datetime.now(last_time.tzinfo)
        time_diff = (current_time_utc - last_time).total_seconds()
        
        price_status = "🔴 Forming" if time_diff < 60 else "🟢 Closed"
        c4.metric("Last Price", f"{last_price:.5f}", delta=price_status)
        
        # Chart
        fig = plot_chart(df_1m, zones, st.session_state.signals, symbol)
        chart_ph.plotly_chart(fig, use_container_width=True)
        
        # Signal Table
        if st.session_state.signals:
            signals_ph.dataframe(pd.DataFrame(st.session_state.signals).sort_values('time', ascending=False))
        else:
            signals_ph.info("No signals yet.")
            
    if auto_refresh:
        time.sleep(60)
        st.rerun()

else:
    st.info("Click 'Refresh Now' or enable 'Auto Refresh' to start.")

