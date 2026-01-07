import os
import logging
import random
import asyncio
import threading
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from flask import Flask

# ========== FLASK ПРИЛОЖЕНИЕ ДЛЯ HEALTH CHECKS ==========
app = Flask(__name__)

@app.route('/')
def home():
    return """
    <html>
        <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
            <h1>♔ Шахматный тренер работает! ♚</h1>
            <p>Телеграм бот для тренировки игры вслепую</p>
            <p>Статус: <span style="color: green;">● Активен</span></p>
        </body>
    </html>
    """

@app.route('/health')
def health():
    return "OK", 200

@app.route('/ping')
def ping():
    return "pong", 200

# ========== ОСНОВНОЙ КОД БОТА ==========
# Включим логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
CHOOSING, ANSWERING, TESTING = range(3)

# Словарь фигур
PIECES_BY_FILE = {
    'a': ('ладья', '♖'),
    'b': ('конь', '♘'),
    'c': ('слон', '♗'),
    'd': ('ферзь', '♕'),
    'e': ('король', '♔'),
    'f': ('слон', '♗'),
    'g': ('конь', '♘'),
    'h': ('ладья', '♖')
}

# Глобальные переменные для хранения состояния
user_sessions = {}

# Генерация случайной клетки
def get_random_square():
    files = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
    file = random.choice(files)
    rank = random.choice([1, 8])
    return file, rank

# Получение правильной информации
def get_correct_info(file, rank):
    piece_name, piece_symbol = PIECES_BY_FILE[file]
    color_letter = 'Б' if rank == 1 else 'Ч'
    return piece_name, color_letter, piece_symbol

# Проверка ввода цвета
def validate_color_input(user_input):
    color_map = {
        'б': 'Б', 'белый': 'Б', 'белая': 'Б', 'белые': 'Б',
        'ч': 'Ч', 'черный': 'Ч', 'черная': 'Ч', 'черные': 'Ч',
        'white': 'Б', 'black': 'Ч', 'w': 'Б', 'b': 'Ч'
    }
    return color_map.get(user_input.lower().strip())

# Проверка ввода фигуры
def validate_piece_input(user_input):
    piece_map = {
        'л': 'ладья', 'ладья': 'ладья', 'тура': 'ладья', 'rook': 'ладья',
        'к': 'конь', 'конь': 'конь', 'кн': 'конь', 'horse': 'конь', 'knight': 'конь',
        'с': 'слон', 'слон': 'слон', 'bishop': 'слон',
        'ф': 'ферзь', 'ферзь': 'ферзь', 'королева': 'ферзь', 'queen': 'ферзь',
        'кр': 'король', 'король': 'король', 'king': 'король'
    }
    return piece_map.get(user_input.lower().strip())

# Создание клавиатуры для выбора режима
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("🎮 Легкий режим"), KeyboardButton("🎯 Средний режим")],
        [KeyboardButton("⚡ Сложный режим"), KeyboardButton("📝 Тест (10 вопросов)")],
        [KeyboardButton("📚 Справка"), KeyboardButton("📊 Статистика")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Создание клавиатуры для ответа
def get_answer_keyboard():
    keyboard = [
        [KeyboardButton("🏁 Завершить"), KeyboardButton("🔄 Еще вопрос")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_sessions[user_id] = {
        'mode': None,
        'score': 0,
        'total': 0,
        'test_in_progress': False,
        'test_questions': 0,
        'test_correct': 0
    }
    
    welcome_text = (
        "👑 *Тренер для игры в шахматы вслепую*\n\n"
        "Я помогу вам запомнить расположение фигур на доске!\n\n"
        "*Как это работает:*\n"
        "1. Я покажу координату клетки (например, e1)\n"
        "2. Вы должны назвать фигуру и цвет, который там стоит в начале игры\n"
        "3. Я проверю ваш ответ и дам обратную связь\n\n"
        "Выберите режим тренировки:"
    )
    
    await update.message.reply_text(
        welcome_text,
        parse_mode='Markdown',
        reply_markup=get_main_keyboard()
    )
    return CHOOSING

# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "*📚 Справка по боту*\n\n"
        "*1-я горизонталь (БЕЛЫЕ фигуры):*\n"
        "• a1, h1 - ладья (♖)\n"
        "• b1, g1 - конь (♘)\n" 
        "• c1, f1 - слон (♗)\n"
        "• d1 - ферзь (♕)\n"
        "• e1 - король (♔)\n\n"
        "*8-я горизонталь (ЧЁРНЫЕ фигуры):*\n"
        "• a8, h8 - ладья (♖)\n"
        "• b8, g8 - конь (♘)\n"
        "• c8, f8 - слон (♗)\n"
        "• d8 - ферзь (♕)\n"
        "• e8 - король (♔)\n\n"
        "*Форматы ответа:*\n"
        "• Цвет: Б, белый, Ч, черный\n"
        "• Фигура: ладья, конь, слон, ферзь, король\n"
        "• Или одной строкой: 'Б ладья', 'черный конь'\n\n"
        "*Режимы:*\n"
        "• 🎮 Легкий - с подсказкой\n"
        "• 🎯 Средний - без подсказки\n"
        "• ⚡ Сложный - ввод одной строкой\n"
        "• 📝 Тест - 10 вопросов с подсчетом результатов"
    )
    
    await update.message.reply_text(
        help_text,
        parse_mode='Markdown',
        reply_markup=get_main_keyboard()
    )

# Обработка выбора режима
async def choose_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    if user_id not in user_sessions:
        user_sessions[user_id] = {
            'mode': None,
            'score': 0,
            'total': 0,
            'test_in_progress': False,
            'test_questions': 0,
            'test_correct': 0
        }
    
    if text == "🎮 Легкий режим":
        user_sessions[user_id]['mode'] = 'easy'
        await ask_question(update, context, 'easy')
        return ANSWERING
        
    elif text == "🎯 Средний режим":
        user_sessions[user_id]['mode'] = 'medium'
        await ask_question(update, context, 'medium')
        return ANSWERING
        
    elif text == "⚡ Сложный режим":
        user_sessions[user_id]['mode'] = 'hard'
        await ask_question(update, context, 'hard')
        return ANSWERING
        
    elif text == "📝 Тест (10 вопросов)":
        user_sessions[user_id]['mode'] = 'medium'
        user_sessions[user_id]['test_in_progress'] = True
        user_sessions[user_id]['test_questions'] = 0
        user_sessions[user_id]['test_correct'] = 0
        await start_test(update, context)
        return TESTING
        
    elif text == "📚 Справка":
        await help_command(update, context)
        return CHOOSING
        
    elif text == "📊 Статистика":
        await show_stats(update, context)
        return CHOOSING
    
    return CHOOSING

# Задать вопрос
async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE, mode=None):
    user_id = update.effective_user.id
    
    if mode is None:
        mode = user_sessions[user_id].get('mode', 'medium')
    
    # Генерация вопроса
    file, rank = get_random_square()
    piece_name, color_letter, piece_symbol = get_correct_info(file, rank)
    
    # Сохраняем правильный ответ в контексте
    context.user_data['current_question'] = {
        'file': file,
        'rank': rank,
        'correct_piece': piece_name,
        'correct_color': color_letter,
        'symbol': piece_symbol
    }
    
    # Формируем вопрос в зависимости от режима
    if mode == 'easy':
        hint = "1-я горизонталь (белые)" if rank == 1 else "8-я горизонталь (черные)"
        question_text = (
            f"*Координата:* `{file.upper()}{rank}`\n"
            f"*Подсказка:* {hint}\n\n"
            "Введите *цвет* и *фигуру* (например: `Б ладья` или `черный конь`)"
        )
    elif mode == 'medium':
        question_text = (
            f"*Координата:* `{file.upper()}{rank}`\n\n"
            "Введите *цвет* и *фигуру* (например: `Б ладья` или `черный конь`)"
        )
    else:  # hard mode
        question_text = (
            f"*Координата:* `{file.upper()}{rank}`\n\n"
            "Введите ответ *одной строкой* (например: `Б ладья` или `черный конь`)"
        )
    
    await update.message.reply_text(
        question_text,
        parse_mode='Markdown',
        reply_markup=get_answer_keyboard()
    )

# Обработка ответа
async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_input = update.message.text
    
    # Проверяем специальные команды
    if user_input == "🏁 Завершить":
        await update.message.reply_text(
            "Тренировка завершена! Возвращаюсь в главное меню.",
            reply_markup=get_main_keyboard()
        )
        return CHOOSING
    
    elif user_input == "🔄 Еще вопрос":
        mode = user_sessions[user_id].get('mode', 'medium')
        await ask_question(update, context, mode)
        return ANSWERING
    
    # Получаем текущий вопрос
    if 'current_question' not in context.user_data:
        await update.message.reply_text(
            "Что-то пошло не так. Давайте начнем заново.",
            reply_markup=get_main_keyboard()
        )
        return CHOOSING
    
    question = context.user_data['current_question']
    
    # Парсим ответ пользователя
    user_input_lower = user_input.lower().strip()
    parts = user_input_lower.split()
    
    if len(parts) >= 2:
        # Пытаемся определить цвет и фигуру
        color_input = ' '.join(parts[:-1])
        piece_input = parts[-1]
    else:
        color_input = ''
        piece_input = user_input_lower
    
    # Проверяем ввод
    validated_color = validate_color_input(color_input) or validate_color_input(piece_input)
    validated_piece = validate_piece_input(piece_input)
    
    # Если не удалось определить цвет из первого слова, пробуем все слова
    if not validated_color:
        for word in parts:
            color = validate_color_input(word)
            if color:
                validated_color = color
                break
    
    # Если не удалось определить фигуру, пробуем все слова
    if not validated_piece:
        for word in parts:
            piece = validate_piece_input(word)
            if piece:
                validated_piece = piece
                break
    
    # Проверяем правильность
    piece_correct = validated_piece == question['correct_piece']
    color_correct = validated_color == question['correct_color']
    
    # Формируем ответ
    correct_answer = f"{question['correct_color']} {question['correct_piece']} {question['symbol']}"
    
    if piece_correct and color_correct:
        response = f"✅ *Правильно!* {correct_answer}"
        score = 2
    elif piece_correct and not color_correct:
        response = f"⚠️ *Фигура угадана, цвет нет!*\nПравильно: {correct_answer}"
        score = 1
    elif not piece_correct and color_correct:
        response = f"⚠️ *Цвет угадан, фигура нет!*\nПравильно: {correct_answer}"
        score = 1
    else:
        response = f"❌ *Неправильно!*\nПравильно: {correct_answer}"
        score = 0
    
    # Обновляем статистику
    if user_id not in user_sessions:
        user_sessions[user_id] = {'score': 0, 'total': 0}
    
    user_sessions[user_id]['score'] += score
    user_sessions[user_id]['total'] += 2  # Максимальный балл за вопрос
    
    await update.message.reply_text(
        response,
        parse_mode='Markdown',
        reply_markup=get_answer_keyboard()
    )
    
    return ANSWERING

# Начать тест
async def start_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    user_sessions[user_id]['test_questions'] = 0
    user_sessions[user_id]['test_correct'] = 0
    
    await update.message.reply_text(
        "📝 *Начинаем тест! 10 вопросов.*\n\n"
        "Отвечайте на вопросы. В конце увидите статистику.\n"
        "Формат ответа: `цвет фигура` (например: `Б ладья`)",
        parse_mode='Markdown'
    )
    
    await ask_test_question(update, context)

# Задать тестовый вопрос
async def ask_test_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_sessions[user_id]['test_questions'] >= 10:
        await finish_test(update, context)
        return
    
    # Генерация вопроса
    file, rank = get_random_square()
    piece_name, color_letter, piece_symbol = get_correct_info(file, rank)
    
    # Сохраняем вопрос
    context.user_data['current_test_question'] = {
        'file': file,
        'rank': rank,
        'correct_piece': piece_name,
        'correct_color': color_letter,
        'symbol': piece_symbol
    }
    
    user_sessions[user_id]['test_questions'] += 1
    
    question_num = user_sessions[user_id]['test_questions']
    await update.message.reply_text(
        f"*Вопрос {question_num}/10:*\n"
        f"Координата: `{file.upper()}{rank}`\n\n"
        "Ваш ответ (цвет фигура):",
        parse_mode='Markdown'
    )

# Обработка ответа в тесте
async def handle_test_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_input = update.message.text
    
    if 'current_test_question' not in context.user_data:
        await ask_test_question(update, context)
        return
    
    question = context.user_data['current_test_question']
    
    # Парсим ответ
    user_input_lower = user_input.lower().strip()
    parts = user_input_lower.split()
    
    if len(parts) >= 2:
        color_input = ' '.join(parts[:-1])
        piece_input = parts[-1]
    else:
        color_input = ''
        piece_input = user_input_lower
    
    validated_color = validate_color_input(color_input) or validate_color_input(piece_input)
    validated_piece = validate_piece_input(piece_input)
    
    # Проверяем правильность
    piece_correct = validated_piece == question['correct_piece']
    color_correct = validated_color == question['correct_color']
    
    if piece_correct and color_correct:
        user_sessions[user_id]['test_correct'] += 1
        response = "✅ Правильно!"
    else:
        correct_answer = f"{question['correct_color']} {question['correct_piece']}"
        response = f"❌ Неправильно. Правильно: {correct_answer}"
    
    await update.message.reply_text(response)
    
    if user_sessions[user_id]['test_questions'] < 10:
        await ask_test_question(update, context)
    else:
        await finish_test(update, context)

# Завершить тест
async def finish_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    correct = user_sessions[user_id]['test_correct']
    total = user_sessions[user_id]['test_questions']
    percentage = (correct / total * 100) if total > 0 else 0
    
    if percentage >= 90:
        emoji = "🏆"
        comment = "Отличный результат! Вы настоящий мастер!"
    elif percentage >= 70:
        emoji = "👍"
        comment = "Хороший результат!"
    elif percentage >= 50:
        emoji = "💪"
        comment = "Неплохо, но можно лучше!"
    else:
        emoji = "📚"
        comment = "Потренируйтесь еще!"
    
    result_text = (
        f"{emoji} *Результаты теста:*\n\n"
        f"Правильных ответов: *{correct}/{total}*\n"
        f"Процент правильных: *{percentage:.1f}%*\n\n"
        f"{comment}"
    )
    
    user_sessions[user_id]['test_in_progress'] = False
    
    await update.message.reply_text(
        result_text,
        parse_mode='Markdown',
        reply_markup=get_main_keyboard()
    )
    
    return CHOOSING

# Показать статистику
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in user_sessions or user_sessions[user_id]['total'] == 0:
        await update.message.reply_text(
            "У вас пока нет статистики. Начните тренировку!",
            reply_markup=get_main_keyboard()
        )
        return
    
    score = user_sessions[user_id]['score']
    total = user_sessions[user_id]['total']
    percentage = (score / total * 100) if total > 0 else 0
    
    stats_text = (
        "*📊 Ваша статистика:*\n\n"
        f"Накопленный балл: *{score}/{total}*\n"
        f"Процент правильных: *{percentage:.1f}%*\n\n"
        "*Как считается:*\n"
        "• 2 балла - правильно и фигура, и цвет\n"
        "• 1 балл - правильно только что-то одно\n"
        "• 0 баллов - ошибка в обоих"
    )
    
    await update.message.reply_text(
        stats_text,
        parse_mode='Markdown',
        reply_markup=get_main_keyboard()
    )

# Отмена
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_sessions:
        user_sessions[user_id]['test_in_progress'] = False
    
    await update.message.reply_text(
        "Тренировка прервана. Возвращаюсь в главное меню.",
        reply_markup=get_main_keyboard()
    )
    return CHOOSING

# ========== ФУНКЦИИ ДЛЯ ЗАПУСКА ==========
def run_flask(port):
    """Запуск Flask сервера"""
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

async def run_bot():
    """Запуск Telegram бота"""
    TOKEN = os.getenv("TOKEN")
    
    if not TOKEN:
        print("❌ ОШИБКА: Не установлен TOKEN!")
        print("Добавьте переменную окружения TOKEN в настройках Render")
        return
    
    application = Application.builder().token(TOKEN).build()
    
    # Создаем ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CHOOSING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, choose_mode)
            ],
            ANSWERING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer)
            ],
            TESTING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_test_answer)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Добавляем обработчики
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('stats', show_stats))
    
    # Запускаем бота
    print("🤖 Бот запущен!")
    await application.run_polling(allowed_updates=Update.ALL_TYPES)

def main():
    """Основная функция"""
    # Получаем порт из переменных окружения (Render дает порт)
    PORT = int(os.getenv("PORT", 5000))
    
    print(f"🚀 Запуск приложения на порту {PORT}")
    
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, args=(PORT,))
    flask_thread.daemon = True
    flask_thread.start()
    
    print(f"🌐 Веб-сервер запущен: http://0.0.0.0:{PORT}")
    print(f"🔗 Health check: http://0.0.0.0:{PORT}/health")
    
    # Запускаем бота
    asyncio.run(run_bot())

if __name__ == '__main__':
    main()
