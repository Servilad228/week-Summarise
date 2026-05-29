import httpx
import logging
import config

logger = logging.getLogger("summarizer.summary_generator")

# Enforce a system prompt that guides the model to produce a structured summary in Russian.
SYSTEM_PROMPT = (
    "Вы — умный ассистент, анализирующий историю сообщений в Telegram-чате.\n"
    "Ваша задача — составить информативный и структурированный недельный отчет (summary) происходящего в чате на русском языке.\n"
    "Пожалуйста, выделите:\n"
    "1. Основные темы обсуждений (сгруппированные по категориям, с кратким описанием сути).\n"
    "2. Важные объявления, новости или решения.\n"
    "3. Полезные ссылки, файлы, контакты или советы, которыми делились участники.\n"
    "4. Общую атмосферу/настроение в чате (кратко).\n\n"
    "Форматируйте текст аккуратно с использованием markdown (жирный шрифт, списки, цитаты), "
    "чтобы его было удобно читать в Telegram. Не используйте слишком крупные заголовки H1/H2, лучше использовать жирный текст.\n"
    "Сделайте отчет лаконичным, но содержательным, без лишней «воды»."
)

async def generate_summary(chat_history_text: str) -> str:
    """
    Sends the formatted chat history to OpenRouter to generate a summary.
    """
    if not chat_history_text.strip():
        return "В указанный период в чате не было текстовых сообщений."

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://github.com/valdes/telegram-weekly-summarizer",
        "X-Title": "Telegram Weekly Summarizer",
        "Content-Type": "application/json"
    }

    # Add a fallback for models if not specified
    model = config.OPENROUTER_MODEL or "google/gemini-2.5-flash"
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Вот история сообщений чата за прошедшую неделю:\n\n{chat_history_text}"}
        ],
        "temperature": 0.3 # Low temperature for more factual summaries
    }

    logger.info(f"Sending request to OpenRouter API (model: {model}, text size: {len(chat_history_text)} chars)...")
    
    # Use httpx client with custom timeout (LLMs can take time to answer large prompts)
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            
            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                summary = data["choices"][0]["message"]["content"]
                return summary.strip()
            else:
                logger.error(f"Unexpected response structure from OpenRouter: {data}")
                return "Ошибка: Не удалось получить ответ от нейросети (некорректная структура ответа)."
                
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error from OpenRouter: {e.response.status_code} - {e.response.text}")
        return f"Ошибка OpenRouter API (HTTP {e.response.status_code}): {e.response.text}"
    except httpx.RequestError as e:
        logger.error(f"Network error trying to connect to OpenRouter: {e}")
        return f"Сетевая ошибка при запросе к OpenRouter: {e}"
    except Exception as e:
        logger.error(f"Unexpected error in generate_summary: {e}")
        return f"Произошла непредвиденная ошибка при генерации summary: {e}"
