import os
import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters
)

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Получаем токен из переменных окружения
TOKEN = os.getenv("BOT_TOKEN")

# Состояния
QUIZ = 1

# Примеры упражнений по артиклям
exercises = [
    {
        "question": "___ zaino è pesante.",
        "options": ["Il", "Lo", "La"],
        "answer": "Lo",
        "explanation": "‘Zaino’ начинается с ‘z’ — используется артикль ‘Lo’."
    },
    {
        "question": "___ penna è blu.",
        "options": ["Il", "La", "Lo"],
        "answer": "La",
        "explanation": "‘Penna’ — ж.р., ед.ч. → La."
    },
    {
        "question": "___ libro è interessante.",
        "options": ["Lo", "La", "Il"],
        "answer": "Il",
        "explanation": "‘Libro’ — м.р., обычное слово → Il."
    }
]

# Хранение индекса для каждого пользователя
user_data = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Это тренажёр по итальянским артиклям."
Напиши /quiz, чтобы начать."
    )

async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id] = {"index": 0}
    return await send_question(update, context)

async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    index = user_data[user_id]["index"]

    if index >= len(exercises):
        await update.message.reply_text("Все упражнения завершены. Напиши /quiz, чтобы начать снова.")
        return ConversationHandler.END

    ex = exercises[index]
    keyboard = ReplyKeyboardMarkup([[opt] for opt in ex["options"]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(f"Заполни пропуск:\n{ex['question']}", reply_markup=keyboard)
    return QUIZ

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    index = user_data[user_id]["index"]
    ex = exercises[index]
    user_answer = update.message.text.strip()

    if user_answer == ex["answer"]:
        await update.message.reply_text(f"✅ Верно!\n{ex['explanation']}")
    else:
        await update.message.reply_text(f"❌ Неверно. Правильный ответ: {ex['answer']}\n{ex['explanation']}")

    user_data[user_id]["index"] += 1
    return await send_question(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выход из режима викторины. Напиши /quiz, чтобы начать снова.")
    return ConversationHandler.END

def main():
    if not TOKEN:
        print("❌ BOT_TOKEN не найден. Убедись, что переменная окружения установлена.")
        return

    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("quiz", quiz)],
        states={QUIZ: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)

    print("✅ Бот запущен. Ожидаем команды в Telegram...")
    app.run_polling()

if __name__ == "__main__":
    main()
