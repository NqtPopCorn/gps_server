import os
import logging
from django.conf import settings
from google import genai
from google.genai import types
import edge_tts
from edge_tts import VoicesManager
import asyncio

import wave
import json
import logging
from typing import Dict

logger = logging.getLogger(__name__)

# The new google-genai library uses GOOGLE_API_KEY environment variable by default
def get_genai_client():
    try:
        return genai.Client()
    except Exception as e:
        logger.warning(f"Could not initialize GenAI client: {e}")
        return None

logger = logging.getLogger(__name__)

def translate_poi_data(name: str, description: str, target_language: str) -> Dict[str, str]:
    """Translates POI name and description using Gemini model."""

    logger.info(f"Translating POI data: {name}, {description}, {target_language}")
    client = get_genai_client()
    if not client:
        raise ValueError("Google Gen AI client is not configured properly.")
        
    # Tối ưu Prompt: Yêu cầu trả về JSON chuẩn xác
    prompt = f"""Task: Translate the Point of Interest (POI) data into the language corresponding to ISO-639-1 code: {target_language}.

            Context: The content is for a travel/map application. Translations should be natural, culturally appropriate, and preserve the original tone.

            Data to translate:
            - Name: {name}
            - Description: {description}

            Constraint: Return ONLY a raw JSON object. No markdown formatting, no preamble, no backticks.
            JSON Structure:
            {{"name": "translated_name", "description": "translated_description"}}"""

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash-lite',
            contents=prompt,
        )
        
        result_text = response.text.strip()
        
        # Dọn dẹp markdown rác nếu LLM "lỡ" thêm vào
        if result_text.startswith("```json"):
            result_text = result_text[7:-3].strip()
        elif result_text.startswith("```"):
            result_text = result_text[3:-3].strip()
            
        logger.info(f"Translated text using Gemini: {result_text}")
        # Parse JSON và trả về Dictionary
        return json.loads(result_text)

    except Exception as e:
        # Fallback to googletrans
        logger.warning(f"Gemini translation failed: {e}, using googletrans fallback")
        try:
            return asyncio.run(translate_poi_data_googletrans(name, description, target_language))
        except Exception as fallback_e:
            logger.error(f"Googletrans fallback also failed: {fallback_e}")
            # Trả về dữ liệu gốc để không làm sập ứng dụng
            return {
                "name": name,
                "description": description
            }

async def translate_poi_data_googletrans(name: str, description: str, target_language: str) -> Dict[str, str]:
    from googletrans import Translator
    translator = Translator()
    # Dịch từng trường riêng biệt cho fallback
    translated_name = await translator.translate(name, dest=target_language)
    translated_desc = await translator.translate(description, dest=target_language)

    logger.info(f"Target language: {target_language}")
    logger.info(f"Translated name: {translated_name.text}")
    logger.info(f"Translated description: {translated_desc.text}")
    
    return {
        "name": translated_name.text.strip(),
        "description": translated_desc.text.strip()
    } 

async def generate_speech(text: str, lang_code: str, gender: str = "Female"):
    try:
        voices = await VoicesManager.create()
        locale = find_general_locale(lang_code)    
        if not locale:
            voice = voices.find(Gender=gender, Language=lang_code)
        else: 
            voice = voices.find(Gender=gender, Locale=locale)
        if not voice:
            raise ValueError("Could not find a voice for the given language code and gender.")
        import random
        communicate = edge_tts.Communicate(text, random.choice(voice)["Name"])
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]

    except Exception as e:
        logger.error(f"Error generating speech: {e}")
        raise ValueError("Error generating speech. May caused by wrong language code or locale.")

# list locale for vietnam tourism
vietnam_tourism_locales = [
    "ko-KR",
    "zh-CN",
    "zh-TW",
    "en-US",
    "ja-JP",
    "en-AU",
    "hi-IN",
    "km-KH",
    "ms-MY",
    "th-TH",
    "vi-VN"
]

def find_general_locale(lang_code: str) -> str:
    for locale in vietnam_tourism_locales:
        if locale.startswith(lang_code):
            return locale
    return None

# Set up the wave file to save the output:
def wave_file(filename, pcm, channels=1, rate=24000, sample_width=2):
   with wave.open(filename, "wb") as wf:
      wf.setnchannels(channels)
      wf.setsampwidth(sample_width)
      wf.setframerate(rate)
      wf.writeframes(pcm)

    