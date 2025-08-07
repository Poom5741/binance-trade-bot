# Technical Overview

This document summarises the architecture of the enhanced trading bot and
highlights key configuration points.

## Weighted Moving Average (WMA)

The bot calculates short and long period WMAs to determine market trends.  The
period lengths can be configured via Telegram using the `/config` commands or
by editing `user.cfg`.

## Risk Management

Daily loss limits are enforced by the risk manager.  When losses exceed the
configured percentage the bot halts trading and records a risk event.

## AI Adapter

Historical trade performance feeds into an adaptive model that recommends
parameter adjustments.  Learning state is persisted to disk and restored on
start-up.

## Backup and Recovery

`BackupManager` periodically stores trading history and the main SQLite database
in the `backups/` directory.  Corruption is detected on start-up and the latest
backup is restored automatically.

## Deployment

The project can be run via Docker.  The compose file mounts the `backups/`
volume and exposes configuration through environment variables.
