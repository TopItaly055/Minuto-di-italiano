import os
import logging
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.getenv("BOT_TOKEN")

# Состояния ConversationHandler
CHOOSE_TOPIC, QUIZ = range(2)

# Темы и упражнения
TOPICS = {
    "Артикли": [
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
    ],
    "Множественное число": [
        {
            "question": "Каково множественное число слова 'ragazzo'?",
            "options": ["ragazzi", "ragazze", "ragazza"],
            "answer": "ragazzi",
            "explanation": "‘Ragazzo’ → ‘ragazzi’ (мужской род, окончание -o меняется на -i)."
        },
        {
            "question": "Каково множественное число слова 'amica'?",
            "options": ["amici", "amiche", "amicas"],
            "answer": "amiche",
            "explanation": "‘Amica’ → ‘amiche’ (женский род, окончание -a меняется на -e, c → ch перед e)."
        }
    ]
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Это тренажёр по итальянскому языку.\nНапиши /quiz, чтобы выбрать тему."
    )

async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(topic, callback_data=f"topic|{topic}")]
        for topic in TOPICS
    ]
    await update.message.reply_text(
        "Выберите тему:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSE_TOPIC

async def on_topic_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    topic = query.data.split('|')[1]
    context.user_data["topic"] = topic
    context.user_data["index"] = 0
    await query.edit_message_text(f"Тема выбрана: {topic}\nНачнем викторину!")
    return await send_question(update, context, query_message=True)

async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE, query_message=False):
    topic = context.user_data.get("topic")
    index = context.user_data.get("index", 0)
    exercises = TOPICS[topic]
    if index >= len(exercises):
        if query_message:
            await update.callback_query.message.reply_text("Все упражнения завершены. Напиши /quiz, чтобы выбрать новую тему.")
        else:
            await update.message.reply_text("Все упражнения завершены. Напиши /quiz, чтобы выбрать новую тему.")
        return ConversationHandler.END

    ex = exercises[index]
    keyboard = ReplyKeyboardMarkup([[opt] for opt in ex["options"]], resize_keyboard=True, one_time_keyboard=True)
    if query_message:
        await update.callback_query.message.reply_text(f"Заполни пропуск:\n{ex['question']}", reply_markup=keyboard)
    else:
        await update.message.reply_text(f"Заполни пропуск:\n{ex['question']}", reply_markup=keyboard)
    return QUIZ

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = context.user_data.get("topic")
    index = context.user_data.get("index", 0)
    exercises = TOPICS[topic]
    ex = exercises[index]
    user_answer = update.message.text.strip()

    if user_answer == ex["answer"]:
        await update.message.reply_text(f"✅ Верно!\n{ex['explanation']}")
    else:
        await update.message.reply_text(f"❌ Неверно. Правильный ответ: {ex['answer']}\n{ex['explanation']}")

    context.user_data["index"] = index + 1
    return await send_question(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выход из режима викторины. Напиши /quiz, чтобы начать снова.")
    return ConversationHandler.END

def main():
    import telegram
    print("PTB version:", telegram.__version__)
    if not TOKEN:
        print("❌ BOT_TOKEN не найден.")
        return

    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("quiz", quiz)],
        states={
            CHOOSE_TOPIC: [CallbackQueryHandler(on_topic_select, pattern=r"^topic\|")],
            QUIZ: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    print("✅ Бот запущен. Ожидаем команды в Telegram...")
    app.run_polling()

if __name__ == "__main__":
    main()
    
