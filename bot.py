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
    """Обработчик выбора уровня; показывает доступные темы."""
    query = update.callback_query
    await query.answer()
    _, level = query.data.split("|", 1)
    context.user_data["level"] = level

    folder = os.path.join("content", level)
    if not os.path.isdir(folder):
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
            data = json.load(open(os.path.join(folder, fname), encoding="utf-8"))
            name = data.get("topic_name", key)
        except Exception as e:
            logging.error(f"Ошибка загрузки {fname}: {e}")
            continue
        keyboard.append([InlineKeyboardButton(name, callback_data=f"topic|{key}")])

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

    if not os.path.isfile(path):
        await query.edit_message_text("❌ Файл с упражнениями не найден.")
        return ConversationHandler.END

    try:
        data = json.load(open(path, encoding="utf-8"))
        exercises = data.get("exercises", [])
        topic_name = data.get("topic_name", topic_key)
    except Exception as e:
        logging.error(f"Ошибка загрузки {path}: {e}")
        await query.edit_message_text("❌ Ошибка при загрузке упражнений.")
        return ConversationHandler.END

    if not exercises:
        await query.edit_message_text("❌ Упражнения в этой теме отсутствуют.")
        return ConversationHandler.END

    context.user_data.update({
        "exercises": exercises,
        "topic_name": topic_name,
        "index": 0,
    })
    await query.edit_message_text(
        f"Тема *{topic_name}* выбрана. Начинаем викторину!",
        parse_mode="Markdown",
    )
    return await send_question(update, context)

async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет текущее упражнение."""
    idx = context.user_data["index"]
    exercises = context.user_data["exercises"]
    if idx >= len(exercises):
        return await _reply(update, "🎉 Все упражнения пройдены! Напиши /quiz для нового уровня.")

    ex = exercises[idx]
    kb = ReplyKeyboardMarkup([[opt] for opt in ex.get("options", [])],
                             resize_keyboard=True, one_time_keyboard=True)
    return await _reply(update,
        f"🔢 Упражнение {idx+1}:\n{ex.get('question','')}",
        reply_markup=kb
    )

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверяет ответ и переходит к следующему упражнению."""
    idx = context.user_data["index"]
    exercises = context.user_data["exercises"]
    ex = exercises[idx]
    user_ans = update.message.text.strip()
    correct = ex.get("answer","")

    if user_ans.lower() == correct.lower():
        await update.message.reply_text(f"✅ Верно!\n{ex.get('explanation','')}")
    else:
        await update.message.reply_text(
            f"❌ Неверно.\nПравильно: {correct}\n{ex.get('explanation','')}"
        )

    context.user_data["index"] = idx + 1
    return await send_question(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена викторины."""
    await update.message.reply_text("❌ Викторина отменена. Напиши /quiz для перезапуска.")
    return ConversationHandler.END

async def _reply(update: Update, text: str, **kwargs):
    """Универсальный ответ: из callback_query или из message."""
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

    app = ApplicationBuilder().token(TOKEN).build()

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

    logging.info("✅ Бот запущен. Ожидает команд.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
