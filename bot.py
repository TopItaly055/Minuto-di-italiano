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

# Токен бота из переменных окружения
TOKEN = os.getenv("BOT_TOKEN")

# Состояния разговора
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
    """Обработчик выбора уровня; показывает темы этого уровня."""
    query = update.callback_query
    await query.answer()
    _, level = query.data.split("|", 1)
    context.user_data["level"] = level
    # Считываем JSON-файлы из папки content/<level>/
    folder = os.path.join("content", level)
    files = sorted(f for f in os.listdir(folder) if f.endswith(".json"))
    keyboard = []
    for fname in files:
        key = fname[:-5]  # убрать .json
        data = json.load(open(os.path.join(folder, fname), encoding="utf-8"))
        name = data.get("topic_name", key)
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
    # Загрузить все упражнения в память
    path = os.path.join("content", level, f"{level}_{topic_key}.json")
    data = json.load(open(path, encoding="utf-8"))
    context.user_data["exercises"] = data["exercises"]
    context.user_data["topic_name"] = data["topic_name"]
    context.user_data["index"] = 0
    await query.edit_message_text(f"Тема *{data['topic_name']}* выбрана. Начинаем викторину!", parse_mode="Markdown")
    return await send_question(update, context)

async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет очередное упражнение."""
    idx = context.user_data["index"]
    ex_list = context.user_data["exercises"]
    if idx >= len(ex_list):
        # конец викторины
        await _reply(update, context, "🎉 Все упражнения пройдены! Напиши /quiz, чтобы выбрать новый уровень.")
        return ConversationHandler.END

    ex = ex_list[idx]
    kb = ReplyKeyboardMarkup([[opt] for opt in ex["options"]], resize_keyboard=True, one_time_keyboard=True)
    await _reply(update, context, f"🔢 Упражнение {idx+1}:\n{ex['question']}", reply_markup=kb)
    return STATE_QUIZ

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверяет ответ и переходит к следующему вопросу."""
    idx = context.user_data["index"]
    ex = context.user_data["exercises"][idx]
    user_ans = update.message.text.strip()
    if user_ans == ex["answer"]:
        await update.message.reply_text(f"✅ Верно!\n{ex['explanation']}")
    else:
        await update.message.reply_text(f"❌ Неверно.\nПравильно: {ex['answer']}\n{ex['explanation']}")
    context.user_data["index"] += 1
    return await send_question(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Прерывает викторину."""
    await update.message.reply_text("❌ Викторина отменена. Напиши /quiz, чтобы начать заново.")
    return ConversationHandler.END

# Утилита: ответ в зависимости от update типа
async def _reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, **kwargs):
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
    app.run_polling()

if __name__ == "__main__":
    main()
