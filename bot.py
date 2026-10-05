import json
import sys
import uuid
import time
import base64
import secrets
import os
from curl_cffi import requests as cffi_requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# --- Constants (extracted from Meesho APK) ---
MEESHO_API = "https://prod.meeshoapi.com/api"
MEESHO_AUTH = "32c4d8137cn9eb493a1921f203173080"
ANON_XO = ("eyJ0eXBlIjoiY29tcG9zaXRlIn0=.eyJqd3QiOiJleUpoYkdjaU9pSklVekkxTmlJc0ltaDBkSEJ6"
           "T2k4dmJXVmxjMmh2TG1OdmJTOXBjMjlmWTI5MWJuUnllVjlqYjJSbElqb2lTVTRpTENKb2RIUndjem92"
           "TDIxbFpYTm9ieTVqYjIwdmRtVnljMmx2YmlJNklqRWlMQ0owZVhBaU9pSktWMVFpZlEuZXlKbGVIQWlP"
           "akU1TkRVek16STVOemdzSW1oMGRIQnpPaTh2YldWbGMyaHZMbU52YlM5aGJtOXVlVzF2ZFhOZmRYTmxj"
           "bDlwWkNJNkltTTVZbUk0WVRVekxUSXhaVE10TkRkallTMWlOamMwTFdGalpURXpOekZtWVRVM01TSXNJ"
           "bWgwZEhCek9pOHZiV1ZsYzJodkxtTnZiUzlwYm5OMFlXNWpaVjlwWkNJNkltUTNNVGc1TW1OaFlUZ3la"
           "alE1TlRFNVpqUmhNek5oTUdVd1lqZzNaamN3SWl3aWFXRjBJam94TnpnM05qVXlPVGM0ZlEuLUN6TXkt"
           "TEJ2VHpGV042VlROMDNKdzItLXhiX0lqSU9VZmpJRTk4eWlQUSIsInhvIjoiIn0=")

MEESHO_RSA_PUBKEY_B64 = ("MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAslmrLKGRzVnAtii3o89yI33FXZoRfBJ"
                         "V89PaCTp9Mxu7FgAaAOtaOnB2xWGG2a6Rz6zRzKPilRdAsm5oBW8mm8Uzvt7mbf7c7pjfBrjNdnKji"
                         "/9/zM3fpjh364/GwG3OpyYngD49i09ySljA7Elh97Pp+QJH2z25Xv2eRSHJPizgQ8TE1bJkP9fd9J"
                         "cfpGFyeEJX1bUIbgRlfED2TpJKGeaEfZ9no5+i/rgCaIRO9t86UqgeVJyCyJLnUkrU/ARPj9q/Aij"
                         "JV9kvyPT137UQLO+Cl6nZYOglqGcPnRbGiW6WM7imkSxR2XBn6N4ojf49nJOwnN826hkdH5JaPJ1p"
                         "AQIDAQAB")

# OTPLESS config
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

    # Step 1: Get state
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

    # Step 2: Send OTP intent
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

    # Exchange for Meesho xo
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

    # 3 header variants like meesho_json_generator.py
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
        print(f"  Login attempt {attempt+1} http {login_resp.status_code}")
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


def meesho_login_bot():
    print("Meesho Normal Account Creator (OTPLESS)\n")
    mobile = input("Enter 10 digit mobile number: ")

    print(f"\n[1/2] Sending OTP to {mobile}...")
    result = send_meesho_otp(mobile)
    if not result.get("ok"):
        print(f"OTP Failed: {result.get('error')}")
        sys.exit()
    print(f"OTP Sent! Status: OK")

    print("\nCheck your phone for OTP...")
    otp = input("Enter the OTP: ")

    print(f"\n[2/2] Verifying OTP...")
    vr = verify_meesho_otp(mobile, otp, result["session"])

    if vr.get("ok"):
        user_id = vr["user_id"]
        xo = vr["xo"]
        instance_id = vr["instance_id"]
        app_session_id = vr.get("app_session_id") or uuid.uuid4().hex
        ga_id = vr.get("ga_id") or str(uuid.uuid4())
        ox = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")[:88]
        phone_num = vr.get("phone") or mobile
        phone_last4 = str(phone_num)[-4:]
        is_new = vr.get("is_new", True)

        final_json = {
            "ok": True,
            "mobile": phone_num,
            "user_id": user_id,
            "phone": f"+91{phone_num}" if not phone_num.startswith("+") else phone_num,
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
    else:
        final_json = vr

    print(f"\n{'='*80}")
    print("FULL ACCOUNT JSON RESPONSE:")
    print(f"{'='*80}")
    print(json.dumps(final_json, indent=2))
    print()

    filename = f"meesho_{mobile}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(final_json, f, indent=2)
    print(f"Account saved as: {filename}")
    print("Done!")


if __name__ == "__main__":
    meesho_login_bot()
