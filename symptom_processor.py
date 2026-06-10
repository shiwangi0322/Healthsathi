"""
HealthSathi — modules/symptom_processor.py
Full NLP pipeline: normalize → intent → entities → response
Supports Hindi, English, Hinglish
"""

import re
import difflib
import random
from typing import Optional, Dict, List

from modules.health_db import (
    search_symptoms,
    search_diseases,
    search_first_aid,
    get_all_keywords,
)

# ── Hinglish → English map ────────────────────────────────────
HINGLISH_MAP: Dict[str, str] = {
    "bukhar": "fever", "bukhaar": "fever", "bhukar": "fever",
    "tez bukhar": "high fever", "halka bukhar": "mild fever",
    "raat ko bukhar": "night fever",
    "khansi": "cough", "khasi": "cough", "khansee": "cough",
    "sookhi khansi": "dry cough", "balgam wali khansi": "wet cough",
    "sir dard": "headache", "sardard": "headache", "sar dard": "headache",
    "sirdard": "headache", "sir me dard": "headache", "sir mein dard": "headache",
    "pet dard": "stomach pain", "pait dard": "stomach pain",
    "pet mein dard": "stomach pain", "pait mein dard": "stomach pain",
    "pet mein marord": "stomach cramps",
    "ulti": "vomiting", "ultee": "vomiting",
    "dast": "diarrhea", "loose motion": "diarrhea",
    "kabz": "constipation", "qabz": "constipation",
    "kamzori": "weakness", "kamazori": "weakness",
    "thakaan": "fatigue", "thakan": "fatigue",
    "chakkar": "dizziness", "chakker": "dizziness",
    "behosh": "fainting", "behoshi": "fainting",
    "saans ki takleef": "breathing difficulty",
    "saans phulna": "shortness of breath",
    "sans phulna": "shortness of breath",
    "dama": "asthma", "dam": "asthma",
    "kamar dard": "back pain", "peeth dard": "back pain",
    "badan dard": "body pain", "badan mein dard": "body pain",
    "seene mein dard": "chest pain", "seena dard": "chest pain",
    "seene mein jalan": "heartburn",
    "jodo mein dard": "joint pain",
    "gale mein dard": "sore throat", "gale dard": "sore throat",
    "kan dard": "ear pain", "kaan dard": "ear pain",
    "aankh dard": "eye pain", "aankhein laal": "red eyes",
    "daant dard": "toothache", "dant dard": "toothache",
    "khujli": "itching", "khujlee": "itching",
    "daad": "ringworm", "khaj": "scabies",
    "peshab mein jalan": "burning urination",
    "peshaab jalan": "burning urination",
    "baar baar peshab": "frequent urination",
    "mahwari dard": "period pain", "maahwari": "period pain",
    "neend nahi aati": "sleep problem", "neend nahi": "sleep problem",
    "nakseer": "nose bleeding", "naak se khoon": "nose bleeding",
    "baal girna": "hair fall",
    "maleria": "malaria", "malariya": "malaria",
    "dengoo": "dengue", "dengu": "dengue",
    "taifaid": "typhoid", "taifo": "typhoid",
    "tb": "tuberculosis", "ti bi": "tuberculosis",
    "sugar": "diabetes", "madhumeh": "diabetes", "shakar bimari": "diabetes",
    "bp": "hypertension", "blood pressure high": "hypertension",
    "piliya": "jaundice", "peeliya": "jaundice",
    "haija": "cholera",
    "mirgi": "epilepsy", "mirgi ka daura": "epilepsy",
    "chechak": "chickenpox", "khasra": "measles",
    "galsua": "mumps", "bawasir": "piles",
    "dil ka daura": "heart attack", "heart attak": "heart attack",
    "lakwa": "stroke", "paralysis": "stroke",
    "khun": "bleeding", "khoon": "bleeding", "khoon aana": "bleeding",
    "jalana": "burn", "jal gaya": "burn",
    "saanp kaatna": "snake bite", "saanp ne kaata": "snake bite",
    "bijli lagana": "electric shock", "current lagna": "electric shock",
    "haddi tutna": "fracture", "haddi tooti": "fracture",
    "daub jana": "drowning", "doob jana": "drowning",
    "lu lagna": "heat stroke", "lu": "heat stroke",
    "dog kaatna": "dog bite", "kutta kaata": "dog bite",
    "zeher": "poisoning", "zaher": "poisoning",
    "namaste": "hello", "namaskar": "hello",
    "sat sri akal": "hello", "assalamualaikum": "hello",
    "shukriya": "thanks", "dhanyawaad": "thanks",
    "alvida": "bye", "tata": "bye",
    "kya hal": "how are you", "kaisa hai": "how are you",
    "kaise ho": "how are you",
}

STOP_WORDS = {
    "mujhe", "mujhko", "meri", "mera", "mere", "aapko", "apna",
    "hai", "hain", "ho", "raha", "rahi", "rahe", "tha", "thi", "the",
    "aur", "or", "bhi", "se", "mein", "ko", "ka", "ki", "ke",
    "nahi", "nahin", "kuch", "koi", "yeh", "woh",
    "main", "hum", "aap", "bahut", "thoda", "zyada",
    "lagta", "lagti", "laga", "please", "bata", "batao",
    "karo", "karna", "kya", "kaisa", "kaise",
    "i", "me", "my", "have", "has", "am", "is", "are",
    "feel", "feeling", "getting", "got",
    "a", "an", "the", "and", "or",
    "with", "some", "bit", "little", "very", "much",
    "please", "help", "tell", "about",
    "what", "how", "do", "does", "in", "on", "at", "been",
    "also", "too", "since", "for",
}

EMERGENCY_KEYWORDS = {
    "heart attack", "heart attak", "dil ka daura",
    "stroke", "lakwa", "paralysis",
    "unconscious", "behosh",
    "bleeding", "severe bleeding", "khun", "khoon",
    "drowning", "doob jana", "daub jana",
    "snake bite", "saanp kaata",
    "electric shock", "bijli", "current",
    "fracture", "haddi tooti",
    "choking", "gala band",
    "accident", "haadsa",
    "burn", "jal gaya", "fire",
    "poisoning", "zeher", "zaher",
    "seizure", "mirgi ka daura",
    "heat stroke", "lu lagna",
    "cough with blood", "khoon wali khansi",
    "chest pain", "seena dard",
    "anaphylaxis", "chemical burn",
    "acid attack", "scorpion sting",
}

GREET_WORDS = {
    "hello", "hi", "hey", "namaste", "namaskar",
    "sat sri akal", "assalamualaikum", "jai hind",
    "good morning", "good evening", "good afternoon",
    "good night", "helo", "hii",
}
FAREWELL_WORDS = {"bye", "goodbye", "alvida", "tata", "exit", "stop", "band karo", "khatam"}
THANKS_WORDS   = {"thanks", "thank you", "shukriya", "dhanyawaad", "shukriyaa", "bahut shukriya"}
HOW_ARE_W      = {"how are you", "kya hal hai", "kaisa hai", "kaise ho", "aap kaise hain", "how r u"}
ABOUT_W        = {"who are you", "aap kaun ho", "tumhara naam", "your name", "about you", "kya ho tum"}
JOKE_W         = {"joke", "jokes", "funny", "mujhe hasao", "koi joke sunao"}
HELP_W         = {"help", "madad", "kya kar sakte", "what can you do", "features"}

RESPONSES: Dict[str, List[str]] = {
    "greeting": [
        "Namaste! Main HealthSathi hoon. Aapki tabiyat kaisi hai? Koi takleef ho to batayein.",
        "Hello! HealthSathi yahan hai. Kya takleef hai aapko?",
        "Hi there! Main aapka AI health dost hoon. Batayen kya pareshani hai?",
    ],
    "farewell": [
        "Alvida! Apna aur apne parivaar ka khayal rakhein. Swasth rahein!",
        "Take care! Sehat hi sabse badi daulat hai. Phir milenge!",
    ],
    "thanks": [
        "Aapka swagat hai! Koi aur sawaal ho to zaroor poochein. Swasth rahein!",
        "My pleasure! Main hamesha yahan hoon aapki madad ke liye.",
    ],
    "how_are_you": [
        "Main bilkul theek hoon, shukriya! Main ek AI hoon — hamesha ready hoon. Aap kaise hain?",
        "Mujhe toh koi takleef nahi — main AI hoon! Par aap batayein, aap kaisa feel kar rahe hain?",
    ],
    "about": [
        "Main HealthSathi AI hoon — aapka offline AI health assistant. Hindi, English aur Hinglish samajhta hoon. Symptoms, diseases, first aid — sab pooch sakte hain!",
    ],
    "joke": [
        "Doctor ne patient se kaha: 'Roz seb khao.' Patient bola: 'Toh doctor ko kab milenge?'",
        "Patient: Doctor saab, mujhe neend nahi aati. Doctor: Koi baat nahi, mujhe bhi nahi aati — apni fees sun ke!",
    ],
    "help": [
        "Main yeh kar sakta hoon: Symptoms batao (jaise bukhar, khansi), bimari ke baare mein poochho (dengue, malaria), first aid jaano. Hindi ya English mein baat karo!",
    ],
    "emergency_generic": [
        "Yeh emergency lagti hai! Turant 108 call karein. Shant rahein aur madad ka intezaar karein.",
    ],
    "not_found": [
        "Mujhe samajh nahi aaya. Zara aur detail mein batayein? Jaise: 'mujhe bukhar hai' ya 'dengue ke baare mein batao'.",
        "Main samajh nahi paya. Kripya clearly batayein — jaise 'pet mein dard hai' ya 'what is diabetes'.",
    ],
}


def normalize_text(text: str) -> str:
    """Clean and normalize input."""
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    for hinglish, english in sorted(HINGLISH_MAP.items(), key=lambda x: -len(x[0])):
        if hinglish in text:
            text = text.replace(hinglish, english)
    words   = text.split()
    cleaned = " ".join(w for w in words if w not in STOP_WORDS)
    return cleaned or text


def _fuzzy_best(query: str, candidates: List[str], threshold: float = 0.65) -> Optional[str]:
    if not query or not candidates or len(query) < 3:
        return None
    matches = difflib.get_close_matches(query, candidates, n=1, cutoff=threshold)
    return matches[0] if matches else None


def _build_phrases(tokens: List[str]) -> List[str]:
    phrases: List[str] = []
    n = len(tokens)
    for i in range(n):
        phrases.append(tokens[i])
        if i + 1 < n:
            phrases.append("{} {}".format(tokens[i], tokens[i + 1]))
        if i + 2 < n:
            phrases.append("{} {} {}".format(tokens[i], tokens[i + 1], tokens[i + 2]))
    return phrases


def detect_intent(normalized: str, original: str) -> str:
    lower_orig = original.lower()
    for kw in EMERGENCY_KEYWORDS:
        if kw in lower_orig or kw in normalized:
            return "emergency"
    words = set(lower_orig.split())
    if words & GREET_WORDS:
        return "greeting"
    if words & FAREWELL_WORDS:
        return "farewell"
    if words & THANKS_WORDS:
        return "thanks"
    if any(p in lower_orig for p in HOW_ARE_W):
        return "how_are_you"
    if any(p in lower_orig for p in ABOUT_W):
        return "about"
    if any(p in lower_orig for p in JOKE_W):
        return "joke"
    if any(p in lower_orig for p in HELP_W):
        return "help"
    return "health_query"


def extract_entities(normalized: str, all_kw: Dict[str, List[str]]) -> Dict[str, List[str]]:
    found: Dict[str, List[str]] = {"symptoms": [], "diseases": [], "first_aid": []}
    tokens  = normalized.split()
    phrases = _build_phrases(tokens)
    for phrase in phrases:
        for table in ["first_aid", "diseases", "symptoms"]:
            kl = all_kw[table]
            if phrase in kl:
                if phrase not in found[table]:
                    found[table].append(phrase)
            elif len(phrase) >= 4:
                m = _fuzzy_best(phrase, kl, 0.68)
                if m and m not in found[table]:
                    found[table].append(m)
    return found


def build_response(intent: str, entities: Dict[str, List[str]], original: str) -> str:
    if intent == "emergency":
        orig_lower = original.lower()
        all_kw = get_all_keywords()
        for kw in all_kw["first_aid"]:
            if kw in orig_lower:
                steps = search_first_aid(kw)
                if steps:
                    return "Emergency! {}".format(steps)
        for fa in entities["first_aid"]:
            steps = search_first_aid(fa)
            if steps:
                return "Emergency! {}".format(steps)
        return RESPONSES["emergency_generic"][0]

    quick = ["greeting", "farewell", "thanks", "how_are_you", "about", "joke", "help"]
    if intent in quick:
        return random.choice(RESPONSES[intent])

    responses: List[str] = []
    for fa in entities["first_aid"]:
        r = search_first_aid(fa)
        if r:
            responses.append(r)
    for disease in entities["diseases"]:
        info = search_diseases(disease)
        if info:
            responses.append("Yeh {} ho sakta hai. {}".format(disease, info["precautions"]))
    for sym in entities["symptoms"]:
        r = search_symptoms(sym)
        if r:
            responses.append(r)

    if responses:
        return responses[0]

    return random.choice(RESPONSES["not_found"])


def process_nlp(user_text: str) -> Dict[str, object]:
    """
    Full pipeline: text → normalize → intent → entities → response
    Returns dict: hindi_response, intent, entities, normalized_text
    """
    if not user_text or not user_text.strip():
        return {
            "hindi_response":  "Kripya kuch bolein.",
            "intent":          "empty",
            "entities":        {"symptoms": [], "diseases": [], "first_aid": []},
            "normalized_text": "",
        }

    normalized = normalize_text(user_text)
    intent     = detect_intent(normalized, user_text)

    entities: Dict[str, List[str]] = {"symptoms": [], "diseases": [], "first_aid": []}

    if intent in ("health_query", "emergency"):
        try:
            all_kw   = get_all_keywords()
            entities = extract_entities(normalized, all_kw)
            if entities["first_aid"]:
                intent = "emergency"
            elif entities["diseases"] and not entities["symptoms"]:
                intent = "disease"
            elif entities["symptoms"]:
                intent = "symptom"
        except Exception as ex:
            print("[NLP Error] {}".format(ex))

    response = build_response(intent, entities, user_text)

    return {
        "hindi_response":  response,
        "intent":          intent,
        "entities":        entities,
        "normalized_text": normalized,
    }