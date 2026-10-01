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
        await db.execute("""CREATE TABLE IF NOT EXISTS qrcodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            qr_data TEXT,
            title TEXT,
            reward REAL,
            claimed_by INTEGER DEFAULT NULL,
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

async def add_qr(qr_data, title, reward):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO qrcodes (qr_data, title, reward) VALUES (?, ?, ?)", (qr_data, title, reward))
        await db.commit()

async def get_available_qrs():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, qr_data, title, reward FROM qrcodes WHERE claimed_by IS NULL") as c:
            return await c.fetchall()

async def get_all_qrs():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, qr_data, title, reward, claimed_by FROM qrcodes") as c:
            return await c.fetchall()

async def claim_qr(qr_id, uid):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE qrcodes SET claimed_by=?, claimed_at=datetime('now') WHERE id=? AND claimed_by IS NULL", (uid, qr_id))
        await db.commit()

async def get_qr(qr_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, qr_data, title, reward, claimed_by FROM qrcodes WHERE id=?", (qr_id,)) as c:
            return await c.fetchone()

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

async def count_qrs():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM qrcodes WHERE claimed_by IS NULL") as c:
            r = await c.fetchone()
            return r[0] if r else 0

# ============ STATES ============
class AdminStates(StatesGroup):
    qr_data = State()
    title = State()
    reward = State()

class WithdrawStates(StatesGroup):
    upi = State()
    amount = State()

# ============ KEYBOARDS ============
def user_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Available QR Tasks", callback_data="qrs")],
        [InlineKeyboardButton(text="💰 Balance", callback_data="balance")],
        [InlineKeyboardButton(text="💸 Withdraw", callback_data="withdraw")],
    ])

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add QR", callback_data="add_qr")],
        [InlineKeyboardButton(text="📋 All QRs", callback_data="qr_list")],
        [InlineKeyboardButton(text="🗑 Delete QR", callback_data="del_qr")],
        [InlineKeyboardButton(text="💸 Withdraw Requests", callback_data="withdraw_list")],
        [InlineKeyboardButton(text="👥 Total Users", callback_data="total_users")],
        [InlineKeyboardButton(text="📊 Stats", callback_data="stats")],
    ])

# ============ START ============
@dp.message(Command("start"))
async def start(message: Message):
    await add_user(message.from_user.id, message.from_user.username or "NoUser")
    bal = await get_balance(message.from_user.id)
    avail = await count_qrs()
    await message.answer(
        f"👋 Welcome {message.from_user.first_name}!\n\n"
        f"💰 Balance: ₹{bal}\n"
        f"📋 Available QRs: {avail}\n"
        f"💵 Min Withdraw: ₹{MIN_WITHDRAW}\n\n"
        f"QR claim karke paisa kamayein!",
        reply_markup=user_menu()
    )

# ============ ADMIN ============
@dp.message(Command("admin"))
async def admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("🛠️ Admin Panel", reply_markup=admin_menu())

@dp.callback_query(F.data == "add_qr")
async def add_qr_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("📱 QR Data bhejein (UPI ID / Link / Text):\n\nExample: `upi://pay?pa=example@upi`")
    await state.set_state(AdminStates.qr_data)

@dp.message(AdminStates.qr_data)
async def qr_data(message: Message, state: FSMContext):
    await state.update_data(qr_data=message.text)
    await message.answer("📝 Title bhejein (Example: PANCARD NEW >18yearsold):")
    await state.set_state(AdminStates.title)

@dp.message(AdminStates.title)
async def qr_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("💰 Reward (₹) bhejein (Example: 0.5 / 1 / 5):")
    await state.set_state(AdminStates.reward)

@dp.message(AdminStates.reward)
async def qr_reward(message: Message, state: FSMContext):
    try:
        reward = float(message.text)
    except:
        await message.answer("❌ Sirf number bhejein.")
        return
    data = await state.get_data()
    await add_qr(data['qr_data'], data['title'], reward)
    await message.answer(f"✅ QR Added!\n\n📌 {data['title']}\n💰 ₹{reward}")
    await state.clear()

@dp.callback_query(F.data == "qr_list")
async def qr_list(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    qrs = await get_all_qrs()
    if not qrs:
        await call.message.answer("❌ Koi QR nahi hai.")
        return
    text = "📋 All QRs:\n\n"
    for q in qrs:
        status = "❌ Taken" if q[4] else "✅ Available"
        text += f"🆔 {q[0]} | {q[2]} | ₹{q[3]} | {status}\n"
    await call.message.answer(text)

@dp.callback_query(F.data == "del_qr")
async def del_qr(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    qrs = await get_all_qrs()
    if not qrs:
        await call.message.answer("❌ Koi QR nahi.")
        return
    btns = []
    for q in qrs:
        btns.append([InlineKeyboardButton(text=f"❌ {q[2]} (₹{q[3]})", callback_data=f"rmqr_{q[0]}")])
    await call.message.answer("Delete karne ke liye click karein:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("rmqr_"))
async def rmqr(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    qid = int(call.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM qrcodes WHERE id=?", (qid,))
        await db.commit()
    await call.message.answer(f"✅ QR {qid} delete.")

@dp.callback_query(F.data == "total_users")
async def total_users(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    users = await get_all_users()
    await call.message.answer(f"👥 Total Users: {len(users)}")

@dp.callback_query(F.data == "stats")
async def stats(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    qrs = await get_all_qrs()
    avail = sum(1 for q in qrs if not q[4])
    taken = sum(1 for q in qrs if q[4])
    users = await get_all_users()
    pending = await get_pending_withdrawals()
    await call.message.answer(
        f"📊 Stats:\n\n"
        f"👥 Users: {len(users)}\n"
        f"📋 Total QRs: {len(qrs)}\n"
        f"✅ Available: {avail}\n"
        f"❌ Taken: {taken}\n"
        f"💸 Pending Withdrawals: {len(pending)}"
    )

# ============ USER QR TASKS ============
@dp.callback_query(F.data == "qrs")
async def show_qrs(call: CallbackQuery):
    qrs = await get_available_qrs()
    if not qrs:
        await call.message.answer("❌ Abhi koi QR available nahi hai. Thodi der baad try karein.")
        return
    for q in qrs:
        text = f"📌 {q[2]}\n💰 Reward: ₹{q[3]}"
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔓 Claim", callback_data=f"claim_{q[0]}")
        ]])
        await call.message.answer(text, reply_markup=kb)

@dp.callback_query(F.data.startswith("claim_"))
async def claim(call: CallbackQuery):
    qid = int(call.data.split("_")[1])
    qr = await get_qr(qid)
    if not qr:
        await call.answer("QR not found!", show_alert=True)
        return
    if qr[4]:
        await call.message.answer(
            f"⚠️ This QR has already been taken.\n\n"
            f"👤 Worker: @{call.from_user.username or 'NoUser'}\n"
            f"🆔 ID: q{call.from_user.id}"
        )
        return
    await claim_qr(qid, call.from_user.id)
    qr = await get_qr(qid)
    await call.message.answer(
        f"✅ QR Claimed!\n\n"
        f"📌 {qr[2]}\n"
        f"💰 Reward: ₹{qr[3]}\n"
        f"📱 QR Data: `{qr[1]}`\n\n"
        f"👤 Worker: @{call.from_user.username or 'NoUser'}\n"
        f"🆔 ID: q{call.from_user.id}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Complete Task", callback_data=f"complete_{qid}")
        ]])
    )

@dp.callback_query(F.data.startswith("complete_"))
async def complete_task(call: CallbackQuery):
    qid = int(call.data.split("_")[1])
    qr = await get_qr(qid)
    if not qr:
        return
    if qr[4] != call.from_user.id:
        await call.answer("Yeh QR aapne claim nahi kiya!", show_alert=True)
        return
    await add_balance(call.from_user.id, qr[3])
    await call.message.answer(
        f"🎉 Task Complete!\n\n"
        f"💰 ₹{qr[3]} aapke balance mein add ho gaye.\n"
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
