import json
import time

import requests
from pydantic import ValidationError

from .config import get_settings
from .schemas import LLMResponse


SYSTEM_PROMPT = """
Ты — строгий анализатор запросов. У тебя есть данные тура: {tour_data}

Оцени сообщение пользователя и верни валидный JSON-объект:
{{
  "status": "ANSWER",
  "reply": "Сухой ответ только на основе данных тура"
}}

Допустимые статусы:
- ANSWER: вопрос понятен и ответ есть в данных тура;
- NO_DATA: вопрос понятен, но ответа в данных тура нет;
- UNCLEAR: сообщение бессмысленно или не содержит конкретного вопроса.

Для NO_DATA и UNCLEAR оставь reply пустым. Не придумывай факты.
""".strip()


class LLMResponseError(ValueError):
    """YandexGPT вернул ответ, который не соответствует ожидаемой схеме."""


def call_yandex_gpt(tour_data: dict, user_message: str) -> LLMResponse:
    settings = get_settings()
    if not settings.yandex_is_configured():
        raise requests.RequestException("YandexGPT credentials are not configured")

    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {
        "Authorization": f"Api-Key {settings.YC_API_KEY}",
        "x-folder-id": settings.YC_FOLDER_ID,
        "Content-Type": "application/json",
    }
    prompt = SYSTEM_PROMPT.format(
        tour_data=json.dumps(tour_data, ensure_ascii=False)
    )
    payload = {
        "modelUri": f"gpt://{settings.YC_FOLDER_ID}/yandexgpt-lite/latest",
        "completionOptions": {
            "stream": False,
            "temperature": 0.1,
            "maxTokens": "700",
        },
        "jsonObject": True,
        "messages": [
            {"role": "system", "text": prompt},
            {"role": "user", "text": user_message},
        ],
    }

    for attempt in range(3):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=15.0,
            )
            if response.status_code in (429, 500, 502, 503, 504):
                if attempt < 2:
                    time.sleep(2**attempt)
                    continue
                response.raise_for_status()

            response.raise_for_status()
            raw_text = response.json()["result"]["alternatives"][0]["message"]["text"]
            return LLMResponse.model_validate_json(raw_text)
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2**attempt)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValidationError) as exc:
            raise LLMResponseError("Invalid YandexGPT response") from exc

    raise requests.RequestException("Превышено количество попыток запроса к YandexGPT")

