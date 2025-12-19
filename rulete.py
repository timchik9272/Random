import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# --- КОНФИГУРАЦИЯ ---
TOKEN = "ВАШ_НОВЫЙ_ТОКЕН"  # Вставьте сюда новый токен от BotFather

# --- ЛОГИРОВАНИЕ ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# --- ХРАНИЛИЩЕ ДАННЫХ (В ПАМЯТИ) ---
# В продакшене лучше использовать базу данных (SQLite/PostgreSQL)
queue = set()           # Очередь пользователей (random search)
active_chats = {}       # Связь: user_id -> partner_id
private_rooms = {}      # Код комнаты -> user_id (создатель)
users_in_menu = set()   # Кто находится в меню (чтобы не спамить)

# --- ТЕКСТЫ И КЛАВИАТУРЫ ---
def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("🎲 Найти собеседника", callback_data="find_random")],
        [InlineKeyboardButton("🔐 Комната по коду", callback_data="room_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)

def chat_keyboard():
    keyboard = [
        [InlineKeyboardButton("⏭ Следующий", callback_data="next_chat"),
         InlineKeyboardButton("🛑 Стоп", callback_data="stop_chat")]
    ]
    return InlineKeyboardMarkup(keyboard)

def stop_keyboard():
    keyboard = [[InlineKeyboardButton("🔙 В главное меню", callback_data="main_menu")]]
    return InlineKeyboardMarkup(keyboard)

# --- ОСНОВНАЯ ЛОГИКА ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start: Показывает главное меню."""
    user = update.effective_user
    # Очистка старых состояний
    if user.id in queue: queue.remove(user.id)
    if user.id in active_chats: active_chats.pop(user.id, None)
    
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "Я бот для анонимного общения.\n"
        "Выбери режим ниже:",
        reply_markup=main_menu_keyboard()
    )

async def handle_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на инлайн-кнопки."""
    query = update.callback_query
    user_id = query.from_user.id
    
    await query.answer()

    if query.data == "main_menu":
        # Очистка состояний при возврате в меню
        if user_id in queue: queue.remove(user_id)
        if user_id in active_chats: 
            partner_id = active_chats.pop(user_id)
            active_chats.pop(partner_id, None)
            try:
                await context.bot.send_message(partner_id, "🚫 Собеседник покинул чат.", reply_markup=main_menu_keyboard())
            except:
                pass
        
        await query.edit_message_text(
            "🏠 Главное меню.\nВыбери действие:",
            reply_markup=main_menu_keyboard()
        )

    elif query.data == "find_random":
        if user_id in active_chats:
            await query.edit_message_text("⚠️ Ты уже в чате!", reply_markup=chat_keyboard())
            return

        if user_id in queue:
            await query.edit_message_text("🔎 Поиск уже идет... Ожидай собеседника.", reply_markup=stop_keyboard())
            return

        # Логика поиска
        if len(queue) > 0:
            # Нашли пару
            partner_id = queue.pop()
            
            # Сохраняем связь
            active_chats[user_id] = partner_id
            active_chats[partner_id] = user_id
            
            # Уведомляем обоих
            await query.edit_message_text("✅ **Собеседник найден!**\nМожете общаться.", parse_mode="Markdown", reply_markup=chat_keyboard())
            try:
                await context.bot.send_message(partner_id, "✅ **Собеседник найден!**\nМожете общаться.", parse_mode="Markdown", reply_markup=chat_keyboard())
            except:
                await query.edit_message_text("🚫 Ошибка соединения. Попробуй еще раз.", reply_markup=main_menu_keyboard())
                active_chats.pop(user_id, None)
                active_chats.pop(partner_id, None)
        else:
            # Никого нет, встаем в очередь
            queue.add(user_id)
            await query.edit_message_text("🔎 **Ищу собеседника...**\nЖди, это может занять время.", parse_mode="Markdown", reply_markup=stop_keyboard())

    elif query.data == "stop_chat":
        if user_id in active_chats:
            partner_id = active_chats.pop(user_id)
            active_chats.pop(partner_id, None)
            
            await query.edit_message_text("🛑 Диалог завершен.", reply_markup=main_menu_keyboard())
            try:
                await context.bot.send_message(partner_id, "🛑 Собеседник завершил диалог.", reply_markup=main_menu_keyboard())
            except:
                pass
        elif user_id in queue:
            queue.remove(user_id)
            await query.edit_message_text("🛑 Поиск отменен.", reply_markup=main_menu_keyboard())
        else:
            await query.edit_message_text("Ты сейчас не в диалоге.", reply_markup=main_menu_keyboard())

    elif query.data == "next_chat":
        # Завершаем текущий, если есть
        if user_id in active_chats:
            partner_id = active_chats.pop(user_id)
            active_chats.pop(partner_id, None)
            try:
                await context.bot.send_message(partner_id, "⏭ Собеседник переключился на другого.", reply_markup=main_menu_keyboard())
            except:
                pass
        
        # Сразу запускаем поиск
        if user_id in queue: queue.remove(user_id) # На всякий случай
        
        if len(queue) > 0:
            partner_id = queue.pop()
            active_chats[user_id] = partner_id
            active_chats[partner_id] = user_id
            
            await query.edit_message_text("✅ **Новый собеседник найден!**", parse_mode="Markdown", reply_markup=chat_keyboard())
            try:
                await context.bot.send_message(partner_id, "✅ **Собеседник найден!**", parse_mode="Markdown", reply_markup=chat_keyboard())
            except:
                pass
        else:
            queue.add(user_id)
            await query.edit_message_text("🔎 **Ищу нового собеседника...**", parse_mode="Markdown", reply_markup=stop_keyboard())

    elif query.data == "room_menu":
        await query.edit_message_text(
            "🔐 **Режим комнат**\n\n"
            "Чтобы создать комнату или подключиться, просто отправь мне **секретный код** (любое слово или число) в чат.\n\n"
            "Пример: `1234` или `секрет`",
            parse_mode="Markdown",
            reply_markup=stop_keyboard()
        )
        context.user_data['waiting_for_code'] = True

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений, фото, стикеров и т.д."""
    user_id = update.effective_user.id
    
    # 1. Если пользователь вводит КОД КОМНАТЫ
    if context.user_data.get('waiting_for_code'):
        code = update.message.text.strip()
        context.user_data['waiting_for_code'] = False # Сбрасываем флаг
        
        if code in private_rooms:
            # Соединяем
            partner_id = private_rooms.pop(code)
            
            # Нельзя соединиться с самим собой
            if partner_id == user_id:
                await update.message.reply_text("🤔 Ты не можешь подключиться к своей же комнате.", reply_markup=main_menu_keyboard())
                return

            active_chats[user_id] = partner_id
            active_chats[partner_id] = user_id
            
            await update.message.reply_text(f"✅ Подключено к комнате `{code}`!", parse_mode="Markdown", reply_markup=chat_keyboard())
            try:
                await context.bot.send_message(partner_id, f"✅ К тебе подключились по коду `{code}`!", parse_mode="Markdown", reply_markup=chat_keyboard())
            except:
                pass
        else:
            # Создаем комнату
            private_rooms[code] = user_id
            await update.message.reply_text(
                f"🆕 Комната `{code}` создана!\n"
                f"Отправь этот код другу, чтобы он подключился.",
                parse_mode="Markdown",
                reply_markup=stop_keyboard()
            )
        return

    # 2. Если пользователь В ЧАТЕ - пересылаем сообщение
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        try:
            # Метод copy_message универсален (текст, фото, видео, голосовые)
            await update.message.copy(chat_id=partner_id)
        except Exception as e:
            await update.message.reply_text("🚫 Сообщение не отправлено. Собеседник заблокировал бота.", reply_markup=main_menu_keyboard())
            # Разрываем связь
            active_chats.pop(user_id, None)
            active_chats.pop(partner_id, None)
    
    # 3. Если пользователь просто пишет (не в чате и не вводит код)
    else:
        # Игнорируем или предлагаем меню, если не в очереди
        if user_id not in queue and user_id not in private_rooms.values():
            await update.message.reply_text("Используй меню для навигации 👇", reply_markup=main_menu_keyboard())

# --- ЗАПУСК ---

if __name__ == "__main__":
    application = Application.builder().token(TOKEN).build()

    # Хендлеры
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_menu_buttons))
    
    # Обработчик ВСЕХ сообщений (текст, медиа), кроме команд
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))

    print("🤖 Бот запущен...")
    application.run_polling()
