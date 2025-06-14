import os
import json
import logging
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
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

# Token бота из переменных окружения
TOKEN = os.getenv("BOT_TOKEN")

# Состояния разговора
STATE_LEVEL, STATE_TOPIC, STATE_QUIZ = range(3)

# Поддерживаемые уровни
LEVELS = ["A1", "A2", "B1", "B2"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие и инструкция."""
    await update.message.reply_text(
        "👋 Привет! Я — тренажёр по итальянскому.\n"
        "Напиши /quiz, чтобы начать и выбрать уровень."
    )

async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запуск выбора уровня."""
    keyboard = [
        [InlineKeyboardButton(level, callback_data=f"level|{level}")]
        for level in LEVELS
    ]
    await update.message.reply_text(
        "Выберите ваш уровень:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return STATE_LEVEL

async def on_level_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора уровня; показывает темы этого уровня."""
    query = update.callback_query
    await query.answer()
    _, level = query.data.split("|", 1)
    context.user_data["level"] = level
    folder = os.path.join("content", level)
    if not os.path.exists(folder):
        await query.edit_message_text(f"❌ Для уровня {level} не найдено упражнений.")
        return ConversationHandler.END

    files = sorted(f for f in os.listdir(folder) if f.endswith(".json"))
    if not files:
        await query.edit_message_text(f"❌ Для уровня {level} нет тем.")
        return ConversationHandler.END

    keyboard = []
    for fname in files:
        key = fname[:-5]  # убрать .json
        try:
            with open(os.path.join(folder, fname), encoding="utf-8") as f:
                data = json.load(f)
            name = data.get("topic_name", key)
            keyboard.append([InlineKeyboardButton(name, callback_data=f"topic|{key}")])
        except Exception as e:
            logging.error(f"Ошибка при загрузке файла {fname}: {e}")
            continue

    if not keyboard:
        await query.edit_message_text(f"❌ Не удалось загрузить темы для уровня {level}.")
        return ConversationHandler.END

    await query.edit_message_text(
        f"Уровень *{level}* выбран.\nТеперь выберите тему:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return STATE_TOPIC

async def on_topic_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора темы; загружает упражнения и задаёт первый вопрос."""
    query = update.callback_query
    await query.answer()
    topic_key = query.data.split("|", 1)[1]
    level = context.user_data["level"]
    path = os.path.join("content", level, f"{level}_{topic_key}.json")
    if not os.path.exists(path):
        await query.edit_message_text("❌ Не удалось найти файл с упражнениями для выбранной темы.")
        return ConversationHandler.END

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logging.error(f"Ошибка при загрузке файла {path}: {e}")
        await query.edit_message_text("❌ Ошибка при загрузке упражнений.")
        return ConversationHandler.END

    exercises = data.get("exercises", [])
    if not exercises:
        await query.edit_message_text("❌ В этой теме пока нет упражнений.")
        return ConversationHandler.END

    context.user_data["exercises"] = exercises
    context.user_data["topic_name"] = data.get("topic_name", topic_key)
    context.user_data["index"] = 0
    await query.edit_message_text(
        f"Тема *{context.user_data['topic_name']}* выбрана. Начинаем викторину!",
        parse_mode="Markdown"
    )
    return await send_question(update, context, from_callback=True)

async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    """Отправляет очередное упражнение."""
    idx = context.user_data.get("index", 0)
    ex_list = context.user_data.get("exercises", [])
    if idx >= len(ex_list):
        await _reply(update, context, "🎉 Все упражнения пройдены! Напиши /quiz, чтобы выбрать новый уровень.")
        return ConversationHandler.END

    ex = ex_list[idx]
    kb = ReplyKeyboardMarkup([[opt] for opt in ex.get("options", [])], resize_keyboard=True, one_time_keyboard=True)
    await _reply(update, context, f"🔢 Упражнение {idx+1}:\n{ex.get('question', 'Нет вопроса')}", reply_markup=kb)
    return STATE_QUIZ

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверяет ответ и переходит к следующему вопросу."""
    idx = context.user_data.get("index", 0)
    ex_list = context.user_data.get("exercises", [])
    if idx >= len(ex_list):
        await update.message.reply_text("Все упражнения уже завершены. Напиши /quiz, чтобы начать сначала.")
        return ConversationHandler.END
    ex = ex_list[idx]
    user_ans = update.message.text.strip()
    right_ans = ex.get("answer", "")
    if user_ans.lower() == right_ans.lower():
        await update.message.reply_text(f"✅ Верно!\n{ex.get('explanation', '')}")
    else:
        await update.message.reply_text(f"❌ Неверно.\nПравильно: {right_ans}\n{ex.get('explanation', '')}")
    context.user_data["index"] = idx + 1
    return await send_question(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Прерывает викторину."""
    await update.message.reply_text("❌ Викторина отменена. Напиши /quiz, чтобы начать заново.")
    return ConversationHandler.END

# Утилита: универсальный ответ в зависимости от типа update
async def _reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, **kwargs):
    if hasattr(update, "callback_query") and update.callback_query:
        await update.callback_query.message.reply_text(text, **kwargs)
    elif hasattr(update, "message") and update.message:
        await update.message.reply_text(text, **kwargs)

def main():
    import telegram
    logging.info(f"PTB version: {telegram.__version__}")

    if not TOKEN:
        logging.error("❌ BOT_TOKEN не найден в окружении.")
        return

    app = ApplicationBuilder().token(TOKEN).build()

    # ConversationHandler для /quiz → выбор уровня → выбор темы → ответы
    conv = ConversationHandler(
        entry_points=[CommandHandler("quiz", quiz)],
        states={
            STATE_LEVEL: [CallbackQueryHandler(on_level_select, pattern=r"^level\|")],
            STATE_TOPIC: [CallbackQueryHandler(on_topic_select, pattern=r"^topic\|")],
            STATE_QUIZ: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)

    logging.info("✅ Бот запущен, ожидает команд.")
    import asyncio

async def async_main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    await app.bot.delete_webhook(drop_pending_updates=True)
    app.run_polling()

if __name__ == "__main__":
    asyncio.run(async_main())
