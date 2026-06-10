"""HealthSathi — modules/chatbot.py"""
from modules.symptom_processor import process_nlp


def get_chatbot_response(user_message: str) -> str:
    if not user_message or not user_message.strip():
        return "Kripya kuch likhein."
    result = process_nlp(user_message)
    return str(result.get("hindi_response", "Samajh nahi aaya. Dobara likhein."))