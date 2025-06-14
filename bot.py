import os
import json
import logging
from telegram import (
    Bot,
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
#           Конфигурация логирования
# ——————————————————————————————————————————————
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# Токен бота из переменных окружения
TOKEN = os.getenv("BOT_TOKEN")

# Состояния ConversationHandler
STATE_LEVEL, STATE_TOPIC, STATE_QUIZ = range(3)

# Поддерживаемые уровни
LEVELS = ["A1", "A2", "B1", "B2"]

# ——————————————————————————————————————————————
#           Хэндлеры
# ——————————————————————————————————————————————

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие и инструкция."""
    await update.message.reply_text(
        "👋 Привет! Я — тренажёр по итальянскому.\n"
        "Напиши /quiz, чтобы начать и выбрать уровень."
    )

async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запуск выбора уровня."""
    buttons = [[InlineKeyboardButton(lvl, callback_data=f"level|{lvl}")] for lvl in LEVELS]
    await update.message.reply_text(
        "Выберите уровень:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return STATE_LEVEL

async def on_level_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показываем темы выбранного уровня."""
    query = update.callback_query
    await query.answer()
    _, level = query.data.split("|", 1)
    context.user_data["level"] = level

    folder = os.path.join("content", level)
    if not os.path.isdir(folder):
        await query.edit_message_text(f"❌ Нет папки content/{level} с упражнениями.")
        return STATE_LEVEL

    files = sorted(f for f in os.listdir(folder) if f.endswith(".json"))
    if not files:
        await query.edit_message_text(f"❌ В папке content/{level} нет JSON-файлов.")
        return STATE_LEVEL

    buttons = []
    for fname in files:
        path = os.path.join(folder, fname)
        try:
            data = json.load(open(path, encoding="utf-8"))
            name = data.get("topic_name", fname[:-5])
        except Exception as e:
            logging.error(f"Не смог загрузить {path}: {e}")
            continue
        buttons.append([InlineKeyboardButton(name, callback_data=f"topic|{fname}")])

    if not buttons:
        await query.edit_message_text("❌ Не удалось найти ни одной корректной темы.")
        return STATE_LEVEL

    await query.edit_message_text(
        f"Уровень *{level}* выбран.\nВыберите тему:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return STATE_TOPIC

async def on_topic_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Загружаем упражнения и показываем первое."""
    query = update.callback_query
    await query.answer()
    topic_file = query.data.split("|", 1)[1]
    level = context.user_data.get("level")
    path = os.path.join("content", level, topic_file)

    try:
        data = json.load(open(path, encoding="utf-8"))
    except FileNotFoundError:
        await query.edit_message_text("❌ Файл тем не найден — выберите другую тему.")
        return STATE_TOPIC
    except Exception as e:
        logging.error(f"Ошибка при чтении {path}: {e}")
        await query.edit_message_text("❌ Ошибка при загрузке упражнений.")
        return STATE_TOPIC

    exercises = data.get("exercises")
    if not isinstance(exercises, list) or not exercises:
        await query.edit_message_text("❌ В этой теме нет упражнений.")
        return STATE_TOPIC

    context.user_data.update({
        "topic_name": data.get("topic_name", topic_file[:-5]),
        "exercises": exercises,
        "index": 0,
    })
    await query.edit_message_text(
        f"Тема *{context.user_data['topic_name']}* выбрана. Поехали!",
        parse_mode="Markdown",
    )
    return await send_question(update, context)

async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляем текущее упражнение."""
    idx = context.user_data.get("index", 0)
    exercises = context.user_data.get("exercises", [])
    if idx >= len(exercises):
        return await _reply(update, "🎉 Все упражнения пройдены! Напиши /quiz чтобы начать заново.")

    ex = exercises[idx]
    question = ex.get("question", "Вопрос отсутствует.")
    options = ex.get("options", [])
    kb = ReplyKeyboardMarkup([[opt] for opt in options], resize_keyboard=True, one_time_keyboard=True)

    return await _reply(update, f"🔢 Упражнение {idx+1}:\n{question}", reply_markup=kb)

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатываем ответ и идем дальше."""
    idx = context.user_data.get("index", 0)
    exercises = context.user_data.get("exercises", [])
    if idx >= len(exercises):
        return await _reply(update, "Упражнения закончились. Напиши /quiz чтобы начать снова.")

    ex = exercises[idx]
    user_ans = update.message.text.strip()
    correct = ex.get("answer", "")

    if user_ans.lower() == correct.lower():
        await update.message.reply_text(f"✅ Верно!\n{ex.get('explanation','')}")
    else:
        await update.message.reply_text(
            f"❌ Неверно.\nПравильный ответ: {correct}\n{ex.get('explanation','')}"
        )

    context.user_data["index"] = idx + 1
    return await send_question(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Викторина отменена. Напиши /quiz чтобы начать заново.")
    return ConversationHandler.END

async def _reply(update: Update, text: str, **kwargs):
    if update.callback_query:
        await update.callback_query.message.reply_text(text, **kwargs)
    else:
        await update.message.reply_text(text, **kwargs)

# ——————————————————————————————————————————————
#           Точка входа
# ——————————————————————————————————————————————

def main():
    if not TOKEN:
        logging.error("❌ BOT_TOKEN не найден в окружении.")
        return

    # 1) удаляем старый webhook и очищаем очередь
    bot = Bot(token=TOKEN)
    bot.delete_webhook(drop_pending_updates=True)
    logging.info("🔄 Webhook удалён и старые обновления сброшены.")

    # 2) создаём приложение
    app = ApplicationBuilder().token(TOKEN).build()

    # 3) настраиваем ConversationHandler
    conv = ConversationHandler(
        entry_points=[CommandHandler("quiz", quiz)],
        states={
            STATE_LEVEL: [CallbackQueryHandler(on_level_select, pattern=r"^level\|")],
            STATE_TOPIC: [CallbackQueryHandler(on_topic_select, pattern=r"^topic\|")],
            STATE_QUIZ:   [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)

    logging.info("✅ Бот запущен. Ожидает команд.")
    # 4) запускаем polling, сбрасывая pending updates
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
