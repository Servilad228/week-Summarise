import argparse
import asyncio
import logging
import sys
import config
import telegram_client
import scheduler

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("summarizer.main")

async def main():
    parser = argparse.ArgumentParser(description="Telegram Weekly Chat Summarizer with LLM (OpenRouter)")
    parser.add_argument("--login", action="store_true", help="Run interactive login to authorize Telegram session")
    parser.add_argument("--run-now", action="store_true", help="Run the summary logic once immediately and exit")
    parser.add_argument("--days", type=int, default=7, help="Number of past days to summarize if running with --run-now (default: 7)")
    
    args = parser.parse_args()

    # 1. Login Mode
    if args.login:
        config.validate_config(is_login_only=True)
        try:
            await telegram_client.interactive_login()
            logger.info("Login completed. You can now start the script in scheduler mode.")
        except Exception as e:
            logger.error(f"Login failed: {e}", exc_info=True)
            sys.exit(1)
        return

    # 2. Standard validation (non-login modes require full config)
    config.validate_config(is_login_only=False)

    logger.info("Initializing Telegram Client...")
    try:
        client = await telegram_client.get_telegram_client()
    except Exception as e:
        logger.error(f"Failed to start Telegram client: {e}")
        logger.error("Make sure you have authenticated the session by running the script with --login first.")
        sys.exit(1)

    try:
        # 3. Manual immediate execution mode
        if args.run_now:
            logger.info(f"Executing immediate summary for the past {args.days} days...")
            await scheduler.run_now(client, days_history=args.days)
            logger.info("Immediate execution completed successfully.")
            return

        # 4. Scheduler mode
        await scheduler.start_scheduler_loop(client)

    except asyncio.CancelledError:
        logger.info("Scheduler task cancelled.")
    except KeyboardInterrupt:
        logger.info("Scheduler interrupted by user.")
    except Exception as e:
        logger.error(f"Fatal error in main process: {e}", exc_info=True)
    finally:
        logger.info("Disconnecting Telegram client...")
        await client.disconnect()
        logger.info("Shutdown complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown complete.")
        sys.exit(0)
