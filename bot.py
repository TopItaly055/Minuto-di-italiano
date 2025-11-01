import os
import json
import logging
from typing import Any, Dict, List
import pickle
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

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
WEBHOOK_URL_RAW = os.getenv("WEBHOOK_URL", "").strip()

# Исправляем webhook URL если он неправильный
WEBHOOK_URL = ""
if WEBHOOK_URL_RAW:
    # КРИТИЧЕСКАЯ ПРОВЕРКА: если URL содержит "api.render.com/deploy" - это неправильный URL!
    if "api.render.com/deploy" in WEBHOOK_URL_RAW:
        # Это неправильный URL от Render - используем правильный публичный URL
        log.warning(f"⚠️  Обнаружен неправильный webhook URL: {WEBHOOK_URL_RAW[:50]}...")
        log.warning("   Используем правильный публичный URL")
        WEBHOOK_URL = "https://minuto-di-italiano-bot.onrender.com/webhook"
    elif not WEBHOOK_URL_RAW.startswith("http"):
        # Не HTTP URL - используем fallback
        WEBHOOK_URL = "https://minuto-di-italiano-bot.onrender.com/webhook"
    else:
        # Гарантируем что URL заканчивается на /webhook
        url_clean = WEBHOOK_URL_RAW.rstrip('/')
        if not url_clean.endswith('/webhook'):
            WEBHOOK_URL = f"{url_clean}/webhook"
        else:
            WEBHOOK_URL = url_clean
else:
    # WEBHOOK_URL не установлен - используем fallback (для Render)
    WEBHOOK_URL = "https://minuto-di-italiano-bot.onrender.com/webhook"

# PORT должен быть строкой для Render, потом конвертируем в int
PORT_STR = os.getenv("PORT", "10000")
try:
    PORT = int(PORT_STR)
except (ValueError, TypeError):
    PORT = 10000
    log.warning(f"⚠️  Не удалось преобразовать PORT '{PORT_STR}' в int, используем {PORT}")
CONTENT_DIR = "content"
LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]

STATE_LEVEL, STATE_TOPIC, STATE_QUIZ = range(3)

# Статистика пользователей
USER_STATS = {}
STATS_FILE = "user_stats.pkl"

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


def _load_user_stats():
    """Загрузить статистику пользователей из файла."""
    global USER_STATS
    try:
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, 'rb') as f:
                USER_STATS = pickle.load(f)
            log.info(f"Загружена статистика для {len(USER_STATS)} пользователей")
    except Exception as e:
        log.warning(f"Ошибка загрузки статистики: {e}")
        USER_STATS = {}


def _save_user_stats():
    """Сохранить статистику пользователей в файл."""
    try:
        with open(STATS_FILE, 'wb') as f:
            pickle.dump(USER_STATS, f)
        log.info(f"Статистика сохранена для {len(USER_STATS)} пользователей")
    except Exception as e:
        log.error(f"Ошибка сохранения статистики: {e}")


def _get_user_id(update: Update) -> int:
    """Получить ID пользователя."""
    if update.message:
        return update.message.from_user.id
    elif update.callback_query:
        return update.callback_query.from_user.id
    return 0


def _init_user_stats(user_id: int) -> Dict[str, Any]:
    """Инициализировать статистику пользователя."""
    if user_id not in USER_STATS:
        USER_STATS[user_id] = {
            "total_exercises": 0,
            "correct_answers": 0,
            "topics_completed": [],
            "levels_completed": [],
            "current_streak": 0,
            "best_streak": 0
        }
    return USER_STATS[user_id]


def _get_motivational_message(stats: Dict[str, Any]) -> str:
    """Получить мотивационное сообщение на основе статистики."""
    if stats["total_exercises"] == 0:
        return "🚀 Начните свой путь изучения итальянского!"
    
    accuracy = (stats["correct_answers"] / stats["total_exercises"]) * 100
    
    if accuracy >= 90:
        return "🌟 Отлично! Вы настоящий мастер итальянского!"
    elif accuracy >= 80:
        return "👏 Превосходно! Продолжайте в том же духе!"
    elif accuracy >= 70:
        return "💪 Хорошая работа! Вы на правильном пути!"
    elif accuracy >= 60:
        return "📚 Неплохо! Еще немного практики и будет отлично!"
    else:
        return "🎯 Не сдавайтесь! Каждая ошибка - это шаг к успеху!"


def _update_user_stats(user_id: int, is_correct: bool, topic_name: str, level: str):
    """Обновить статистику пользователя."""
    stats = _init_user_stats(user_id)
    stats["total_exercises"] += 1
    
    if is_correct:
        stats["correct_answers"] += 1
        stats["current_streak"] += 1
        if stats["current_streak"] > stats["best_streak"]:
            stats["best_streak"] = stats["current_streak"]
    else:
        stats["current_streak"] = 0
    
    if topic_name not in stats["topics_completed"]:
        stats["topics_completed"].append(topic_name)
    
    if level not in stats["levels_completed"]:
        stats["levels_completed"].append(level)
    
    # Сохраняем статистику после каждого обновления
    _save_user_stats()


# ——————————————————————————————————————————————
#                  ХЕНДЛЕРЫ
# ——————————————————————————————————————————————
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    log.info(f"📥 Получена команда /start")
    user_id = _get_user_id(update)
    _init_user_stats(user_id)
    
    try:
        await _reply(
            update,
            "👋 Привет! Я — тренажёр по итальянскому языку.\n\n"
            "📚 Доступные команды:\n"
            "• /quiz - начать тренировку\n"
            "• /stats - посмотреть статистику\n"
            "• /achievements - ваши достижения\n"
            "• /help - справка по командам\n"
            "• /reset - сбросить статистику\n"
            "• /cancel - отменить текущую тренировку\n\n"
            "Выберите /quiz, чтобы начать!",
        )
        log.info(f"✅ Ответ отправлен")
    except Exception as e:
        log.error(f"❌ Ошибка отправки: {e}")
        raise


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _reply(
        update,
        "📖 Справка по командам:\n\n"
        "🎯 /quiz - начать новую тренировку\n"
        "   Выберите уровень (A1, A2, B1, B2) и тему\n\n"
        "📊 /stats - посмотреть вашу статистику\n"
        "   Узнайте свой прогресс и достижения\n\n"
        "🏅 /achievements - ваши достижения\n"
        "   Посмотрите заработанные награды\n\n"
        "🗑️ /reset - сбросить статистику\n"
        "   Начать отслеживание заново\n\n"
        "❌ /cancel - отменить текущую тренировку\n"
        "   Используйте, если хотите начать заново\n\n"
        "ℹ️ /help - показать эту справку\n\n"
        "Удачи в изучении итальянского! 🇮🇹"
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = _get_user_id(update)
    stats = _init_user_stats(user_id)
    
    accuracy = 0
    if stats["total_exercises"] > 0:
        accuracy = round((stats["correct_answers"] / stats["total_exercises"]) * 100, 1)
    
    levels_text = ", ".join(stats["levels_completed"]) if stats["levels_completed"] else "пока нет"
    topics_text = len(stats["topics_completed"])
    motivational_msg = _get_motivational_message(stats)
    
    await _reply(
        update,
        f"📊 Ваша статистика:\n\n"
        f"🎯 Всего упражнений: {stats['total_exercises']}\n"
        f"✅ Правильных ответов: {stats['correct_answers']}\n"
        f"📈 Точность: {accuracy}%\n"
        f"🔥 Текущая серия: {stats['current_streak']}\n"
        f"🏆 Лучшая серия: {stats['best_streak']}\n"
        f"📚 Изученных тем: {topics_text}\n"
        f"🎓 Пройденные уровни: {levels_text}\n\n"
        f"{motivational_msg}"
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
        # Показываем статистику по завершенной теме
        user_id = _get_user_id(update)
        stats = _init_user_stats(user_id)
        topic_name = context.user_data.get("topic_name", "тема")
        
        await _reply(
            update,
            f"🎉 Все упражнения по теме '{topic_name}' завершены!\n\n"
            f"📊 Ваша статистика:\n"
            f"• Точность: {round((stats['correct_answers'] / stats['total_exercises']) * 100, 1)}%\n"
            f"• Текущая серия: {stats['current_streak']}\n\n"
            f"Напиши /quiz для новой тренировки или /stats для полной статистики!",
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
    
    # Показываем прогресс
    total_exercises = len(exercises)
    progress = f"({idx + 1}/{total_exercises})"
    
    await _reply(update, f"❓ Упражнение {progress}:\n{question}", reply_markup=kb)
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
    
    # Получаем информацию о пользователе и теме
    user_id = _get_user_id(update)
    topic_name = context.user_data.get("topic_name", "Неизвестная тема")
    level = context.user_data.get("level", "Неизвестный уровень")

    is_correct = text.lower() == correct.lower()
    
    # Обновляем статистику
    _update_user_stats(user_id, is_correct, topic_name, level)

    if is_correct:
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


async def reset_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сбросить статистику пользователя."""
    user_id = _get_user_id(update)
    
    if user_id in USER_STATS:
        del USER_STATS[user_id]
        _save_user_stats()
        await _reply(update, "🗑️ Ваша статистика сброшена!")
    else:
        await _reply(update, "ℹ️ У вас пока нет статистики для сброса.")


async def achievements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать достижения пользователя."""
    user_id = _get_user_id(update)
    stats = _init_user_stats(user_id)
    
    achievements_list = []
    
    # Проверяем достижения
    if stats["total_exercises"] >= 10:
        achievements_list.append("🎯 Первые шаги - выполнено 10 упражнений")
    
    if stats["total_exercises"] >= 50:
        achievements_list.append("📚 Усердный ученик - выполнено 50 упражнений")
    
    if stats["total_exercises"] >= 100:
        achievements_list.append("🏆 Мастер практики - выполнено 100 упражнений")
    
    if stats["best_streak"] >= 5:
        achievements_list.append("🔥 Горячая серия - 5 правильных ответов подряд")
    
    if stats["best_streak"] >= 10:
        achievements_list.append("⚡ Невероятная серия - 10 правильных ответов подряд")
    
    if len(stats["levels_completed"]) >= 2:
        achievements_list.append("🎓 Многогранный - изучено 2 уровня")
    
    if len(stats["topics_completed"]) >= 5:
        achievements_list.append("📖 Эрудит - изучено 5 тем")
    
    if stats["total_exercises"] > 0:
        accuracy = (stats["correct_answers"] / stats["total_exercises"]) * 100
        if accuracy >= 90:
            achievements_list.append("🌟 Совершенство - точность 90%+")
    
    if achievements_list:
        achievements_text = "\n".join(achievements_list)
        await _reply(
            update,
            f"🏅 Ваши достижения:\n\n{achievements_text}\n\n"
            f"Продолжайте изучать итальянский! 🇮🇹"
        )
    else:
        await _reply(
            update,
            "🎯 У вас пока нет достижений.\n"
            "Начните тренировку с /quiz, чтобы заработать первые награды!"
        )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик ошибок"""
    log.error(f"❌ Ошибка обработчика: {context.error}")
    if update:
        try:
            log.error(f"📥 Update type: {type(update)}")
            if hasattr(update, 'message'):
                log.error(f"   Message: {update.message}")
        except:
            pass
    log.exception("Полный traceback:")


# ——————————————————————————————————————————————
#             СБРОС WEBHOOK ПЕРЕД POLLING
# ——————————————————————————————————————————————
async def delete_webhook_on_startup(app):
    await app.bot.delete_webhook(drop_pending_updates=True)
    log.info("🔄 Webhook удалён, очередь сброшена.")

async def set_webhook_on_startup(app):
    """Устанавливаем веб-хук при запуске."""
    # Всегда устанавливаем правильный webhook если есть URL
    webhook_url_to_set = WEBHOOK_URL if WEBHOOK_URL else "https://minuto-di-italiano-bot.onrender.com/webhook"
    
    try:
        # Удаляем старый неправильный webhook если есть
        old_info = await app.bot.get_webhook_info()
        if old_info.url and "api.render.com/deploy" in old_info.url:
            log.warning(f"⚠️  Найден неправильный webhook: {old_info.url}")
            await app.bot.delete_webhook(drop_pending_updates=True)
            log.info("🗑️  Старый webhook удален")
        
        # Устанавливаем правильный webhook
        # ВАЖНО: webhook_url должен заканчиваться на /webhook
        if not webhook_url_to_set.endswith('/webhook'):
            webhook_url_to_set = webhook_url_to_set.rstrip('/') + '/webhook'
        await app.bot.set_webhook(url=webhook_url_to_set, drop_pending_updates=True)
        log.info(f"🔗 Webhook установлен: {webhook_url_to_set}")
        
        # Проверяем статус
        webhook_info = await app.bot.get_webhook_info()
        log.info(f"📊 Webhook info: URL={webhook_info.url}, Pending={webhook_info.pending_update_count}")
        if webhook_info.last_error_date:
            log.warning(f"⚠️  Last webhook error: {webhook_info.last_error_message}")
        if webhook_info.url != webhook_url_to_set:
            log.error(f"❌ Webhook URL не совпадает! Ожидался: {webhook_url_to_set}, установлен: {webhook_info.url}")
    except Exception as e:
        log.error(f"❌ Ошибка установки webhook: {e}")
        import traceback
        log.error(traceback.format_exc())
        raise


# ——————————————————————————————————————————————
#                    MAIN
# ——————————————————————————————————————————————
def main():
    if not TOKEN:
        log.error("❌ BOT_TOKEN не задан.")
        return

    # Загружаем статистику при запуске
    _load_user_stats()

    # Всегда используем webhook для Render (даже если переменная не установлена)
    # Это важно для работы на Render
    log.info(f"📋 WEBHOOK_URL_RAW из env: {WEBHOOK_URL_RAW[:50] if WEBHOOK_URL_RAW else 'не установлен'}...")
    log.info(f"📋 Final WEBHOOK_URL: {WEBHOOK_URL}")
    
    # Используем веб-хук для Render
    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .post_init(set_webhook_on_startup)
        .build()
    )

    app.add_error_handler(on_error)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("achievements", achievements))
    app.add_handler(CommandHandler("reset", reset_stats))
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

    # Всегда запускаем webhook для Render
    log.info("=" * 60)
    log.info("🚀 ЗАПУСК БОТА")
    log.info("=" * 60)
    log.info(f"✅ Запускаем с веб-хуком...")
    log.info(f"🔗 Webhook URL: {WEBHOOK_URL}")
    log.info(f"🔑 BOT_TOKEN: {'✅ установлен' if TOKEN else '❌ ОТСУТСТВУЕТ!'}")
    log.info(f"🌐 PORT (raw): {os.getenv('PORT', 'не установлен')}")
    log.info(f"🌐 PORT (int): {PORT}")
    log.info(f"📂 URL path: webhook (без слэша)")
    log.info(f"📡 Слушаем на: 0.0.0.0:{PORT}")
    log.info("=" * 60)
    
    try:
        # Запускаем webhook сервер
        # ВАЖНО: url_path для python-telegram-bot должен быть БЕЗ начального слэша!
        log.info("🔄 Запускаю run_webhook...")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=WEBHOOK_URL,
            url_path="webhook",  # БЕЗ начального слэша!
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        log.info("✅ Webhook сервер запущен!")
    except OSError as e:
        if "Address already in use" in str(e) or "already in use" in str(e):
            log.error(f"❌ Порт {PORT} уже занят! Попробуйте использовать другой порт.")
        else:
            log.error(f"❌ Ошибка сети: {e}")
        import traceback
        log.error(traceback.format_exc())
        raise
    except Exception as e:
        log.error(f"❌ Ошибка запуска webhook: {e}")
        import traceback
        log.error(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
