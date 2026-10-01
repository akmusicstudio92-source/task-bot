import asyncio
import logging
import os
import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

# ============ CONFIG ============
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "5143070114"))
MIN_WITHDRAW = 50
DB_NAME = "bot.db"
# ================================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ============ DATABASE ============
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, balance REAL DEFAULT 0)")
        await db.execute("CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, link TEXT, reward REAL)")
        await db.execute("CREATE TABLE IF NOT EXISTS completed (user_id INTEGER, task_id INTEGER)")
        await db.execute("CREATE TABLE IF NOT EXISTS withdrawals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, upi TEXT, amount REAL, status TEXT DEFAULT 'pending')")
        await db.commit()

async def add_user(uid, uname):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (uid, uname))
        await db.commit()

async def get_balance(uid):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT balance FROM users WHERE user_id=?", (uid,)) as c:
            r = await c.fetchone()
            return r[0] if r else 0

async def add_balance(uid, amt):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amt, uid))
        await db.commit()

async def deduct_balance(uid, amt):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (amt, uid))
        await db.commit()

async def add_task(title, link, reward):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO tasks (title, link, reward) VALUES (?, ?, ?)", (title, link, reward))
        await db.commit()

async def get_tasks():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, title, link, reward FROM tasks") as c:
            return await c.fetchall()

async def is_completed(uid, tid):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT 1 FROM completed WHERE user_id=? AND task_id=?", (uid, tid)) as c:
            return await c.fetchone() is not None

async def mark_completed(uid, tid):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO completed (user_id, task_id) VALUES (?, ?)", (uid, tid))
        await db.commit()

async def add_withdrawal(uid, upi, amt):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO withdrawals (user_id, upi, amount) VALUES (?, ?, ?)", (uid, upi, amt))
        await db.commit()

async def get_pending_withdrawals():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, user_id, upi, amount FROM withdrawals WHERE status='pending'") as c:
            return await c.fetchall()

async def update_withdraw_status(rid, status):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE withdrawals SET status=? WHERE id=?", (status, rid))
        await db.commit()

async def get_all_users():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM users") as c:
            return await c.fetchall()

# ============ STATES ============
class AdminStates(StatesGroup):
    title = State()
    link = State()
    reward = State()

class WithdrawStates(StatesGroup):
    upi = State()
    amount = State()

# ============ KEYBOARDS ============
def user_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Tasks", callback_data="tasks")],
        [InlineKeyboardButton(text="💰 Balance", callback_data="balance")],
        [InlineKeyboardButton(text="💸 Withdraw", callback_data="withdraw")],
    ])

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add Task", callback_data="add_task")],
        [InlineKeyboardButton(text="📋 Task List", callback_data="task_list")],
        [InlineKeyboardButton(text="🗑 Delete Task", callback_data="del_task")],
        [InlineKeyboardButton(text="💸 Withdraw Requests", callback_data="withdraw_list")],
        [InlineKeyboardButton(text="👥 Total Users", callback_data="total_users")],
    ])

# ============ START ============
@dp.message(Command("start"))
async def start(message: Message):
    await add_user(message.from_user.id, message.from_user.username or "NoUser")
    await message.answer(
        f"👋 Welcome {message.from_user.first_name}!\n\n"
        f"Task complete karke INR (₹) kamayein.\n"
        f"Minimum Withdraw: ₹{MIN_WITHDRAW}",
        reply_markup=user_menu()
    )

# ============ ADMIN ============
@dp.message(Command("admin"))
async def admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("🛠️ Admin Panel", reply_markup=admin_menu())

@dp.callback_query(F.data == "add_task")
async def add_task_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("📝 Task Title bhejein:")
    await state.set_state(AdminStates.title)

@dp.message(AdminStates.title)
async def task_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("🔗 Task Link bhejein:")
    await state.set_state(AdminStates.link)

@dp.message(AdminStates.link)
async def task_link(message: Message, state: FSMContext):
    await state.update_data(link=message.text)
    await message.answer("💰 Reward (₹) bhejein (Example: 0.5):")
    await state.set_state(AdminStates.reward)

@dp.message(AdminStates.reward)
async def task_reward(message: Message, state: FSMContext):
    try:
        reward = float(message.text)
    except:
        await message.answer("❌ Sirf number bhejein.")
        return
    data = await state.get_data()
    await add_task(data['title'], data['link'], reward)
    await message.answer(f"✅ Task Added!\n📌 {data['title']}\n💰 ₹{reward}")
    await state.clear()

@dp.callback_query(F.data == "task_list")
async def task_list(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    tasks = await get_tasks()
    if not tasks:
        await call.message.answer("❌ Koi task nahi.")
        return
    text = "📋 All Tasks:\n\n"
    for t in tasks:
        text += f"🆔 {t[0]} | {t[1]} | ₹{t[3]}\n"
    await call.message.answer(text)

@dp.callback_query(F.data == "del_task")
async def del_task(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    tasks = await get_tasks()
    if not tasks:
        await call.message.answer("❌ Koi task nahi.")
        return
    btns = [[InlineKeyboardButton(text=f"❌ {t[1]} (₹{t[3]})", callback_data=f"rmtask_{t[0]}")] for t in tasks]
    await call.message.answer("Delete karne ke liye click karein:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("rmtask_"))
async def rmtask(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    tid = int(call.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM tasks WHERE id=?", (tid,))
        await db.execute("DELETE FROM completed WHERE task_id=?", (tid,))
        await db.commit()
    await call.message.answer(f"✅ Task {tid} delete.")

@dp.callback_query(F.data == "total_users")
async def total_users(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    users = await get_all_users()
    await call.message.answer(f"👥 Total Users: {len(users)}")

# ============ USER TASKS ============
@dp.callback_query(F.data == "tasks")
async def show_tasks(call: CallbackQuery):
    tasks = await get_tasks()
    if not tasks:
        await call.message.answer("❌ Abhi koi task available nahi.")
        return
    for t in tasks:
        done = await is_completed(call.from_user.id, t[0])
        if done:
            btn = InlineKeyboardButton(text="✅ Completed", callback_data="done")
        else:
            btn = InlineKeyboardButton(text="🔓 Claim", callback_data=f"claim_{t[0]}")
        await call.message.answer(
            f"📌 {t[1]}\n💰 Reward: ₹{t[3]}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[btn]])
        )

@dp.callback_query(F.data.startswith("claim_"))
async def claim(call: CallbackQuery):
    tid = int(call.data.split("_")[1])
    tasks = await get_tasks()
    task = next((t for t in tasks if t[0] == tid), None)
    if not task:
        await call.answer("Task not found!", show_alert=True)
        return
    if await is_completed(call.from_user.id, tid):
        await call.answer("Already completed!", show_alert=True)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Open Task", url=task[2])],
        [InlineKeyboardButton(text="✅ Complete", callback_data=f"done_{tid}")]
    ])
    await call.message.answer("Link kholkar task complete karein:", reply_markup=kb)

@dp.callback_query(F.data.startswith("done_"))
async def complete_task(call: CallbackQuery):
    tid = int(call.data.split("_")[1])
    if await is_completed(call.from_user.id, tid):
        await call.answer("Already completed!", show_alert=True)
        return
    tasks = await get_tasks()
    task = next((t for t in tasks if t[0] == tid), None)
    if not task:
        return
    await mark_completed(call.from_user.id, tid)
    await add_balance(call.from_user.id, task[3])
    await call.message.answer(
        f"✅ Task Complete!\n💰 ₹{task[3]} add ho gaye.\n\n"
        f"👤 Worker: @{call.from_user.username or 'NoUser'}\n"
        f"🆔 ID: q{call.from_user.id}"
    )

# ============ BALANCE ============
@dp.callback_query(F.data == "balance")
async def balance(call: CallbackQuery):
    bal = await get_balance(call.from_user.id)
    await call.message.answer(f"💰 Aapka Balance: ₹{bal}")

# ============ WITHDRAW ============
@dp.callback_query(F.data == "withdraw")
async def withdraw_start(call: CallbackQuery, state: FSMContext):
    await call.message.answer("💳 Apni UPI ID bhejein (Example: name@upi):")
    await state.set_state(WithdrawStates.upi)

@dp.message(WithdrawStates.upi)
async def withdraw_upi(message: Message, state: FSMContext):
    await state.update_data(upi=message.text)
    await message.answer(f"💰 Amount (₹) bhejein (Min ₹{MIN_WITHDRAW}):")
    await state.set_state(WithdrawStates.amount)

@dp.message(WithdrawStates.amount)
async def withdraw_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text)
    except:
        await message.answer("❌ Sirf number bhejein.")
        return
    bal = await get_balance(message.from_user.id)
    if amount < MIN_WITHDRAW:
        await message.answer(f"❌ Min ₹{MIN_WITHDRAW}.")
        return
    if amount > bal:
        await message.answer(f"❌ Balance kam hai: ₹{bal}")
        return
    data = await state.get_data()
    upi = data['upi']
    await deduct_balance(message.from_user.id, amount)
    await add_withdrawal(message.from_user.id, upi, amount)
    await message.answer(f"✅ Withdraw Request Bheja!\n💳 UPI: {upi}\n💰 ₹{amount}")
    await bot.send_message(
        ADMIN_ID,
        f"🔔 New Withdraw Request!\n\n"
        f"👤 User: @{message.from_user.username or 'NoUser'}\n"
        f"🆔 ID: {message.from_user.id}\n"
        f"💳 UPI: {upi}\n"
        f"💰 Amount: ₹{amount}"
    )
    await state.clear()

# ============ ADMIN WITHDRAW ============
@dp.callback_query(F.data == "withdraw_list")
async def withdraw_list(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    rows = await get_pending_withdrawals()
    if not rows:
        await call.message.answer("✅ Koi pending withdrawal nahi.")
        return
    for r in rows:
        text = f"🆔 Req ID: {r[0]}\n👤 User ID: {r[1]}\n💳 UPI: {r[2]}\n💰 ₹{r[3]}"
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Approve", callback_data=f"wapp_{r[0]}"),
            InlineKeyboardButton(text="❌ Reject", callback_data=f"wrej_{r[0]}")
        ]])
        await call.message.answer(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("wapp_"))
async def wapp(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await update_withdraw_status(int(call.data.split("_")[1]), "approved")
    await call.message.edit_text(call.message.text + "\n\n✅ APPROVED")

@dp.callback_query(F.data.startswith("wrej_"))
async def wrej(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    rid = int(call.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id, amount FROM withdrawals WHERE id=?", (rid,)) as c:
            row = await c.fetchone()
    if row:
        await add_balance(row[0], row[1])
    await update_withdraw_status(rid, "rejected")
    await call.message.edit_text(call.message.text + "\n\n❌ REJECTED (Refunded)")

# ============ RUN ============
async def main():
    await init_db()
    print("🤖 Bot chal raha hai...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
