import os
import json
import logging
import asyncio
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
#           Логирование
# ——————————————————————————————————————————————
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# ——————————————————————————————————————————————
#           Константы и локализация
# ——————————————————————————————————————————————
TOKEN = os.getenv("BOT_TOKEN")

STATE_LEVEL, STATE_TOPIC, STATE_QUIZ = range(3)
LEVELS = ["A1", "A2", "B1", "B2"]

MESSAGES = {
    "start": {
        "ru": "👋 Привет! Я — тренажёр по итальянскому.\nНапиши /quiz, чтобы начать и выбрать уровень.",
        "en": "👋 Hi! I'm your Italian practice bot.\nType /quiz to start and select your level.",
    },
    "choose_level": {
        "ru": "Выберите уровень:",
        "en": "Choose your level:",
    },
    "no_exercises": {
        "ru": "❌ Нет упражнений для уровня {level}.",
        "en": "❌ No exercises found for level {level}.",
    },
    "no_valid_topics": {
        "ru": "❌ Для уровня {level} нет корректных тем.",
        "en": "❌ No valid topics for level {level}.",
    },
    "choose_topic": {
        "ru": "📂 Уровень *{level}* выбран.\nВыберите тему:",
        "en": "📂 Level *{level}* selected.\nChoose a topic:",
    },
    "topic_error": {
        "ru": "❌ Ошибка при загрузке упражнений.",
        "en": "❌ Error loading exercises.",
    },
    "topic_empty": {
        "ru": "❌ Упражнения пусты.",
        "en": "❌ No exercises in this topic.",
    },
    "topic_selected": {
        "ru": "🚀 Тема *{topic}* выбрана!",
        "en": "🚀 Topic *{topic}* selected!",
    },
    "quiz_complete": {
        "ru": "🎉 Все упражнения пройдены! Напиши /quiz чтобы начать заново.",
        "en": "🎉 All exercises completed! Type /quiz to start again.",
    },
    "cancel": {
        "ru": "❌ Викторина отменена. Напиши /quiz чтобы начать заново.",
        "en": "❌ Quiz cancelled. Type /quiz to start again.",
    },
    "correct": {
        "ru": "✅ Верно!\n{explanation}",
        "en": "✅ Correct!\n{explanation}",
    },
    "incorrect": {
        "ru": "❌ Неверно.\nПравильный ответ: {answer}\n{explanation}",
        "en": "❌ Incorrect.\nCorrect answer: {answer}\n{explanation}",
    },
    "question": {
        "ru": "❓ Упражнение {num}:\n{question}",
        "en": "❓ Exercise {num}:\n{question}",
    },
    "token_error": {
        "ru": "❌ BOT_TOKEN не задан.",
        "en": "❌ BOT_TOKEN is not set.",
    },
    "file_error": {
        "ru": "❌ Не удалось загрузить файл {file}: {error}",
        "en": "❌ Could not load file {file}: {error}",
    }
}

def get_user_lang(context):
    # Можно расширить чтобы пользователь выбирал язык, пока только ru/en
    return context.user_data.get("lang", "ru")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context)
    await update.message.reply_text(MESSAGES["start"][lang])

async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context)
    kb = [[InlineKeyboardButton(lvl, callback_data=f"level|{lvl}")] for lvl in LEVELS]
    await update.message.reply_text(MESSAGES["choose_level"][lang], reply_markup=InlineKeyboardMarkup(kb))
    return STATE_LEVEL

async def on_level_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(context)
    query = update.callback_query
    await query.answer()
    level = query.data.split("|", 1)[1]
    context.user_data["level"] = level

    folder = os.path.join("content", level)
    if not os.path.isdir(folder):
        await query.edit_message_text(MESSAGES["no_exercises"][lang].format(level=level))
        return STATE_LEVEL

    files = sorted(f for f in os.listdir(folder) if f.endswith(".json"))
    kb = []
    for fn in files:
        try:
            with open(os.path.join(folder, fn), encoding="utf-8") as f:
                data = json.load(f)
            name = data.get("topic_name", fn[:-5])
        except Exception as e:
            logging.error(MESSAGES["file_error"][lang].format

