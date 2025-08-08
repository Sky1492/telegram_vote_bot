import json
import os
import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
import openpyxl

API_TOKEN = "8213391771:AAFVwi2sk5F6sHB-nq0ehWPz9CnsObCPS7U"
ADMIN_IDS = [568126852]  # додай інші ID за потреби

DATA_FILE = "data/users.json"
POLL_FILE = "data/polls.json"
os.makedirs("data", exist_ok=True)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

users = {}
polls = {}

# --- Завантаження/збереження ---
def load_users():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_users():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def load_polls():
    if os.path.exists(POLL_FILE):
        with open(POLL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_polls():
    with open(POLL_FILE, "w", encoding="utf-8") as f:
        json.dump(polls, f, ensure_ascii=False, indent=2)

users = load_users()
polls = load_polls()

# --- Таймер ---
async def poll_timer(poll_id, duration):
    await asyncio.sleep(duration)
    if poll_id in polls and polls[poll_id]["active"]:
        await finish_poll(poll_id, auto=True)

# --- Завершення ---
async def finish_poll(poll_id, auto=False):
    poll = polls.get(poll_id)
    if not poll:
        return
    poll["active"] = False
    save_polls()

    results = {}
    total_votes = len(poll["votes"])
    for vote in poll["votes"].values():
        results[vote] = results.get(vote, 0) + 1

    text = f"{'⏰ Час голосування вичерпано!' if auto else '🏁 Голосування завершено достроково!'}\n\n"
    text += f"📌 {poll['question']}\n\n"

    # Підсумки по варіантах
    for opt in poll["options"]:
        count = results.get(opt, 0)
        percent = (count / total_votes * 100) if total_votes else 0
        text += f"{opt}: {count} голос(ів) ({percent:.1f}%)\n"

    # Підсумки по будинках
    house_stats = {}
    for uid, choice in poll["votes"].items():
        user = users.get(str(uid), {})
        house = user.get("house", "Невідомо")
        house_stats[house] = house_stats.get(house, 0) + 1

    text += "\n🏠 Статистика по будинках:\n"
    for house, count in house_stats.items():
        percent = (count / total_votes * 100) if total_votes else 0
        text += f"Будинок {house}: {count} ({percent:.1f}%)\n"

    for uid, data in users.items():
        if isinstance(data, dict) and data.get("approved"):
            try:
                await bot.send_message(uid, text)
            except:
                pass

# --- /status ---
@dp.message_handler(commands=["status"])
async def poll_status(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.answer("⛔ Лише адміністратор може переглядати результати.")

    if not polls:
        return await message.answer("❌ Немає голосувань.")

    for poll_id, poll in polls.items():
        results = {}
        total_votes = len(poll["votes"])
        for vote in poll["votes"].values():
            results[vote] = results.get(vote, 0) + 1

        text = f"📊 {poll['question']} ({'Активне' if poll['active'] else 'Завершене'})\n"
        for opt in poll["options"]:
            count = results.get(opt, 0)
            percent = (count / total_votes * 100) if total_votes else 0
            text += f"{opt}: {count} ({percent:.1f}%)\n"
        text += "\n"
        await message.answer(text)

# --- /stopvote ---
@dp.message_handler(commands=["stopvote"])
async def stop_vote(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.answer("⛔ Лише адміністратор може завершити голосування.")

    if not polls:
        return await message.answer("❌ Немає голосувань.")

    buttons = InlineKeyboardMarkup()
    for poll_id, poll in polls.items():
        if poll["active"]:
            buttons.add(InlineKeyboardButton(poll["question"], callback_data=f"stop_{poll_id}"))

    if not buttons.inline_keyboard:
        return await message.answer("❌ Немає активних голосувань.")
    await message.answer("Оберіть голосування для зупинки:", reply_markup=buttons)

@dp.callback_query_handler(lambda c: c.data.startswith("stop_"))
async def stop_poll_callback(call: types.CallbackQuery):
    poll_id = call.data.split("_", 1)[1]
    await finish_poll(poll_id, auto=False)
    await call.message.answer("✅ Голосування зупинено.")

# --- Реєстрація ---
@dp.message_handler(commands=["start"])
async def start_cmd(message: types.Message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Почати"))
    await message.answer("👋 Вітаємо у боті для голосувань!", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "Почати")
async def agree(message: types.Message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📱 Надати номер телефону", request_contact=True))
    await message.answer("ℹ️ Надішліть свій номер телефону для підтвердження.", reply_markup=kb)

@dp.message_handler(content_types=types.ContentType.CONTACT)
async def get_contact(message: types.Message):
    uid = str(message.from_user.id)
    users[uid] = {"id": uid, "phone": message.contact.phone_number, "step": "fio"}
    save_users()
    await message.answer("Введіть ПІБ, номер будинку та квартири (через кому):", reply_markup=types.ReplyKeyboardRemove())

@dp.message_handler(lambda m: users.get(str(m.from_user.id), {}).get("step") == "fio")
async def get_fio(message: types.Message):
    uid = str(message.from_user.id)
    parts = [p.strip() for p in message.text.split(",")]
    if len(parts) < 3:
        return await message.answer("❌ Формат: ПІБ, будинок, квартира")
    users[uid].update({"fio": parts[0], "house": parts[1], "flat": parts[2], "approved": True, "step": None})
    save_users()
    await message.answer("✅ Ви зареєстровані!")

# --- Нове голосування ---
@dp.message_handler(commands=["newpoll"])
async def create_poll(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.answer("⛔ Лише адміністратор може створювати голосування.")
    poll_id = str(len(polls) + 1)
    polls[poll_id] = {"question": None, "options": [], "end_time": None, "votes": {}, "active": True}
    users["poll_step"] = {"id": poll_id, "stage": "question"}
    save_users()
    save_polls()
    await message.answer("🗳 Введіть питання:")

@dp.message_handler(lambda m: isinstance(users.get("poll_step"), dict) and users["poll_step"]["stage"] == "question")
async def poll_question(message: types.Message):
    poll_id = users["poll_step"]["id"]
    polls[poll_id]["question"] = message.text
    users["poll_step"]["stage"] = "options"
    save_users()
    save_polls()
    await message.answer("✏ Введіть варіанти через кому:")

@dp.message_handler(lambda m: isinstance(users.get("poll_step"), dict) and users["poll_step"]["stage"] == "options")
async def poll_options(message: types.Message):
    poll_id = users["poll_step"]["id"]
    polls[poll_id]["options"] = [o.strip() for o in message.text.split(",") if o.strip()]
    users["poll_step"]["stage"] = "duration"
    save_users()
    save_polls()
    await message.answer("⏱ Вкажіть тривалість у хвилинах:")

@dp.message_handler(lambda m: isinstance(users.get("poll_step"), dict) and users["poll_step"]["stage"] == "duration")
async def poll_duration(message: types.Message):
    try:
        minutes = int(message.text)
    except:
        return await message.answer("❌ Введіть число.")

    poll_id = users["poll_step"]["id"]
    polls[poll_id]["end_time"] = (datetime.now() + timedelta(minutes=minutes)).isoformat()
    users.pop("poll_step", None)
    save_users()
    save_polls()

    kb = InlineKeyboardMarkup()
    for opt in polls[poll_id]["options"]:
        kb.add(InlineKeyboardButton(opt, callback_data=f"vote_{poll_id}_{opt}"))

    for uid, data in users.items():
        if isinstance(data, dict) and data.get("approved"):
            try:
                await bot.send_message(uid, f"🗳 {polls[poll_id]['question']}", reply_markup=kb)
            except:
                pass

    asyncio.create_task(poll_timer(poll_id, minutes * 60))
    await message.answer("✅ Голосування створене!")

# --- Голосування ---
@dp.callback_query_handler(lambda c: c.data.startswith("vote_"))
async def vote_handler(call: types.CallbackQuery):
    _, poll_id, option = call.data.split("_", 2)
    poll = polls.get(poll_id)
    if not poll or not poll["active"] or datetime.now() > datetime.fromisoformat(poll["end_time"]):
        return await call.answer("⛔ Голосування закрите.", show_alert=True)

    user = users.get(str(call.from_user.id))
    if not user:
        return await call.answer("⛔ Ви не зареєстровані.", show_alert=True)

    # Один голос з квартири
    for uid, choice in poll["votes"].items():
        if users.get(str(uid), {}).get("flat") == user.get("flat") and users.get(str(uid), {}).get("house") == user.get("house"):
            return await call.answer("⛔ З вашої квартири вже голосували.", show_alert=True)

    poll["votes"][call.from_user.id] = option
    save_polls()
    await call.answer(f"✅ Ви проголосували: {option}", show_alert=True)

# --- Експорт ---
@dp.message_handler(commands=["export"])
async def export_results(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.answer("⛔ Лише адміністратор може експортувати.")

    if not polls:
        return await message.answer("❌ Немає голосувань.")

    for poll_id, poll in polls.items():
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["ID", "ПІБ", "Будинок", "Квартира", "Голос"])
        for uid, vote in poll["votes"].items():
            data = users.get(str(uid), {})
            ws.append([uid, data.get("fio", ""), data.get("house", ""), data.get("flat", ""), vote])
        file_path = f"results_{poll_id}.xlsx"
        wb.save(file_path)
        await message.answer_document(open(file_path, "rb"))

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
