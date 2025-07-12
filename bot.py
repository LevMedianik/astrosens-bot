import os
import requests
import re
import shutil
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from astro_pdf_handler import (
    save_file,
    extract_text_from_file,
    index_text_with_faiss,
    query_index,
    summarize_pdf
)
from gdrive_handler import (
    start_flow,
    finish_flow,
    list_files,
    download_file
)

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

def detect_markdown(text: str) -> bool:
    patterns = [
        r'\*\*(.*?)\*\*', r'(?<!\*)\*(?!\*)(.*?)\*(?!\*)',
        r'`.*?`', r'```.*?```', r'__.*?__', r'\[.*?\]\(.*?\)'
    ]
    return any(re.search(p, text) for p in patterns)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Здравствуйте! Я AstroSens — ваш AI-ассистент по астробиологии и космосу.\n\n"
        "Я могу:\n"
        "• Отвечать на вопросы о жизни во Вселенной\n"
        "• Обсуждать спутники, экзопланеты и зарождение жизни\n"
        "• Обрабатывать загруженные статьи и книги (PDF, DOCX, TXT), в том числе из вашего Google Диска\n\n"
        "Для справки введите /help."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 Справка по командам:\n"
        "/start — Приветствие\n"
        "/help — Справка\n"
        "/askfile [вопрос] — Вопрос по загруженному файлу\n"
        "/summary — Краткое содержание\n"
        "/reset — Сбросить индекс\n"
        "/syncdrive — Синхронизировать с Google Диском\n",
        parse_mode='HTML'
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    await update.message.reply_text("🧠 Думаю...")

    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek/deepseek-chat-v3-0324:free",
        "messages": [
            {"role": "system", "content": "Ты — ассистент по астробиологии. Отвечай ясно, на русском."},
            {"role": "user", "content": user_input}
        ]
    }

    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
        data = response.json()
        reply = data['choices'][0]['message']['content'] if 'choices' in data else "⚠️ Ошибка."
    except Exception as e:
        reply = f"Ошибка запроса: {e}"

    if detect_markdown(reply):
        await update.message.reply_text(reply, parse_mode='Markdown')
    else:
        await update.message.reply_text(reply)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not (doc.file_name.endswith(".pdf") or doc.file_name.endswith(".docx") or doc.file_name.endswith(".txt")):
        await update.message.reply_text("Поддерживаются только PDF, DOCX, TXT.")
        return
    file = await doc.get_file()
    file_bytes = await file.download_as_bytearray()
    path = save_file(file_bytes, doc.file_name)
    text = extract_text_from_file(path)
    index_text_with_faiss(text)
    await update.message.reply_text("✅ Файл проиндексирован. Используйте /askfile или /summary.")

async def askfile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = ' '.join(context.args)
    if not query:
        await update.message.reply_text("Пример: /askfile Какие условия на Марсе?")
        return
    await update.message.reply_text("🔍 Ищу ответ...")
    response = query_index(query)
    await update.message.reply_text(response)

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📖 Пересказываю текст...")
    result = summarize_pdf()
    await update.message.reply_text(result)

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if os.path.exists("./faiss_index"):
        shutil.rmtree("./faiss_index")
        os.makedirs("./faiss_index", exist_ok=True)
        await update.message.reply_text("Контекст сброшен.")
    else:
        await update.message.reply_text("Контекст уже пуст.")

pending_auth = {}

async def syncdrive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    flow, auth_url = start_flow(update.effective_user.id)
    pending_auth[update.effective_user.id] = flow
    context.user_data["step"] = "awaiting_auth_code"
    await update.message.reply_text(f"Перейдите по ссылке и отправьте код:\n{auth_url}")

async def handle_drive_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    user_id = update.effective_user.id
    flow = pending_auth.pop(user_id, None)
    if not flow:
        await update.message.reply_text("Сначала выполните /syncdrive.")
        return
    service = finish_flow(flow, code)
    context.user_data['gdrive_service'] = service
    files = list_files(service)
    if not files:
        await update.message.reply_text("Файлы не найдены.")
        return
    msg = "📄 Найденные файлы:\n"
    for fid, fname in files:
        msg += f"{fname} — ID: `{fid}`\n"
    msg += "\nОтправьте ID файла."
    context.user_data['drive_files'] = dict(files)
    context.user_data["step"] = "awaiting_file_id"
    await update.message.reply_text(msg, parse_mode='Markdown')

async def handle_drive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_id = update.message.text.strip()
    drive_files = context.user_data.get('drive_files', {})
    if file_id not in drive_files:
        await update.message.reply_text("ID не найден.")
        return
    service = context.user_data['gdrive_service']
    filename = drive_files[file_id]
    path = os.path.join('./data', filename)
    download_file(service, file_id, path)
    text = extract_text_from_file(path)
    index_text_with_faiss(text)
    context.user_data["step"] = None
    await update.message.reply_text(f"✅ Файл {filename} проиндексирован. Используйте /askfile или /summary.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("step")
    if step == "awaiting_auth_code":
        await handle_drive_code(update, context)
    elif step == "awaiting_file_id":
        await handle_drive_file(update, context)
    else:
        await handle_message(update, context)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("askfile", askfile))
    app.add_handler(CommandHandler("summary", summary))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("syncdrive", syncdrive))

    app.add_handler(MessageHandler(
        filters.Document.MimeType("application/pdf") |
        filters.Document.MimeType("application/vnd.openxmlformats-officedocument.wordprocessingml.document") |
        filters.Document.MimeType("text/plain"),
        handle_document
    ))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("AstroSens работает. Ждите сообщений в Telegram.")
    app.run_polling()
