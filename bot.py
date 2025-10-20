import os
import json
import logging
from typing import Any, Dict, List

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.constants import ParseMode
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
#                  ЛОГИРОВАНИЕ
# ——————————————————————————————————————————————
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("gram-bot")

# ——————————————————————————————————————————————
#                  КОНСТАНТЫ
# ——————————————————————————————————————————————
TOKEN = os.getenv("BOT_TOKEN")
CONTENT_DIR = "content"
LEVELS = ["A1", "A2", "B1", "B2"]

STATE_LEVEL, STATE_TOPIC, STATE_QUIZ = range(3)

# ——————————————————————————————————————————————
#           ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ——————————————————————————————————————————————
async def _reply(update: Update, text: str, **kw):
    """Универсальный ответ (поддерживает callback и обычное сообщение)."""
    if update.callback_query:
        await update.callback_query.message.reply_text(text, **kw)
    elif update.message:
        await update.message.reply_text(text, **kw)


def _safe_get(d: Dict[str, Any], key: str, default: Any = "") -> Any:
    return d.get(key, default)


# ——————————————————————————————————————————————
#                  ХЕНДЛЕРЫ
# ——————————————————————————————————————————————
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _reply(
        update,
        "👋 Привет! Я — тренажёр по итальянскому языку.\n"
        "Напиши /quiz, чтобы выбрать уровень и начать тренировку.",
    )


async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton(lvl, callback_data=f"level|{lvl}")] for lvl in LEVELS]

    await _reply(update, "Выберите уровень:", reply_markup=InlineKeyboardMarkup(kb))

    return STATE_LEVEL


async def on_level_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not query.data or "|" not in query.data:
        await query.edit_message_text("⚠️ Некорректные данные. Напиши /quiz заново.")
        return ConversationHandler.END

    _, level = query.data.split("|", 1)
    context.user_data["level"] = level

    folder = os.path.join(CONTENT_DIR, level)
    if not os.path.isdir(folder):
        await query.edit_message_text(f"❌ Нет упражнений для уровня {level}.")
        return STATE_LEVEL

    files = sorted(f for f in os.listdir(folder) if f.endswith(".json"))
    kb: List[List[InlineKeyboardButton]] = []

    for fn in files:
        try:
            with open(os.path.join(folder, fn), encoding="utf-8") as f:
                topic = json.load(f)
            name = _safe_get(topic, "topic_name", fn[:-5])
        except Exception as e:
            log.warning("Ошибка чтения темы %s: %s", fn, e)
            continue
        kb.append([InlineKeyboardButton(name, callback_data=f"topic|{fn}")])

    if not kb:
        await query.edit_message_text(f"❌ Для уровня {level} нет корректных тем.")
        return STATE_LEVEL

    await query.edit_message_text(
        f"📂 Уровень *{level}* выбран.\nВыберите тему:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return STATE_TOPIC


async def on_topic_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not query.data or "|" not in query.data:
        await query.edit_message_text("⚠️ Некорректные данные. Напиши /quiz.")
        return ConversationHandler.END

    _, fn = query.data.split("|", 1)
    level = context.user_data.get("level")

    if not level:
        await query.edit_message_text("⚠️ Сессия сброшена. Напиши /quiz заново.")
        return ConversationHandler.END

    path = os.path.join(CONTENT_DIR, level, fn)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        exercises: List[Dict[str, Any]] = data.get("exercises", [])
        topic_name = _safe_get(data, "topic_name", fn[:-5])
    except Exception as e:
        log.exception("Ошибка загрузки %s: %s", path, e)
        await query.edit_message_text("❌ Ошибка при загрузке упражнений.")
        return STATE_TOPIC

    if not exercises:
        await query.edit_message_text("❌ Упражнения пусты.")
        return STATE_TOPIC

    context.user_data.update(
        {"topic_name": topic_name, "exercises": exercises, "index": 0}
    )

    await query.edit_message_text(
        f"🚀 Тема *{topic_name}* выбрана!", parse_mode=ParseMode.MARKDOWN
    )

    # Переход к вопросам
    return await send_question(update, context)


async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = int(context.user_data.get("index", 0))
    exercises: List[Dict[str, Any]] = context.user_data.get("exercises", [])

    if not exercises:
        await _reply(update, "⚠️ Нет упражнений. Напиши /quiz.")
        return ConversationHandler.END

    if idx >= len(exercises):
        await _reply(
            update,
            "🎉 Все упражнения завершены! Напиши /quiz, чтобы начать заново.",
            reply_markup=ReplyKeyboardRemove(),
        )
        for k in ("exercises", "index", "topic_name"):
            context.user_data.pop(k, None)
        return ConversationHandler.END

    ex = exercises[idx]
    question = _safe_get(ex, "question", "—")
    options: List[str] = ex.get("options", [])

    if not options:
        log.warning("Пустые options у задания #%s, пропускаю", idx)
        context.user_data["index"] = idx + 1
        return await send_question(update, context)

    kb = ReplyKeyboardMarkup(
        [[opt] for opt in options], resize_keyboard=True, one_time_keyboard=True
    )
    await _reply(update, f"❓ Упражнение {idx + 1}:\n{question}", reply_markup=kb)
    return STATE_QUIZ


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    idx = int(context.user_data.get("index", 0))
    exercises: List[Dict[str, Any]] = context.user_data.get("exercises", [])

    if not exercises or idx >= len(exercises):
        await update.message.reply_text("⚠️ Сессия викторины неактивна. Напиши /quiz.")
        return ConversationHandler.END

    ex = exercises[idx]
    correct = str(_safe_get(ex, "answer", "")).strip()
    explanation = _safe_get(ex, "explanation", "")

    if text.lower() == correct.lower():
        msg = "✅ Верно!"
        if explanation:
            msg += f"\n{explanation}"
        await update.message.reply_text(msg)
    else:
        msg = f"❌ Неверно.\nПравильный ответ: {correct}"
        if explanation:
            msg += f"\n{explanation}"
        await update.message.reply_text(msg)

    context.user_data["index"] = idx + 1
    return await send_question(update, context)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ Викторина отменена. Напиши /quiz, чтобы начать заново.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Ошибка обработчика: %s", context.error)


# ——————————————————————————————————————————————
#             СБРОС WEBHOOK ПЕРЕД POLLING
# ——————————————————————————————————————————————
async def delete_webhook_on_startup(app):
    await app.bot.delete_webhook(drop_pending_updates=True)
    log.info("🔄 Webhook удалён, очередь сброшена.")


# ——————————————————————————————————————————————
#                    MAIN
# ——————————————————————————————————————————————
def main():
    if not TOKEN:
        log.error("❌ BOT_TOKEN не задан.")
        return

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .post_init(delete_webhook_on_startup)
        .build()
    )

    app.add_error_handler(on_error)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))

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
    app.add_handler(conv)

    log.info("✅ Запускаем polling…")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
