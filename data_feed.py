import yfinance as yf
import pandas as pd
import time
from datetime import datetime, timezone
try:
    from iqoptionapi.stable_api import IQ_Option
except ImportError:
    IQ_Option = None

class DataFeed:
    def __init__(self, symbol="EURUSD=X"):
        self.symbol = symbol
        self.iq_api = None
        self.use_iq = False
        self.is_connected = False

    def connect_iq(self, email, password, account_type="PRACTICE"):
        """
        Connects to IQ Option API.
        account_type: "PRACTICE" or "REAL"
        """
        if not IQ_Option:
            return False, "iqoptionapi library not installed."
        
        try:
            self.iq_api = IQ_Option(email, password)
            
            # Retry logic for connection
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    print(f"Attempting connection {attempt+1}/{max_retries}...")
                    check, reason = self.iq_api.connect()
                    
                    if check:
                        print("Connection Check: Success")
                        
                        # Ensure account type is valid and switch
                        target_account = account_type.upper()
                        print(f"Switching to {target_account} account...")
                        self.iq_api.change_balance(target_account) 
                        
                        # Verify balance type (optional, just logging)
                        current_balance = self.iq_api.get_balance()
                        print(f"Connected. Balance: {current_balance}")
                        
                        self.is_connected = True
                        self.use_iq = True
                        return True, f"Connected to {target_account} account."
                    else:
                        print(f"Connection Check: Failed ({reason})")
                        if attempt < max_retries - 1:
                            time.sleep(2) # Wait before retry
                            continue
                        return False, f"Connection failed: {reason}"
                except Exception as e:
                    print(f"Connection Exception: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                    return False, f"Connection Error: {str(e)}"
            
            return False, "Connection failed after retries."
            
        except Exception as e:
            return False, str(e)

    def fetch_data(self, symbol=None, period="5d", interval="1m"):
        """
        Fetches data. If connected to IQ Option, fetches from there.
        Otherwise falls back to yfinance.
        """
        target_symbol = symbol if symbol else self.symbol
        
        if self.use_iq and self.is_connected:
            return self._fetch_iq_data(target_symbol, interval)
        else:
            return self._fetch_yf_data(target_symbol, period, interval)

    def _fetch_iq_data(self, symbol, interval):
        """
        Fetches candles from IQ Option.
        """
        # Map symbol to IQ Option format (remove =X)
        iq_symbol = symbol.replace("=X", "").replace("/", "")
        # IQ Option usually uses "EURUSD", "GBPUSD" etc.
        
        # Interval map (IQ uses seconds)
        size = 60 # 1m
        if interval == "1m": size = 60
        elif interval == "5m": size = 300
        elif interval == "15m": size = 900
        
        try:
            # Get candles (1000 candles max usually)
            # API: get_candles(ACTIVES, INTERVAL, COUNT, ENDTIME)
            endtime = int(time.time())
            
            # Retry logic for fetching candles
            max_retries = 3
            candles = []
            
            for attempt in range(max_retries):
                try:
                    candles = self.iq_api.get_candles(iq_symbol, size, 1000, endtime)
                    if candles:
                        break
                    time.sleep(1) # Small pause if empty
                except Exception as e:
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        # Reconnect if we suspect connection dropped
                        if "10060" in str(e) or "socket" in str(e).lower():
                            self.iq_api.connect()
                        continue
                    print(f"IQ Option Data Error (Retried): {e}")
                    return None
            
            if not candles:
                return None
                
            # Convert to DataFrame
            data = []
            for c in candles:
                # IQ returns: 'id', 'from', 'at', 'to', 'open', 'close', 'min', 'max', 'volume'
                # We need: time (index), open, high, low, close, volume
                dt = datetime.fromtimestamp(c['from'], tz=timezone.utc)
                data.append({
                    'time': dt,
                    'open': c['open'],
                    'high': c['max'],
                    'low': c['min'],
                    'close': c['close'],
                    'volume': c['volume']
                })
            
            df = pd.DataFrame(data)
            df.set_index('time', inplace=True)
            return df
            
        except Exception as e:
            print(f"IQ Option Data Error: {e}")
            return None

    def _fetch_yf_data(self, symbol, period, interval):
        """
        Fetches data from yfinance.
        For 1m data, max period is 7d.
        """
        # ... (Existing yfinance logic) ...
        try:
            # yfinance tickers for forex often have =X, e.g. EURUSD=X
            # auto_adjust=False to suppress FutureWarning and keep standard OHLC
            df = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=False)
            if df.empty:
                return None
            
            # Clean up MultiIndex columns if present (yfinance update)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(1)
                
            df = df.reset_index()
            # Ensure columns are standard
            df.columns = [c.lower() for c in df.columns]
            df.rename(columns={'datetime': 'time', 'date': 'time'}, inplace=True)
            
            # Ensure time is localized/aware
            if df['time'].dt.tz is None:
                df['time'] = df['time'].dt.tz_localize('UTC')
            else:
                df['time'] = df['time'].dt.tz_convert('UTC')
                
            df.set_index('time', inplace=True)
            
            return df
        except Exception as e:
            print(f"Error fetching data: {e}")
            return None

    def check_asset_open(self, symbol):
        """
        Checks if asset is open for Binary or Digital.
        Returns: {'binary': bool, 'digital': bool, 'reason': str}
        """
        if not self.use_iq or not self.is_connected:
            return {'binary': False, 'digital': False, 'reason': "Not Connected"}
        
        iq_symbol = symbol.replace("=X", "").replace("/", "")
        iq_symbol_upper = iq_symbol.upper()
        
        debug_log = []
        is_binary_open = False
        is_digital_open = False
        
        try:
            # 1. Check Binary Payouts (actives list)
            try:
                all_profits = self.iq_api.get_all_profit()
                if iq_symbol_upper in all_profits:
                    is_binary_open = True
                    debug_log.append("Found in all_profit")
            except Exception as e:
                debug_log.append(f"all_profit err: {e}")

            # 2. Check Open Times (Turbo/Binary/Digital)
            try:
                open_times = self.iq_api.get_all_open_time()
            except Exception as e:
                debug_log.append(f"get_all_open_time err: {e}")
                open_times = {}

            # Helper to safely check open status
            def check_open(category, sym):
                try:
                    if category in open_times and sym in open_times[category]:
                        val = open_times[category][sym]['open']
                        return val
                except Exception:
                    pass
                return False

            # Check Turbo
            is_turbo = check_open('turbo', iq_symbol_upper)
            
            # Check Binary
            is_std = check_open('binary', iq_symbol_upper)
            
            # Check Digital
            is_dig = check_open('digital', iq_symbol_upper)
            if not is_dig:
                # Try searching keys if exact match fails
                try:
                    if 'digital' in open_times:
                        for k in open_times['digital']:
                            if k.upper() == iq_symbol_upper:
                                is_dig = open_times['digital'][k]['open']
                                break
                except:
                    pass

            debug_log.append(f"T:{is_turbo} B:{is_std} D:{is_dig}")

            # Consolidate
            if is_turbo or is_std:
                is_binary_open = True
            
            if is_dig:
                is_digital_open = True
                
            return {
                'binary': is_binary_open,
                'digital': is_digital_open,
                'reason': "; ".join(debug_log)
            }
            
        except Exception as e:
            return {'binary': False, 'digital': False, 'reason': f"Critical: {e}"}

    def get_account_currency(self):
        if self.use_iq and self.is_connected:
            try:
                return self.iq_api.get_currency()
            except:
                return "USD" # Default fallback
        return "USD"

    def execute_trade(self, symbol, action, amount, duration, trade_mode="AUTO"):
        """
        Executes a trade on IQ Option.
        action: 'CALL' or 'PUT'
        duration: duration in minutes (int)
        trade_mode: 'AUTO', 'BINARY', 'DIGITAL'
        """
        if not self.use_iq or not self.is_connected:
            return False, "Not connected to IQ Option."

        # Ensure connection is alive
        if self.iq_api.check_connect() == False:
            self.iq_api.connect()

        iq_symbol = symbol.replace("=X", "").replace("/", "").upper()
        action_lower = action.lower() # 'call' or 'put'
        
        # Check balance (optional logging)
        try:
            balance = self.iq_api.get_balance()
            if balance < amount:
                return False, f"Insufficient Balance: ${balance:.2f}"
        except:
            pass

        try:
            # Helper for Digital Execution
            def try_digital():
                # Digital usually supports 1, 5, 15 minutes.
                # We map the requested duration to the closest Digital timeframe.
                digital_duration = 1
                if duration >= 3 and duration < 10:
                    digital_duration = 5
                elif duration >= 10:
                    digital_duration = 15
                
                # Check if asset is open for Digital (Instrument ID lookup)
                # Sometimes buy_digital_spot fails if asset name is slightly off or unavailable
                
                # buy_digital_spot args: (active, amount, action, duration)
                check, trade_id = self.iq_api.buy_digital_spot(iq_symbol, amount, action_lower, digital_duration)
                
                if check:
                    return True, f"Digital Trade Executed! ID: {trade_id} (Duration: {digital_duration}m)"
                
                # If failed, trade_id often contains the error message/reason
                return False, f"Digital Failed: {trade_id}"

            # Helper for Binary Execution
            def try_binary():
                # check if pair is open
                check, trade_id = self.iq_api.buy(amount, iq_symbol, action_lower, duration)
                if check:
                    return True, f"Binary Trade Executed! ID: {trade_id}"
                
                return False, f"Binary Failed: {trade_id}"

            # Execution Logic based on Mode
            if trade_mode == "DIGITAL":
                return try_digital()
            
            elif trade_mode == "BINARY":
                return try_binary()
                
            else: # AUTO (Try Binary -> Fallback Digital)
                success, msg = try_binary()
                if success:
                    return True, msg
                
                # If Binary failed, try Digital
                # Log that Binary failed
                binary_msg = msg
                
                success, msg = try_digital()
                if success:
                    return True, msg
                else:
                    return False, f"Execution Failed. {binary_msg} | {msg}"

        except Exception as e:
            return False, f"Execution Error: {e}"

    def get_resampled_data(self, df_1m, timeframe="5m"):
        """
        Resamples 1m data to higher timeframes.
        timeframe: '5m', '15m'
        """
        if df_1m is None or df_1m.empty:
            return None
            
        logic = {
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }
        
        # Resample
        # 5m = '5min', 15m = '15min'
        freq = timeframe.replace('m', 'min')
        df_resampled = df_1m.resample(freq).agg(logic)
        
        # Remove rows with NaN (periods with no data)
        df_resampled.dropna(inplace=True)
        
        return df_resampled
