import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота
BOT_TOKEN = "8337305923:AAGkurBTl64iT1QokihBxdjQYoIUvNVGZUY"

# Состояния пользователей
WAITING = "waiting"
CHATTING = "chatting"

# База данных для хранения состояний пользователей
class Database:
    def __init__(self):
        self.conn = sqlite3.connect('chat_bot.db', check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                state TEXT DEFAULT 'idle',
                partner_id INTEGER,
                gender TEXT,
                age INTEGER
            )
        ''')
        self.conn.commit()

    def get_user(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        return cursor.fetchone()

    def add_user(self, user_id, username, first_name):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO users (user_id, username, first_name, state)
            VALUES (?, ?, ?, 'idle')
        ''', (user_id, username, first_name))
        self.conn.commit()

    def update_state(self, user_id, state, partner_id=None):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE users SET state = ?, partner_id = ? WHERE user_id = ?
        ''', (state, partner_id, user_id))
        self.conn.commit()

    def get_waiting_users(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT user_id FROM users WHERE state = ?', (WAITING,))
        return [row[0] for row in cursor.fetchall()]

    def delete_user(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
        self.conn.commit()

# Инициализация базы данных
db = Database()

# Основные команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_user(user.id, user.username, user.first_name)
    
    welcome_text = """
👋 Добро пожаловать в Анонимный Чат!

🤫 Здесь вы можете общаться с незнакомцами абсолютно анонимно.

📋 Доступные команды:
/start - Начать работу
/search - Найти собеседника
/stop - Остановить диалог
/help - Помощь

🎯 Нажмите кнопку ниже чтобы начать поиск собеседника!
    """
    
    keyboard = [
        [InlineKeyboardButton("🔍 Найти собеседника", callback_data="search")],
        [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📖 Помощь по боту:

🔍 /search - Начать поиск собеседника
🛑 /stop - Завершить текущий диалог
❌ /cancel - Отменить поиск

📝 Правила:
• Сообщения передаются анонимно
• Не раскрывайте личную информацию
• Уважайте собеседников
• Запрещены оскорбления и спам

⚠️ Нарушители будут заблокированы!
    """
    await update.message.reply_text(help_text)

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    
    if not user_data:
        await update.message.reply_text("Сначала используйте /start")
        return
    
    current_state = user_data[3]  # state field
    
    if current_state == CHATTING:
        await update.message.reply_text("❌ Вы уже в диалоге! Используйте /stop чтобы завершить его.")
        return
    elif current_state == WAITING:
        await update.message.reply_text("🔍 Вы уже в поиске...")
        return
    
    # Начинаем поиск
    db.update_state(user_id, WAITING)
    await update.message.reply_text("🔍 Ищем собеседника...")
    
    # Ищем подходящего партнера
    waiting_users = db.get_waiting_users()
    waiting_users = [uid for uid in waiting_users if uid != user_id]  # Исключаем себя
    
    if waiting_users:
        partner_id = waiting_users[0]
        # Соединяем пользователей
        db.update_state(user_id, CHATTING, partner_id)
        db.update_state(partner_id, CHATTING, user_id)
        
        # Уведомляем обоих пользователей
        await context.bot.send_message(
            user_id,
            "✅ Собеседник найден! Начинайте общение.\nИспользуйте /stop чтобы завершить диалог."
        )
        await context.bot.send_message(
            partner_id,
            "✅ Собеседник найден! Начинайте общение.\nИспользуйте /stop чтобы завершить диалог."
        )
    else:
        await update.message.reply_text("⏳ Ожидаем подключения других пользователей...")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    
    if not user_data:
        return
    
    current_state = user_data[3]
    partner_id = user_data[4]
    
    if current_state == CHATTING and partner_id:
        # Завершаем диалог у обоих пользователей
        db.update_state(user_id, 'idle')
        db.update_state(partner_id, 'idle')
        
        # Уведомляем обоих пользователей
        await update.message.reply_text("❌ Диалог завершен.")
        await context.bot.send_message(partner_id, "❌ Собеседник завершил диалог.")
        
    elif current_state == WAITING:
        db.update_state(user_id, 'idle')
        await update.message.reply_text("❌ Поиск отменен.")
    else:
        await update.message.reply_text("❌ Вы не в диалоге и не в поиске.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    
    if not user_data:
        await update.message.reply_text("Сначала используйте /start")
        return
    
    current_state = user_data[3]
    partner_id = user_data[4]
    
    if current_state == CHATTING and partner_id:
        # Пересылаем сообщение партнеру
        try:
            if update.message.text:
                await context.bot.send_message(partner_id, f"💬 {update.message.text}")
            elif update.message.sticker:
                await context.bot.send_sticker(partner_id, update.message.sticker.file_id)
            elif update.message.photo:
                await context.bot.send_photo(partner_id, update.message.photo[-1].file_id)
            elif update.message.voice:
                await context.bot.send_voice(partner_id, update.message.voice.file_id)
            else:
                await update.message.reply_text("❌ Этот тип сообщения не поддерживается")
        except Exception as e:
            await update.message.reply_text("❌ Не удалось отправить сообщение. Возможно, собеседник отключился.")
            db.update_state(user_id, 'idle')
    elif current_state == WAITING:
        await update.message.reply_text("⏳ Пожалуйста, подождите пока найдется собеседник...")
    else:
        await update.message.reply_text("❌ Используйте /search чтобы найти собеседника")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if query.data == "search":
        # Имитируем команду /search
        await search_for_chat(query, context)
    elif query.data == "help":
        await help_command(query, context)

async def search_for_chat(query, context: ContextTypes.DEFAULT_TYPE):
    user_id = query.from_user.id
    user_data = db.get_user(user_id)
    
    if not user_data:
        return
    
    current_state = user_data[3]
    
    if current_state == CHATTING:
        await query.edit_message_text("❌ Вы уже в диалоге! Используйте /stop чтобы завершить его.")
        return
    elif current_state == WAITING:
        await query.edit_message_text("🔍 Вы уже в поиске...")
        return
    
    db.update_state(user_id, WAITING)
    await query.edit_message_text("🔍 Ищем собеседника...")
    
    waiting_users = db.get_waiting_users()
    waiting_users = [uid for uid in waiting_users if uid != user_id]
    
    if waiting_users:
        partner_id = waiting_users[0]
        db.update_state(user_id, CHATTING, partner_id)
        db.update_state(partner_id, CHATTING, user_id)
        
        await context.bot.send_message(user_id, "✅ Собеседник найден! Начинайте общение.\nИспользуйте /stop чтобы завершить диалог.")
        await context.bot.send_message(partner_id, "✅ Собеседник найден! Начинайте общение.\nИспользуйте /stop чтобы завершить диалог.")
    else:
        await query.edit_message_text("⏳ Ожидаем подключения других пользователей...")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

def main():
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()

    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("search", search))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("cancel", stop))
    
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.ALL, handle_message))
    
    application.add_error_handler(error_handler)

    # Запускаем бота
    print("Бот запущен...")
    application.run_polling()

if __name__ == "__main__":
    main()
