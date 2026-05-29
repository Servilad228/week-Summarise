import argparse
import asyncio
import logging
import sys
import config
import telegram_client
import scheduler
import summary_generator

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("summarizer.main")

def is_test_service_message(text: str) -> bool:
    if not text:
        return False
    indicators = [
        "Результат Теста Саммаризатора",
        "Какой стиль саммари использовать на этой неделе",
        "Выбран стиль:",
        "Начинаю генерацию саммари",
        "Время выбора стиля истекло",
        "Стиль выбран:",
        "Тестовый отчет (Саммари)"
    ]
    for ind in indicators:
        if ind in text:
            return True
            
    # Also ignore button reply texts
    button_texts = [
        "1. бро-стиль 😎",
        "2. факты 📊",
        "3. рапорт 🪖"
    ]
    if text.strip().lower() in button_texts:
        return True
    return False

async def run_tests(client) -> bool:
    logger.info("Starting diagnostic tests...")
    
    # Test 1: Telegram Authorization Check
    logger.info("Test 1/4: Checking Telegram authorization...")
    try:
        me = await client.get_me()
        if me:
            logger.info(f" -> SUCCESS: Authorized as {me.first_name} (@{me.username or 'no_username'})")
        else:
            logger.error(" -> FAILED: Telegram client authorized but get_me() returned None")
            return False
    except Exception as e:
        logger.error(f" -> FAILED: Telegram authorization failed: {e}")
        return False
        
    # Test 2: Fetch messages from Saved Messages (filtering out previous test messages)
    logger.info("Test 2/4: Fetching 10-20 text messages from Saved Messages ('me')...")
    messages = []
    try:
        async for message in client.iter_messages('me', limit=200):
            if len(messages) >= 20:
                break
            if message.text and not message.action:
                if not is_test_service_message(message.text):
                    messages.append(message)
        logger.info(f" -> SUCCESS: Fetched {len(messages)} text messages from Saved Messages")
    except Exception as e:
        logger.error(f" -> FAILED: Could not fetch messages from Saved Messages: {e}")
        return False

    # Format the messages
    formatted_lines = []
    messages.reverse()  # Chronological order
    for msg in messages:
        text_clean = msg.text.replace('\n', ' ')
        date_str = msg.date.strftime('%Y-%m-%d %H:%M')
        formatted_lines.append(f"[{date_str}] Избранное: {text_clean}")
        
    if len(formatted_lines) < 5:
        logger.info("В Избранном найдено мало текстовых сообщений (менее 5). Для полноценного теста добавляем демонстрационные сообщения...")
        dummy_data = [
            "[2026-05-29 10:00] Тестовый Автор: Обсуждаем разработку нового бота для саммари.",
            "[2026-05-29 10:05] Разработчик: Отличная идея! Будем использовать Telethon и Docker.",
            "[2026-05-29 10:10] Тестовый Автор: Да, и обязательно добавим режим диагностики через --test.",
            "[2026-05-29 10:15] Разработчик: Готово. Тест берет сообщения из Избранного и делает тестовый саммари."
        ]
        formatted_lines.extend(dummy_data)
        
    # Test 3: Prompt for style and test OpenRouter API
    logger.info("Test 3/4: Prompting for summary style and requesting OpenRouter summary...")
    chat_history_text = "\n".join(formatted_lines)
    try:
        style_code = await telegram_client.request_summary_style(client)
        summary = await summary_generator.generate_summary(chat_history_text, style_code)
        if "Ошибка" in summary:
            logger.error(f" -> FAILED: OpenRouter API error: {summary}")
            return False
        logger.info(" -> SUCCESS: Received summary from OpenRouter!")
    except Exception as e:
        logger.error(f" -> FAILED: OpenRouter request failed: {e}")
        return False
        
    # Test 4: Send the summary back to Saved Messages
    logger.info("Test 4/4: Sending the test summary back to Saved Messages ('me')...")
    try:
        test_output = (
            "🔔 **[Результат Теста Саммаризатора]**\n"
            "Диагностический тест выполнен успешно! Проверена выгрузка сообщений из Избранного, "
            "работа OpenRouter API и обратная отправка.\n\n"
            f"**Тестовый отчет (Саммари):**\n{summary}"
        )
        from telegram_client import split_message
        chunks = split_message(test_output)
        for chunk in chunks:
            await client.send_message('me', chunk, link_preview=False)
        logger.info(" -> SUCCESS: Summary sent to Saved Messages ('me')")
    except Exception as e:
        logger.error(f" -> FAILED: Could not send summary to Saved Messages: {e}")
        return False
            
    logger.info("🎉 All diagnostic tests completed successfully! Your configuration is working properly.")
    return True

async def main():
    parser = argparse.ArgumentParser(description="Telegram Weekly Chat Summarizer with LLM (OpenRouter)")
    parser.add_argument("--login", action="store_true", help="Run interactive login to authorize Telegram session")
    parser.add_argument("--run-now", action="store_true", help="Run the summary logic once immediately and exit")
    parser.add_argument("--days", type=int, default=7, help="Number of past days to summarize if running with --run-now (default: 7)")
    parser.add_argument("--test", action="store_true", help="Run connection and API diagnostics then exit")
    
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

    # 2. Standard validation (non-login modes require config validation)
    is_test_mode = getattr(args, 'test', False)
    config.validate_config(is_login_only=False, is_test_only=is_test_mode)

    logger.info("Initializing Telegram Client...")
    try:
        client = await telegram_client.get_telegram_client()
    except Exception as e:
        logger.error(f"Failed to start Telegram client: {e}")
        logger.error("Make sure you have authenticated the session by running the script with --login first.")
        sys.exit(1)

    try:
        # 3. Diagnostic tests
        if args.test:
            success = await run_tests(client)
            if success:
                sys.exit(0)
            else:
                sys.exit(1)

        # 4. Manual immediate execution mode
        if args.run_now:
            logger.info(f"Executing immediate summary for the past {args.days} days...")
            await scheduler.run_now(client, days_history=args.days)
            logger.info("Immediate execution completed successfully.")
            return

        # 5. Scheduler mode
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
