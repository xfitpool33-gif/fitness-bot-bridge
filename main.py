import os
import asyncio
from aiohttp import web
import aiohttp
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# Считываем настройки из панели управления облаком
TG_TOKEN = os.environ.get("TG_TOKEN")
VK_TOKEN = os.environ.get("VK_TOKEN")
TG_CHAT_ID = int(os.environ.get("TG_CHAT_ID", 0))
VK_CHAT_ID = os.environ.get("VK_CHAT_ID", "")

# Базовый URL для API VK Teams
VK_API_URL = "https://mail.ru"

# Инициализация Telegram-приложения
tg_app = Application.builder().token(TG_TOKEN).build()

# ----------------- 1. ИЗ TELEGRAM В VK TEAMS -----------------
async def from_tg_to_vk(update: Update, context: ContextTypes.DEFAULT_TYPE):
if update.effective_chat.id != TG_CHAT_ID or update.message.from_user.is_bot:
return

author = update.message.from_user.first_name
text = update.message.text or update.message.caption or ""

async with aiohttp.ClientSession() as session:
# Если прислали фото
if update.message.photo:
photo_file = await update.message.photo[-1].get_file()
photo_bytes = await photo_file.download_as_bytearray()

data = aiohttp.FormData()
data.add_field('chatId', VK_CHAT_ID)
data.add_field('caption', f"📸 [ТГ] {author}: {text}")
data.add_field('file', bytes(photo_bytes), filename='photo.jpg', content_type='image/jpeg')

async with session.post(f"{VK_API_URL}/messages/sendIM", data=data, headers={"Authorization": f"Bearer {VK_TOKEN}"}) as resp:
await resp.json()
# Если просто текст
elif text:
payload = {"chatId": VK_CHAT_ID, "text": f"💬 [ТГ] {author}: {text}"}
headers = {"Authorization": f"Bearer {VK_TOKEN}"}
async with session.post(f"{VK_API_URL}/messages/sendText", json=payload, headers=headers) as resp:
await resp.json()

# ----------------- 2. ИЗ VK TEAMS В TELEGRAM -----------------
async def from_vk_to_tg(request):
try:
data = await request.json()
# Проверяем, что это новое сообщение и оно не от самого бота
if data.get("type") == "newMessage" and not data.get("from", {}).get("isBot", False):
chat_id = data.get("chat", {}).get("chatId")
if chat_id == VK_CHAT_ID:
author = data.get("from", {}).get("firstName", "Сотрудник")
text = data.get("text", "")

# Если в VK Teams прикрепили файл/фото
if "parts" in data:
for part in data["parts"]:
if part.get("type") == "file":
file_id = part["payload"]["fileId"]
# Скачиваем файл из VK Teams и пересылаем в Telegram
async with aiohttp.ClientSession() as session:
headers = {"Authorization": f"Bearer {VK_TOKEN}"}
async with session.get(f"{VK_API_URL}/files/getInfo?fileId={file_id}", headers=headers) as resp:
file_info = await resp.json()
file_url = file_info.get("url")

if file_url:
await tg_app.bot.send_photo(chat_id=TG_CHAT_ID, photo=file_url, caption=f"📸 [Макс] {author}: {text}")
elif text:
await tg_app.bot.send_message(chat_id=TG_CHAT_ID, text=f"💬 [Макс] {author}: {text}")
except Exception as e:
print(f"Ошибка вебхука: {e}")
return web.Response(text="OK")

# ----------------- ЗАПУСК ВСЕЙ СИСТЕМЫ -----------------
async def main():
# Настраиваем обработчик Telegram
tg_app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, from_tg_to_vk))
await tg_app.initialize()
await tg_app.start_polling() # Слушаем Telegram напрямую

# Настраиваем вебхук-сервер для приема сообщений из VK Teams
app = web.Application()
app.router.add_post('/webhook', from_vk_to_tg)

runner = web.AppRunner(app)
await runner.setup()
port = int(os.environ.get("PORT", 8080))
site = web.TCPSite(runner, '0.0.0.0', port)
await site.start()

# Держим бота запущенным
while True:
await asyncio.sleep(3600)

if __name__ == "__main__":
asyncio.run(main())
