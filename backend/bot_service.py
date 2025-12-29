from iqoptionapi.stable_api import IQ_Option
import time
import threading
import random

import traceback

class IQBot:
    def __init__(self):
        self.api = None
        self.email = None
        self.password = None
        self.connected = False
        self.is_running = False
        self.balance = 0
        self.currency = ""
        self.logs = [] # Store logs for frontend
        
        # Trade Config
        self.trade_amount = 1
        self.trade_duration = 1 # minutes
        self.stop_loss = 0
        self.take_profit = 0
        self.max_consecutive_losses = 0
        
        # Session Stats
        self.initial_balance = 0
        self.total_profit = 0
        self.wins = 0
        self.losses = 0
        self.trades_taken = 0
        self.trade_in_progress = False
        self.current_consecutive_losses = 0

    def set_config(self, amount, duration, stop_loss, take_profit, max_consecutive_losses):
        self.trade_amount = amount
        self.trade_duration = duration
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.max_consecutive_losses = max_consecutive_losses

    def reset_stats(self):
        self.total_profit = 0
        self.wins = 0
        self.losses = 0
        self.trades_taken = 0
        self.initial_balance = self.balance

    def add_log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        print(log_entry)
        self.logs.append(log_entry)
        # Keep only last 100 logs to avoid memory issues
        if len(self.logs) > 100:
            self.logs.pop(0)

    def get_logs(self):
        return self.logs

    def clear_logs(self):
        self.logs = []

    def connect(self, email, password, mode="PRACTICE"):
        self.email = email
        self.password = password
        self.api = IQ_Option(email, password)
        
        # Attempt connection
        check, reason = self.api.connect()
        
        if check:
            self.connected = True
            self.is_running = True
            
            # Change account mode
            self.api.change_balance(mode)
            
            self.update_balance()
            self.reset_stats()
            return True, f"Connected successfully ({mode})"
        else:
            self.connected = False
            self.is_running = False
            if reason == "[{'code': 'invalid_credentials', 'message': 'You entered the wrong credentials. Please check that the login and password is correct.'}]":
                 return False, "Invalid Credentials"
            
            return False, f"Connection failed: {reason}"

    def update_balance(self):
        if self.connected:
            self.balance = self.api.get_balance()
            self.currency = self.api.get_currency()

    def start_trading(self):
        self.is_running = True
        threading.Thread(target=self._trading_loop).start()

    def _trading_loop(self):
        while self.is_running and self.connected:
            try:
                # 1. Skip Open Check for now to avoid 'underlying' error
                # We will just try to trade and let the API reject if closed
                
                # For now, let's just pick a few popular pairs to scan
                pairs_to_scan = ["EURUSD-OTC", "GBPUSD-OTC", "AUDCAD-OTC", "USDCHF-OTC", "NZDUSD-OTC", "USDJPY-OTC"]
                # Remove restricted pairs if any were accidentally added or just filter strictly
                # User requested: "usdjyo-otc, nzdusd-otc do not trade them"
                # So we keep the list safe:
                pairs_to_scan = ["EURUSD-OTC", "GBPUSD-OTC", "AUDCAD-OTC", "USDCHF-OTC"]
                
                # Shuffle pairs to ensure we don't always pick the first one (since random strategy always fires)
                random.shuffle(pairs_to_scan)
                
                for pair in pairs_to_scan:
                    if not self.is_running: break
                    
                    # Double check if trade started during loop
                    if self.trade_in_progress: break

                    try:
                        if self._process_pair(pair):
                            # Trade placed, break loop to wait for it to finish
                            break
                    except Exception as e:
                        print(f"Error processing {pair}: {e}")
                        # traceback.print_exc()
                        
                time.sleep(1) # Wait a bit before next scan cycle
            except Exception as e:
                print(f"Error in trading loop: {e}")
                traceback.print_exc()
                time.sleep(5)

    def _process_pair(self, pair):
        # 3. Random Strategy
        # Randomly choose CALL or PUT
        direction = random.choice(["call", "put"])
            
        if direction:
            # 4. Place Trade
            check, id = self.api.buy(self.trade_amount, pair, direction, self.trade_duration)
            if check:
                self.trade_in_progress = True
                self.add_log(f"Trade placed: {pair} {direction} ${self.trade_amount} ({self.trade_duration}m)")
                
                # Check result in a separate thread to not block scanning
                threading.Thread(target=self._check_trade_result, args=(id,)).start()
                
                self.update_balance()
            else:
                self.add_log(f"Trade failed: {pair} {direction}")

    def _check_trade_result(self, order_id):
        try:
            # Wait for duration + buffer
            # We add a bit more buffer to ensure IQ Option has processed it
            time.sleep(self.trade_duration * 60 + 5)
            
            result = None
            
            # Try check_win_v4 first
            try:
                result = self.api.check_win_v4(order_id)
            except:
                pass

            # Fallback to check_win_v3 if v4 fails or returns nothing
            if result is None:
                 try:
                     result = self.api.check_win_v3(order_id)
                 except:
                     pass

            if result is not None:
                profit = float(result)
                if profit > 0:
                    self.wins += 1
                    self.current_consecutive_losses = 0
                    self.add_log(f"WIN: +${profit:.2f}")
                elif profit < 0:
                    self.losses += 1
                    self.current_consecutive_losses += 1
                    self.add_log(f"LOSS: ${profit:.2f}")
                else:
                    self.add_log(f"TIE: $0.00")
                    
                self.total_profit += profit
                self.trades_taken += 1
                self.update_balance()
                
                # Check limits immediately after result
                if self.stop_loss > 0 and self.total_profit <= -self.stop_loss:
                     self.add_log(f"Stop Loss reached (-${self.stop_loss}). Stopping bot.")
                     self.stop()
                elif self.take_profit > 0 and self.total_profit >= self.take_profit:
                     self.add_log(f"Take Profit reached (+${self.take_profit}). Stopping bot.")
                     self.stop()

            else:
                self.add_log(f"Warning: Could not fetch result for trade {order_id}")
                
        except Exception as e:
            print(f"Error checking trade result: {e}")
            self.add_log(f"Error checking trade result: {e}")

        finally:
            self.trade_in_progress = False

    def stop(self):
        self.is_running = False
        if self.api:
            # self.api.close() # Close connection might be too aggressive if we just want to stop trading
            pass
        return True, "Bot stopped"

    def get_status(self):
        win_rate = 0
        if self.trades_taken > 0:
            win_rate = (self.wins / self.trades_taken) * 100
            
        return {
            "connected": self.connected,
            "running": self.is_running,
            "balance": self.balance,
            "currency": self.currency,
            "stats": {
                "profit": round(self.total_profit, 2),
                "wins": self.wins,
                "losses": self.losses,
                "win_rate": round(win_rate, 1)
            }
        }

# Global instance
bot_instance = IQBot()
