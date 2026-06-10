import os
import sys
import logging
import sqlite3
import hashlib
import threading

from flask import (
    Flask, render_template, request,
    jsonify, session, Response, redirect, url_for
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Only import what is actually used ─────────────────────────
from modules.health_db         import init_db, get_db, save_conversation, get_user_history
from modules.symptom_processor import process_nlp
from modules.voice_handler     import speak, listen_generator

# ── Silence Flask dev logs ─────────────────────────────────────
logging.getLogger("werkzeug").setLevel(logging.ERROR)

app = Flask(__name__)
app.secret_key = "healthsathi_2025_secret"


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def hash_pw(pw: str) -> str:
    """SHA-256 hash for passwords."""
    return hashlib.sha256(pw.encode()).hexdigest()


def speak_bg(text: str) -> None:
    """Speak text in a background thread (non-blocking)."""
    t = threading.Thread(target=speak, args=(text,), daemon=True)
    t.start()


# ══════════════════════════════════════════════════════════════
# PAGE ROUTES
# ══════════════════════════════════════════════════════════════

@app.route("/")
def home():
    return render_template("home.html")


@app.route("/voice_assistant")
def voice_assistant():
    return render_template("voice_assistant.html")


@app.route("/chatbot")
def chatbot():
    return render_template("chatbot.html")


@app.route("/symptoms")
def symptoms():
    return render_template("symptoms.html")


@app.route("/health_tips")
def health_tips():
    return render_template("health_tips.html")


@app.route("/emergency")
def emergency():
    return render_template("emergency.html")


@app.route("/about")
def about():
    return render_template("about.html")


# ══════════════════════════════════════════════════════════════
# AUTH — LOGIN
# ══════════════════════════════════════════════════════════════

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    data     = request.get_json() or {}
    login_id = str(data.get("login_id", "")).strip()
    password = str(data.get("password", "")).strip()

    if not login_id or not password:
        return jsonify({
            "success": False,
            "message": "Email/phone aur password zaroori hain."
        })

    conn = get_db()
    row  = conn.execute(
        "SELECT * FROM users WHERE (phone = ? OR email = ?) AND password = ?",
        (login_id, login_id, hash_pw(password))
    ).fetchone()
    conn.close()

    if row:
        session["user_id"]   = row["id"]
        session["user_name"] = row["full_name"]
        return jsonify({
            "success":  True,
            "message":  "Swagat hai {}!".format(row["full_name"]),
            "redirect": "/"
        })

    return jsonify({
        "success": False,
        "message": "Phone/email ya password galat hai."
    })


# ══════════════════════════════════════════════════════════════
# AUTH — SIGNUP
# ══════════════════════════════════════════════════════════════

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("signup.html")

    data      = request.get_json() or {}
    full_name = str(data.get("full_name", "")).strip()
    phone     = str(data.get("phone", "")).strip().replace(" ", "")
    email     = str(data.get("email", "")).strip() or None
    password  = str(data.get("password", "")).strip()

    if not full_name or not phone or not password:
        return jsonify({"success": False, "message": "Naam, phone aur password zaroori hain."})
    if len(phone) < 10:
        return jsonify({"success": False, "message": "Sahi phone number daalein."})
    if len(password) < 6:
        return jsonify({"success": False, "message": "Password 6+ characters ka hona chahiye."})

    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO users (full_name, phone, email, password) VALUES (?,?,?,?)",
            (full_name, phone, email, hash_pw(password))
        )
        conn.commit()
        uid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()

        session["user_id"]   = uid
        session["user_name"] = full_name

        return jsonify({
            "success":  True,
            "message":  "{}, swagat hai HealthSathi mein!".format(full_name),
            "redirect": "/"
        })

    except sqlite3.IntegrityError:
        return jsonify({
            "success": False,
            "message": "Yeh phone pehle se registered hai. Login karein."
        })

    except Exception as ex:
        return jsonify({"success": False, "message": str(ex)})


# ══════════════════════════════════════════════════════════════
# AUTH — LOGOUT
# ══════════════════════════════════════════════════════════════

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# ══════════════════════════════════════════════════════════════
# VOICE API — /process_voice
# Called by voice_assistant.html after Web Speech API captures text
# ══════════════════════════════════════════════════════════════

@app.route("/process_voice", methods=["POST"])
def process_voice():
    """
    POST { "text": "mujhe bukhar hai" }
    Returns { "response": "...", "intent": "..." }
    Also speaks the response via pyttsx3 in background.
    """
    data = request.get_json() or {}
    text = str(data.get("text", "")).strip()

    if not text:
        return jsonify({"response": "Kripya kuch bolein.", "intent": "empty"})

    result   = process_nlp(text)
    response = str(result["hindi_response"])
    intent   = str(result["intent"])

    save_conversation(session.get("user_id"), text, response, intent)
    speak_bg(response)

    return jsonify({
        "response": response,
        "intent":   intent,
        "entities": result["entities"],
    })


# ══════════════════════════════════════════════════════════════
# CHAT API — /chat
# Called by chatbot.html
# ══════════════════════════════════════════════════════════════

@app.route("/chat", methods=["POST"])
def chat():
    """
    POST { "message": "mujhe bukhar hai" }
    Returns { "response": "..." }
    """
    data = request.get_json() or {}
    msg  = str(data.get("message", "")).strip()

    if not msg:
        return jsonify({"response": "Kripya kuch likhein."})

    result   = process_nlp(msg)
    response = str(result["hindi_response"])
    save_conversation(session.get("user_id"), msg, response, str(result["intent"]))
    return jsonify({"response": response})


# ══════════════════════════════════════════════════════════════
# STREAM VOICE — /stream_voice (SSE)
# Real-time voice transcription via Vosk + Server-Sent Events
# ══════════════════════════════════════════════════════════════

@app.route("/stream_voice")
def stream_voice():
    """SSE endpoint: streams partial + final voice recognition results."""
    import json as _json

    def generate():
        final_text = ""

        for result_str in listen_generator(timeout=8):
            result = _json.loads(result_str)

            if result["type"] == "partial":
                yield "data: {}\n\n".format(
                    _json.dumps({"type": "partial", "text": result["text"]})
                )

            elif result["type"] == "final":
                final_text = result["text"]
                break

            elif result["type"] == "error":
                yield "data: {}\n\n".format(
                    _json.dumps({"type": "error", "text": result["text"]})
                )
                return

        if not final_text:
            msg = "Mujhe sunai nahi diya. Dobara bolein."
            yield "data: {}\n\n".format(
                _json.dumps({"type": "final", "text": "", "response": msg})
            )
            speak_bg(msg)
            return

        nlp_result = process_nlp(final_text)
        response   = str(nlp_result["hindi_response"])

        yield "data: {}\n\n".format(
            _json.dumps({
                "type":     "final",
                "text":     final_text,
                "response": response,
                "intent":   str(nlp_result["intent"]),
            })
        )
        speak_bg(response)
        save_conversation(
            session.get("user_id"),
            final_text,
            response,
            str(nlp_result["intent"])
        )

    return Response(generate(), mimetype="text/event-stream")


# ══════════════════════════════════════════════════════════════
# UTILITY APIS
# ══════════════════════════════════════════════════════════════

@app.route("/api/speak", methods=["POST"])
def api_speak():
    """Speak arbitrary text via pyttsx3."""
    data = request.get_json() or {}
    text = str(data.get("text", "")).strip()
    if text:
        speak_bg(text)
    return jsonify({"status": "speaking"})


@app.route("/api/history", methods=["GET"])
def api_history():
    """Return last 10 conversations for current user."""
    history = get_user_history(session.get("user_id"), limit=10)
    return jsonify({"history": history})


@app.route("/api/clear_history", methods=["POST"])
def api_clear_history():
    """Clear conversation history for current user."""
    try:
        conn = get_db()
        conn.execute(
            "DELETE FROM conversations WHERE user_id = ?",
            (session.get("user_id"),)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
    return jsonify({"status": "cleared"})


@app.route("/health")
def health_check():
    """Server health check endpoint."""
    return jsonify({"status": "ok", "app": "HealthSathi", "version": "6.0"})


# ══════════════════════════════════════════════════════════════
# STARTUP
# ══════════════════════════════════════════════════════════════

def startup() -> None:
    print("\n" + "=" * 52)
    print("   HealthSathi AI — v6.0")
    print("=" * 52)
    init_db()
    print("\n  Open:  http://127.0.0.1:5000")
    print("  Voice: http://127.0.0.1:5000/voice_assistant")
    print("  Chat:  http://127.0.0.1:5000/chatbot")
    print("=" * 52 + "\n")


if __name__ == "__main__":
    startup()
    app.run(debug=True, use_reloader=False, port=5000)