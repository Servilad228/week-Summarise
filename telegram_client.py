import datetime
import logging
from telethon import TelegramClient
from telethon.tl.types import PeerUser, PeerChat, PeerChannel
import config

logger = logging.getLogger("summarizer.telegram_client")

async def interactive_login():
    """
    Runs interactive login to generate the Telethon session file.
    """
    logger.info("Initializing Telegram Client for login...")
    client = TelegramClient(config.SESSION_NAME, config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH)
    print("Starting Telegram Client authentication...")
    await client.start()
    print("Successfully authenticated!")
    me = await client.get_me()
    print(f"Logged in as: {me.first_name} (@{me.username or 'no_username'})")
    await client.disconnect()

async def get_telegram_client() -> TelegramClient:
    """
    Returns an authorized TelegramClient instance.
    Raises RuntimeError if the user is not authenticated.
    """
    client = TelegramClient(config.SESSION_NAME, config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        raise RuntimeError(
            "Telegram Session is not authorized. "
            "Please run the script with '--login' flag to authenticate first."
        )
    return client

async def fetch_chat_history(client: TelegramClient, start_date: datetime.datetime) -> str:
    """
    Fetches text messages from config.TELEGRAM_CHAT_ID starting from start_date (UTC).
    Returns a formatted string representing the history.
    """
    logger.info(f"Fetching messages from chat {config.TELEGRAM_CHAT_ID} since {start_date}...")
    
    # Resolve the chat entity
    try:
        chat_entity = await client.get_input_entity(config.TELEGRAM_CHAT_ID)
    except Exception as e:
        logger.error(f"Failed to resolve chat ID '{config.TELEGRAM_CHAT_ID}': {e}")
        # Try getting the entity directly (in case it is in cache or dialogs)
        try:
            chat_entity = await client.get_entity(config.TELEGRAM_CHAT_ID)
        except Exception as e2:
            raise RuntimeError(f"Could not resolve Telegram chat ID: {e2}. Ensure the account is a member of this chat/group.")

    messages = []
    sender_cache = {}
    
    # We fetch messages backwards (newest first) and break when we go past start_date
    count = 0
    async for message in client.iter_messages(chat_entity, limit=config.MAX_MESSAGES_LIMIT):
        # Stop if the message is older than the start date
        if message.date < start_date:
            break
            
        # Ignore service messages, media-only messages without text, etc.
        if not message.text or message.action:
            continue
            
        # Optimize sender name resolution by caching sender entities
        sender_id = message.sender_id
        sender_name = "Unknown"
        
        if sender_id:
            if sender_id not in sender_cache:
                try:
                    sender = await message.get_sender()
                    if sender:
                        if hasattr(sender, 'first_name') and sender.first_name:
                            name = sender.first_name
                            if hasattr(sender, 'last_name') and sender.last_name:
                                name += f" {sender.last_name}"
                        elif hasattr(sender, 'title') and sender.title:
                            name = sender.title
                        else:
                            name = getattr(sender, 'username', None) or str(sender_id)
                        sender_cache[sender_id] = name
                    else:
                        sender_cache[sender_id] = str(sender_id)
                except Exception as e:
                    logger.debug(f"Could not resolve sender {sender_id}: {e}")
                    sender_cache[sender_id] = str(sender_id)
            
            sender_name = sender_cache[sender_id]

        messages.append((message.date, sender_name, message.text))
        count += 1
        if count % 100 == 0:
            logger.info(f"Fetched {count} messages so far...")

    logger.info(f"Total relevant messages fetched: {len(messages)}")
    
    # Reverse messages to make them chronological (oldest to newest)
    messages.reverse()
    
    # Format messages into a single text block
    formatted_lines = []
    for date, sender, text in messages:
        # Clean newlines inside the message text to save formatting and context size
        text_clean = text.replace('\n', ' ')
        formatted_lines.append(f"[{date.strftime('%Y-%m-%d %H:%M')}] {sender}: {text_clean}")
        
    return "\n".join(formatted_lines)

def split_message(text: str, limit: int = 4096) -> list:
    """
    Splits a message into chunks within the Telegram length limit.
    Attempts to split by code blocks or double newlines (paragraphs) where possible.
    """
    if len(text) <= limit:
        return [text]
        
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
            
        # Try to find a good split point near the limit
        split_pos = text.rfind('\n\n', 0, limit)
        if split_pos == -1 or split_pos < (limit * 0.7):
            split_pos = text.rfind('\n', 0, limit)
        if split_pos == -1 or split_pos < (limit * 0.7):
            split_pos = text.rfind(' ', 0, limit)
        if split_pos == -1:
            split_pos = limit
            
        chunks.append(text[:split_pos].strip())
        text = text[split_pos:].strip()
        
    return chunks

async def send_summary(client: TelegramClient, summary_text: str):
    """
    Sends the generated summary to all configured targets.
    """
    targets = config.TELEGRAM_TARGET_CHATS
    if not targets:
        logger.warning("No targets configured to send the summary to.")
        return

    chunks = split_message(summary_text)
    
    for target in targets:
        try:
            logger.info(f"Sending summary to target: {target} (chunks: {len(chunks)})")
            # In Telethon, 'me' resolves to Saved Messages. 
            # If target is an int or username, Telethon resolves it automatically.
            entity = await client.get_input_entity(target) if target != 'me' else 'me'
            
            for chunk in chunks:
                await client.send_message(entity, chunk, link_preview=False)
                
            logger.info(f"Successfully sent summary to target: {target}")
        except Exception as e:
            logger.error(f"Failed to send summary to target '{target}': {e}")
