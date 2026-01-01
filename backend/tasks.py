import os
import time
import json
import redis
from celery_app import celery_app, REDIS_URL
from bot_engine.trading_bot import IQBot

# Redis Connection (Separate from Celery's internal one)
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

@celery_app.task(bind=True, name="run_trading_bot")
def run_trading_bot(self, email, password, mode="PRACTICE", config=None, push_token=None):
    """
    Long-running Celery task that manages the IQBot instance.
    """
    bot = IQBot()
    task_id = self.request.id
    
    # Keys
    prefix = f"bot:{email}"
    key_status = f"{prefix}:status"
    key_logs = f"{prefix}:logs"
    key_stop = f"{prefix}:stop"
    key_config = f"{prefix}:config"
    key_active = f"{prefix}:active"
    
    # Mark as active (with task ID for debugging)
    redis_client.set(key_active, task_id)
    
    # Clean up previous stop signals
    redis_client.delete(key_stop)
    
    print(f"[Task-{task_id}] Starting bot for {email}")
    
    # Connect
    success, message = bot.connect(email, password, mode)
    
    if not success:
        print(f"[Task-{task_id}] Connection failed: {message}")
        redis_client.rpush(key_logs, f"Connection failed: {message}")
        redis_client.delete(key_active)
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
            if redis_client.exists(key_stop):
                print(f"[Task-{task_id}] Stop signal received.")
                bot.stop()
                break
                
            # 2. Check CONFIG updates
            update_data = redis_client.get(key_config)
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
                    redis_client.delete(key_config) # Consume update
                except Exception as e:
                    print(f"Config update error: {e}")
            
            # 3. Sync State to Redis
            
            # Logs
            new_logs = bot.get_logs()
            if new_logs:
                # Clear and push
                redis_client.delete(key_logs)
                redis_client.rpush(key_logs, *new_logs)
            
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
            redis_client.set(key_status, json.dumps(status_data))
            
            # 4. Health Check
            if not bot.connected:
                print(f"[Task-{task_id}] Bot disconnected.")
                break
                
            time.sleep(1) # Sync Interval
            
    except Exception as e:
        print(f"[Task-{task_id}] Error: {e}")
        bot.add_log(f"Critical Error: {e}")
        
    finally:
        # Cleanup
        bot.disconnect()
        redis_client.delete(key_active)
        # Set status to stopped
        status_data = {
            "connected": False,
            "running": False,
            "balance": bot.balance,
            "currency": bot.currency,
            "stats": {"profit": bot.total_profit, "wins": bot.wins, "losses": bot.losses},
            "last_update": time.time()
        }
        redis_client.set(key_status, json.dumps(status_data))
        print(f"[Task-{task_id}] Task finished.")
