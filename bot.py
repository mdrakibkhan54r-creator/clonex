import asyncio
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import edge_tts
import httpx
from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M, Update
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler,
    ContextTypes, MessageHandler, filters,
)

# টোকেন ফাইলে নয়, হোস্টিং সাইটের Environment Variable এ রাখা হয় (নাম: BOT_TOKEN)
TOKEN = os.environ["BOT_TOKEN"]

VOICES = {
    "bn": {"female": "bn-BD-NabanitaNeural", "male": "bn-BD-PradeepNeural"},
    "en": {"female": "en-US-AriaNeural", "male": "en-US-GuyNeural"},
    "hi": {"female": "hi-IN-SwaraNeural", "male": "hi-IN-MadhurNeural"},
}
NAMES = {"bn": "বাংলা", "en": "English", "hi": "हिन्दी"}
S = {}

# ক্লোন ভয়েস (ঐচ্ছিক): Render এর Environment Variables এ বসাতে হয়
ELEVEN_KEY = os.environ.get("ELEVEN_API_KEY", "")
ELEVEN_MODEL = os.environ.get("ELEVEN_MODEL", "eleven_multilingual_v2")
ELEVEN_VOICE = {
    "male": os.environ.get("VOICE_MALE", ""),
    "female": os.environ.get("VOICE_FEMALE", ""),
}


async def eleven(t, voice_id, out):
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(
            "https://api.elevenlabs.io/v1/text-to-speech/" + voice_id,
            headers={"xi-api-key": ELEVEN_KEY},
            json={
                "text": t,
                "model_id": ELEVEN_MODEL,
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.85,
                    "style": 0.2,
                    "use_speaker_boost": True,
                },
            },
        )
        r.raise_for_status()
        with open(out, "wb") as fh:
            fh.write(r.content)


def st(uid):
    return S.setdefault(uid, {"lang": "bn", "gender": "female"})


def menu(s):
    g = "মেয়ে" if s["gender"] == "female" else "ছেলে"
    return M([
        [B("ভাষা: " + NAMES[s["lang"]], callback_data="m:lang")],
        [B("ভয়েস: " + g, callback_data="m:gender")],
    ])


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    s = st(update.effective_user.id)
    await update.message.reply_text(
        "সেটিংস ঠিক করুন, তারপর যেকোনো লেখা পাঠান।", reply_markup=menu(s)
    )


async def button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    s = st(q.from_user.id)
    a, _, v = q.data.partition(":")
    if a == "m" and v == "lang":
        kb = [[B(n, callback_data="l:" + c)] for c, n in NAMES.items()]
        await q.edit_message_text("ভাষা বাছাই করুন:", reply_markup=M(kb))
        return
    if a == "m" and v == "gender":
        kb = [
            [B("মেয়ে", callback_data="g:female")],
            [B("ছেলে", callback_data="g:male")],
        ]
        await q.edit_message_text("ভয়েস বাছাই করুন:", reply_markup=M(kb))
        return
    if a == "l":
        s["lang"] = v
    if a == "g":
        s["gender"] = v
    await q.edit_message_text("ঠিক আছে। এখন লেখা পাঠান।", reply_markup=menu(s))


async def text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    s = st(update.effective_user.id)
    t = update.message.text.strip()[:1500]
    await ctx.bot.send_chat_action(update.effective_chat.id, "record_voice")
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "voice.mp3")
        try:
            done = False
            vid = ELEVEN_VOICE[s["gender"]]
            # ১) আপনার নিজের ক্লোন করা ভয়েস (ElevenLabs), key আর voice id থাকলে
            if ELEVEN_KEY and vid:
                try:
                    await eleven(t, vid, f)
                    done = True
                except Exception as e:
                    print("ElevenLabs failed:", e, flush=True)
            # ২) Microsoft ভয়েস (কিছু ক্লাউড সার্ভারে 403 দেয়)
            if not done:
                try:
                    await edge_tts.Communicate(t, VOICES[s["lang"]][s["gender"]]).save(f)
                    done = True
                except Exception as e:
                    print("Edge failed:", e, flush=True)
            # ৩) শেষ ভরসা: Google ভয়েস
            if not done:
                from gtts import gTTS

                await asyncio.to_thread(gTTS(t, lang=s["lang"]).save, f)
            with open(f, "rb") as fh:
                await update.message.reply_audio(fh, title="Voice")
        except Exception as e:
            await update.message.reply_text("হয়নি: " + str(e))


class Ping(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, *a):
        pass


def keep_alive():
    # ফ্রি হোস্টিং সাইট পোর্ট খোঁজে, আর UptimeRobot এই ঠিকানায় পিং করে বটকে জাগিয়ে রাখে
    port = int(os.environ.get("PORT", "10000"))
    HTTPServer(("0.0.0.0", port), Ping).serve_forever()


def main():
    threading.Thread(target=keep_alive, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text))
    print("Bot running...", flush=True)
    app.run_polling()


if __name__ == "__main__":
    main()
