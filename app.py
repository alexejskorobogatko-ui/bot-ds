import discord
from discord.ext import commands
import asyncio
import os
import json
import glob
import time
import random
import threading
import aiohttp
import sys
from datetime import datetime, timedelta
from flask import Flask

# ==================== ФИКС ДЛЯ WINDOWS ====================
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ==================== ВЕБ-СЕРВЕР ====================
web_app = Flask(__name__)

@web_app.route('/')
def health():
    return "Selfbot is running", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

# ==================== НАСТРОЙКИ ====================
TOKEN = "ВАШ_ТОКЕН_ЗДЕСЬ" # ВСТАВЬ СВОЙ ТОКЕН

TEMPLATES_DIR = "templates"
MEDIA_DIR = "media"
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(MEDIA_DIR, exist_ok=True)

# ==================== МЕДИА ДЛЯ МЕНЮ ====================
help_media = None

default_template_path = os.path.join(TEMPLATES_DIR, "main.txt")
if not os.path.exists(default_template_path):
    with open(default_template_path, 'w', encoding='utf-8') as f:
        f.write("текст по умолчанию 1\nтекст по умолчанию 2")

# ==================== ИНИЦИАЛИЗАЦИЯ ====================
bot = commands.Bot(command_prefix='.', self_bot=True, help_command=None)

start_time = time.time()
current_shablon = []
spam_tasks = {}
tagger_tasks = {}
afk_state = False
afk_reason = "АФК"
autoreply_list = []

# Кулдауны для АФК (ID пользователя: время последнего ответа)
afk_cooldowns = {} 
AFK_COOLDOWN_SECONDS = 300 # 5 минут

def load_template(template_name):
    global current_shablon
    path = os.path.join(TEMPLATES_DIR, f"{template_name}.txt")
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            current_shablon = [line.strip() for line in f.readlines() if line.strip()]
        return True
    return False

load_template("main")

# ==================== СКАЧИВАНИЕ МЕДИА ====================
async def download_media(url):
    if not url or not url.startswith("http"):
        return None
    
    ext = url.split('.')[-1].split('?')[0]
    if len(ext) > 5: ext = 'mp4'
    
    file_path = os.path.join(MEDIA_DIR, f"temp_{int(time.time())}.{ext}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    with open(file_path, 'wb') as f:
                        f.write(await response.read())
                    return file_path
    except Exception as e:
        print(f"Ошибка скачивания: {e}")
    return None

# ==================== СОБЫТИЯ ====================
@bot.event
async def on_ready():
    print(f"[+] Бот запущен как: {bot.user}")
    print("[+] Ожидание команд...")

@bot.event
async def on_message(message):
    global afk_state, afk_reason, autoreply_list, afk_cooldowns
    
    if message.author.id != bot.user.id:
        # ЛОГИКА АФК С КУЛДАУНОМ
        if afk_state and isinstance(message.channel, discord.DMChannel):
            user_id = message.author.id
            current_time = time.time()
            
            # Проверяем, прошло ли 5 минут с последнего ответа
            if user_id not in afk_cooldowns or (current_time - afk_cooldowns[user_id]) > AFK_COOLDOWN_SECONDS:
                afk_cooldowns[user_id] = current_time # Записываем время ответа
                await message.reply(f"⛧ Я в АФК. Причина: {afk_reason}")
            return # Если кулдаун не прошел - просто игнорируем
            
        if message.author.id in autoreply_list:
            text = random.choice(current_shablon) if current_shablon else "Автоответ"
            await message.reply(text)
            return
        return

    await bot.process_commands(message)

# ==================== МЕНЮ (.help) ====================
@bot.command()
async def help(ctx, *, args: str = None):
    global help_media
    
    if args and args.startswith("http"):
        help_media = args.strip()
        return await ctx.send(f"⛧ Медиа для `.help` установлено:\n`{help_media}`")
    
    if args and args.lower() == "none":
        help_media = None
        return await ctx.send("⛧ Медиа для `.help` убрано.")

    text = """⛧ **ОСНОВНОЕ МЕНЮ** ⛧

**Спам:**
`.avt [сек] [ссылка(опц)] [текст]` — спам
`.stop` — остановить

**Теггер:**
`.tagger [ID] [сек] [ссылка(опц)] [текст]` — тегать
`.off` — остановить

**Автоответчик:**
`.reply [ID]` — включить
`.creply [ID]` — выключить

**AFK:**
`.afk [причина]` — вкл/выкл (с КД 5 мин)

**Шаблоны:**
`.shb list` / `.shb load [имя]` / `.shb save [имя]` + реплай на .txt

**Прочее:**
`.ping` — пинг
`.x0` + реплай на медиа — загрузить на хостинг

⛧ **Настройка меню:**
`.help [ссылка]` — установить видео
`.help none` — убрать видео
"""
    
    if help_media:
        try:
            media_path = await asyncio.wait_for(download_media(help_media), timeout=5.0)
        except asyncio.TimeoutError:
            media_path = None
            print("⛧ Таймаут скачивания видео для меню, отправляю текст.")

        if media_path and os.path.exists(media_path):
            try:
                await ctx.send(content=text, file=discord.File(media_path))
            except Exception as e:
                print(f"⛧ Ошибка отправки видео: {e}")
                await ctx.send(text)
            finally:
                try: os.remove(media_path)
                except: pass
        else:
            await ctx.send(text)
    else:
        await ctx.send(text)

@bot.command()
async def ping(ctx):
    start = time.perf_counter()
    msg = await ctx.send("⛧ Пингую...")
    end = time.perf_counter()
    await msg.edit(content=f"⛧ Пинг: **{round((end - start) * 1000)} ms**")

# ==================== СПАМ (.avt) ====================
@bot.command()
async def avt(ctx, time_val: int, *, args: str = ""):
    if time_val < 3:
        return await ctx.send("⛧ Мин. задержка - 3 секунды.")
    
    parts = args.split(maxsplit=1)
    media_url = None
    text = ""
    
    if parts and parts[0].startswith("http"):
        media_url = parts[0]
        text = parts[1] if len(parts) > 1 else ""
    else:
        text = args

    chat_id = ctx.channel.id
    if chat_id in spam_tasks:
        spam_tasks[chat_id].cancel()
    
    await ctx.message.delete()
    
    media_path = None
    if media_url:
        media_path = await download_media(media_url)
        if not media_path:
            return await ctx.send("⛧ Ошибка скачивания медиа.")

    async def spam_loop():
        while True:
            random_phrase = random.choice(current_shablon) if current_shablon else ""
            send_text = f"{text} {random_phrase}".strip()
            
            try:
                if media_path and os.path.exists(media_path):
                    await ctx.send(content=send_text, file=discord.File(media_path))
                else:
                    await ctx.send(send_text)
            except Exception as e:
                print(f"Ошибка спама: {e}")
                
            await asyncio.sleep(time_val)
            
    task = asyncio.create_task(spam_loop())
    spam_tasks[chat_id] = task
    await ctx.send(f"⛧ **СПАМ ЗАПУЩЕН** ⛧\nИнтервал: {time_val} сек.\nМедиа: {'Да' if media_path else 'Нет'}\nОстановить: `.stop`")

@bot.command()
async def stop(ctx):
    chat_id = ctx.channel.id
    if chat_id in spam_tasks:
        spam_tasks[chat_id].cancel()
        del spam_tasks[chat_id]
        await ctx.send("⛧ **СПАМ ОСТАНОВЛЕН** ⛧")
    else:
        await ctx.send("⛧ Спам не запущен.")

# ==================== ТЕГГЕР (.tagger) ====================
@bot.command()
async def tagger(ctx, user_id: str, time_val: int, *, args: str = ""):
    if time_val < 3:
        return await ctx.send("⛧ Мин. задержка - 3 секунды.")
    
    clean_id = user_id.replace('<@', '').replace('!', '').replace('>', '').strip()
    
    parts = args.split(maxsplit=1)
    media_url = None
    text = ""
    
    if parts and parts[0].startswith("http"):
        media_url = parts[0]
        text = parts[1] if len(parts) > 1 else ""
    else:
        text = args
        
    chat_id = ctx.channel.id
    if chat_id in tagger_tasks:
        tagger_tasks[chat_id].cancel()
        
    await ctx.message.delete()
    
    media_path = None
    if media_url:
        media_path = await download_media(media_url)
        if not media_path:
            return await ctx.send("⛧ Ошибка скачивания медиа.")

    async def tagger_loop():
        while True:
            random_phrase = random.choice(current_shablon) if current_shablon else ""
            send_text = f"<@{clean_id}> {text} {random_phrase}".strip()
            try:
                if media_path and os.path.exists(media_path):
                    await ctx.send(content=send_text, file=discord.File(media_path))
                else:
                    await ctx.send(send_text)
            except Exception as e:
                print(f"Ошибка теггера: {e}")
            await asyncio.sleep(time_val)
            
    task = asyncio.create_task(tagger_loop())
    tagger_tasks[chat_id] = task
    await ctx.send(f"⛧ **ТЕГГЕР ЗАПУЩЕН** ⛧\nЦель: <@{clean_id}>\nМедиа: {'Да' if media_path else 'Нет'}\nОстановить: `.off`")

@bot.command()
async def off(ctx):
    chat_id = ctx.channel.id
    if chat_id in tagger_tasks:
        tagger_tasks[chat_id].cancel()
        del tagger_tasks[chat_id]
        await ctx.send("⛧ **ТЕГГЕР ОСТАНОВЛЕН** ⛧")
    else:
        await ctx.send("⛧ Теггер не запущен.")

# ==================== АВТООТВЕТЧИК ====================
@bot.command()
async def reply(ctx, target: str = None):
    global autoreply_list
    if not target:
        return await ctx.send("⛧ Укажи ID: `.reply 123456789`")
    try:
        clean_id = int(target.replace('<@', '').replace('!', '').replace('>', ''))
        if clean_id not in autoreply_list:
            autoreply_list.append(clean_id)
        await ctx.send(f"⛧ Автоответчик включен для <@{clean_id}>")
    except:
        await ctx.send("⛧ Неверный ID.")

@bot.command()
async def creply(ctx, target: str = None):
    global autoreply_list
    if target:
        try:
            clean_id = int(target.replace('<@', '').replace('!', '').replace('>', ''))
            if clean_id in autoreply_list:
                autoreply_list.remove(clean_id)
                await ctx.send(f"⛧ Автоответчик выключен для <@{clean_id}>")
        except:
            pass

# ==================== AFK ====================
@bot.command()
async def afk(ctx, *, reason: str = "АФК"):
    global afk_state, afk_reason, afk_cooldowns
    afk_state = not afk_state
    if afk_state:
        afk_reason = reason
        afk_cooldowns.clear() # Очищаем кулдауны при включении
        await ctx.send(f"⛧ **AFK ВКЛЮЧЕН** ⛧\nПричина: {reason}")
    else:
        await ctx.send("⛧ **AFK ВЫКЛЮЧЕН** ⛧")

# ==================== ШАБЛОНЫ (.shb) ====================
@bot.command()
async def shb(ctx, action: str, name: str = None):
    global current_shablon
    if action == "list":
        files = glob.glob(os.path.join(TEMPLATES_DIR, "*.txt"))
        if not files:
            return await ctx.send("⛧ Нет шаблонов.")
        res = "⛧ **ШАБЛОНЫ** ⛧\n"
        for f in files:
            res += f"- `{os.path.basename(f).replace('.txt', '')}`\n"
        await ctx.send(res)
        
    elif action == "load" and name:
        if load_template(name):
            await ctx.send(f"⛧ Шаблон `{name}` загружен ({len(current_shablon)} фраз).")
        else:
            await ctx.send("⛧ Шаблон не найден.")
            
    elif action == "save" and name and ctx.message.reference:
        ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        if ref_msg.attachments:
            attachment = ref_msg.attachments[0]
            if attachment.filename.endswith('.txt'):
                content = await attachment.read()
                path = os.path.join(TEMPLATES_DIR, f"{name}.txt")
                with open(path, 'wb') as f:
                    f.write(content)
                await ctx.send(f"⛧ Шаблон `{name}` сохранен!")

# ==================== X0.AT (.x0) ====================
@bot.command()
async def x0(ctx):
    if not ctx.message.reference:
        return await ctx.send("⛧ Нужен реплай на сообщение с медиа.")
    
    ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
    
    if not ref_msg.attachments:
        return await ctx.send("⛧ В сообщении нет вложений.")
    
    attachment = ref_msg.attachments[0]
    file_url = attachment.url
    
    msg = await ctx.send("⛧ Загружаю на x0.at...")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as resp:
                if resp.status != 200:
                    return await msg.edit(content="⛧ Ошибка скачивания файла.")
                file_data = await resp.read()
        
        async with aiohttp.ClientSession() as session:
            form = aiohttp.FormData()
            form.add_field('file', file_data, filename=attachment.filename)
            
            async with session.post('https://x0.at/', data=form) as response:
                if response.status == 200:
                    link = await response.text()
                    await msg.edit(content=f"⛧ **Ссылка на x0.at:**\n`{link.strip()}`")
                else:
                    await msg.edit(content=f"⛧ Ошибка x0.at: {response.status}")
                    
    except Exception as e:
        await msg.edit(content=f"⛧ Ошибка: {e}")

# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    bot.run(TOKEN)