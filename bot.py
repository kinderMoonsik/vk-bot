import sqlite3
import re
import time
import random
import os
from vkbottle.bot import Bot, Message
from vkbottle import Keyboard, KeyboardButtonColor, Callback

# ==========================================
# 1. НАСТРОЙКИ
# ==========================================
TOKEN = os.getenv("MAGNIT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
bot = Bot(token=TOKEN)

RANKS = {
    0: "Участник", 1: "Модератор", 2: "Администратор", 3: "Куратор",
    4: "ЗГА", 5: "Главный Администратор", 6: "Зам Специального",
    7: "Специальный Администратор", 8: "Заместитель Владельца", 9: "Владелец"
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
conn.commit()

def get_user_rank(peer_id, user_id):
    if user_id == ADMIN_ID: 
        return 9
    cur.execute("SELECT rank FROM roles WHERE peer_id=? AND user_id=?", (peer_id, user_id))
    res = cur.fetchone()
    return res[0] if res else 0

def get_target_id(message: Message):
    if message.reply_message: 
        return message.reply_message.from_id
    if message.fwd_messages: 
        return message.fwd_messages[0].from_id
    match = re.search(r'id(\d+)', message.text)
    if match: 
        return int(match.group(1))
    match_num = re.findall(r'\d+', message.text)
    if match_num: 
        return int(match_num[0])
    return None

# ==========================================
# 3. ФОНОВЫЕ ПРОВЕРКИ
# ==========================================
@bot.on.chat_message()
async def background_handler(message: Message):
    if message.from_id == ADMIN_ID:
        if message.text and message.text.startswith('/'): 
            return
        try:
            cur.execute("INSERT INTO messages (peer_id, user_id, count) VALUES (?, ?, 1) ON CONFLICT(peer_id, user_id) DO UPDATE SET count = count + 1", (message.peer_id, message.from_id))
            conn.commit()
        except: 
            pass
        return

    cur.execute("SELECT user_id FROM sysbans WHERE user_id=?", (message.from_id,))
    if cur.fetchone():
        try:
            await bot.api.messages.delete(message_ids=message.id, delete_for_all=1)
            await bot.api.messages.remove_chat_user(chat_id=message.chat_id, user_id=message.from_id)
        except: 
            pass
        return

    cur.execute("SELECT user_id FROM bans WHERE peer_id=? AND user_id=?", (message.peer_id, message.from_id))
    if cur.fetchone():
        try: 
            await bot.api.messages.remove_chat_user(chat_id=message.chat_id, user_id=message.from_id)
        except: 
            pass
        return

    cur.execute("SELECT expire FROM mutes WHERE peer_id=? AND user_id=?", (message.peer_id, message.from_id))
    mute = cur.fetchone()
    if mute:
        if time.time() < mute[0]:
            try: 
                await bot.api.messages.delete(message_ids=message.id, delete_for_all=1)
            except: 
                pass
            return
        else:
            cur.execute("DELETE FROM mutes WHERE peer_id=? AND user_id=?", (message.peer_id, message.from_id))
            conn.commit()

    if message.text and message.text.startswith('/'): 
        return
    try:
        cur.execute("INSERT INTO messages (peer_id, user_id, count) VALUES (?, ?, 1) ON CONFLICT(peer_id, user_id) DO UPDATE SET count = count + 1", (message.peer_id, message.from_id))
        conn.commit()
    except: 
        pass

# ==========================================
# 4. КОМАНДЫ
# ==========================================
@bot.on.chat_message(text="/ping")
async def ping(message: Message): 
    await message.answer("Pong! Я на месте.")

@bot.on.chat_message(text="/getid")
async def get_id(message: Message): 
    await message.answer(f"Твой ID: {message.from_id}\nID чата: {message.peer_id}")

@bot.on.chat_message(text="/stats")
async def stats(message: Message):
    target_id = get_target_id(message) or message.from_id
    cur.execute("SELECT count FROM messages WHERE peer_id=? AND user_id=?", (message.peer_id, target_id))
    res = cur.fetchone()
    count = res[0] if res else 0
    rank = get_user_rank(message.peer_id, target_id)
    cur.execute("SELECT count FROM warns WHERE peer_id=? AND user_id=?", (message.peer_id, target_id))
    warns = cur.fetchone()
    warns = warns[0] if warns else 0
    
    cur.execute("SELECT nick FROM nicknames WHERE peer_id=? AND user_id=?", (message.peer_id, target_id))
    nick_res = cur.fetchone()
    display_name = nick_res[0] if nick_res else f"[id{target_id}|пользователя]"
    
    await message.answer(f"📊 Статистика {display_name}:\nСообщений: {count}\nРанг: {rank} ({RANKS.get(rank)})\nВарны: {warns}/3")

@bot.on.chat_message(text="/setrank")
async def set_rank(message: Message):
    my_rank = get_user_rank(message.peer_id, message.from_id)
    if my_rank < 4: 
        return await message.answer("Выдавать ранги может только ЗГА (4) и выше.")
    target_id = get_target_id(message)
    try: 
        rank_to_give = int(message.text.split()[-1])
    except: 
        return await message.answer("Напиши ранг числом. Пример: ответь на сообщение `/setrank 2`")
    
    if not target_id or target_id == ADMIN_ID: 
        return await message.answer("Не понял кому. Или ты пытаешься выдать ранг Владельцу.")
    
    if my_rank == 9: 
        max_limit = 8
    elif my_rank == 8: 
        max_limit = 7
    elif my_rank == 6: 
        max_limit = 5
    elif my_rank in [4, 5]: 
        max_limit = 3
    else: 
        max_limit = 0

    if rank_to_give > max_limit or rank_to_give >= my_rank:
        return await message.answer(f"Ты можешь выдавать ранги только до {max_limit}.")

    cur.execute("INSERT OR REPLACE INTO roles (peer_id, user_id, rank) VALUES (?, ?, ?)", (message.peer_id, target_id, rank_to_give))
    conn.commit()
    await message.answer(f"Пользователю {target_id} выдан ранг {rank_to_give} ({RANKS.get(rank_to_give)}).")

@bot.on.chat_message(text="/kick")
async def kick_user(message: Message):
    if get_user_rank(message.peer_id, message.from_id) < 1: 
        return await message.answer("Нужен Модератор+.")
    target_id = get_target_id(message)
    if target_id:
        try:
            await bot.api.messages.remove_chat_user(chat_id=message.chat_id, user_id=target_id)
            await message.answer(f"Пользователь {target_id} исключён.")
        except Exception as e: 
            await message.answer(f"Ошибка: {e}")

@bot.on.chat_message(text="/ban")
async def ban_user(message: Message):
    if get_user_rank(message.peer_id, message.from_id) < 2: 
        return await message.answer("Нужен Администратор+.")
    target_id = get_target_id(message)
    if target_id:
        try: 
            await bot.api.messages.remove_chat_user(chat_id=message.chat_id, user_id=target_id)
        except: 
            pass
        cur.execute("INSERT OR IGNORE INTO bans (peer_id, user_id) VALUES (?, ?)", (message.peer_id, target_id))
        conn.commit()
        await message.answer(f"Пользователь {target_id} забанен в этом чате.")

@bot.on.chat_message(text="/mute")
async def mute_user(message: Message):
    if get_user_rank(message.peer_id, message.from_id) < 1: 
        return await message.answer("Нужен Модератор+.")
    target_id = get_target_id(message)
    time_match = re.findall(r'\d+', message.text.split()[-1])
    minutes = int(time_match[0]) if time_match else 10
    if target_id:
        expire = int(time.time()) + (minutes * 60)
        cur.execute("INSERT OR REPLACE INTO mutes (peer_id, user_id, expire) VALUES (?, ?, ?)", (message.peer_id, target_id, expire))
        conn.commit()
        await message.answer(f"Пользователь {target_id} замучен на {minutes} мин.")

@bot.on.chat_message(text="/warn")
async def warn_user(message: Message):
    if get_user_rank(message.peer_id, message.from_id) < 1: 
        return await message.answer("Нужен Модератор+.")
    target_id = get_target_id(message)
    if target_id:
        cur.execute("INSERT OR IGNORE INTO warns (peer_id, user_id, count) VALUES (?, ?, 0)", (message.peer_id, target_id))
        cur.execute("UPDATE warns SET count = count + 1 WHERE peer_id=? AND user_id=?", (message.peer_id, target_id))
        conn.commit()
        cur.execute("SELECT count FROM warns WHERE peer_id=? AND user_id=?", (message.peer_id, target_id))
        count = cur.fetchone()[0]
        if count >= 3:
            try: 
                await bot.api.messages.remove_chat_user(chat_id=message.chat_id, user_id=target_id)
            except: 
                pass
            cur.execute("INSERT OR IGNORE INTO bans (peer_id, user_id) VALUES (?, ?)", (message.peer_id, target_id))
            conn.commit()
            await message.answer(f"Пользователь {target_id} получил 3/3 варна и забанен.")
        else: 
            await message.answer(f"Пользователь {target_id} получил варн. Всего: {count}/3.")

@bot.on.chat_message(text="/unban")
async def unban_user(message: Message):
    if get_user_rank(message.peer_id, message.from_id) < 2: 
        return await message.answer("Нужен Администратор+.")
    target_id = get_target_id(message)
    if target_id:
        cur.execute("DELETE FROM bans WHERE peer_id=? AND user_id=?", (message.peer_id, target_id))
        conn.commit()
        await message.answer(f"Пользователь {target_id} разбанен в этом чате.")

@bot.on.chat_message(text="/unmute")
async def unmute_user(message: Message):
    if get_user_rank(message.peer_id, message.from_id) < 1: 
        return await message.answer("Нужен Модератор+.")
    target_id = get_target_id(message)
    if target_id:
        cur.execute("DELETE FROM mutes WHERE peer_id=? AND user_id=?", (message.peer_id, target_id))
        conn.commit()
        await message.answer(f"Пользователь {target_id} размучен.")

@bot.on.chat_message(text="/unwarn")
async def unwarn_user(message: Message):
    if get_user_rank(message.peer_id, message.from_id) < 1: 
        return await message.answer("Нужен Модератор+.")
    target_id = get_target_id(message)
    if target_id:
        cur.execute("UPDATE warns SET count = max(0, count - 1) WHERE peer_id=? AND user_id=?", (message.peer_id, target_id))
        conn.commit()
        await message.answer(f"С пользователя {target_id} снят 1 варн.")

@bot.on.chat_message(text="/sysban")
async def sysban_user(message: Message):
    if get_user_rank(message.peer_id, message.from_id) < 8: 
        return await message.answer("Нужен ранг Заместителя (8+).")
    target_id = get_target_id(message)
    if target_id:
        cur.execute("INSERT OR IGNORE INTO sysbans (user_id) VALUES (?)", (target_id,))
        conn.commit()
        try: 
            await bot.api.messages.remove_chat_user(chat_id=message.chat_id, user_id=target_id)
        except: 
            pass
        await message.answer(f"⛔ Пользователь {target_id} забанен ГЛОБАЛЬНО.")

@bot.on.chat_message(text="/unsysban")
async def unsysban_user(message: Message):
    if get_user_rank(message.peer_id, message.from_id) < 8: 
        return await message.answer("Нужен ранг Заместителя (8+).")
    target_id = get_target_id(message)
    if target_id:
        cur.execute("DELETE FROM sysbans WHERE user_id=?", (target_id,))
        conn.commit()
        await message.answer(f"Пользователь {target_id} разбанен ГЛОБАЛЬНО.")

@bot.on.chat_message(text="/zov <text>")
async def zov_broadcast(message: Message, text: str):
    if get_user_rank(message.peer_id, message.from_id) < 8: 
        return await message.answer("Рассылка доступна только с ранга Заместителя Владельца (8)+.")
    try: 
        conversations = await bot.api.messages.get_conversations(peer_types=["chat"], count=200)
    except Exception as e: 
        return await message.answer(f"Ошибка: {e}")
    
    sent, errors = 0, 0
    for conv in conversations.items:
        try:
            await bot.api.messages.send(peer_id=conv.peer.id, message=text, random_id=random.randint(1, 999999))
            sent += 1
        except: 
            errors += 1
    await message.answer(f"📢 Рассылка завершена.\nОтправлено: {sent}\nОшибок: {errors}")

# ==========================================
# 5. СИСТЕМА ЖАЛОБ (Создают все, отвечают ЗГА+)
# ==========================================

# Создание тикета (Доступно всем пользователям)
@bot.on.chat_message(text="/report <text>")
async def create_ticket(message: Message, text: str):
    if not text:
        return await message.answer("Использование: /report [текст]")

    cur.execute("INSERT INTO tickets (peer_id, user_id, text, status) VALUES (?, ?, ?, 'open')", 
                (message.peer_id, message.from_id, text))
    conn.commit()
    ticket_id = cur.lastrowid

    await message.answer(f"Тикет #{ticket_id} создан. Ожидайте ответа руководства.")

    # Ищем всех, у кого ранг 4+ в этой беседе (ЗГА, Главный админ и т.д.)
    cur.execute("SELECT user_id FROM roles WHERE peer_id=? AND rank >= 4", (message.peer_id,))
    admins = [row[0] for row in cur.fetchall()]
    
    if ADMIN_ID not in admins:
        admins.append(ADMIN_ID)

    # Отправляем уведомления админам в ЛС
    for admin_id in admins:
        try:
            kb = (
                Keyboard(inline=True)
                .add(Callback("✍️ Ответить", {"cmd": "ticket_reply", "ticket_id": ticket_id}), color=KeyboardButtonColor.PRIMARY)
                .add(Callback("🔒 Закрыть", {"cmd": "ticket_close", "ticket_id": ticket_id}), color=KeyboardButtonColor.NEGATIVE)
            ).get_json()

            await bot.api.messages.send(
                peer_id=admin_id,
                message=f"🔔 **Новый тикет #{ticket_id}**\n"
                        f"Чат: {message.peer_id}\n"
                        f"От: [id{message.from_id}|Пользователь]\n\n"
                        f"Текст: {text}",
                keyboard=kb,
                random_id=0
            )
        except Exception:
            pass

# Обработка кнопок в ЛС (Только ЗГА+)
@bot.on.raw_event("message_event")
async def ticket_admin_handler(event: dict):
    payload = event.get("object", {}).get("payload", {})
    if payload.get("cmd") not in ["ticket_reply", "ticket_close"]:
        return

    event_id = event.get("object", {}).get("event_id")
    user_id = event.get("object", {}).get("user_id")
    peer_id = event.get("object", {}).get("peer_id")
    
    ticket_id = payload.get("ticket_id")
    cur.execute("SELECT peer_id, user_id, status FROM tickets WHERE id=?", (ticket_id,))
    ticket = cur.fetchone()

    if not ticket or ticket[2] == 'closed':
        return await bot.api.messages.send_message_event_answer(
            event_id=event_id, user_id=user_id, peer_id=peer_id,
            event_data={"type": "show_snackbar", "text": "Тикет не найден или уже закрыт"}
        )

    target_peer, target_user, status = ticket

    # Проверка ранга (ЗГА 4+)
    my_rank = get_user_rank(target_peer, user_id)
    if my_rank < 4 and user_id != ADMIN_ID:
        return await bot.api.messages.send_message_event_answer(
            event_id=event_id, user_id=user_id, peer_id=peer_id,
            event_data={"type": "show_snackbar", "text": "У вас нет прав (нужен ЗГА+)"}
        )

    if payload.get("cmd") == "ticket_close":
        cur.execute("UPDATE tickets SET status='closed' WHERE id=?", (ticket_id,))
        conn.commit()

        # Кнопки оценки для пользователя
        kb = (
            Keyboard(inline=True)
            .add(Callback("1", {"cmd": "rate", "ticket_id": ticket_id, "score": 1}), color=KeyboardButtonColor.PRIMARY)
            .add(Callback("2", {"cmd": "rate", "ticket_id": ticket_id, "score": 2}), color=KeyboardButtonColor.PRIMARY)
            .add(Callback("3", {"cmd": "rate", "ticket_id": ticket_id, "score": 3}), color=KeyboardButtonColor.PRIMARY)
            .add(Callback("4", {"cmd": "rate", "ticket_id": ticket_id, "score": 4}), color=KeyboardButtonColor.PRIMARY)
            .add(Callback("5", {"cmd": "rate", "ticket_id": ticket_id, "score": 5}), color=KeyboardButtonColor.PRIMARY)
        ).get_json()

        await bot.api.messages.send(
            peer_id=target_peer,
            message=f"Тикет #{ticket_id} закрыт руководством.\nОцените нашу работу от 1 до 5:",
            keyboard=kb,
            random_id=0
        )
        
        await bot.api.messages.send_message_event_answer(
            event_id=event_id, user_id=user_id, peer_id=peer_id,
            event_data={"type": "show_snackbar", "text": "Тикет закрыт"}
        )

    elif payload.get("cmd") == "ticket_reply":
        await bot.api.messages.send_message_event_answer(
            event_id=event_id, user_id=user_id, peer_id=peer_id,
            event_data={"type": "show_snackbar", "text": "Напиши текст ответа в этот чат"}
        )
        await bot.api.messages.send(
            peer_id=peer_id, 
            message=f"Чтобы ответить на тикет #{ticket_id}, напиши сюда:\n/answer {ticket_id} [твой текст]",
            random_id=0
        )

# Ответ на тикет (Только ЗГА+)
@bot.on.message(text="/answer <ticket_id> <text>")
async def answer_ticket(message: Message, ticket_id: int, text: str):
    cur.execute("SELECT peer_id, user_id, status FROM tickets WHERE id=?", (ticket_id,))
    ticket = cur.fetchone()

    if not ticket:
        return await message.answer("Тикет не найден.")
    
    target_peer, target_user, status = ticket

    if status == 'closed':
        return await message.answer("Этот тикет уже закрыт.")

    # Проверка ранга отвечающего
    my_rank = get_user_rank(target_peer, message.from_id)
    if my_rank < 4 and message.from_id != ADMIN_ID:
        return await message.answer("Отвечать на тикеты может только ЗГА (4)+.")

    try:
        await bot.api.messages.send(
            peer_id=target_peer,
            message=f"💬 **Ответ по тикету #{ticket_id}**\n\n"
                    f"{text}\n\n"
                    f"Ваш тикет всё ещё открыт. Если у вас есть дополнения, напишите /report",
            random_id=0
        )
        await message.answer(f"✅ Ответ отправлен в беседу {target_peer}.")
    except Exception as e:
        await message.answer(f"Не удалось отправить ответ: {e}")

# ==========================================
# 6. СИСТЕМА НИКОВ (Только ЗГА (4) и выше)
# ==========================================
@bot.on.chat_message(text="/nick <name>")
async def set_nick(message: Message, name: str):
    if get_user_rank(message.peer_id, message.from_id) < 4:
        return await message.answer("Менять ник может только ЗГА (4) и выше.")
        
    if len(name) > 20:
        return await message.answer("Ник слишком длинный. Максимум 20 символов.")
    
    cur.execute("INSERT OR REPLACE INTO nicknames (peer_id, user_id, nick) VALUES (?, ?, ?)", 
                (message.peer_id, message.from_id, name))
    conn.commit()
    await message.answer(f"✅ Твой ник в этой беседе изменён на: {name}")

@bot.on.chat_message(text="/rnick")
async def del_nick(message: Message):
    if get_user_rank(message.peer_id, message.from_id) < 4:
        return await message.answer("Удалять ник может только ЗГА (4) и выше.")

    cur.execute("DELETE FROM nicknames WHERE peer_id=? AND user_id=?", (message.peer_id, message.from_id))
    conn.commit()
    await message.answer("🗑 Твой ник удалён. Теперь я буду звать тебя по имени из профиля ВК.")

# ==========================================
# ЗАПУСК
# ==========================================
if __name__ == "__main__":
    print("Бот запущен! Иерархия 9 рангов, Тикет-система и Ники (4+) активны.")
    bot.run_forever()
