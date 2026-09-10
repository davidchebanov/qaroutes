"""
Мои маршруты — Telegram bot
Хостинг: Render (Web Service, free tier)
"""
import os, time, logging, threading, urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)   # не засорять логи
log = logging.getLogger("qaroutes")

BOT_TOKEN  = os.environ["BOT_TOKEN"]
WEBAPP_URL = os.environ["WEBAPP_URL"]
PORT       = int(os.environ.get("PORT", 10000))
SELF_URL   = os.environ.get("RENDER_EXTERNAL_URL")     # Render задаёт сам


# ── 1. заглушка на порт: Render требует открытый порт у Web Service ──
class Ping(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"qaroutes bot is alive")

    def log_message(self, *a):
        pass


def serve():
    HTTPServer(("0.0.0.0", PORT), Ping).serve_forever()


threading.Thread(target=serve, daemon=True).start()
log.info(f"HTTP keep-alive server on :{PORT}")


# ── 2. самопинг раз в 10 минут — не даёт сервису заснуть ────────────
def keep_awake():
    if not SELF_URL:
        log.warning("RENDER_EXTERNAL_URL не задан — самопинг выключен")
        return
    while True:
        time.sleep(600)
        try:
            urllib.request.urlopen(SELF_URL, timeout=20).read()
            log.info("self-ping ok")
        except Exception as e:
            log.warning(f"self-ping failed: {e}")


threading.Thread(target=keep_awake, daemon=True).start()


# ── 3. бот ──────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton(
        "🗺 создать маршрут",
        web_app=WebAppInfo(url=WEBAPP_URL),
    )]]
    await update.message.reply_text(
        "привет!\n\n"
        "я собираю маршруты по москве из личной карты канала — "
        "611 проверенных места: кофе, бары, галереи, парки, театры и не только.\n\n"
        "нажми кнопку ниже ✦",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start — открыть генератор маршрутов\n\nканал: @qaroutes"
    )


if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    log.info("bot started, polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
