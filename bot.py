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
        await db.execute("PRAGMA journal_mode=WAL")  # Concurrency ke liye
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, balance REAL DEFAULT 0)")
        await db.execute("""CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            link TEXT,
            reward REAL,
            claimed_by INTEGER DEFAULT NULL,
            claim_status TEXT DEFAULT 'available',
            claimed_at TEXT DEFAULT NULL
        )""")
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
        cursor = await db.execute("INSERT INTO tasks (title, link, reward) VALUES (?, ?, ?)", (title, link, reward))
        await db.commit()
        return cursor.lastrowid

async def get_available_tasks():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, title, link, reward FROM tasks WHERE claim_status='available'") as c:
            return await c.fetchall()

async def get_all_tasks():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, title, link, reward, claim_status, claimed_by FROM tasks") as c:
            return await c.fetchall()

async def get_task(task_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, title, link, reward, claim_status, claimed_by FROM tasks WHERE id=?", (task_id,)) as c:
            return await c.fetchone()

async def delete_task(task_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        await db.commit()

async def claim_task_atomic(task_id, uid):
    """
    Atomic claim - sirf ek user jeetega
    Returns: (success: bool, task_data or None)
    """
    async with aiosqlite.connect(DB_NAME) as db:
        # Atomic UPDATE - sirf tab update hoga jab claim_status='available' ho
        cursor = await db.execute(
            "UPDATE tasks SET claimed_by=?, claim_status='pending', claimed_at=CURRENT_TIMESTAMP WHERE id=? AND claim_status='available'",
            (uid, task_id)
        )
        await db.commit()
        if cursor.rowcount == 0:
            # Koi aur user ne pehle claim kar liya
            return False, None
        # Claim successful - task data fetch karo
        async with db.execute("SELECT id, title, link, reward FROM tasks WHERE id=?", (task_id,)) as c:
            task = await c.fetchone()
        return True, task

async def approve_task(task_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE tasks SET claim_status='approved' WHERE id=? AND claim_status='pending'", (task_id,))
        await db.commit()

async def reject_task(task_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE tasks SET claim_status='rejected' WHERE id=? AND claim_status='pending'", (task_id,))
        await db.commit()

async def get_pending_claims():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, title, reward, claimed_by FROM tasks WHERE claim_status='pending'") as c:
            return await c.fetchall()

async def get_all_users():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM users") as c:
            return await c.fetchall()

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

async def count_available_tasks():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM tasks WHERE claim_status='available'") as c:
            r = await c.fetchone()
            return r[0] if r else 0

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
        [InlineKeyboardButton(text="📋 Available Tasks", callback_data="tasks")],
        [InlineKeyboardButton(text="💰 Balance", callback_data="balance")],
        [InlineKeyboardButton(text="💸 Withdraw", callback_data="withdraw")],
    ])

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add Task", callback_data="add_task")],
        [InlineKeyboardButton(text="📋 All Tasks", callback_data="task_list")],
        [InlineKeyboardButton(text="🗑 Delete Task", callback_data="del_task")],
        [InlineKeyboardButton(text="⏳ Pending Claims", callback_data="pending_claims")],
        [InlineKeyboardButton(text="💸 Withdraw Requests", callback_data="withdraw_list")],
        [InlineKeyboardButton(text="👥 Total Users", callback_data="total_users")],
    ])

# ============ START ============
@dp.message(Command("start"))
async def start(message: Message):
    await add_user(message.from_user.id, message.from_user.username or "NoUser")
    bal = await get_balance(message.from_user.id)
    avail = await count_available_tasks()
    await message.answer(
        f"👋 Welcome {message.from_user.first_name}!\n\n"
        f"💰 Balance: ₹{bal}\n"
        f"📋 Available Tasks: {avail}\n"
        f"💵 Min Withdraw: ₹{MIN_WITHDRAW}\n\n"
        f"Task claim karke paisa kamayein!",
        reply_markup=user_menu()
    )

# ============ ADMIN PANEL ============
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
    await message.answer("💰 Reward (₹) bhejein:")
    await state.set_state(AdminStates.reward)

@dp.message(AdminStates.reward)
async def task_reward(message: Message, state: FSMContext):
    try:
        reward = float(message.text)
    except:
        await message.answer("❌ Sirf number bhejein.")
        return
    data = await state.get_data()
    task_id = await add_task(data['title'], data['link'], reward)
    await message.answer(f"✅ Task Added!\n\n📌 {data['title']}\n💰 ₹{reward}\n🆔 Task ID: {task_id}")

    # Saare users ko notification
    users = await get_all_users()
    sent = 0
    failed = 0
    for u in users:
        try:
            await bot.send_message(
                u[0],
                f"🔔 New Task Available!\n\n"
                f"📌 {data['title']}\n"
                f"💰 Reward: ₹{reward}\n\n"
                f"⚠️ Sirf ek user claim kar sakta hai!\n"
                f"Jaldi karein!",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="🔓 Claim Now", callback_data=f"claim_{task_id}")
                ]])
            )
            sent += 1
        except:
            failed += 1
        await asyncio.sleep(0.05)
    await message.answer(f"📢 Notification sent!\n✅ Success: {sent}\n❌ Failed: {failed}")
    await state.clear()

@dp.callback_query(F.data == "task_list")
async def task_list(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    tasks = await get_all_tasks()
    if not tasks:
        await call.message.answer("❌ Koi task nahi.")
        return
    text = "📋 All Tasks:\n\n"
    for t in tasks:
        status_emoji = {"available": "🟢", "pending": "🟡", "approved": "✅", "rejected": "❌"}.get(t[4], "❓")
        text += f"🆔 {t[0]} | {t[1]} | ₹{t[3]} | {status_emoji} {t[4]}\n"
    await call.message.answer(text)

@dp.callback_query(F.data == "del_task")
async def del_task(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    tasks = await get_all_tasks()
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
    await delete_task(tid)
    await call.message.answer(f"✅ Task {tid} delete.")

@dp.callback_query(F.data == "total_users")
async def total_users(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    users = await get_all_users()
    await call.message.answer(f"👥 Total Users: {len(users)}")

# ============ PENDING CLAIMS ============
@dp.callback_query(F.data == "pending_claims")
async def pending_claims(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    rows = await get_pending_claims()
    if not rows:
        await call.message.answer("✅ Koi pending claim nahi.")
        return
    for r in rows:
        task_id, title, reward, user_id = r
        text = (
            f"⏳ Pending Claim\n\n"
            f"🆔 Task ID: {task_id}\n"
            f"📌 {title}\n"
            f"💰 ₹{reward}\n"
            f"👤 User ID: {user_id}"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Approve", callback_data=f"approve_{task_id}"),
            InlineKeyboardButton(text="❌ Reject", callback_data=f"reject_{task_id}")
        ]])
        await call.message.answer(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("approve_"))
async def approve_claim(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    task_id = int(call.data.split("_")[1])
    task = await get_task(task_id)
    if not task:
        await call.answer("Task not found!", show_alert=True)
        return
    if task[4] != 'pending':
        await call.answer(f"Already {task[4]}!", show_alert=True)
        return
    await approve_task(task_id)
    await add_balance(task[5], task[3])
    await call.message.edit_text(call.message.text + "\n\n✅ APPROVED")
    try:
        await bot.send_message(
            task[5],
            f"🎉 Task Approved!\n\n"
            f"📌 {task[1]}\n"
            f"💰 ₹{task[3]} aapke balance mein add ho gaye."
        )
    except:
        pass

@dp.callback_query(F.data.startswith("reject_"))
async def reject_claim(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    task_id = int(call.data.split("_")[1])
    task = await get_task(task_id)
    if not task:
        return
    if task[4] != 'pending':
        await call.answer(f"Already {task[4]}!", show_alert=True)
        return
    await reject_task(task_id)
    await call.message.edit_text(call.message.text + "\n\n❌ REJECTED")
    try:
        await bot.send_message(
            task[5],
            f"❌ Aapka task reject ho gaya.\n\nAdmin se contact karein."
        )
    except:
        pass

# ============ USER TASKS ============
@dp.callback_query(F.data == "tasks")
async def show_tasks(call: CallbackQuery):
    tasks = await get_available_tasks()
    if not tasks:
        await call.message.answer("❌ Abhi koi task available nahi hai.")
        return
    for t in tasks:
        text = f"📌 {t[1]}\n💰 Reward: ₹{t[3]}"
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔓 Claim", callback_data=f"claim_{t[0]}")
        ]])
        await call.message.answer(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("claim_"))
async def claim(call: CallbackQuery):
    task_id = int(call.data.split("_")[1])
    
    # ===== ATOMIC CLAIM =====
    success, task = await claim_task_atomic(task_id, call.from_user.id)
    
    if not success:
        # Koi aur user ne pehle claim kar liya
        await call.answer(
            "⚠️ This task has already been taken by another user!",
            show_alert=True
        )
        await call.message.edit_text(
            f"⚠️ This task has already been taken.\n\n"
            f"👤 Worker: @{call.from_user.username or 'NoUser'}\n"
            f"🆔 ID: q{call.from_user.id}"
        )
        return
    
    # Claim successful
    await call.message.edit_text(
        f"✅ Task Claimed Successfully!\n\n"
        f"📌 {task[1]}\n"
        f"💰 Reward: ₹{task[3]}\n\n"
        f"🔗 Task Link:\n{task[2]}\n\n"
        f"👤 Worker: @{call.from_user.username or 'NoUser'}\n"
        f"🆔 ID: q{call.from_user.id}\n\n"
        f"⚠️ Admin verify karega, uske baad paisa milega."
    )
    
    # ===== Admin ko alert =====
    try:
        await bot.send_message(
            ADMIN_ID,
            f"🔔 New Claim!\n\n"
            f"🆔 Task ID: {task_id}\n"
            f"📌 {task[1]}\n"
            f"💰 ₹{task[3]}\n"
            f"👤 User: @{call.from_user.username or 'NoUser'}\n"
            f"🆔 User ID: {call.from_user.id}\n\n"
            f"Verify karke approve/reject karein.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Approve", callback_data=f"approve_{task_id}"),
                InlineKeyboardButton(text="❌ Reject", callback_data=f"reject_{task_id}")
            ]])
        )
    except:
        pass

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
