import datetime
import json
import os
import logging
import asyncio
import pytz
import config
import telegram_client
import summary_generator

logger = logging.getLogger("summarizer.scheduler")

def load_state() -> dict:
    """
    Loads scheduler state from config.STATE_FILE_PATH.
    """
    if os.path.exists(config.STATE_FILE_PATH):
        try:
            with open(config.STATE_FILE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading state file {config.STATE_FILE_PATH}: {e}")
    return {"last_run": None}

def save_state(last_run: datetime.datetime):
    """
    Saves scheduler state with the last run timestamp in UTC.
    """
    # Ensure timezone is UTC
    if last_run.tzinfo is None:
        last_run = last_run.replace(tzinfo=datetime.timezone.utc)
    else:
        last_run = last_run.astimezone(datetime.timezone.utc)
        
    state = {"last_run": last_run.isoformat()}
    try:
        # Ensure directory exists just in case
        config.ensure_directories()
        with open(config.STATE_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        logger.debug(f"Saved state: {state}")
    except Exception as e:
        logger.error(f"Error writing state file {config.STATE_FILE_PATH}: {e}")

def get_last_run_time(state: dict) -> datetime.datetime:
    """
    Extracts the last run datetime from state, ensuring it is timezone-aware (UTC).
    """
    lr = state.get("last_run")
    if lr:
        try:
            dt = datetime.datetime.fromisoformat(lr)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt.astimezone(datetime.timezone.utc)
        except Exception as e:
            logger.error(f"Failed to parse last_run date '{lr}': {e}")
    return None

def get_most_recent_scheduled_time(now_tz: datetime.datetime, target_weekday_str: str, hour: int, minute: int) -> datetime.datetime:
    """
    Calculates the most recent scheduled datetime (<= now_tz) based on the target weekday, hour, and minute.
    All logic executes within the configured timezone.
    """
    weekday_map = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6
    }
    target_weekday = weekday_map[target_weekday_str]
    
    # Start with today's date in the target timezone, set to scheduled hour/minute
    scheduled = now_tz.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    # Subtract days to match target weekday
    days_diff = scheduled.weekday() - target_weekday
    scheduled = scheduled - datetime.timedelta(days=days_diff)
    
    # If the calculated scheduled time is in the future, the most recent one was 7 days ago
    if scheduled > now_tz:
        scheduled = scheduled - datetime.timedelta(days=7)
        
    return scheduled

async def run_now(client, days_history: int = 7):
    """
    Triggers an immediate summary run for the specified number of past days.
    """
    logger.info(f"Triggering immediate manual run (fetching past {days_history} days)...")
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    start_date = now_utc - datetime.timedelta(days=days_history)
    
    # Fetch, summarize, send
    history_text = await telegram_client.fetch_chat_history(client, start_date)
    summary = await summary_generator.generate_summary(history_text)
    await telegram_client.send_summary(client, summary)
    
    # Update last run state
    save_state(now_utc)
    logger.info("Manual run completed successfully and state updated.")

async def start_scheduler_loop(client):
    """
    Main loop that checks the schedule every 60 seconds.
    """
    logger.info(f"Starting scheduler loop in mode: '{config.RUN_MODE}'...")
    
    # Initialize state if not present
    state = load_state()
    last_run = get_last_run_time(state)
    
    if last_run is None:
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        if config.RUN_MODE == "interval":
            logger.info("First boot in interval mode. Scheduling first run for immediately.")
            # We don't trigger now, we let the loop detect it or run it now.
            # Running immediately on empty state is good.
        else:
            # Scheduled mode: initialize state to now so we don't trigger immediately
            logger.info("First boot in scheduled mode. Initializing state to avoid immediate trigger.")
            save_state(now_utc)
            last_run = now_utc
            
            # Print next run info
            now_tz = datetime.datetime.now(config.TIMEZONE)
            scheduled_tz = get_most_recent_scheduled_time(
                now_tz, 
                config.SCHEDULE_WEEKDAY, 
                config.SCHEDULE_HOUR, 
                config.SCHEDULE_MINUTE
            )
            next_run_tz = scheduled_tz + datetime.timedelta(days=7)
            logger.info(f"Next run is scheduled for: {next_run_tz.strftime('%Y-%m-%d %H:%M')} ({config.TIMEZONE_STR})")

    while True:
        try:
            state = load_state()
            last_run = get_last_run_time(state)
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            
            should_run = False
            start_date = None
            
            if config.RUN_MODE == "interval":
                if last_run is None:
                    should_run = True
                    start_date = now_utc - datetime.timedelta(days=config.INTERVAL_DAYS)
                else:
                    next_run = last_run + datetime.timedelta(days=config.INTERVAL_DAYS)
                    if now_utc >= next_run:
                        should_run = True
                        start_date = now_utc - datetime.timedelta(days=config.INTERVAL_DAYS)
                        
            elif config.RUN_MODE == "scheduled":
                now_tz = datetime.datetime.now(config.TIMEZONE)
                scheduled_tz = get_most_recent_scheduled_time(
                    now_tz, 
                    config.SCHEDULE_WEEKDAY, 
                    config.SCHEDULE_HOUR, 
                    config.SCHEDULE_MINUTE
                )
                scheduled_utc = scheduled_tz.astimezone(datetime.timezone.utc)
                
                if last_run is None:
                    # Fallback (should be handled on startup, but just in case)
                    should_run = True
                    start_date = scheduled_utc - datetime.timedelta(days=7)
                elif last_run < scheduled_utc:
                    should_run = True
                    start_date = scheduled_utc - datetime.timedelta(days=7)
                    logger.info(
                        f"Scheduled event detected. "
                        f"Last run ({last_run.strftime('%Y-%m-%d %H:%M:%S UTC')}) is before "
                        f"scheduled slot ({scheduled_utc.strftime('%Y-%m-%d %H:%M:%S UTC')})."
                    )

            if should_run:
                logger.info("Executing summary job...")
                history_text = await telegram_client.fetch_chat_history(client, start_date)
                summary = await summary_generator.generate_summary(history_text)
                await telegram_client.send_summary(client, summary)
                
                # Save execution timestamp
                save_state(now_utc)
                logger.info("Job executed successfully. Next schedule check in progress.")
                
        except Exception as e:
            logger.error(f"Error in scheduler check loop: {e}", exc_info=True)
            
        # Wait 60 seconds before next check
        await asyncio.sleep(60)
