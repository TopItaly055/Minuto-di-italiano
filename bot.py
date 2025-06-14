import os
import json
import logging
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# ——————————————————————————————————————————————
#           Логирование
# ——————————————————————————————————————————————
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

TOKEN = os.getenv("BOT_TOKEN")
STATE_LEVEL, STATE_TOPIC, STATE_QUIZ = range(3)
LEVELS = ["A1", "A2", "B1", "B2"]

# ——————————————————————————————————————————————
#           Хэндлеры
# ——————————————————————————————————————————————

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я — итальянский тренажёр.\n"
        "Напиши /quiz, чтобы выбрать уровень и тему."
    )

async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton(l, callback_data=f"level|{l}")] for l in LEVELS]
    await update.message.reply_text(
        "Выберите уровень:",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return STATE_LEVEL

async def on_level_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    level = query.data.split("|",1)[1]
    context.user_data["level"] = level

    folder = os.path.join("content", level)
    if not os.path.isdir(folder):
        await query.edit_message_text(f"❌ Нет упражнений для уровня {level}.")
        return STATE_LEVEL

    files = [f for f in sorted(os.listdir(folder)) if f.endswith(".json")]
    if not files:
        await query.edit_message_text(f"❌ Нет тем в {folder}.")
        return STATE_LEVEL

    kb = []
    for fn in files:
        path = os.path.join(folder, fn)
        try:
            data = json.load(open(path, encoding="utf-8"))
            name = data.get("topic_name", fn[:-5])
        except Exception:
            continue
        kb.append([InlineKeyboardButton(name, callback_data=f"topic|{fn}")])

    await query.edit_message_text(
        f"📂 Уровень *{level}* выбран.\nВыберите тему:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return STATE_TOPIC

async def on_topic_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    topic_file = query.data.split("|",1)[1]
    level = context.user_data.get("level")
    path = os.path.join("content", level, topic_file)

    try:
        data = json.load(open(path, encoding="utf-8"))
        exercises = data.get("exercises", [])
    except Exception:
        await query.edit_message_text("❌ Не удалось загрузить упражнения.")
        return STATE_TOPIC

    if not exercises:
        await query.edit_message_text("❌ В этой теме нет упражнений.")
        return STATE_TOPIC

    context.user_data.update({
        "topic_name": data.get("topic_name", topic_file[:-5]),
        "exercises": exercises,
        "index": 0,
    })
    await query.edit_message_text(
        f"🚀 Тема *{context.user_data['topic_name']}* выбрана!",
        parse_mode="Markdown",
    )
    return await send_question(update, context)

async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data["index"]
    exercises = context.user_data["exercises"]
    if idx >= len(exercises):
        return await _reply(update, "🎉 Все упражнения пройдены! Напиши /quiz чтобы начать заново.")

    ex = exercises[idx]
    kb = ReplyKeyboardMarkup([[opt] for opt in ex.get("options",[])],
                             resize_keyboard=True, one_time_keyboard=True)
    return await _reply(update,
        f"❓ Упражнение {idx+1}:\n{ex.get('question','')}",
        reply_markup=kb
    )

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data["index"]
    exercises = context.user_data["exercises"]
    ex = exercises[idx]

    user = update.message.text.strip()
    correct = ex.get("answer","")
    if user.lower() == correct.lower():
        await update.message.reply_text(f"✅ Верно!\n{ex.get('explanation','')}")
    else:
        await update.message.reply_text(f"❌ Неверно.\nПравильно: {correct}\n{ex.get('explanation','')}")
    context.user_data["index"] += 1
    return await send_question(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Викторина отменена. Напиши /quiz чтобы начать заново.")
    return ConversationHandler.END

async def _reply(update: Update, text: str, **kw):
    if update.callback_query:
        await update.callback_query.message.reply_text(text, **kw)
    else:
        await update.message.reply_text(text, **kw)

# ——————————————————————————————————————————————
#           Main
# ——————————————————————————————————————————————

def main():
    if not TOKEN:
        logging.error("❌ BOT_TOKEN не задан.")
        return

    app = ApplicationBuilder().token(TOKEN).build()
    # удаляем старые webhooks и pending updates
    app.bot.delete_webhook(drop_pending_updates=True)
    logging.info("🔄 Webhook удалён, очередь сброшена.")

    conv = ConversationHandler(
        entry_points=[CommandHandler("quiz", quiz)],
        states={
            STATE_LEVEL: [CallbackQueryHandler(on_level_select, pattern="^level\\|")],
            STATE_TOPIC: [CallbackQueryHandler(on_topic_select, pattern="^topic\\|")],
            STATE_QUIZ:  [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)

    logging.info("✅ Бот запущен, ожидаем команд.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
