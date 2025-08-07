# Telegram Interface Guide

This guide provides an overview of the Telegram commands exposed by the
trading bot.  The bot requires that users are authorised before commands will
be processed.

## Command Reference

- `/status` – show current trading status
- `/stop` – pause automatic trading
- `/resume` – resume trading after a stop
- `/shutdown` – safely terminate the bot
- `/stats` – display daily statistics
- `/weekly` – show weekly performance
- `/total` – show overall performance
- `/portfolio` – list current holdings
- `/set_backup <seconds>` – update automatic backup interval

## Setup

1. Create a Telegram bot via [@BotFather](https://t.me/BotFather).
2. Place the bot token in the `TELEGRAM_TOKEN` environment variable.
3. Run the bot and issue `/start` to register.

## Troubleshooting

- Ensure the bot is reachable from the internet.
- Check logs for authentication errors when commands are ignored.
- If commands fail, verify that required dependencies are installed.
