"""
Мои маршруты — Telegram bot
Хостинг: Render (Web Service, free tier)
"""
import os, time, logging, threading, urllib.request
import asyncio, hashlib, hmac, json
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import AIORateLimiter, Application, CallbackQueryHandler, CommandHandler, ContextTypes

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
CHANNEL = "@qaroutes"
CHECK_APP = None
CHECK_LOOP = None


def subscribed(member):
    return member.status in ("creator", "administrator", "member") or (
        member.status == "restricted" and member.is_member)


def verified_user(data):
    pairs = parse_qsl(data, keep_blank_values=True)
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise ValueError("duplicate fields")
    received = fields.pop("hash", "")
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(received, expected):
        raise ValueError("invalid signature")
    age = time.time() - int(fields["auth_date"])
    if not -30 <= age <= 86400:
        raise ValueError("expired session")
    user_id = json.loads(fields["user"])["id"]
    if type(user_id) is not int or user_id <= 0:
        raise ValueError("invalid user")
    return user_id


# ── 1. заглушка на порт: Render требует открытый порт у Web Service ──
class Ping(BaseHTTPRequestHandler):
    def api_reply(self, code, payload):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", urlsplit(WEBAPP_URL).scheme + "://" + urlsplit(WEBAPP_URL).netloc)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", urlsplit(WEBAPP_URL).scheme + "://" + urlsplit(WEBAPP_URL).netloc)
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.end_headers()

    def do_POST(self):
        if self.path != "/subscription":
            return self.api_reply(404, {"error": "not_found"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 16384:
                raise ValueError("invalid size")
            user_id = verified_user(json.loads(self.rfile.read(size))["initData"])
        except (ValueError, KeyError, TypeError):
            return self.api_reply(401, {"error": "invalid_session"})
        if CHECK_APP is None or CHECK_LOOP is None:
            return self.api_reply(503, {"error": "unavailable"})
        future = asyncio.run_coroutine_threadsafe(
            CHECK_APP.bot.get_chat_member(CHANNEL, user_id), CHECK_LOOP)
        try:
            member = future.result(timeout=12)
        except Exception:
            future.cancel()
            return self.api_reply(503, {"error": "unavailable"})
        self.api_reply(200, {"subscribed": subscribed(member)})

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"qaroutes bot is alive")

    def log_message(self, *a):
        pass


def serve():
    ThreadingHTTPServer(("0.0.0.0", PORT), Ping).serve_forever()


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
    if update.callback_query:
        await update.callback_query.answer()
    try:
        member = await context.bot.get_chat_member(CHANNEL, update.effective_user.id)
    except Exception:
        await update.effective_message.reply_text(
            "не получилось проверить подписку. попробуй /start чуть позже.")
        return
    if not subscribed(member):
        await update.effective_message.reply_text(
            "чтобы собирать маршруты, подпишись на канал «мои маршруты», затем нажми «проверить подписку».",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("подписаться на канал", url="https://t.me/qaroutes")],
                [InlineKeyboardButton("проверить подписку", callback_data="check_subscription")],
            ]))
        return
    if not SELF_URL:
        await update.effective_message.reply_text("генератор временно недоступен. попробуй позже.")
        return
    parts = urlsplit(WEBAPP_URL)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != "api"]
    query.append(("api", SELF_URL.rstrip("/")))
    app_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    kb = [[InlineKeyboardButton(
        "🗺 создать маршрут",
        web_app=WebAppInfo(url=app_url),
    )]]
    await update.effective_message.reply_text(
        "привет!\n\n"
        "я собираю маршруты по москве из личной карты канала — "
        "612 проверенных мест: кофе, бары, галереи, парки, театры и не только.\n\n"
        "нажми кнопку ниже ✦",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start — открыть генератор маршрутов\n\nканал: @qaroutes"
    )


async def prepare_subscription_api(app):
    global CHECK_APP, CHECK_LOOP
    CHECK_APP = app
    CHECK_LOOP = asyncio.get_running_loop()


def build_application():
    # Отправка ответа ждёт сеть: другие команды в это время обрабатываются.
    # Лимитер ограничивает исходящие запросы и повторяет их после RetryAfter.
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .concurrent_updates(8)
        .connection_pool_size(16)
        .pool_timeout(10)
        .post_init(prepare_subscription_api)
        .rate_limiter(AIORateLimiter(overall_max_rate=25, max_retries=3))
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(start, pattern="^check_subscription$"))
    return app


if __name__ == "__main__":
    app = build_application()
    log.info("bot started, polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
