import os
import requests
import re
from dotenv import load_dotenv
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from astro_pdf_handler import save_file, extract_text_from_file, index_text_with_faiss, query_index, summarize_pdf
from gdrive_handler import start_flow, finish_flow, list_files, download_file


# Загрузка переменных окружения
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Определение Markdown в ответе
def detect_markdown(text: str) -> bool:
    markdown_patterns = [
        r'\*\*(.*?)\*\*',
        r'(?<!\*)\*(?!\*)(.*?)\*(?!\*)',
        r'`.*?`',
        r'```.*?```',
        r'__.*?__',
        r'\[.*?\]\(.*?\)',
    ]
    return any(re.search(p, text) for p in markdown_patterns)

# Приветствие
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Здравствуйте! Я AstroSens — ваш AI-ассистент по астробиологии и космосу.\n\n"
        "Я могу:\n"
        "• Отвечать на вопросы о жизни во Вселенной\n"
        "• Обсуждать спутники, экзопланеты и зарождение жизни\n"
        "• Обрабатывать загруженные статьи и книги (PDF, DOCX, TXT), в том числе из вашего Google Диска\n\n"
        "Просто задайте вопрос — и я постараюсь ответить по существу.\n"
        "Для справки введите /help."
    )

# Ответ на сообщения
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    await update.message.reply_text("🧠 Думаю...")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "deepseek/deepseek-chat-v3-0324:free",
        "messages": [
            {"role": "system", "content": "Ты — высокоточный научный ассистент по астробиологии. Отвечай на русском языке, избегая ошибок и мусорных символов. Пиши грамотно и ясно, как преподаватель биологии и астрономии в университете."},
            {"role": "user", "content": user_input}
        ]
    }

    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
        data = response.json()

        if 'choices' in data:
            reply = data['choices'][0]['message']['content']
        else:
            reply = f"Ошибка в ответе: {data.get('error', 'Неизвестная ошибка')}"
            print("JSON-ответ:", data)

    except Exception as e:
        reply = f"Ошибка запроса: {e}"

    if detect_markdown(reply):
        await update.message.reply_text(reply, parse_mode='Markdown')
    else:
        await update.message.reply_text(reply)

# Обработка документов (PDF, DOCX, TXT)
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not (document.file_name.endswith(".pdf") or 
            document.file_name.endswith(".docx") or 
            document.file_name.endswith(".txt")):
        await update.message.reply_text("Пожалуйста, отправьте файл в формате PDF, DOCX или TXT.")
        return

    file = await document.get_file()
    file_bytes = await file.download_as_bytearray()
    filepath = save_file(file_bytes, document.file_name)

    try:
        text = extract_text_from_file(filepath)
        index_text_with_faiss(text)
        await update.message.reply_text("Файл принят и проиндексирован. Теперь вы можете использовать команду /askfile для вопросов по тексту или /summary для краткого обзора.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка обработки файла: {e}")

# Ответ на команду /askfile
async def askfile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = ' '.join(context.args)
    if not query:
        await update.message.reply_text("Уточните вопрос после команды. Пример: /askfile Как образовалась биосфера Земли?")
        return

    await update.message.reply_text("🔍 Ищу ответ...")
    response = query_index(query)
    await update.message.reply_text(response)

# Команда /summary
async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📖 Пересказываю текст...")
    result = summarize_pdf()
    await update.message.reply_text(result)

from telegram.ext import CommandHandler
import shutil

# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Справка по командам:\n\n"
        "/start — Приветствие и инструкции\n"
        "/help — Справка по командам\n"
        "/askfile [вопрос] — Задать вопрос по загруженному PDF/DOCX/TXT\n"
        "/summary — Краткое содержание загруженного файла\n"
        "/reset — Сбросить контекст текущего файла для загрузки нового\n"
        "/syncdrive — Синхронизация с Google Диском",
        parse_mode='HTML'
    )

# Команда /reset — удалить текущий FAISS-индекс
async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    index_file = "./faiss_index/index.faiss"
    if os.path.exists(index_file):
        shutil.rmtree("./faiss_index")
        os.makedirs("./faiss_index", exist_ok=True)
        await update.message.reply_text("Контекст сброшен. Вы можете загрузить новый файл.")
    else:
        await update.message.reply_text("Контекст уже пуст.")

# Хранить state
drive_files = {}
pending_auth = {}

async def syncdrive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    flow, auth_url = start_flow(update.effective_user.id)
    pending_auth[update.effective_user.id] = flow
    await update.message.reply_text(
        f"Перейдите по ссылке и отправьте код:\n{auth_url}"
    )

async def handle_drive_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in pending_auth:
        await update.message.reply_text("Сначала выполните /syncdrive.")
        return
    code = update.message.text.strip()
    flow = pending_auth.pop(user_id)
    service = finish_flow(flow, code)
    context.user_data['gdrive_service'] = service
    files = list_files(service)
    if not files:
        await update.message.reply_text("На диске нет подходящих файлов.")
        return
    msg = "📄 Найденные файлы:\n"
    for fid, fname in files:
        msg += f"{fname} — ID: `{fid}`\n"
    msg += "\nСкопируйте ID файла и отправьте в чат для чтения."
    context.user_data['drive_files'] = dict(files)
    await update.message.reply_text(msg, parse_mode='Markdown')

async def handle_drive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_id = update.message.text.strip()
    drive_files = context.user_data.get('drive_files', {})
    if file_id not in drive_files:
        await update.message.reply_text("ID не найден. Попробуйте снова.")
        return
    service = context.user_data['gdrive_service']
    filename = drive_files[file_id]
    path = os.path.join('./data', filename)
    download_file(service, file_id, path)
    text = extract_text_from_file(path)
    index_text_with_faiss(text)
    await update.message.reply_text(f"✅ Файл {filename} загружен, проиндексирован и готов к запросам.\n"
                                     "Теперь вы можете использовать команду /askfile для вопросов по тексту или /summary для краткого обзора.")


# Запуск бота
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("askfile", askfile))
    app.add_handler(CommandHandler("summary", summary))
    app.add_handler(CommandHandler("syncdrive", syncdrive))
    app.add_handler(MessageHandler(
        filters.Document.MimeType("application/pdf") |
        filters.Document.MimeType("application/vnd.openxmlformats-officedocument.wordprocessingml.document") |
        filters.Document.MimeType("text/plain"),
        handle_document
    ))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(MessageHandler(filters.Regex(r"^\d{4,}$"), handle_drive_code))
    app.add_handler(MessageHandler(filters.Regex(r"^[\w-]{10,}$"), handle_drive_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("AstroSens работает. Ждите сообщений в Telegram.")
    app.run_polling()
