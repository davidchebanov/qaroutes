import os, logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

BOT_TOKEN  = os.environ["BOT_TOKEN"]
WEBAPP_URL = os.environ["WEBAPP_URL"]
CHANNEL    = "@qaroutes"

async def is_subscribed(bot, user_id):
    try:
        m = await bot.get_chat_member(CHANNEL, user_id)
        return m.status in ("member", "administrator", "creator")
    except Exception as e:
        logging.warning(f"Subscription check failed: {e}")
        return False

async def show_gate(update, context):
    kb = [
        [InlineKeyboardButton("📍 подписаться на канал", url="https://t.me/qaroutes")],
        [InlineKeyboardButton("✓ уже подписан", callback_data="check")],
    ]
    text = (
        "привет\!\n\n"
        "этот бот строит маршруты по москве на основе личной карты канала *мои маршруты*\.\n\n"
        "чтобы открыть — подпишись на канал 👇"
    )
    if update.message:
        await update.message.reply_text(
            text, parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(kb)
        )
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(kb)
        )

async def show_app(update, context):
    kb = [[InlineKeyboardButton(
        "🗺 создать маршрут",
        web_app=WebAppInfo(url=WEBAPP_URL)
    )]]
    text = "всё готово — нажми кнопку и составляй маршрут ✦"
    if update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_subscribed(context.bot, update.effective_user.id):
        await show_app(update, context)
    else:
        await show_gate(update, context)

async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    if await is_subscribed(context.bot, update.callback_query.from_user.id):
        await show_app(update, context)
    else:
        await update.callback_query.answer(
            "не вижу подписки — подпишись и нажми снова 🙁",
            show_alert=True
        )

if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(check, pattern="^check$"))
    app.run_polling(allowed_updates=Update.ALL_TYPES)
