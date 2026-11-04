import sqlite3
import re
import time
import random
import os
import asyncio
import datetime
from vkbottle.bot import Bot, Message
from vkbottle import Keyboard, KeyboardButtonColor, Callback

# ==========================================
# 1. НАСТРОЙКИ
# ==========================================
TOKEN = os.getenv("MAGNIT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
bot = Bot(token=TOKEN)

RANKS = {
    0: "Участник", 20: "Модератор", 40: "Администратор", 
    60: "Главный Администратор", 80: "Специальный Администратор", 100: "Владелец"
}

# ==========================================
# 2. БАЗА ДАННЫХ
# ==========================================
conn = sqlite3.connect('bot.db', check_same_thread=False)
cur = conn.cursor()

cur.execute('''CREATE TABLE IF NOT EXISTS messages (peer_id INTEGER, user_id INTEGER, count INTEGER DEFAULT 0, PRIMARY KEY (peer_id, user_id))''')
cur.execute('''CREATE TABLE IF NOT EXISTS roles (peer_id INTEGER, user_id INTEGER, rank INTEGER DEFAULT 0, PRIMARY KEY (peer_id, user_id))''')
cur.execute('''CREATE TABLE IF NOT EXISTS mutes (peer_id INTEGER, user_id INTEGER, expire INTEGER, PRIMARY KEY (peer_id, user_id))''')
cur.execute('''CREATE TABLE IF NOT EXISTS bans (peer_id INTEGER, user_id INTEGER, PRIMARY KEY (peer_id, user_id))''')
cur.execute('''CREATE TABLE IF NOT EXISTS warns (peer_id INTEGER, user_id INTEGER, count INTEGER DEFAULT 0, PRIMARY KEY (peer_id, user_id))''')
cur.execute('''CREATE TABLE IF NOT EXISTS sysbans (user_id INTEGER PRIMARY KEY)''')
cur.execute('''CREATE TABLE IF NOT EXISTS tickets (id INTEGER PRIMARY KEY AUTOINCREMENT, peer_id INTEGER, user_id INTEGER, text TEXT, status TEXT)''')
cur.execute('''CREATE TABLE IF NOT EXISTS nicknames (peer_id INTEGER, user_id INTEGER, nick TEXT, PRIMARY KEY (peer_id, user_id))''')
cur.execute('''CREATE TABLE IF NOT EXISTS vip_users (peer_id INTEGER, user_id INTEGER, is_vip INTEGER DEFAULT 0, color TEXT DEFAULT '', PRIMARY KEY (peer_id, user_id))''')
cur.execute('''CREATE TABLE IF NOT EXISTS balances (peer_id INTEGER, user_id INTEGER, coins INTEGER DEFAULT 0, PRIMARY KEY (peer_id, user_id))''')
cur.execute('''CREATE TABLE IF NOT EXISTS profiles (peer_id INTEGER, user_id INTEGER, bio TEXT DEFAULT '', rep INTEGER DEFAULT 0, last_rep TEXT DEFAULT '', PRIMARY KEY (peer_id, user_id))''')
cur.execute('''CREATE TABLE IF NOT EXISTS sync_chats (chat1 INTEGER, chat2 INTEGER, PRIMARY KEY (chat1, chat2))''')
cur.execute('''CREATE TABLE IF NOT EXISTS custom_ranks (rank_id INTEGER PRIMARY KEY, rank_name TEXT)''')
cur.execute('''CREATE TABLE IF NOT EXISTS support_chat (id INTEGER PRIMARY KEY, peer_id INTEGER)''')
conn.commit()

def get_rank_name(rank_id):
    cur.execute("SELECT rank_name FROM custom_ranks WHERE rank_id=?", (rank_id,))
    res = cur.fetchone()
    if res: return res[0]
    return RANKS.get(rank_id, f"Ранг {rank_id}")

def get_user_rank(peer_id, user_id):
    if user_id == ADMIN_ID: return 100
    cur.execute("SELECT rank FROM roles WHERE peer_id=? AND user_id=?", (peer_id, user_id))
    res = cur.fetchone()
    return res[0] if res else 0

def get_target_id(message: Message):
    if message.reply_message: return message.reply_message.from_id
    if message.fwd_messages: return message.fwd_messages[0].from_id
    match = re.search(r'id(\d+)', message.text)
    if match: return int(match.group(1))
    match_num = re.findall(r'\d+', message.text)
    if match_num: return int(match_num[0])
    return None

def is_vip(peer_id, user_id):
    if user_id == ADMIN_ID: return True
    cur.execute("SELECT is_vip FROM vip_users WHERE peer_id=? AND user_id=?", (peer_id, user_id))
    res = cur.fetchone()
    return bool(res[0]) if res else False

def can_punish(peer_id, my_id, target_id):
    my_rank = get_user_rank(peer_id, my_id)
    target_rank = get_user_rank(peer_id, target_id)
    if my_id == ADMIN_ID: return True
    if target_id == ADMIN_ID: return False
    return my_rank > target_rank

# ==========================================
# 3. ФОНОВЫЕ ПРОВЕРКИ
# ==========================================
@bot.on.chat_message()
async def background_handler(message: Message):
    if message.from_id == ADMIN_ID:
        if message.text and message.text.startswith(('/', '+')): return
        try:
            cur.execute("INSERT INTO messages (peer_id, user_id, count) VALUES (?, ?, 1) ON CONFLICT(peer_id, user_id) DO UPDATE SET count = count + 1", (message.peer_id, message.from_id))
            cur.execute("INSERT INTO balances (peer_id, user_id, coins) VALUES (?, ?, 1) ON CONFLICT(peer_id, user_id) DO UPDATE SET coins = coins + 1", (message.peer_id, message.from_id))
            conn.commit()
        except: pass
        return

    cur.execute("SELECT user_id FROM sysbans WHERE user_id=?", (message.from_id,))
    if cur.fetchone():
        try:
            await bot.api.messages.delete(message_ids=message.id, delete_for_all=1)
            await bot.api.messages.remove_chat_user(chat_id=message.chat_id, user_id=message.from_id)
        except: pass
        return

    cur.execute("SELECT user_id FROM bans WHERE peer_id=? AND user_id=?", (message.peer_id, message.from_id))
    if cur.fetchone():
        try: await bot.api.messages.remove_chat_user(chat_id=message.chat_id, user_id=message.from_id)
        except: pass
        return

    cur.execute("SELECT expire FROM mutes WHERE peer_id=? AND user_id=?", (message.peer_id, message.from_id))
    mute = cur.fetchone()
    if mute:
        if time.time() < mute[0]:
            try: await bot.api.messages.delete(message_ids=message.id, delete_for_all=1)
            except: pass
            return
        else:
            cur.execute("DELETE FROM mutes WHERE peer_id=? AND user_id=?", (message.peer_id, message.from_id))
            conn.commit()

    if message.text and message.text.startswith(('/', '+')): return
    try:
        cur.execute("INSERT INTO messages (peer_id, user_id, count) VALUES (?, ?, 1) ON CONFLICT(peer_id, user_id) DO UPDATE SET count = count + 1", (message.peer_id, message.from_id))
        cur.execute("INSERT INTO balances (peer_id, user_id, coins) VALUES (?, ?, 1) ON CONFLICT(peer_id, user_id) DO UPDATE SET coins = coins + 1", (message.peer_id, message.from_id))
        conn.commit()
    except: pass

# ==========================================
# 4. ПОЛЬЗОВАТЕЛЬСКИЕ КОМАНДЫ
# ==========================================
@bot.on.chat_message(regex=r"^[\/\+](ping|пинг)")
async def ping(message: Message): await message.answer("Pong! Я на месте.")

@bot.on.chat_message(regex=r"^[\/\+](getid|айди)")
async def get_id(message: Message): await message.answer(f"Твой ID: {message.from_id}\nID чата: {message.peer_id}")

@bot.on.chat_message(regex=r"^[\/\+](stats|стата|статистика)")
async def stats(message: Message):
    target_id = get_target_id(message) or message.from_id
    cur.execute("SELECT count FROM messages WHERE peer_id=? AND user_id=?", (message.peer_id, target_id))
    res = cur.fetchone()
    count = res[0] if res else 0
    rank = get_user_rank(message.peer_id, target_id)
    cur.execute("SELECT nick FROM nicknames WHERE peer_id=? AND user_id=?", (message.peer_id, target_id))
    nick_res = cur.fetchone()
    display_name = nick_res[0] if nick_res else f"[id{target_id}|пользователь]"
    cur.execute("SELECT color, is_vip FROM vip_users WHERE peer_id=? AND user_id=?", (message.peer_id, target_id))
    vip_res = cur.fetchone()
    prefix = ""
    if (vip_res and vip_res[1]) or target_id == ADMIN_ID:
        prefix = vip_res[0] if (vip_res and vip_res[0]) else "👑"
    cur.execute("SELECT bio, rep FROM profiles WHERE peer_id=? AND user_id=?", (message.peer_id, target_id))
    prof_res = cur.fetchone()
    bio = prof_res[0] if prof_res else "Не установлено"
    rep = prof_res[1] if prof_res else 0
    await message.answer(f"📊 **Статистика {prefix} {display_name}:**\n💬 Сообщений: {count}\n👑 Ранг: {rank} ({get_rank_name(rank)})\n❤️ Репутация: {rep}\n📝 О себе: {bio}")

@bot.on.chat_message(regex=r"^[\/\+](bio|био)\s+(.+)")
async def set_bio(message: Message):
    text = message.text.split(maxsplit=1)[1]
    if len(text) > 50: return await message.answer("Био слишком длинное (макс. 50 символов).")
    cur.execute("INSERT INTO profiles (peer_id, user_id, bio) VALUES (?, ?, ?) ON CONFLICT(peer_id, user_id) DO UPDATE SET bio = ?", (message.peer_id, message.from_id, text, text))
    conn.commit()
    await message.answer(f"✅ Твое био обновлено: {text}")

@bot.on.chat_message(regex=r"^[\/\+](rep|реп)")
async def give_rep(message: Message):
    target_id = get_target_id(message)
    if not target_id: return await message.answer("Ответь на сообщение того, кому хочешь повысить репутацию.")
    if target_id == message.from_id: return await message.answer("Нельзя повышать репутацию самому себе.")
    today = str(datetime.date.today())
    cur.execute("SELECT last_rep FROM profiles WHERE peer_id=? AND user_id=?", (message.peer_id, message.from_id))
    last_rep = cur.fetchone()
    if last_rep and last_rep[0] == today: return await message.answer("Ты уже повышал кому-то репутацию сегодня. Возвращайся завтра!")
    cur.execute("INSERT INTO profiles (peer_id, user_id, rep) VALUES (?, ?, 1) ON CONFLICT(peer_id, user_id) DO UPDATE SET rep = rep + 1", (message.peer_id, target_id))
    cur.execute("INSERT INTO profiles (peer_id, user_id, last_rep) VALUES (?, ?, ?) ON CONFLICT(peer_id, user_id) DO UPDATE SET last_rep = ?", (message.peer_id, message.from_id, today, today))
    conn.commit()
    await message.answer(f"❤️ Ты повысил репутацию [id{target_id}|пользователю]!")

# ==========================================
# 5. МОДЕРАЦИЯ И РАНГИ (С ЗАЩИТОЙ)
# ==========================================
@bot.on.chat_message(regex=r"^[\/\+](newrole|ньюроль)\s+(\d+)\s+(.+)")
async def new_role(message: Message, rank_id: int, rank_name: str):
    if message.from_id != ADMIN_ID: return await message.answer("❌ Создавать новые ранги может только Владелец.")
    if rank_id < 0 or rank_id > 100: return await message.answer("❌ Ранг должен быть от 0 до 100.")
    cur.execute("INSERT OR REPLACE INTO custom_ranks (rank_id, rank_name) VALUES (?, ?)", (rank_id, rank_name))
    conn.commit()
    await message.answer(f"✅ Создан новый ранг **{rank_id}** с названием **{rank_name}**.")

@bot.on.chat_message(regex=r"^[\/\+](setrank|ранг)\s+\d+")
async def set_rank(message: Message):
    my_rank = get_user_rank(message.peer_id, message.from_id)
    if my_rank < 60: return await message.answer("Выдавать ранги может только Главный Администратор (60) и выше.")
    target_id = get_target_id(message)
    try: rank_to_give = int(message.text.split()[-1])
    except: return await message.answer("Напиши ранг числом. Пример: ответь на сообщение `/setrank 20`")
    if not target_id or target_id == ADMIN_ID: return await message.answer("Не понял кому. Или ты пытаешься выдать ранг Владельцу.")
    if my_rank == 60: max_limit = 40
    elif my_rank == 80: max_limit = 60
    elif my_rank == 100: max_limit = 99
    else: max_limit = 0
    if rank_to_give > max_limit or rank_to_give >= my_rank: return await message.answer(f"Ты можешь выдавать ранги только до {max_limit}.")
    cur.execute("INSERT OR REPLACE INTO roles (peer_id, user_id, rank) VALUES (?, ?, ?)", (message.peer_id, target_id, rank_to_give))
    conn.commit()
    await message.answer(f"Пользователю {target_id} выдан ранг {rank_to_give} ({get_rank_name(rank_to_give)}).")

@bot.on.chat_message(regex=r"^[\/\+](рроль|remrank|снятьранг)")
async def remove_rank(message: Message):
    my_rank = get_user_rank(message.peer_id, message.from_id)
    if my_rank < 60: return await message.answer("Снимать ранги может только Главный Администратор (60) и выше.")
    target_id = get_target_id(message)
    if not target_id: return await message.answer("Ответь на сообщение того, с кого хочешь снять ранг.")
    target_rank = get_user_rank(message.peer_id, target_id)
    if target_id == ADMIN_ID: return await message.answer("Нельзя снять ранг Владельцу.")
    if target_rank >= my_rank and message.from_id != ADMIN_ID: return await message.answer("❌ Ты не можешь снять ранг с того, кто выше или равен тебе.")
    cur.execute("DELETE FROM roles WHERE peer_id=? AND user_id=?", (message.peer_id, target_id))
    conn.commit()
    await message.answer(f"📉 С пользователя [id{target_id}|пользователь] снят ранг.")

@bot.on.chat_message(regex=r"^[\/\+](kick|кик)")
async def kick_user(message: Message):
    if get_user_rank(message.peer_id, message.from_id) < 20: return await message.answer("Нужен Модератор (20)+.")
    target_id = get_target_id(message)
    if target_id:
        if not can_punish(message.peer_id, message.from_id, target_id): return await message.answer("❌ Ты не можешь наказать того, кто выше или равен тебе по рангу.")
        try:
            await bot.api.messages.remove_chat_user(chat_id=message.chat_id, user_id=target_id)
            await message.answer(f"Пользователь {target_id} исключён.")
        except Exception as e: await message.answer(f"Ошибка: {e}")

@bot.on.chat_message(regex=r"^[\/\+](ban|бан)")
async def ban_user(message: Message):
    if get_user_rank(message.peer_id, message.from_id) < 40: return await message.answer("Нужен Администратор (40)+.")
    target_id = get_target_id(message)
    if target_id:
        if not can_punish(message.peer_id, message.from_id, target_id): return await message.answer("❌ Ты не можешь забанить того, кто выше или равен тебе по рангу.")
        try: await bot.api.messages.remove_chat_user(chat_id=message.chat_id, user_id=target_id)
        except: pass
        cur.execute("INSERT OR IGNORE INTO bans (peer_id, user_id) VALUES (?, ?)", (message.peer_id, target_id))
        conn.commit()
        await message.answer(f"Пользователь {target_id} забанен в этом чате.")

@bot.on.chat_message(regex=r"^[\/\+](mute|мут)\s*\d*")
async def mute_user(message: Message):
    if get_user_rank(message.peer_id, message.from_id) < 20: return await message.answer("Нужен Модератор (20)+.")
    target_id = get_target_id(message)
    if target_id:
        if not can_punish(message.peer_id, message.from_id, target_id): return await message.answer("❌ Ты не можешь замутить того, кто выше или равен тебе по рангу.")
        time_match = re.findall(r'\d+', message.text)
        minutes = int(time_match[-1]) if time_match else 10
        expire = int(time.time()) + (minutes * 60)
        cur.execute("INSERT OR REPLACE INTO mutes (peer_id, user_id, expire) VALUES (?, ?, ?)", (message.peer_id, target_id, expire))
        conn.commit()
        await message.answer(f"Пользователь {target_id} замучен на {minutes} мин.")

@bot.on.chat_message(regex=r"^[\/\+](warn|варн)")
async def warn_user(message: Message):
    if get_user_rank(message.peer_id, message.from_id) < 20: return await message.answer("Нужен Модератор (20)+.")
    target_id = get_target_id(message)
    if target_id:
        if not can_punish(message.peer_id, message.from_id, target_id): return await message.answer("❌ Ты не можешь выдать варн тому, кто выше или равен тебе по рангу.")
        cur.execute("INSERT OR IGNORE INTO warns (peer_id, user_id, count) VALUES (?, ?, 0)", (message.peer_id, target_id))
        cur.execute("UPDATE warns SET count = count + 1 WHERE peer_id=? AND user_id=?", (message.peer_id, target_id))
        conn.commit()
        cur.execute("SELECT count FROM warns WHERE peer_id=? AND user_id=?", (message.peer_id, target_id))
        count = cur.fetchone()[0]
        if count >= 3:
            try: await bot.api.messages.remove_chat_user(chat_id=message.chat_id, user_id=target_id)
            except: pass
            cur.execute("INSERT OR IGNORE INTO bans (peer_id, user_id) VALUES (?, ?)", (message.peer_id, target_id))
            conn.commit()
            await message.answer(f"Пользователь {target_id} получил 3/3 варна и забанен.")
        else: await message.answer(f"Пользователь {target_id} получил варн. Всего: {count}/3.")

@bot.on.chat_message(regex=r"^[\/\+](unban|разбан)")
async def unban_user(message: Message):
    if get_user_rank(message.peer_id, message.from_id) < 40: return await message.answer("Нужен Администратор (40)+.")
    target_id = get_target_id(message)
    if target_id:
        cur.execute("DELETE FROM bans WHERE peer_id=? AND user_id=?", (message.peer_id, target_id))
        conn.commit()
        await message.answer(f"Пользователь {target_id} разбанен в этом чате.")

@bot.on.chat_message(regex=r"^[\/\+](unmute|размут)")
async def unmute_user(message: Message):
    if get_user_rank(message.peer_id, message.from_id) < 20: return await message.answer("Нужен Модератор (20)+.")
    target_id = get_target_id(message)
    if target_id:
        cur.execute("DELETE FROM mutes WHERE peer_id=? AND user_id=?", (message.peer_id, target_id))
        conn.commit()
        await message.answer(f"Пользователь {target_id} размучен.")

@bot.on.chat_message(regex=r"^[\/\+](unwarn|снятьварн)")
async def unwarn_user(message: Message):
    if get_user_rank(message.peer_id, message.from_id) < 20: return await message.answer("Нужен Модератор (20)+.")
    target_id = get_target_id(message)
    if target_id:
        cur.execute("UPDATE warns SET count = max(0, count - 1) WHERE peer_id=? AND user_id=?", (message.peer_id, target_id))
        conn.commit()
        await message.answer(f"С пользователя {target_id} снят 1 варн.")

# ГЛОБАЛЬНЫЙ БАН (ТОЛЬКО ВЛАДЕЛЕЦ)
@bot.on.chat_message(regex=r"^[\/\+](sysban|гбан)")
async def sysban_user(message: Message):
    if message.from_id != ADMIN_ID: 
        return await message.answer("❌ Глобальный бан может использовать только Владелец.")
    target_id = get_target_id(message)
    if target_id:
        if not can_punish(message.peer_id, message.from_id, target_id): return await message.answer("❌ Ты не можешь забанить того, кто выше или равен тебе по рангу.")
        cur.execute("INSERT OR IGNORE INTO sysbans (user_id) VALUES (?)", (target_id,))
        conn.commit()
        try: await bot.api.messages.remove_chat_user(chat_id=message.chat_id, user_id=target_id)
        except: pass
        await message.answer(f"⛔ Пользователь {target_id} забанен ГЛОБАЛЬНО.")

@bot.on.chat_message(regex=r"^[\/\+](unsysban|разгбан)")
async def unsysban_user(message: Message):
    if message.from_id != ADMIN_ID: 
        return await message.answer("❌ Снимать глобальный бан может только Владелец.")
    target_id = get_target_id(message)
    if target_id:
        cur.execute("DELETE FROM sysbans WHERE user_id=?", (target_id,))
        conn.commit()
        await message.answer(f"Пользователь {target_id} разбанен ГЛОБАЛЬНО.")

# ==========================================
# 6. ЗОВ И СИНХРОНИЗАЦИЯ
# ==========================================
@bot.on.chat_message(regex=r"^[\/\+](zov|зов)\s+(.+)")
async def zov_local(message: Message):
    if get_user_rank(message.peer_id, message.from_id) < 80: return await message.answer("Локальный зов доступен с ранга Специального Администратора (80)+.")
    text = message.text.split(maxsplit=1)[1]
    try:
        await bot.api.messages.send(peer_id=message.peer_id, message=f"📢 **Объявление:**\n\n{text}", random_id=random.randint(1, 999999))
    except Exception as e: await message.answer(f"Ошибка: {e}")

@bot.on.chat_message(regex=r"^[\/\+](globalzov|глобалзов)\s+(.+)")
async def zov_global(message: Message):
    if message.from_id != ADMIN_ID: return await message.answer("❌ Глобальную рассылку может делать только Владелец.")
    text = message.text.split(maxsplit=1)[1]
    await message.answer("🚀 Начинаю глобальную рассылку...")
    try: conversations = await bot.api.messages.get_conversations(peer_types=["chat"], count=200)
    except Exception as e: return await message.answer(f"Ошибка: {e}")
    sent, errors = 0, 0
    for conv in conversations.items:
        try:
            await bot.api.messages.send(peer_id=conv.peer.id, message=f"📢 **Глобальное объявление:**\n\n{text}", random_id=random.randint(1, 999999))
            sent += 1
        except: errors += 1
        await asyncio.sleep(2.5)
    await message.answer(f"📢 Глобальная рассылка завершена.\nОтправлено: {sent}\nОшибок: {errors}")

@bot.on.chat_message(regex=r"^[\/\+](sync|синк)")
async def sync_chats(message: Message):
    if message.from_id != ADMIN_ID: return await message.answer("❌ Синхронизация доступна только Владельцу.")
    target_id = get_target_id(message)
    if not target_id: return await message.answer("❌ Ответь на сообщение из другого чата, чтобы синхронизировать его с текущим.")
    if target_id == message.peer_id: return await message.answer("❌ Нельзя синхронизировать чат с самим собой.")
    cur.execute("INSERT OR IGNORE INTO sync_chats (chat1, chat2) VALUES (?, ?)", (message.peer_id, target_id))
    cur.execute("INSERT OR IGNORE INTO sync_chats (chat1, chat2) VALUES (?, ?)", (target_id, message.peer_id))
    conn.commit()
    await message.answer(f"🔗 Чат {message.peer_id} успешно синхронизирован с чатом {target_id}.")

@bot.on.chat_message(regex=r"^[\/\+](unsync|разсинк)")
async def unsync_chats(message: Message):
    if message.from_id != ADMIN_ID: return await message.answer("❌ Разрывать синхронизацию может только Владелец.")
    target_id = get_target_id(message)
    if not target_id: return await message.answer("❌ Ответь на сообщение из другого чата, чтобы разорвать синхронизацию.")
    cur.execute("DELETE FROM sync_chats WHERE (chat1=? AND chat2=?) OR (chat1=? AND chat2=?)", (message.peer_id, target_id, target_id, message.peer_id))
    conn.commit()
    await message.answer(f"🔗 Синхронизация с чатом {target_id} разорвана.")

@bot.on.chat_message(regex=r"^[\/\+](syncinfo|синкинфо)")
async def sync_info(message: Message):
    cur.execute("SELECT chat2 FROM sync_chats WHERE chat1=?", (message.peer_id,))
    rows = cur.fetchall()
    if not rows: return await message.answer("🔗 Этот чат ни с чем не синхронизирован.")
    text = "🔗 **Этот чат синхронизирован с:**\n"
    for row in rows: text += f"• Чат ID: {row[0]}\n"
    await message.answer(text)

@bot.on.chat_message(regex=r"^[\/\+](ssnick|ссник)\s+(.+)")
async def sync_nick(message: Message):
    if get_user_rank(message.peer_id, message.from_id) < 60: return await message.answer("Менять синхронизированный ник может только Главный Администратор (60) и выше.")
    name = message.text.split(maxsplit=1)[1]
    if len(name) > 20: return await message.answer("Ник слишком длинный (макс. 20).")
    cur.execute("INSERT OR REPLACE INTO nicknames (peer_id, user_id, nick) VALUES (?, ?, ?)", (message.peer_id, message.from_id, name))
    cur.execute("SELECT chat2 FROM sync_chats WHERE chat1=?", (message.peer_id,))
    linked_chats = [row[0] for row in cur.fetchall()]
    for chat in linked_chats:
        cur.execute("INSERT OR REPLACE INTO nicknames (peer_id, user_id, nick) VALUES (?, ?, ?)", (chat, message.from_id, name))
    conn.commit()
    await message.answer(f"✅ Твой ник **{name}** установлен во всех связанных беседах ({len(linked_chats) + 1} шт).")

@bot.on.chat_message(regex=r"^[\/\+](ррник|rrsnick|удалитьниквезде)")
async def sync_del_nick(message: Message):
    if get_user_rank(message.peer_id, message.from_id) < 60: return await message.answer("Удалять синхронизированный ник может только Главный Администратор (60) и выше.")
    cur.execute("DELETE FROM nicknames WHERE peer_id=? AND user_id=?", (message.peer_id, message.from_id))
    cur.execute("SELECT chat2 FROM sync_chats WHERE chat1=?", (message.peer_id,))
    linked_chats = [row[0] for row in cur.fetchall()]
    for chat in linked_chats:
        cur.execute("DELETE FROM nicknames WHERE peer_id=? AND user_id=?", (chat, message.from_id))
    conn.commit()
    await message.answer(f"🗑 Твой ник удалён во всех связанных беседах ({len(linked_chats) + 1} шт).")

# ==========================================
# 7. ТИКЕТЫ (ЦЕНТР ПОДДЕРЖКИ)
# ==========================================
@bot.on.chat_message(regex=r"^[\/\+](setsupport|сетсаппорт)")
async def set_support(message: Message):
    if message.from_id != ADMIN_ID: return await message.answer("❌ Настраивать центр поддержки может только Владелец.")
    cur.execute("INSERT OR REPLACE INTO support_chat (id, peer_id) VALUES (1, ?)", (message.peer_id,))
    conn.commit()
    await message.answer("✅ **Этот чат назначен Центром Поддержки!**\nТеперь все жалобы будут прилетать сюда и Владельцу в ЛС.")

@bot.on.chat_message(regex=r"^[\/\+](report|репорт)\s+(.+)")
async def create_ticket(message: Message):
    text = message.text.split(maxsplit=1)[1]
    cur.execute("INSERT INTO tickets (peer_id, user_id, text, status) VALUES (?, ?, ?, 'open')", (message.peer_id, message.from_id, text))
    conn.commit()
    ticket_id = cur.lastrowid
    await message.answer(f"Тикет #{ticket_id} создан. Ожидайте ответа.")
    
    ticket_text = f"🔔 **Новый тикет #{ticket_id}**\nЧат: {message.peer_id}\nОт: [id{message.from_id}|Пользователь]\n\nТекст: {text}"
    kb = (Keyboard(inline=True).add(Callback("✍️ Ответить", {"cmd": "ticket_reply", "ticket_id": ticket_id}), color=KeyboardButtonColor.PRIMARY).add(Callback("🔒 Закрыть", {"cmd": "ticket_close", "ticket_id": ticket_id}), color=KeyboardButtonColor.NEGATIVE)).get_json()

    try: await bot.api.messages.send(peer_id=ADMIN_ID, message=ticket_text, keyboard=kb, random_id=0)
    except Exception: pass

    cur.execute("SELECT peer_id FROM support_chat WHERE id=1")
    support_res = cur.fetchone()
    if support_res:
        support_peer = support_res[0]
        if support_peer != message.peer_id:
            try: await bot.api.messages.send(peer_id=support_peer, message=ticket_text, keyboard=kb, random_id=0)
            except Exception: pass

@bot.on.raw_event("message_event")
async def ticket_admin_handler(event: dict):
    payload = event.get("object", {}).get("payload", {})
    if payload.get("cmd") not in ["ticket_reply", "ticket_close"]: return
    event_id = event.get("object", {}).get("event_id")
    user_id = event.get("object", {}).get("user_id")
    peer_id = event.get("object", {}).get("peer_id")
    ticket_id = payload.get("ticket_id")
    cur.execute("SELECT peer_id, user_id, status FROM tickets WHERE id=?", (ticket_id,))
    ticket = cur.fetchone()
    if not ticket or ticket[2] == 'closed':
        return await bot.api.messages.send_message_event_answer(event_id=event_id, user_id=user_id, peer_id=peer_id, event_data={"type": "show_snackbar", "text": "Тикет не найден или закрыт"})
    target_peer, target_user, status = ticket
    my_rank = get_user_rank(target_peer, user_id)
    if my_rank < 60 and user_id != ADMIN_ID:
        return await bot.api.messages.send_message_event_answer(event_id=event_id, user_id=user_id, peer_id=peer_id, event_data={"type": "show_snackbar", "text": "У вас нет прав (нужен 60+)"})
    if payload.get("cmd") == "ticket_close":
        cur.execute("UPDATE tickets SET status='closed' WHERE id=?", (ticket_id,))
        conn.commit()
        kb = (Keyboard(inline=True).add(Callback("1", {"cmd": "rate", "ticket_id": ticket_id, "score": 1}), color=KeyboardButtonColor.PRIMARY).add(Callback("5", {"cmd": "rate", "ticket_id": ticket_id, "score": 5}), color=KeyboardButtonColor.PRIMARY)).get_json()
        await bot.api.messages.send(peer_id=target_peer, message=f"Тикет #{ticket_id} закрыт. Оцените от 1 до 5:", keyboard=kb, random_id=0)
        await bot.api.messages.send_message_event_answer(event_id=event_id, user_id=user_id, peer_id=peer_id, event_data={"type": "show_snackbar", "text": "Тикет закрыт"})
    elif payload.get("cmd") == "ticket_reply":
        await bot.api.messages.send_message_event_answer(event_id=event_id, user_id=user_id, peer_id=peer_id, event_data={"type": "show_snackbar", "text": "Напиши текст ответа сюда"})
        await bot.api.messages.send(peer_id=peer_id, message=f"Чтобы ответить на тикет #{ticket_id}, напиши:\n/answer {ticket_id} [текст]", random_id=0)

@bot.on.message(regex=r"^[\/\+](answer|ответ)\s+\d+\s+(.+)")
async def answer_ticket(message: Message):
    args = message.text.split(maxsplit=2)
    try: ticket_id = int(args[1])
    except: return await message.answer("Неверный номер тикета.")
    text = args[2]
    cur.execute("SELECT peer_id, status FROM tickets WHERE id=?", (ticket_id,))
    ticket = cur.fetchone()
    if not ticket or ticket[1] == 'closed': return await message.answer("Тикет не найден или закрыт.")
    target_peer = ticket[0]
    if get_user_rank(target_peer, message.from_id) < 60 and message.from_id != ADMIN_ID: return await message.answer("Нужен Главный Админ (60)+.")
    try:
        await bot.api.messages.send(peer_id=target_peer, message=f"💬 Ответ по тикету #{ticket_id}:\n\n{text}", random_id=0)
        await message.answer(f"✅ Отправлено в беседу {target_peer}.")
    except Exception as e: await message.answer(f"Ошибка: {e}")

# ==========================================
# 8. НИКИ, VIP И ЭКОНОМИКА
# ==========================================
@bot.on.chat_message(regex=r"^[\/\+](nick|ник)\s+(.+)")
async def set_nick(message: Message):
    if get_user_rank(message.peer_id, message.from_id) < 60: return await message.answer("Менять ник может только Главный Администратор (60) и выше.")
    name = message.text.split(maxsplit=1)[1]
    if len(name) > 20: return await message.answer("Ник слишком длинный (макс. 20).")
    cur.execute("INSERT OR REPLACE INTO nicknames (peer_id, user_id, nick) VALUES (?, ?, ?)", (message.peer_id, message.from_id, name))
    conn.commit()
    await message.answer(f"✅ Твой ник изменён на: {name}")

@bot.on.chat_message(regex=r"^[\/\+](rnick|снятьник)")
async def del_nick(message: Message):
    if get_user_rank(message.peer_id, message.from_id) < 60: return await message.answer("Удалять ник может только Главный Администратор (60) и выше.")
    cur.execute("DELETE FROM nicknames WHERE peer_id=? AND user_id=?", (message.peer_id, message.from_id))
    conn.commit()
    await message.answer("🗑 Твой ник удалён.")

@bot.on.chat_message(regex=r"^[\/\+](gnick|мойник)")
async def get_nick(message: Message):
    target_id = get_target_id(message) or message.from_id
    if target_id != message.from_id and get_user_rank(message.peer_id, message.from_id) < 40: return await message.answer("❌ Проверять чужие ники может только Администратор (40)+.")
    cur.execute("SELECT nick FROM nicknames WHERE peer_id=? AND user_id=?", (message.peer_id, target_id))
    res = cur.fetchone()
    if res: await message.answer(f"🔍 [id{target_id}|Пользователь] использует ник: **{res[0]}**")
    else: await message.answer(f"❌ У [id{target_id}|пользователя] нет кастомного ника.")

@bot.on.chat_message(regex=r"^[\/\+](понику|findnick)\s+(.+)")
async def find_by_nick(message: Message):
    if get_user_rank(message.peer_id, message.from_id) < 40 and message.from_id != ADMIN_ID: return await message.answer("❌ Поиск по никам доступен только с 40 ранга.")
    query = message.text.split(maxsplit=1)[1]
    cur.execute("SELECT user_id, nick FROM nicknames WHERE peer_id=? AND nick LIKE ?", (message.peer_id, f"%{query}%"))
    results = cur.fetchall()
    if not results: return await message.answer(f"🔍 По запросу «{query}» никого не найдено.")
    text = f"🔍 **Результаты поиска по нику «{query}»:**\n"
    for i, (user_id, nick) in enumerate(results[:10], 1): text += f"{i}. [id{user_id}|{nick}]\n"
    await message.answer(text)

@bot.on.chat_message(regex=r"^[\/\+](setvip|выдатьвип)")
async def set_vip(message: Message):
    if message.from_id != ADMIN_ID: return await message.answer("Только Владелец.")
    target_id = get_target_id(message)
    if not target_id: return await message.answer("Ответь на сообщение.")
    cur.execute("INSERT OR REPLACE INTO vip_users (peer_id, user_id, is_vip) VALUES (?, ?, 1)", (message.peer_id, target_id))
    conn.commit()
    await message.answer(f"💎 [id{target_id}|Пользователю] выдан VIP!")

@bot.on.chat_message(regex=r"^[\/\+](delvip|снятьвип)")
async def del_vip(message: Message):
    if message.from_id != ADMIN_ID: return await message.answer("Только Владелец.")
    target_id = get_target_id(message)
    if not target_id: return await message.answer("Ответь на сообщение.")
    cur.execute("UPDATE vip_users SET is_vip=0 WHERE peer_id=? AND user_id=?", (message.peer_id, target_id))
    conn.commit()
    await message.answer(f"VIP снят с [id{target_id}|пользователя].")

@bot.on.chat_message(regex=r"^[\/\+](color|цвет)\s+(.+)")
async def set_color(message: Message):
    if not is_vip(message.peer_id, message.from_id): return await message.answer("Установка цвета доступна только VIP-пользователям! 💎")
    color_name = message.text.split(maxsplit=1)[1].lower()
    colors = {"красный": "🔴", "синий": "🔵", "зеленый": "🟢", "желтый": "🟡", "фиолетовый": "🟣", "черный": "⚫", "белый": "⚪", "red": "🔴", "blue": "🔵", "green": "🟢", "yellow": "🟡", "purple": "🟣", "black": "⚫", "white": "⚪"}
    chosen_color = colors.get(color_name)
    if not chosen_color: return await message.answer("Доступные цвета: красный, синий, зеленый, желтый, фиолетовый, черный, белый.")
    cur.execute("INSERT OR REPLACE INTO vip_users (peer_id, user_id, color) VALUES (?, ?, ?)", (message.peer_id, message.from_id, chosen_color))
    conn.commit()
    await message.answer(f"✅ Твой цвет изменен на {chosen_color} {color_name}!")

@bot.on.chat_message(regex=r"^[\/\+](balance|баланс)")
async def check_balance(message: Message):
    target_id = get_target_id(message) or message.from_id
    cur.execute("SELECT coins FROM balances WHERE peer_id=? AND user_id=?", (message.peer_id, target_id))
    res = cur.fetchone()
    coins = res[0] if res else 0
    await message.answer(f"💳 Баланс [id{target_id}|пользователя]: **{coins} 🪙 монеток**.")

@bot.on.chat_message(regex=r"^[\/\+](top|топ)")
async def top_rich(message: Message):
    cur.execute("SELECT user_id, coins FROM balances WHERE peer_id=? ORDER BY coins DESC LIMIT 10", (message.peer_id,))
    rows = cur.fetchall()
    if not rows: return await message.answer("Пока ни у кого нет монеток.")
    text = "🏆 **Топ-10 богачей чата:**\n"
    for i, (user_id, coins) in enumerate(rows, 1): text += f"{i}. [id{user_id}|Пользователь] — {coins} 🪙\n"
    await message.answer(text)

@bot.on.chat_message(regex=r"^[\/\+](casino|казино)\s+\d+")
async def casino(message: Message):
    bet_amount = int(re.findall(r'\d+', message.text)[-1])
    if bet_amount < 10: return await message.answer("Минимальная ставка — 10 монеток 🪙.")
    cur.execute("SELECT coins FROM balances WHERE peer_id=? AND user_id=?", (message.peer_id, message.from_id))
    res = cur.fetchone()
    coins = res[0] if res else 0
    if coins < bet_amount: return await message.answer(f"❌ Недостаточно средств! У тебя только {coins} 🪙.")
    win = random.choice([True, False])
    if win:
        cur.execute("UPDATE balances SET coins = coins + ? WHERE peer_id=? AND user_id=?", (bet_amount, message.peer_id, message.from_id))
        conn.commit()
        await message.answer(f"🎰 Крутим рулетку...\n\n🎉 **ПОБЕДА!** Ты выиграл **{bet_amount} 🪙**! Твой баланс: {coins + bet_amount}.")
    else:
        cur.execute("UPDATE balances SET coins = coins - ? WHERE peer_id=? AND user_id=?", (bet_amount, message.peer_id, message.from_id))
        conn.commit()
        await message.answer(f"🎰 Крутим рулетку...\n\n💀 **ПРОИГРЫШ...** Ты потерял **{bet_amount} 🪙**. Твой баланс: {coins - bet_amount}.")

@bot.on.chat_message(regex=r"^[\/\+](duel|дуэль)\s+\d+")
async def duel(message: Message):
    bet_amount = int(re.findall(r'\d+', message.text)[-1])
    if bet_amount < 10: return await message.answer("Минимальная ставка для дуэли — 10 🪙.")
    target_id = get_target_id(message)
    if not target_id: return await message.answer("❌ Ответь на сообщение того, кого хочешь вызвать на дуэль.")
    if target_id == message.from_id: return await message.answer("Ты не можешь вызвать сам себя.")
    if target_id == ADMIN_ID: return await message.answer("❌ Нельзя вызывать Владельца на дуэль.")
    cur.execute("SELECT coins FROM balances WHERE peer_id=? AND user_id=?", (message.peer_id, message.from_id))
    coins_me = cur.fetchone()[0] if cur.fetchone() else 0
    cur.execute("SELECT coins FROM balances WHERE peer_id=? AND user_id=?", (message.peer_id, target_id))
    coins_target = cur.fetchone()[0] if cur.fetchone() else 0
    if coins_me < bet_amount: return await message.answer(f"❌ У тебя недостаточно средств ({coins_me} 🪙).")
    if coins_target < bet_amount: return await message.answer(f"❌ У соперника недостаточно средств ({coins_target} 🪙).")
    winner = random.choice([message.from_id, target_id])
    if winner == message.from_id:
        cur.execute("UPDATE balances SET coins = coins + ? WHERE peer_id=? AND user_id=?", (bet_amount, message.peer_id, message.from_id))
        cur.execute("UPDATE balances SET coins = coins - ? WHERE peer_id=? AND user_id=?", (bet_amount, message.peer_id, target_id))
        conn.commit()
        await message.answer(f"⚔️ **ДУЭЛЬ!**\n\n[id{message.from_id}|Пользователь] победил [id{target_id}|Пользователя] и забрал **{bet_amount} 🪙**!")
    else:
        cur.execute("UPDATE balances SET coins = coins - ? WHERE peer_id=? AND user_id=?", (bet_amount, message.peer_id, message.from_id))
        cur.execute("UPDATE balances SET coins = coins + ? WHERE peer_id=? AND user_id=?", (bet_amount, message.peer_id, target_id))
        conn.commit()
        await message.answer(f"⚔️ **ДУЭЛЬ!**\n\n[id{target_id}|Пользователь] победил [id{message.from_id}|Пользователя] и забрал **{bet_amount} 🪙**!")

@bot.on.chat_message(regex=r"^[\/\+](transfer|перевод)\s+\d+")
async def transfer_coins(message: Message):
    amount = int(re.findall(r'\d+', message.text)[-1])
    if amount <= 0: return await message.answer("Сумма перевода должна быть больше нуля.")
    target_id = get_target_id(message)
    if not target_id: return await message.answer("❌ Ответь на сообщение того, кому хочешь перевести монетки.")
    if target_id == message.from_id: return await message.answer("Нельзя переводить монетки самому себе.")
    cur.execute("SELECT coins FROM balances WHERE peer_id=? AND user_id=?", (message.peer_id, message.from_id))
    res = cur.fetchone()
    my_coins = res[0] if res else 0
    if my_coins < amount: return await message.answer(f"❌ У тебя недостаточно средств. У тебя только {my_coins} 🪙.")
    cur.execute("UPDATE balances SET coins = coins - ? WHERE peer_id=? AND user_id=?", (amount, message.peer_id, message.from_id))
    cur.execute("INSERT INTO balances (peer_id, user_id, coins) VALUES (?, ?, ?) ON CONFLICT(peer_id, user_id) DO UPDATE SET coins = coins + ?", (message.peer_id, target_id, amount, amount))
    conn.commit()
    await message.answer(f"💸 [id{message.from_id}|Пользователь] перевел **{amount} 🪙** [id{target_id}|Пользователю].")

@bot.on.chat_message(regex=r"^[\/\+](givemoney|выдатьмонеты)\s+-?\d+")
async def give_money(message: Message):
    if message.from_id != ADMIN_ID: return await message.answer("❌ Выдавать монетки может только Владелец лично.")
    amount = int(re.findall(r'-?\d+', message.text)[-1])
    target_id = get_target_id(message)
    if not target_id: return await message.answer("❌ Ответь на сообщение того, кому хочешь выдать монетки.")
    if amount < 0:
        cur.execute("UPDATE balances SET coins = max(0, coins + ?) WHERE peer_id=? AND user_id=?", (amount, message.peer_id, target_id))
        conn.commit()
        await message.answer(f"📉 С баланса [id{target_id}|пользователя] списано {abs(amount)} 🪙.")
    else:
        cur.execute("INSERT INTO balances (peer_id, user_id, coins) VALUES (?, ?, ?) ON CONFLICT(peer_id, user_id) DO UPDATE SET coins = coins + ?", (message.peer_id, target_id, amount, amount))
        conn.commit()
        await message.answer(f"📈 Пользователю [id{target_id}|пользователь] начислено {amount} 🪙 монеток!")

# ==========================================
# ЗАПУСК
# ==========================================
if __name__ == "__main__":
    print("Бот запущен! Все системы в норме.")
    bot.run_forever()
