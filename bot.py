import json
import sys
import uuid
import time
import base64
import secrets
import os
import asyncio
import logging
from curl_cffi import requests as cffi_requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# --- Config from Environment Variables ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "meesho_secret_123")
PORT = int(os.environ.get("PORT", 8080))
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "0").split(",") if x.strip().isdigit()]

# --- Meesho / OTPLESS Constants ---
MEESHO_API = "https://prod.meeshoapi.com/api"
MEESHO_AUTH = "32c4d8137cn9eb493a1921f203173080"
ANON_XO = ("eyJ0eXBlIjoiY29tcG9zaXRlIn0=.eyJqd3QiOiJleUpoYkdjaU9pSklVekkxTmlJc0ltaDBkSEJ6"
           "T2k4dmJXVmxjMmh2TG1OdmJTOXBjMjlmWTI5MWJuUnllVjlqYjJSbElqb2lTVTRpTENKb2RIUndjem92"
           "TDIxbFpYTm9ieTVqYjIwdmRtVnljMmx2YmlJNklqRWlMQ0owZVhBaU9pSktWMVFpZlEuZXlKbGVIQWlP"
           "akU1TkRVek16STVOemdzSW1oMGRIQnpPaTh2YldWbGMyaHZMbU52YlM5aGJtOXVlVzF2ZFhObGNsOXBa"
           "Q0k2SW1NNVltSTRZVFV6TFRJeFpUTXRORGRqWVMxaU5qYzBMV0ZqWlRFek56Rm1ZVFUzTVNJc0ltaDBk"
           "SEJ6T2k4dmJXVmxjMmh2TG1OdmJTOXBibk4wWVc1alpWOXBaQ0k2SW1RM01UZzVNbU5oWVRneVpqUTVO"
           "VEU1WmpSaE16TmhNR1V3WWpnM1pqY3dJaXdpYVdGMElqb3hOemczTmpVeU9UYzRmUS4tQ3pNeS1MQnZU"
           "ekZXTjZWVE4wM0p3Mi0teGJfSWpJT1VmaklFOTl5aVBR")

MEESHO_RSA_PUBKEY_B64 = ("MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAslmrLKGRzVnAtii3o89yI33FXZoRfBJ"
                         "V89PaCTp9Mxu7FgAaAOtaOnB2xWGG2a6Rz6zRzKPilRdAsm5oBW8mm8Uzvt7mbf7c7pjfBrjNdnKji"
                         "/9/zM3fpjh364/GwG3OpyYngD49i09ySljA7Elh97Pp+QJH2z25Xv2eRSHJPizgQ8TE1bJkP9fd9J"
                         "cfpGFyeEJX1bUIbgRlfED2TpJKGeaEfZ9no5+i/rgCaIRO9t86UqgeVJyCyJLnUkrU/ARPj9q/Aij"
                         "JV9kvyPT137UQLO+Cl6nZYOglqGcPnRbGiW6WM7imkSxR2XBn6N4ojf49nJOwnN826hkdH5JaPJ1p"
                         "AQIDAQAB")

OTPLESS_APP_ID = "XN07RN1IQC548C9YK5I4"
OTPLESS_PACKAGE = "com.meesho.supply"
OTPLESS_LOGIN_URI = "otpless.xn07rn1iqc548c9yk5i4://otpless"
OTPLESS_OTP_HASH = "oBcOM6bXKNc"
OTPLESS_APP_SIGNATURE = "oBcOM6bXKNcqouiPFcR1ur60Z6myTuVIDNSNWuKOlzU"
OTPLESS_UA = "okhttp/4.9.0"
OTPLESS_ORIGIN = "https://otpless.com"

DEVICE_INFO = {
    "platform": "android", "vendor": "motorola", "browser": "", "connection": "",
    "language": "en-IN", "cookieEnabled": "", "screenWidth": 1080, "screenHeight": 2225,
    "userAgent": "Dalvik/2.1.0 (Linux; U; Android 12; moto g(60) Build/S2RI32.32-20-9-9-2) otplesssdk",
    "timezoneOffset": 330, "cpuArchitecture": "aarch64",
}

KEY_CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()-_=+"

# Premium Emoji IDs — replace with your real premium emoji IDs
EMOJI = {
    "rocket": "5368324170671202286",
    "check": "5368324170671202286",
    "cross": "5368324170671202286",
    "phone": "5368324170671202286",
    "lock": "5368324170671202286",
    "key": "5368324170671202286",
    "star": "5368324170671202286",
    "fire": "5368324170671202286",
    "sparkle": "5368324170671202286",
    "shield": "5368324170671202286",
    "user": "5368324170671202286",
    "id": "5368324170671202286",
    "info": "5368324170671202286",
    "warning": "5368324170671202286",
    "loading": "5368324170671202286",
}

WAITING_PHONE, WAITING_OTP = range(2)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# --- Meesho Core Helpers ---
def _ts_id():
    return f"{uuid.uuid4()}-{int(time.time() * 1000)}"


def _gen_key():
    return "".join(secrets.choice(KEY_CHARSET) for _ in range(16))


def _aes_gcm_encrypt(plaintext, key):
    iv = os.urandom(12)
    ct = AESGCM(key[:16].encode()).encrypt(iv, plaintext, None)
    return base64.b64encode(iv + ct).decode("ascii")


def _rsa_encrypt(data):
    pub = serialization.load_der_public_key(base64.b64decode(MEESHO_RSA_PUBKEY_B64))
    return base64.b64encode(pub.encrypt(data.encode(), padding.PKCS1v15())).decode("ascii")


def _build_intent_body(phone, ts_id, in_id):
    ga_id = str(uuid.uuid4())
    app_info = {
        "platform": "android", "manufacturer": "motorola", "androidVersion": "31",
        "packageName": OTPLESS_PACKAGE, "model": "moto g(60)",
        "appSignature": OTPLESS_APP_SIGNATURE,
        "hasTelegram": "true", "hasMiChat": "false", "hasLine": "false",
        "hasDiscord": "false", "hasSlack": "false", "hasViber": "false",
        "hasSignal": "false", "hasBotim": "false", "hasTrueCaller": "false",
        "hasWhatsapp": "false", "sdkVersion": "1.3.3",
        "inId": in_id, "tsId": ts_id,
        "isSilentAuthSupported": "true", "isWebAuthnSupported": "true",
        "isCellularDataEnabled": "false",
        "secureDetail": {"simDetail": {"currentTransportType": "WiFi", "isSimInserted": "false"}},
    }
    device_id_info = {
        "androidId": "aa5e8c37ca4077f7",
        "mediaId": "044507f8402972db73de4f938b76584c89336763bec73f4a9f97b3e36136862f",
        "gaid": ga_id,
    }
    metadata = json.dumps({
        "appInfo": json.dumps(app_info),
        "deviceInfo": json.dumps(DEVICE_INFO),
        "deviceIdInfo": json.dumps(device_id_info),
    })
    return {
        "selectedCountryCode": "+91", "mobile": f"91{phone}",
        "silentAuthEnabled": False, "hasWhatsapp": "false",
        "deliveryChannel": "SMS", "metadata": metadata,
        "triggerWebauthn": False,
        "telephonyInfo": {"isMobileDataOn": False, "hasReadPhoneStatePermission": False, "all": [{}]},
        "clientMetaData": json.dumps({"tid": secrets.token_urlsafe(12)[:16]}),
        "asId": "", "isViSnaWhitelisted": True, "isAirtelSnaWhitelisted": True,
        "isAutoIntent": True, "origin": "https://otpless.com", "version": "V4",
        "tsId": ts_id, "inId": in_id, "deviceInfo": json.dumps(DEVICE_INFO),
        "loginUri": OTPLESS_LOGIN_URI, "appId": OTPLESS_APP_ID,
        "isHeadless": True, "packageName": OTPLESS_PACKAGE, "package": OTPLESS_PACKAGE,
        "otpHash": OTPLESS_OTP_HASH, "platform": "HEADLESS",
    }


def send_meesho_otp(phone):
    ts_id, in_id = _ts_id(), _ts_id()
    session = cffi_requests.Session(impersonate="chrome120")
    headers = {"user-agent": OTPLESS_UA}

    state_resp = session.get(
        "https://user-auth.otpless.app/v2/state",
        params={
            "origin": OTPLESS_ORIGIN, "version": "V3", "tsId": ts_id, "inId": in_id,
            "isHeadless": "true", "platform": "android", "isLoginPage": "false",
            "packageName": OTPLESS_PACKAGE, "package": OTPLESS_PACKAGE,
            "appId": OTPLESS_APP_ID, "loginUri": OTPLESS_LOGIN_URI,
            "deviceInfo": json.dumps(DEVICE_INFO),
        },
        headers=headers, timeout=15,
    )
    state = (state_resp.json() or {}).get("state")
    if not state:
        return {"ok": False, "error": "State failed"}

    intent_resp = session.post(
        f"https://user-auth.otpless.app/v3/lp/user/transaction/intent/{state}",
        headers={**headers, "content-type": "application/json; charset=utf-8"},
        json=_build_intent_body(phone, ts_id, in_id),
        timeout=15,
    )
    data = intent_resp.json() or {}
    leap = data.get("quantumLeap") or {}
    if not leap.get("uid") or not leap.get("channelAuthToken"):
        return {"ok": False, "error": f"OTP rejected: {json.dumps(data)[:200]}"}

    return {
        "ok": True,
        "session": {
            "state": state, "uid": leap["uid"], "token": leap["channelAuthToken"],
            "as_id": leap.get("asId", ""), "ts_id": ts_id, "in_id": in_id,
            "instance_id": uuid.uuid4().hex,
        },
    }


def verify_meesho_otp(phone, otp, session):
    otp_headers = {"user-agent": OTPLESS_UA, "content-type": "application/json; charset=utf-8"}
    otp_body = {
        "selectedCountryCode": "91", "mobile": phone, "otp": otp,
        "value": f"91{phone}", "isOTPAutoRead": "false",
        "uid": session["uid"], "token": session["token"], "asId": session["as_id"],
        "origin": OTPLESS_ORIGIN, "version": "V4",
        "tsId": session["ts_id"], "inId": session["in_id"],
        "deviceInfo": json.dumps(DEVICE_INFO, separators=(",", ":")),
        "loginUri": OTPLESS_LOGIN_URI, "appId": OTPLESS_APP_ID,
        "isHeadless": True, "packageName": OTPLESS_PACKAGE, "package": OTPLESS_PACKAGE,
        "otpHash": OTPLESS_OTP_HASH, "platform": "HEADLESS",
    }

    http = cffi_requests.Session(impersonate="chrome120")
    verify_resp = http.post(
        f"https://user-auth.otpless.app/v3/lp/user/transaction/otp/{session['state']}",
        headers=otp_headers, json=otp_body, timeout=20,
    )
    data = verify_resp.json() or {}
    one_tap = data.get("oneTap") or {}
    token = one_tap.get("token")
    id_token = (one_tap.get("merchantUserInfo") or {}).get("idToken")
    if not token or not id_token:
        status = (data.get("authDetail") or {}).get("status", "FAILED")
        return {"ok": False, "error": f"OTP verify failed ({status})"}

    key = _gen_key()
    app_session_id = uuid.uuid4().hex
    ga_id = str(uuid.uuid4())
    login_body = {
        "login_type": "otpless",
        "otpless": {
            "token": token,
            "id_token": _aes_gcm_encrypt(id_token.encode(), key),
            "aes_key_encrypted": _rsa_encrypt(key),
            "version": "v2",
        },
        "ga_id": ga_id,
    }

    login_headers_variants = [
        {"authorization": MEESHO_AUTH, "app-version": "29.1", "app-version-code": "860", "instance-id": session["instance_id"], "country-iso": "in", "application-id": "com.meesho.supply", "app-session-id": app_session_id, "app-sdk-version": "30", "app-client-id": "android", "shield-session-id": "", "xo": ANON_XO, "app-iso-language-code": "en", "meesho-user-context": "anonymous", "content-type": "application/json; charset=UTF-8", "user-agent": "okhttp/4.9.0"},
        {"authorization": MEESHO_AUTH, "app-version": "29.1", "app-version-code": "860", "instance-id": session["instance_id"], "country-iso": "in", "application-id": "com.meesho.supply", "app-session-id": app_session_id, "app-sdk-version": "30", "app-client-id": "android", "shield-session-id": "", "app-iso-language-code": "en", "meesho-user-context": "anonymous", "content-type": "application/json; charset=UTF-8", "user-agent": "okhttp/4.9.0"},
        {"authorization": MEESHO_AUTH, "app-version": "29.1", "app-version-code": "858", "instance-id": session["instance_id"], "country-iso": "in", "application-id": "com.meesho.supply", "app-session-id": app_session_id, "app-sdk-version": "30", "app-client-id": "android", "xo": ANON_XO, "app-iso-language-code": "en", "meesho-user-context": "anonymous", "content-type": "application/json; charset=UTF-8", "user-agent": "okhttp/4.9.0"},
    ]

    last_err = ""
    for attempt, login_headers in enumerate(login_headers_variants):
        login_resp = http.post(
            f"{MEESHO_API}/2.0/user/login",
            headers=login_headers, json=login_body, timeout=20,
        )
        logger.info(f"Login attempt {attempt+1} http {login_resp.status_code}")
        if login_resp.status_code == 200:
            ldata = login_resp.json() or {}
            user = ldata.get("user") or {}
            xo = (ldata.get("xoox") or {}).get("xo") or ""
            if xo:
                return {
                    "ok": True, "user_id": user.get("user_id"),
                    "phone": user.get("phone") or phone, "xo": xo,
                    "instance_id": session["instance_id"],
                    "app_session_id": app_session_id, "ga_id": ga_id,
                    "is_new": bool(user.get("new")),
                }
            last_err = f"No xo: {json.dumps(ldata)[:200]}"
            continue
        last_err = f"Login HTTP {login_resp.status_code}: {login_resp.text[:200]}"
        if login_resp.status_code == 500:
            time.sleep(1.2)
            continue

    return {"ok": False, "error": last_err}


def build_final_json(phone, vr):
    user_id = vr["user_id"]
    xo = vr["xo"]
    instance_id = vr["instance_id"]
    app_session_id = vr.get("app_session_id") or uuid.uuid4().hex
    ga_id = vr.get("ga_id") or str(uuid.uuid4())
    ox = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")[:88]
    phone_num = vr.get("phone") or phone
    phone_last4 = str(phone_num)[-4:]
    is_new = vr.get("is_new", True)

    return {
        "ok": True,
        "mobile": phone_num,
        "user_id": user_id,
        "phone": f"+91{phone_num}" if not str(phone_num).startswith("+") else phone_num,
        "xo": xo,
        "ox": ox,
        "instance_id": instance_id,
        "gaid": ga_id,
        "identity": {
            "instance_id": instance_id,
            "gaid": ga_id,
            "app_session_id": app_session_id,
            "anon_xo": ANON_XO,
        },
        "app_session_id": app_session_id,
        "anon_xo": ANON_XO,
        "phone_last4": phone_last4,
        "is_first_order": 1 if is_new else 0,
        "is_new": is_new,
    }


# --- Telegram Helpers ---
def premium_emoji(emoji_id: str) -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">⭐</tg-emoji>'


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def send_premium_message(update: Update, text: str, **kwargs):
    try:
        return await update.effective_message.reply_text(text, parse_mode="HTML", **kwargs)
    except Exception as e:
        logger.error(f"Premium message failed: {e}")
        import re
        clean = re.sub(r'<tg-emoji[^>]*>(.*?)</tg-emoji>', r'\1', text)
        return await update.effective_message.reply_text(clean, **kwargs)


# --- Bot Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    context.user_data.clear()

    keyboard = [
        [InlineKeyboardButton("🚀 Create Account", callback_data="create_account")],
        [InlineKeyboardButton("📊 My Stats", callback_data="my_stats")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
    ]
    if is_admin(user.id):
        keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel")])

    text = (
        f"{premium_emoji(EMOJI['sparkle'])} <b>Welcome {user.first_name}!</b> {premium_emoji(EMOJI['sparkle'])}\n\n"
        f"{premium_emoji(EMOJI['rocket'])} <b>Meesho Account Creator Bot</b>\n\n"
        f"{premium_emoji(EMOJI['check'])} Create Meesho accounts instantly\n"
        f"{premium_emoji(EMOJI['shield'])} Secure OTP verification\n"
        f"{premium_emoji(EMOJI['key'])} Get account credentials\n\n"
        f"{premium_emoji(EMOJI['info'])} Select an option below:"
    )
    await send_premium_message(update, text, reply_markup=InlineKeyboardMarkup(keyboard))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"{premium_emoji(EMOJI['info'])} <b>How to Use:</b>\n\n"
        f"1. Click {premium_emoji(EMOJI['rocket'])} <b>Create Account</b>\n"
        f"2. Send your 10-digit mobile number\n"
        f"3. Enter the OTP received on your phone\n"
        f"4. Get your account credentials!\n\n"
        f"{premium_emoji(EMOJI['warning'])} <b>Note:</b>\n"
        f"• Use valid Indian mobile numbers\n"
        f"• OTP must be entered within time\n"
        f"• One account per number"
    )
    await send_premium_message(update, text)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "create_account":
        context.user_data["state"] = WAITING_PHONE
        text = (
            f"{premium_emoji(EMOJI['phone'])} <b>Send your mobile number</b>\n\n"
            f"Please enter your <b>10-digit</b> Indian mobile number.\n"
            f"Example: <code>9876543210</code>"
        )
        await query.edit_message_text(text, parse_mode="HTML")

    elif data == "my_stats":
        user = query.from_user
        text = (
            f"{premium_emoji(EMOJI['user'])} <b>Your Profile</b>\n\n"
            f"{premium_emoji(EMOJI['id'])} <b>User ID:</b> <code>{user.id}</code>\n"
            f"{premium_emoji(EMOJI['info'])} <b>Name:</b> {user.full_name}\n"
            f"{premium_emoji(EMOJI['user'])} <b>Username:</b> @{user.username or 'N/A'}"
        )
        await query.edit_message_text(text, parse_mode="HTML")

    elif data == "help":
        text = (
            f"{premium_emoji(EMOJI['info'])} <b>Help</b>\n\n"
            f"/start - Main menu\n/create - Create new account\n"
            f"/cancel - Cancel operation\n/help - Show help"
        )
        await query.edit_message_text(text, parse_mode="HTML")

    elif data == "admin_panel" and is_admin(query.from_user.id):
        text = (
            f"{premium_emoji(EMOJI['star'])} <b>Admin Panel</b>\n\n"
            f"{premium_emoji(EMOJI['check'])} Bot running\n"
            f"{premium_emoji(EMOJI['fire'])} Accounts created: {context.bot_data.get('accounts_created', 0)}"
        )
        await query.edit_message_text(text, parse_mode="HTML")


async def create_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = WAITING_PHONE
    text = (
        f"{premium_emoji(EMOJI['phone'])} <b>Send your mobile number</b>\n\n"
        f"Enter your <b>10-digit</b> Indian mobile number.\n"
        f"Example: <code>9876543210</code>"
    )
    await send_premium_message(update, text)


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await send_premium_message(
        update, f"{premium_emoji(EMOJI['cross'])} <b>Cancelled</b>\n\nUse /start to begin again."
    )


async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    if not phone.isdigit() or len(phone) != 10:
        await send_premium_message(
            update,
            f"{premium_emoji(EMOJI['warning'])} <b>Invalid Number</b>\n\n"
            f"Send a valid <b>10-digit</b> mobile number.",
        )
        return WAITING_PHONE

    context.user_data["phone"] = phone
    context.user_data["state"] = WAITING_OTP

    status_msg = await send_premium_message(
        update,
        f"{premium_emoji(EMOJI['loading'])} <b>Sending OTP...</b>\n\n"
        f"📱 Number: <code>{phone}</code>",
    )

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, send_meesho_otp, phone)

    if not result.get("ok"):
        await status_msg.edit_text(
            f"{premium_emoji(EMOJI['cross'])} <b>OTP Failed</b>\n\n"
            f"❌ <code>{result.get('error', 'Unknown')}</code>\n\nUse /create to retry.",
            parse_mode="HTML",
        )
        context.user_data.clear()
        return ConversationHandler.END

    context.user_data["session"] = result["session"]
    await status_msg.edit_text(
        f"{premium_emoji(EMOJI['check'])} <b>OTP Sent!</b>\n\n"
        f"📱 <code>{phone}</code>\n"
        f"{premium_emoji(EMOJI['key'])} <b>Enter the OTP:</b>",
        parse_mode="HTML",
    )
    return WAITING_OTP


async def handle_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    otp = update.message.text.strip()
    phone = context.user_data.get("phone")
    session = context.user_data.get("session")

    if not phone or not session:
        await send_premium_message(
            update, f"{premium_emoji(EMOJI['cross'])} <b>Session expired.</b> Use /create."
        )
        return ConversationHandler
