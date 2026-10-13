import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import edge_tts
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
            voice = VOICES[s["lang"]][s["gender"]]
            await edge_tts.Communicate(t, voice).save(f)
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
