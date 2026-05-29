import httpx
import logging
import config

logger = logging.getLogger("summarizer.summary_generator")

# System prompt guiding the model to produce a structured longread in Russian for the friend in the army.
SYSTEM_PROMPT = """You are an AI chronicler of a friendly Telegram chat. One of the chat members is currently serving in the army for a year. Your task is to read the chat history for the past week and create a detailed, engaging, and comprehensive longread summary so he knows exactly what he missed.

CRITICAL RULES:
1. OUTPUT LANGUAGE: You MUST write the entire summary in Russian.
2. STYLE & TONE: For this week, strictly use the following style: [SELECTED_STYLE]. 
3. UNCENSORED VOCABULARY: Preserve the original vocabulary of the chat. Do not censor profanity, slang, or swear words. Keep the raw, authentic flavor of the conversations.
4. NO JUNK: Do NOT include any URLs, links, file names, or system logs. Focus purely on the content of the conversations.
5. VOLUME: Write a detailed longread. Do not skip funny or interesting details.
6. QUIET DAYS: If there are significant gaps in the chat history or days with no messages, explicitly mention it (e.g., "On Wednesday and Thursday, the chat was completely dead").
7. NO HASHTAGS: Do not use any hashtags for navigation.

STRUCTURE OF THE LONGREAD:
Format the output using neat Markdown (use emojis, bullet points, and bold text for user names). Divide the text into the following exact sections:

👋 ВСТУПЛЕНИЕ
Describe the overall atmosphere of the chat this week. Was it active, toxic, funny, or quiet? Explicitly mention any dead days here.

🌍 ЧТО ПРОИСХОДИТ В ЖИЗНИ
A detailed recap of the members' real-life events (studies, work, where they went, what happened to them). Separate different topics into paragraphs.

🎮 ИГРЫ И ГИКТОВЩИНА
A section dedicated to joint games, servers, coding, creative stuff, and hobbies. Describe who did what and what ideas were discussed.

🏆 КТО ОТЛИЧИЛСЯ
A dedicated paragraph listing specific names and their main "achievements", ideas, or epic fails of the week. Who was the most active? Who complained the most?

🤡 ГЛАВНЫЕ РОФЛЫ И ЦИТАТЫ
Gather the funniest moments, local memes, absurd arguments, and exact funny quotes that made people laugh.

Make it feel like a seamless, immersive story for the friend in the army, bringing him right back into the circle.
"""

STYLE_DESCRIPTIONS = {
    "1": "дружеский бро-стиль (с юмором, использованием молодежного сленга, смайликов, локальных мемов, в теплом неформальном дружеском тоне)",
    "2": "нейтральная выжимка фактов (строгий информативный тон, хронологическое лаконичное описание событий без лишних эмоций и сленга)",
    "3": "армейский рапорт (шуточный строгий военный стиль, уставной канцелярит, докладывать по уставу с использованием терминов 'личный состав', 'боевые задачи', 'нарушение дисциплины')"
}

async def generate_summary(chat_history_text: str, style_code: str = "2") -> str:
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
    
    # Select the style description and format the system prompt
    selected_style = STYLE_DESCRIPTIONS.get(style_code, STYLE_DESCRIPTIONS["2"])
    formatted_system_prompt = SYSTEM_PROMPT.replace("[SELECTED_STYLE]", selected_style)
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": formatted_system_prompt},
            {"role": "user", "content": f"Вот история сообщений чата за прошедшую неделю:\n\n{chat_history_text}"}
        ],
        # Slightly higher temperature (0.5) to allow more style creativity in slang/humor modes
        "temperature": 0.5
    }

    logger.info(f"Sending request to OpenRouter API (model: {model}, style: {selected_style}, text size: {len(chat_history_text)} chars)...")
    
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
