import time
import json
import redis
from bot_engine.trading_bot import IQBot

class BotSessionManager:
    def __init__(self, redis_url, task_id=None):
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
        self.task_id = task_id or "Unknown"

    def run_session(self, email, password, mode="PRACTICE", config=None, push_token=None):
        """
        Manages the lifecycle of a single bot session:
        - Connects to IQ Option
        - Applies configuration
        - Starts the internal trading loop
        - Syncs state to Redis
        - Listens for Stop/Update signals from Redis
        """
        bot = IQBot()
        
        # Keys
        prefix = f"bot:{email}"
        key_status = f"{prefix}:status"
        key_logs = f"{prefix}:logs"
        key_stop = f"{prefix}:stop"
        key_config = f"{prefix}:config"
        key_active = f"{prefix}:active"
        
        # Mark as active
        self.redis_client.set(key_active, self.task_id)
        
        # Clean up previous stop signals
        self.redis_client.delete(key_stop)
        
        print(f"[Session-{self.task_id}] Starting bot for {email}")
        
        # Connect
        success, message = bot.connect(email, password, mode)
        
        if not success:
            print(f"[Session-{self.task_id}] Connection failed: {message}")
            self.redis_client.rpush(key_logs, f"Connection failed: {message}")
            self.redis_client.delete(key_active)
            return {"status": "failed", "message": message}
        
        # Apply initial config
        if config:
            bot.set_config(
                config.get('amount', 1),
                config.get('duration', 1),
                config.get('stop_loss', 0),
                config.get('take_profit', 0),
                config.get('max_consecutive_losses', 0),
                config.get('max_trades', 0),
                config.get('auto_trading', True),
                config.get('strategy', 'Momentum')
            )
            
        if push_token:
            bot.set_push_token(push_token)
            
        # Start Trading Loop (Threaded inside IQBot)
        bot.start_trading()
        
        try:
            while True:
                # 1. Check STOP signal
                if self.redis_client.exists(key_stop):
                    print(f"[Session-{self.task_id}] Stop signal received.")
                    bot.stop()
                    break
                    
                # 2. Check CONFIG updates
                update_data = self.redis_client.get(key_config)
                if update_data:
                    try:
                        new_config = json.loads(update_data)
                        bot.set_config(
                            new_config.get('amount', bot.trade_amount),
                            new_config.get('duration', bot.trade_duration),
                            new_config.get('stop_loss', bot.stop_loss),
                            new_config.get('take_profit', bot.take_profit),
                            new_config.get('max_consecutive_losses', bot.max_consecutive_losses),
                            new_config.get('max_trades', bot.max_trades),
                            new_config.get('auto_trading', bot.auto_trading),
                            new_config.get('strategy', bot.strategy)
                        )
                        bot.add_log(f"Config updated dynamically. Strategy: {bot.strategy}")
                        self.redis_client.delete(key_config) # Consume update
                    except Exception as e:
                        print(f"Config update error: {e}")
                
                # 3. Sync State to Redis
                
                # Logs
                new_logs = bot.get_logs()
                if new_logs:
                    # Clear and push
                    self.redis_client.delete(key_logs)
                    self.redis_client.rpush(key_logs, *new_logs)
                
                # Status
                win_rate = 0
                if bot.trades_taken > 0:
                    win_rate = (bot.wins / bot.trades_taken) * 100
                    
                status_data = {
                    "connected": bot.connected,
                    "running": bot.is_running,
                    "balance": bot.balance,
                    "currency": bot.currency,
                    "email": email,
                    "next_trading_time": bot.next_trading_time,
                    "stats": {
                        "profit": round(bot.total_profit, 2),
                        "wins": bot.wins,
                        "losses": bot.losses,
                        "win_rate": round(win_rate, 1)
                    },
                    "signals": bot.get_signals(),
                    "last_update": time.time()
                }
                self.redis_client.set(key_status, json.dumps(status_data))
                
                # 4. Health Check
                if not bot.connected:
                    print(f"[Session-{self.task_id}] Bot disconnected.")
                    break
                    
                time.sleep(1) # Sync Interval
                
        except Exception as e:
            print(f"[Session-{self.task_id}] Error: {e}")
            bot.add_log(f"Critical Error: {e}")
            
        finally:
            # Cleanup
            bot.disconnect()
            self.redis_client.delete(key_active)
            # Set status to stopped
            status_data = {
                "connected": False,
                "running": False,
                "balance": bot.balance,
                "currency": bot.currency,
                "stats": {"profit": bot.total_profit, "wins": bot.wins, "losses": bot.losses},
                "last_update": time.time()
            }
            self.redis_client.set(key_status, json.dumps(status_data))
            print(f"[Session-{self.task_id}] Session finished.")
