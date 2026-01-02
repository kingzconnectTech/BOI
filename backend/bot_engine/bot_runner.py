from trading_bot import IQBot
import time

def run_bot():
    bot = IQBot()

    # TEST credentials (replace)
    email = "kingzconnect911@gmail.com"
    password = "Prosperous911@"

    ok, msg = bot.connect(email, password, mode="PRACTICE")
    print(msg)

    if not ok:
        return

    bot.set_config(
        amount=1,
        duration=1,
        stop_loss=5,
        take_profit=5,
        max_consecutive_losses=2,
        max_trades=5,
        auto_trading=True,
        strategy="Momentum"
    )

    bot.start_trading()

    # Keep process alive
    while bot.is_running:
        time.sleep(5)

if __name__ == "__main__":
    run_bot()
