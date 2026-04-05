# -*- coding: utf-8 -*-
import streamlit as st
import json
import os
import base64
import pandas as pd
from datetime import date, datetime
from PIL import Image
import glob
import requests
import anthropic
import hashlib
import uuid

# ==============================
# 設定
# ==============================
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
USERS_DIR  = os.path.join(BASE_DIR, "data")
USERS_FILE = os.path.join(USERS_DIR, "users.json")
os.makedirs(USERS_DIR, exist_ok=True)

# ==============================
# ユーザー認証
# ==============================
def hash_password(password, salt=None):
    if salt is None:
        salt = uuid.uuid4().hex
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return salt + ":" + hashed

def verify_password(password, stored):
    try:
        salt, _ = stored.split(":")
        return hash_password(password, salt) == stored
    except Exception:
        return False

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def get_user_dirs(username):
    """ユーザーごとのデータディレクトリとファイルパスを返す"""
    user_data = os.path.join(USERS_DIR, "user_" + username)
    user_csv  = os.path.join(user_data, "csv")
    user_photo = os.path.join(user_data, "photos")
    for d in [user_data, user_csv, user_photo]:
        os.makedirs(d, exist_ok=True)
    return {
        "DATA_DIR":        user_data,
        "CSV_DIR":         user_csv,
        "PHOTO_DIR":       user_photo,
        "KIDS_FILE":       os.path.join(user_data, "kids.json"),
        "CLOTHES_FILE":    os.path.join(user_data, "clothes.json"),
        "LINE_TOKEN_FILE": os.path.join(user_data, "line_token.json"),
        "NOTIFY_LOG_FILE": os.path.join(user_data, "notify_log.json"),
        "CLAUDE_KEY_FILE": os.path.join(user_data, "claude_api_key.json"),
    }

# ==============================
# データ読み書き（ユーザー別パス対応）
# ==============================
def _load_json(filepath, default=None):
    if default is None:
        default = []
    if os.path.exists(filepath):
        with open(filepath, encoding="utf-8") as f:
            return json.load(f)
    return default

def _save_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_kids():
    return _load_json(UP["KIDS_FILE"], [])
def save_kids(kids):
    _save_json(UP["KIDS_FILE"], kids)

def load_clothes():
    return _load_json(UP["CLOTHES_FILE"], [])
def save_clothes(clothes):
    _save_json(UP["CLOTHES_FILE"], clothes)

def load_line_token():
    data = _load_json(UP["LINE_TOKEN_FILE"], {})
    return data.get("token", "") if isinstance(data, dict) else ""
def save_line_token(token):
    _save_json(UP["LINE_TOKEN_FILE"], {"token": token})

def load_notify_log():
    return _load_json(UP["NOTIFY_LOG_FILE"], [])
def save_notify_log(log):
    _save_json(UP["NOTIFY_LOG_FILE"], log)

def load_claude_api_key():
    data = _load_json(UP["CLAUDE_KEY_FILE"], {})
    return data.get("api_key", "") if isinstance(data, dict) else ""
def save_claude_api_key(key):
    _save_json(UP["CLAUDE_KEY_FILE"], {"api_key": key})

# ==============================
# サイズアウト予測
# ==============================
SIZE_CHART = [80, 90, 95, 100, 110, 120, 130, 140, 150, 160, 170]
SHOE_SIZE_CHART = [12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25]

def _calc_age_and_growth(birthday_str):
    """誕生日から年齢と年間成長量(cm)を返す"""
    try:
        birthday  = datetime.strptime(birthday_str, "%Y-%m-%d").date()
        age_days  = (date.today() - birthday).days
        age_years = age_days / 365.25
    except Exception:
        age_years = 7
    if age_years <= 2:
        growth = 10
    elif age_years <= 5:
        growth = 7
    elif age_years <= 9:
        growth = 5.5
    else:
        growth = 5
    return age_years, growth

def predict_sizeout(height_cm, birthday_str, current_size):
    age_years, growth = _calc_age_and_growth(birthday_str)
    try:
        size_num = int(str(current_size).replace("cm", "").strip())
    except Exception:
        size_num = height_cm
    next_boundary  = next((s for s in SIZE_CHART if s > size_num), 170)
    cm_to_next     = next_boundary - size_num
    months_to_next = round((cm_to_next / growth) * 12)
    if months_to_next <= 2:
        status = "まもなくサイズアウト"
        color  = "red"
    elif months_to_next <= 5:
        status = "半年以内にサイズアウト"
        color  = "orange"
    else:
        status = "当面大丈夫"
        color  = "green"
    return {"status": status, "color": color, "months": months_to_next,
            "next_size": next_boundary, "cm_to_next": cm_to_next}

def predict_shoe_sizeout(birthday_str, current_shoe_size):
    """靴のサイズアウト予測"""
    age_years, _ = _calc_age_and_growth(birthday_str)
    # 足の成長速度 (cm/年): 幼児1.5cm, 学童1cm, それ以降0.5cm
    if age_years <= 3:
        foot_growth = 1.5
    elif age_years <= 6:
        foot_growth = 1.0
    else:
        foot_growth = 0.5
    try:
        shoe_num = float(str(current_shoe_size).replace("cm", "").strip())
    except Exception:
        shoe_num = 18
    next_shoe = next((s for s in SHOE_SIZE_CHART if s > shoe_num), 25)
    cm_to_next = next_shoe - shoe_num
    months_to_next = round((cm_to_next / foot_growth) * 12)
    if months_to_next <= 2:
        status = "まもなく靴サイズアウト"
        color  = "red"
    elif months_to_next <= 5:
        status = "半年以内に靴サイズアウト"
        color  = "orange"
    else:
        status = "当面大丈夫"
        color  = "green"
    return {"status": status, "color": color, "months": months_to_next,
            "next_size": next_shoe, "cm_to_next": cm_to_next}

# ==============================
# 季節別カテゴリ定義
# ==============================
SEASON_CATEGORIES = {
    "春秋": ["薄手トップス", "長ズボン", "スカート", "カーディガン", "パーカー"],
    "夏":   ["半袖Tシャツ", "タンクトップ", "キャミソール", "半ズボン", "スカート", "ワンピース"],
    "冬":   ["厚手トップス", "ヒートテック", "長ズボン", "スカート", "アウター", "防寒具"],
    "通年": ["下着（肌着）", "下着（パンツ）", "パジャマ", "靴下"],
}

ALL_CLOTHING_TYPES = sorted(set(
    item for items in SEASON_CATEGORIES.values() for item in items
))

# カテゴリ → 大分類（上服/下服/下着/パジャマ/アウター/小物）のマッピング
CATEGORY_TO_GROUP = {
    "薄手トップス": "上服", "半袖Tシャツ": "上服", "タンクトップ": "上服",
    "キャミソール": "上服", "厚手トップス": "上服", "ヒートテック": "上服",
    "カーディガン": "上服", "パーカー": "上服", "ワンピース": "上服",
    "長ズボン": "下服", "半ズボン": "下服", "スカート": "下服",
    "下着（肌着）": "下着", "下着（パンツ）": "下着",
    "パジャマ": "パジャマ",
    "アウター": "アウター", "防寒具": "アウター",
    "靴下": "小物",
}

def count_clothes_by_kid(clothes, kid_name, season_filter=None):
    """登録済みの服データから、子ども別・大分類別の枚数を自動集計"""
    counts = {"上服": 0, "下服": 0, "下着": 0, "パジャマ": 0, "アウター": 0, "小物": 0}
    for c in clothes:
        if c["kid"] != kid_name:
            continue
        if season_filter and season_filter != "すべて":
            if c.get("season", "通年") != season_filter and c.get("season", "通年") != "通年":
                continue
        group = CATEGORY_TO_GROUP.get(c["category"], "上服")
        counts[group] = counts.get(group, 0) + 1
    return counts

SEASONAL_NEEDS = {
    "spring": {
        "label": "春（3〜5月）", "months": [3, 4, 5],
        "items": ["薄手トップス", "長ズボン", "カーディガン", "スカート"],
    },
    "summer": {
        "label": "夏（6〜8月）", "months": [6, 7, 8],
        "items": ["半袖Tシャツ", "タンクトップ", "半ズボン", "スカート", "ワンピース"],
    },
    "autumn": {
        "label": "秋（9〜11月）", "months": [9, 10, 11],
        "items": ["薄手トップス", "長ズボン", "パーカー", "カーディガン"],
    },
    "winter": {
        "label": "冬（12〜2月）", "months": [12, 1, 2],
        "items": ["厚手トップス", "ヒートテック", "長ズボン", "アウター", "防寒具"],
    },
}

def get_current_season(month):
    if month in [3, 4, 5]: return "spring"
    elif month in [6, 7, 8]: return "summer"
    elif month in [9, 10, 11]: return "autumn"
    else: return "winter"

def get_next_season(current):
    order = ["spring", "summer", "autumn", "winter"]
    return order[(order.index(current) + 1) % 4]

def guess_season_from_category(category):
    """服のカテゴリ名から季節を推定"""
    summer_kw = ["半袖", "タンクトップ", "キャミソール", "半ズボン", "ワンピース"]
    winter_kw = ["厚手", "ヒートテック", "アウター", "防寒"]
    spring_kw = ["薄手", "カーディガン", "パーカー"]
    year_kw   = ["下着", "パジャマ", "靴下"]
    for kw in year_kw:
        if kw in category: return "通年"
    for kw in summer_kw:
        if kw in category: return "夏"
    for kw in winter_kw:
        if kw in category: return "冬"
    for kw in spring_kw:
        if kw in category: return "春秋"
    return "通年"

# ==============================
# CSV 分析
# ==============================
KID_CLOTH_CATS = ["子どもの服", "子ども服"]
KID_CLOTH_KW   = ["バースデイ", "西松屋", "ワークマン", "ユニクロ", "しまむら",
                   "アベイル", "ゾゾタウン", "GU", "スクスク", "ニシマツヤ"]
SHOP_KW = {
    "ユニクロ/GU": ["ユニクロ", "GU", "ジーユー", "PLST"],
    "西松屋":      ["西松屋", "ニシマツヤ"],
    "バースデイ":  ["バースデイ", "バースデー"],
    "ワークマン":  ["ワークマン"],
    "しまむら":    ["しまむら", "ファッションセンター"],
    "ゾゾタウン":  ["ゾゾタウン", "ZOZOTOWN"],
    "アベイル":    ["アベイル"],
    "その他":      [],
}

def detect_shop(content):
    for shop, kws in SHOP_KW.items():
        if shop == "その他": continue
        if any(k in content for k in kws): return shop
    return "その他"

def parse_csv_files():
    files = glob.glob(os.path.join(UP["CSV_DIR"], "*.csv"))
    monthly, shop_amounts, transactions = {}, {}, []
    for fpath in files:
        try:
            df = pd.read_csv(fpath, encoding="utf-8", header=0)
        except Exception:
            try:
                df = pd.read_csv(fpath, encoding="shift-jis", header=0)
            except Exception:
                continue
        for _, row in df.iterrows():
            try:
                calc = str(row.iloc[0]); date_s = str(row.iloc[1])
                content = str(row.iloc[2])
                amount = int(str(row.iloc[3]).replace(",", ""))
                sub_cat = str(row.iloc[6]) if len(row) > 6 else ""
            except Exception:
                continue
            if calc == "0" or amount >= 0: continue
            is_kid = (sub_cat in KID_CLOTH_CATS or
                      any(k in content for k in KID_CLOTH_KW) or
                      any(k in sub_cat for k in KID_CLOTH_KW))
            if not is_kid: continue
            amt = abs(amount)
            ym = date_s[:7].replace("/", "-")
            monthly[ym] = monthly.get(ym, 0) + amt
            shop = detect_shop(content)
            shop_amounts.setdefault(shop, []).append(amt)
            transactions.append({"date": date_s, "content": content, "amount": amt, "shop": shop, "ym": ym})
    return monthly, shop_amounts, transactions

def calc_price_per_item(shop_amounts):
    result = {}
    for shop, amts in shop_amounts.items():
        if amts: result[shop] = round(sum(amts) / len(amts) / 2.5)
    return result

# ==============================
# 写真から服カテゴリ推定
# ==============================
def analyze_clothing_image_ai(image, api_key):
    """Claude Vision APIで写真から服の種類を高精度分析"""
    import io
    buf = io.BytesIO()
    img_resized = image.copy()
    img_resized.thumbnail((512, 512))
    img_resized.save(buf, format="JPEG", quality=80)
    img_b64 = base64.b64encode(buf.getvalue()).decode()

    categories_str = "、".join(ALL_CLOTHING_TYPES)
    prompt = (
        "この写真に写っている子ども服を分析してください。\n"
        "以下のカテゴリから最も適切なものを1つ選んでください:\n"
        f"{categories_str}\n\n"
        "回答は必ず以下のJSON形式のみで返してください（説明不要）:\n"
        '{"category": "カテゴリ名", "confidence": "高/中/低", '
        '"color": "色の説明", "detail": "素材や特徴の短い説明", '
        '"alternatives": ["候補2", "候補3"]}'
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        response_text = message.content[0].text.strip()
        # JSON部分を抽出
        if "{" in response_text:
            json_str = response_text[response_text.index("{"):response_text.rindex("}") + 1]
            result = json.loads(json_str)
            cat = result.get("category", "薄手トップス")
            # カテゴリがリストにあるか確認
            if cat not in ALL_CLOTHING_TYPES:
                # 部分一致で探す
                for t in ALL_CLOTHING_TYPES:
                    if t in cat or cat in t:
                        cat = t
                        break
                else:
                    cat = "薄手トップス"
            alts = []
            for a in result.get("alternatives", []):
                if a in ALL_CLOTHING_TYPES:
                    alts.append((a, "中"))
            return {
                "suggested_category": cat,
                "confidence": result.get("confidence", "中"),
                "alternatives": alts,
                "color_info": result.get("color", ""),
                "detail": result.get("detail", ""),
                "ai_used": True,
            }
    except Exception as e:
        return {"error": str(e)}
    return {"error": "解析に失敗しました"}

def analyze_clothing_image_simple(image):
    """フォールバック: 画像の色・形状から簡易推定"""
    import numpy as np
    width, height = image.size
    aspect_ratio = width / height
    thumb = image.resize((100, 100)).convert("RGB")
    pixels = np.array(thumb)
    avg_r, avg_g, avg_b = pixels.mean(axis=(0, 1))
    brightness = (avg_r + avg_g + avg_b) / 3
    is_dark = brightness < 100

    candidates = []
    if aspect_ratio < 0.6:
        candidates.append(("長ズボン" if is_dark else "半ズボン", "低"))
    elif aspect_ratio > 1.5:
        candidates.append(("半袖Tシャツ", "低"))
    elif 0.6 <= aspect_ratio <= 0.85:
        candidates.append(("スカート", "低"))
    else:
        if is_dark:
            candidates.append(("厚手トップス", "低"))
        elif brightness > 210:
            candidates.append(("下着（肌着）", "低"))
        else:
            candidates.append(("薄手トップス", "低"))
    if not candidates:
        candidates.append(("薄手トップス", "低"))
    return {
        "suggested_category": candidates[0][0],
        "confidence": candidates[0][1],
        "alternatives": [],
        "ai_used": False,
    }

def analyze_clothing_image(image):
    """写真から服の種類を推定（APIキーがあればClaude Vision、なければ簡易分析）"""
    api_key = load_claude_api_key()
    if api_key:
        result = analyze_clothing_image_ai(image, api_key)
        if "error" not in result:
            return result
    return analyze_clothing_image_simple(image)

# ==============================
# LINE Notify
# ==============================
def send_line_notify(token, message):
    try:
        r = requests.post("https://notify-api.line.me/api/notify",
                          headers={"Authorization": "Bearer " + token},
                          data={"message": message}, timeout=10)
        return r.status_code == 200, r.status_code
    except Exception as e:
        return False, str(e)

def estimate_sizeout_cost(kid):
    """サイズアウト時にかかる買い替え費用を推定（登録済みの服から自動集計）"""
    recommend = {"上服": 7, "下服": 6, "下着": 10, "パジャマ": 2}
    all_c = load_clothes()
    current_m = datetime.now().month
    cs_key = get_current_season(current_m)
    sn_map = {"spring": "春秋", "summer": "夏", "autumn": "春秋", "winter": "冬"}
    cs_name = sn_map.get(cs_key, "通年")
    counts = count_clothes_by_kid(all_c, kid["name"], cs_name)
    needs = {"上服": max(0, recommend["上服"] - counts["上服"]),
             "下服": max(0, recommend["下服"] - counts["下服"]),
             "下着": max(0, recommend["下着"] - counts["下着"]),
             "パジャマ": max(0, recommend["パジャマ"] - counts["パジャマ"])}
    # CSVデータから平均単価を計算、なければデフォルト
    try:
        _, shop_amounts, _ = parse_csv_files()
        price_per_item = calc_price_per_item(shop_amounts)
        base_price = round(sum(price_per_item.values()) / len(price_per_item)) if price_per_item else 1500
    except Exception:
        base_price = 1500
    clothes_cost = sum(n * base_price for n in needs.values())
    # 靴の買い替え費用（子ども靴の平均）
    shoe_cost = 2500
    total = clothes_cost + shoe_cost
    return {"clothes_cost": clothes_cost, "shoe_cost": shoe_cost, "total": total,
            "base_price": base_price, "needs": needs}

def check_and_notify_sizeout(kids, token):
    results = []
    for kid in kids:
        pred = predict_sizeout(kid.get("height", 120), kid.get("birthday", "2016-01-01"), kid.get("size", "120"))
        shoe_pred = predict_shoe_sizeout(kid.get("birthday", "2016-01-01"), kid.get("shoe_size", "18"))
        # 服または靴がサイズアウト近い場合に通知
        if pred["color"] in ["red", "orange"] or shoe_pred["color"] in ["red", "orange"]:
            cost = estimate_sizeout_cost(kid)
            msg = "\n" + kid["name"] + "のサイズアウト情報\n"
            if pred["color"] in ["red", "orange"]:
                msg += ("\n【服】" + pred["status"] + "\n"
                        "現在: " + str(kid.get("size", "?")) + "cm → 次: " + str(pred["next_size"]) + "cm\n"
                        "あと約" + str(pred["months"]) + "ヶ月\n")
            if shoe_pred["color"] in ["red", "orange"]:
                msg += ("\n【靴】" + shoe_pred["status"] + "\n"
                        "現在: " + str(kid.get("shoe_size", "?")) + "cm → 次: " + str(shoe_pred["next_size"]) + "cm\n"
                        "あと約" + str(shoe_pred["months"]) + "ヶ月\n")
            msg += ("\n【買い替え費用の目安】\n"
                    "服: 約¥" + str(cost["clothes_cost"]) + "\n"
                    "靴: 約¥" + str(cost["shoe_cost"]) + "\n"
                    "合計: 約¥" + str(cost["total"]) + "\n"
                    "(1枚あたり¥" + str(cost["base_price"]) + "で計算)\n"
                    "\nKids Closetで確認してね！")
            success, status = send_line_notify(token, msg)
            notify_status = []
            if pred["color"] in ["red", "orange"]:
                notify_status.append(pred["status"])
            if shoe_pred["color"] in ["red", "orange"]:
                notify_status.append(shoe_pred["status"])
            results.append({"kid": kid["name"], "status": " / ".join(notify_status),
                            "sent": success, "response": status,
                            "cost": cost["total"],
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M")})
    return results

# ==============================
# アイコン読み込み (base64)
# ==============================
ICON_DIR = os.path.join(BASE_DIR, "static", "icons")

def load_icon_b64(filename):
    path = os.path.join(ICON_DIR, filename)
    if os.path.exists(path):
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return ""

# タブ用アイコン
ICON_LOGO     = load_icon_b64("logo.png")
ICON_BABY     = load_icon_b64("baby.png")
ICON_CLOTHING = load_icon_b64("clothing.png")
ICON_CHART    = load_icon_b64("chart.png")
ICON_CAMERA   = load_icon_b64("camera.png")
ICON_BELL     = load_icon_b64("bell.png")
# フォーム用アイコン
ICON_NAMETAG   = load_icon_b64("nametag.png")
ICON_STAR      = load_icon_b64("star.png")
ICON_BIRTHDAY  = load_icon_b64("birthday.png")
ICON_RULER     = load_icon_b64("ruler.png")
ICON_PANTS     = load_icon_b64("pants.png")
ICON_PAJAMAS   = load_icon_b64("pajamas.png")
ICON_UNDERWEAR = load_icon_b64("underwear.png")
ICON_CSV       = load_icon_b64("csv_upload.png")
ICON_SHOE      = load_icon_b64("shoe.png")

def icon_img(b64, size=18):
    """インラインアイコンHTML"""
    if b64:
        return (f'<img src="data:image/png;base64,{b64}" '
                f'width="{size}" height="{size}" '
                f'style="vertical-align:middle;margin-right:4px;">')
    return ""

def icon_heading(b64, text, level=3, size=24):
    """アイコン付き見出しHTML"""
    return (f'<h{level} style="color:#2D1B14;">'
            f'{icon_img(b64, size)}{text}</h{level}>')

# ==============================
# ページ設定
# ==============================
_logo_path = os.path.join(BASE_DIR, "static", "icons", "logo.png")
st.set_page_config(page_title="Kids Closet",
                   page_icon=Image.open(_logo_path) if os.path.exists(_logo_path) else "",
                   layout="centered")

# iOS ホーム画面アイコン & PWA設定
_apple_icon_path = os.path.join(BASE_DIR, "static", "apple-touch-icon.png")
if os.path.exists(_apple_icon_path):
    with open(_apple_icon_path, "rb") as _f:
        _apple_b64 = base64.b64encode(_f.read()).decode()
    import streamlit.components.v1 as components
    components.html(f"""
    <script>
    (function() {{
        if (!document.querySelector('link[rel="apple-touch-icon"]')) {{
            var link = document.createElement('link');
            link.rel = 'apple-touch-icon';
            link.sizes = '180x180';
            link.href = 'data:image/png;base64,{_apple_b64}';
            document.head.appendChild(link);
        }}
        if (!document.querySelector('meta[name="apple-mobile-web-app-capable"]')) {{
            var meta = document.createElement('meta');
            meta.name = 'apple-mobile-web-app-capable';
            meta.content = 'yes';
            document.head.appendChild(meta);
            var meta2 = document.createElement('meta');
            meta2.name = 'apple-mobile-web-app-title';
            meta2.content = 'Kids Closet';
            document.head.appendChild(meta2);
            var meta3 = document.createElement('meta');
            meta3.name = 'apple-mobile-web-app-status-bar-style';
            meta3.content = 'default';
            document.head.appendChild(meta3);
        }}
    }})();
    </script>
    """, height=0)

# ==============================
# カラフルポップCSS + カスタムアイコン
# ==============================
_icon_css = (
    ".stTabs [data-baseweb='tab-list'] button:nth-child(1)"
    "{background-image:url('data:image/png;base64," + ICON_BABY + "')!important}"
    ".stTabs [data-baseweb='tab-list'] button:nth-child(2)"
    "{background-image:url('data:image/png;base64," + ICON_CLOTHING + "')!important}"
    ".stTabs [data-baseweb='tab-list'] button:nth-child(3)"
    "{background-image:url('data:image/png;base64," + ICON_CHART + "')!important}"
    ".stTabs [data-baseweb='tab-list'] button:nth-child(4)"
    "{background-image:url('data:image/png;base64," + ICON_CAMERA + "')!important}"
    ".stTabs [data-baseweb='tab-list'] button:nth-child(5)"
    "{background-image:url('data:image/png;base64," + ICON_BELL + "')!important}"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap');
html, body, [class*="css"] { font-family: 'Noto Sans JP', sans-serif !important; }
.block-container { padding-top: 1rem !important; }
h1 { display: none !important; }
h2, h3 { color: #2D1B14 !important; }
.icon-label { display:flex; align-items:center; gap:4px; margin-bottom:2px; font-size:0.9rem; font-weight:500; color:#2D1B14; }
.icon-label img { flex-shrink:0; }
.stTabs [data-baseweb="tab-list"] {
    gap: 6px; background-color: #FFE8E0; border-radius: 16px; padding: 6px;
    flex-wrap: wrap; justify-content: center;
}
.stTabs [data-baseweb="tab-list"] button {
    border-radius: 14px !important; font-weight: 700;
    padding: 0.5rem 0.8rem 0.5rem 2.5rem; font-size: 0.8rem;
    border: 2px solid transparent !important; background-color: white !important;
    color: #2D1B14 !important; box-shadow: 0 2px 6px rgba(255, 142, 83, 0.15);
    transition: all 0.25s ease; background-repeat: no-repeat !important;
    background-position: 6px center !important; background-size: 18px 18px !important;
}
.stTabs [data-baseweb="tab-list"] button:hover {
    transform: translateY(-1px); box-shadow: 0 4px 12px rgba(255, 107, 107, 0.25);
    border-color: #FF6B6B !important;
}
.stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {
    background-color: #FF6B6B !important; color: white !important;
    border-radius: 14px !important; border-color: #FF6B6B !important;
    box-shadow: 0 4px 14px rgba(255, 107, 107, 0.4);
}
.stButton > button {
    border-radius: 20px !important; font-weight: 600; min-height: 2.5rem;
    border: none !important; background: linear-gradient(135deg, #FF6B6B, #FF8E53) !important;
    color: white !important; transition: all 0.3s ease;
    box-shadow: 0 2px 8px rgba(255, 107, 107, 0.3);
}
.stButton > button:hover {
    transform: translateY(-1px); box-shadow: 0 4px 12px rgba(255, 107, 107, 0.4) !important;
}
.clothing-card {
    border: 2px solid #FFD4C4; border-radius: 16px; padding: 0.8rem;
    margin-bottom: 0.8rem; background: white;
    box-shadow: 0 2px 8px rgba(255, 142, 83, 0.1);
}
.streamlit-expanderHeader {
    font-size: 1rem; font-weight: 600; border-radius: 12px !important;
    background-color: #FFF0EB !important;
}
[data-testid="stMetricValue"] { color: #FF6B6B !important; font-weight: 700 !important; }
.stAlert { border-radius: 12px !important; }
hr { border-color: #FFD4C4 !important; }
.stSelectbox > div > div, .stTextInput > div > div > input,
.stNumberInput > div > div > input {
    border-radius: 12px !important; border-color: #FFD4C4 !important;
}
.season-badge {
    display: inline-block; padding: 2px 10px; border-radius: 10px;
    font-size: 0.75rem; font-weight: 600; margin-left: 4px;
}
.season-spring { background: #E8F5E9; color: #2E7D32; }
.season-summer { background: #FFF3E0; color: #E65100; }
.season-winter { background: #E3F2FD; color: #1565C0; }
.season-year   { background: #F3E5F5; color: #7B1FA2; }
@media (max-width: 768px) {
    .block-container { padding-left: 0.5rem !important; padding-right: 0.5rem !important; padding-top: 1rem !important; }
    .stTabs [data-baseweb="tab-list"] button { font-size: 0.78rem; padding: 0.5rem 0.6rem 0.5rem 2.2rem; }
    .stButton > button { min-height: 2.8rem; font-size: 1rem; width: 100%; }
    .stTextInput input, .stNumberInput input, .stSelectbox select, .stDateInput input { font-size: 16px !important; }
    [data-testid="stMetricValue"] { font-size: 1.3rem !important; }
    .streamlit-expanderHeader { font-size: 1rem; padding: 0.75rem 0.5rem; }
}
</style>
<style>""" + _icon_css + """</style>
""", unsafe_allow_html=True)

# ==============================
# ログイン / 新規登録
# ==============================
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
    st.session_state["username"] = ""

def show_login_page():
    st.markdown(
        f'<div style="text-align:center;margin:2rem 0 1rem;">'
        f'<img src="data:image/png;base64,{ICON_LOGO}" width="80" height="80"><br>'
        f'<span style="font-size:2.2rem;font-weight:800;color:#FF6B6B;">Kids Closet</span>'
        f'<p style="color:#999;font-size:0.9rem;">子どもの成長記録・服の管理・衣類費の予測</p>'
        f'</div>', unsafe_allow_html=True)

    login_tab, register_tab = st.tabs(["ログイン", "新規登録"])

    with login_tab:
        st.markdown(f'<div class="icon-label">{icon_img(ICON_NAMETAG)}ユーザー名</div>', unsafe_allow_html=True)
        login_user = st.text_input("ユーザー名", label_visibility="collapsed", key="login_user",
                                    placeholder="ユーザー名を入力")
        st.markdown(f'<div class="icon-label">{icon_img(ICON_STAR)}パスワード</div>', unsafe_allow_html=True)
        login_pass = st.text_input("パスワード", type="password", label_visibility="collapsed", key="login_pass",
                                    placeholder="パスワードを入力")
        if st.button("ログイン", key="btn_login", use_container_width=True):
            if not login_user or not login_pass:
                st.warning("ユーザー名とパスワードを入力してください")
            else:
                users = load_users()
                if login_user in users and verify_password(login_pass, users[login_user]["password"]):
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = login_user
                    st.rerun()
                else:
                    st.error("ユーザー名またはパスワードが間違っています")

    with register_tab:
        st.markdown(f'<div class="icon-label">{icon_img(ICON_NAMETAG)}ユーザー名（半角英数字）</div>', unsafe_allow_html=True)
        reg_user = st.text_input("ユーザー名", label_visibility="collapsed", key="reg_user",
                                  placeholder="例: kids_closet")
        st.markdown(f'<div class="icon-label">{icon_img(ICON_STAR)}パスワード（6文字以上）</div>', unsafe_allow_html=True)
        reg_pass = st.text_input("パスワード", type="password", label_visibility="collapsed", key="reg_pass",
                                  placeholder="パスワードを入力")
        st.markdown(f'<div class="icon-label">{icon_img(ICON_STAR)}パスワード確認</div>', unsafe_allow_html=True)
        reg_pass2 = st.text_input("パスワード確認", type="password", label_visibility="collapsed", key="reg_pass2",
                                   placeholder="もう一度パスワードを入力")
        if st.button("アカウントを作成", key="btn_register", use_container_width=True):
            if not reg_user or not reg_pass:
                st.warning("ユーザー名とパスワードを入力してください")
            elif len(reg_pass) < 6:
                st.warning("パスワードは6文字以上にしてください")
            elif reg_pass != reg_pass2:
                st.error("パスワードが一致しません")
            elif not reg_user.replace("_", "").replace("-", "").isalnum():
                st.warning("ユーザー名は半角英数字と_-のみ使えます")
            else:
                users = load_users()
                if reg_user in users:
                    st.error("このユーザー名は既に使われています")
                else:
                    users[reg_user] = {
                        "password": hash_password(reg_pass),
                        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    }
                    save_users(users)
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = reg_user
                    st.success("アカウントを作成しました！")
                    st.rerun()

if not st.session_state["logged_in"]:
    show_login_page()
    st.stop()

# ユーザー別のデータパスを設定
UP = get_user_dirs(st.session_state["username"])

# ==============================
# タイトル（ログイン後）
# ==============================
st.title("Kids Closet")

# ログアウトボタンをヘッダー右に配置
col_title, col_logout = st.columns([4, 1])
with col_title:
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:4px;">'
        f'<img src="data:image/png;base64,{ICON_LOGO}" width="52" height="52">'
        f'<span style="font-size:2rem;font-weight:800;color:#FF6B6B;">Kids Closet</span>'
        f'</div>'
        f'<p style="color:#999;font-size:0.9rem;margin-top:0;">'
        f'{icon_img(ICON_BABY, 14)}{st.session_state["username"]} さん</p>',
        unsafe_allow_html=True)
with col_logout:
    if st.button("ログアウト", key="btn_logout"):
        st.session_state["logged_in"] = False
        st.session_state["username"] = ""
        st.rerun()

tabs = st.tabs(["子ども設定", "服の管理", "CSV分析・予測", "写真一覧", "通知設定"])

def season_badge(season):
    cls_map = {"春秋": "season-spring", "夏": "season-summer", "冬": "season-winter", "通年": "season-year"}
    cls = cls_map.get(season, "season-year")
    return f'<span class="season-badge {cls}">{season}</span>'

# ==============================
# TAB 1: 子ども設定
# ==============================
with tabs[0]:
    st.markdown(icon_heading(ICON_BABY, "お子さまの情報"), unsafe_allow_html=True)
    kids = load_kids()

    # 追加成功メッセージの表示
    if st.session_state.get("kid_added"):
        st.success(st.session_state["kid_added"] + " を追加しました！")
        del st.session_state["kid_added"]

    with st.expander("＋ 子どもを追加する", expanded=len(kids) == 0):
        st.markdown(f'<div class="icon-label">{icon_img(ICON_NAMETAG)}名前（例：長男）</div>', unsafe_allow_html=True)
        new_name = st.text_input("名前", label_visibility="collapsed", key="new_name")

        st.markdown(f'<div class="icon-label">{icon_img(ICON_STAR)}性別</div>', unsafe_allow_html=True)
        new_gender = st.selectbox("性別", ["男の子", "女の子"], label_visibility="collapsed", key="new_gender")

        st.markdown(f'<div class="icon-label">{icon_img(ICON_BIRTHDAY)}誕生日</div>', unsafe_allow_html=True)
        new_bday = st.date_input("誕生日", value=date(2016, 1, 1), min_value=date(2000, 1, 1),
                                  max_value=date.today(), label_visibility="collapsed", key="new_bday")

        st.markdown(f'<div class="icon-label">{icon_img(ICON_RULER)}現在の身長 (cm)</div>', unsafe_allow_html=True)
        new_height = st.number_input("身長", 50, 200, 120, label_visibility="collapsed", key="new_height")

        st.markdown(f'<div class="icon-label">{icon_img(ICON_CLOTHING)}現在着ているサイズ</div>', unsafe_allow_html=True)
        new_size = st.selectbox("サイズ", ["80","90","95","100","110","120","130","140","150","160","170"],
                                label_visibility="collapsed", key="new_size")

        st.markdown(f'<div class="icon-label">{icon_img(ICON_SHOE)}現在の靴のサイズ (cm)</div>', unsafe_allow_html=True)
        new_shoe_size = st.selectbox("靴サイズ", ["12","13","14","15","16","17","18","19","20","21","22","23","24","25"],
                                      index=4, label_visibility="collapsed", key="new_shoe")

        if st.button("追加する"):
            if new_name:
                kids.append({"name": new_name, "gender": new_gender,
                             "birthday": new_bday.strftime("%Y-%m-%d"), "height": new_height,
                             "size": new_size, "shoe_size": new_shoe_size})
                save_kids(kids)
                # 成功メッセージをセッションに保存
                st.session_state["kid_added"] = new_name
                # フォームをリセット
                for k in ["new_name", "new_gender", "new_bday", "new_height",
                           "new_size", "new_shoe"]:
                    if k in st.session_state:
                        del st.session_state[k]
                st.rerun()
            else:
                st.warning("名前を入力してください")

    if kids:
        st.divider()
        for i, kid in enumerate(kids):
            st.markdown(f'{icon_heading(ICON_BABY, kid["name"] + "（" + kid.get("gender","") + "）", level=4, size=20)}',
                        unsafe_allow_html=True)
            bday = kid.get("birthday", "")
            try:
                age_days = (date.today() - datetime.strptime(bday, "%Y-%m-%d").date()).days
                age_y = int(age_days // 365)
                age_m = int((age_days % 365) // 30)
                st.markdown(f'<p style="font-size:0.85rem;color:#666;">{icon_img(ICON_BIRTHDAY, 14)}誕生日: {bday}（{age_y}歳{age_m}ヶ月）</p>', unsafe_allow_html=True)
            except Exception:
                st.markdown(f'<p style="font-size:0.85rem;color:#666;">{icon_img(ICON_BIRTHDAY, 14)}誕生日: {bday}</p>', unsafe_allow_html=True)
            st.markdown(
                f'<p style="font-size:0.85rem;color:#666;">'
                f'{icon_img(ICON_RULER, 14)}身長: {kid.get("height","?")}cm　'
                f'{icon_img(ICON_CLOTHING, 14)}サイズ: {kid.get("size","?")}　'
                f'{icon_img(ICON_SHOE, 14)}靴: {kid.get("shoe_size","?")}cm</p>',
                unsafe_allow_html=True)

            pred = predict_sizeout(kid.get("height", 120), kid.get("birthday", "2016-01-01"), kid.get("size", "120"))
            st.markdown(f'<p style="font-weight:600;">{icon_img(ICON_CHART, 16)}服のサイズアウト予測</p>', unsafe_allow_html=True)
            if pred["color"] == "red":
                st.error(pred["status"])
            elif pred["color"] == "orange":
                st.warning(pred["status"])
            else:
                st.success(pred["status"])
            st.caption("次のサイズ(" + str(pred["next_size"]) + "cm)まで あと " +
                       str(pred["cm_to_next"]) + "cm・約 " + str(pred["months"]) + "ヶ月")

            shoe_pred = predict_shoe_sizeout(kid.get("birthday", "2016-01-01"), kid.get("shoe_size", "18"))
            st.markdown(f'<p style="font-weight:600;">{icon_img(ICON_SHOE, 16)}靴のサイズアウト予測</p>', unsafe_allow_html=True)
            if shoe_pred["color"] == "red":
                st.error(shoe_pred["status"])
            elif shoe_pred["color"] == "orange":
                st.warning(shoe_pred["status"])
            else:
                st.success(shoe_pred["status"])
            st.caption("次の靴サイズ(" + str(shoe_pred["next_size"]) + "cm)まで あと約 " + str(shoe_pred["months"]) + "ヶ月")

            # 登録済みの服から自動集計
            all_clothes = load_clothes()
            current_month = datetime.now().month
            cur_season_key = get_current_season(current_month)
            season_name_map = {"spring": "春秋", "summer": "夏", "autumn": "春秋", "winter": "冬"}
            cur_season_name = season_name_map.get(cur_season_key, "通年")

            counts_all = count_clothes_by_kid(all_clothes, kid["name"])
            counts_season = count_clothes_by_kid(all_clothes, kid["name"], cur_season_name)
            total_registered = sum(counts_all.values())

            st.markdown(f'<p style="font-weight:600;">{icon_img(ICON_CLOTHING, 16)}登録済みの服（全{total_registered}枚）</p>', unsafe_allow_html=True)
            # 今のシーズン
            st.markdown(f'<p style="font-size:0.85rem;color:#666;">今のシーズン（{cur_season_name}+通年）の枚数:</p>', unsafe_allow_html=True)
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                st.markdown(f'<span style="font-size:0.85rem;">{icon_img(ICON_CLOTHING, 14)}上服: {counts_season["上服"]}枚</span>', unsafe_allow_html=True)
                st.markdown(f'<span style="font-size:0.85rem;">{icon_img(ICON_PANTS, 14)}下服: {counts_season["下服"]}枚</span>', unsafe_allow_html=True)
            with col_b:
                st.markdown(f'<span style="font-size:0.85rem;">{icon_img(ICON_UNDERWEAR, 14)}下着: {counts_season["下着"]}枚</span>', unsafe_allow_html=True)
                st.markdown(f'<span style="font-size:0.85rem;">{icon_img(ICON_PAJAMAS, 14)}パジャマ: {counts_season["パジャマ"]}枚</span>', unsafe_allow_html=True)
            with col_c:
                st.markdown(f'<span style="font-size:0.85rem;">{icon_img(ICON_CLOTHING, 14)}アウター: {counts_season["アウター"]}枚</span>', unsafe_allow_html=True)
                st.markdown(f'<span style="font-size:0.85rem;">{icon_img(ICON_SHOE, 14)}小物: {counts_season["小物"]}枚</span>', unsafe_allow_html=True)
            if total_registered == 0:
                st.caption("「服の管理」タブで服を登録すると自動的にカウントされます")

            if st.button("削除", key="del_" + str(i)):
                kids.pop(i)
                save_kids(kids)
                st.rerun()
            st.divider()

# ==============================
# TAB 2: 服の管理
# ==============================
with tabs[1]:
    st.markdown(icon_heading(ICON_CLOTHING, "服の登録・管理"), unsafe_allow_html=True)
    kids = load_kids()
    clothes = load_clothes()

    if not kids:
        st.info("先に「子ども設定」タブで子どもを追加してください")
    else:
        with st.expander("パシャッと服を登録する", expanded=False):
            st.markdown(f'<p style="font-weight:600;">{icon_img(ICON_CAMERA, 18)}ステップ1: 写真を撮ろう！</p>', unsafe_allow_html=True)
            st.caption("スマホのカメラで直接撮影するか、写真をアップロードしてね")

            camera_photo = st.camera_input("服の写真を撮る", label_visibility="collapsed")
            upload_photo = st.file_uploader("写真をアップロード", type=["jpg", "jpeg", "png"])

            photo_source = None
            photo_image = None
            if camera_photo is not None:
                photo_source = camera_photo
                photo_image = Image.open(camera_photo)
            elif upload_photo is not None:
                photo_source = upload_photo
                photo_image = Image.open(upload_photo)

            suggested_cat = "薄手トップス"
            suggested_season = "通年"
            if photo_image is not None:
                st.image(photo_image, caption="撮影した写真", use_container_width=True)
                with st.spinner("写真を解析中..."):
                    analysis = analyze_clothing_image(photo_image)
                suggested_cat = analysis["suggested_category"]
                suggested_season = guess_season_from_category(suggested_cat)
                confidence_map = {"高": "高い", "中": "まあまあ", "低": "低い（要確認）"}
                conf_label = confidence_map.get(analysis["confidence"], analysis["confidence"])
                if analysis.get("ai_used"):
                    info_text = "Claude AI判定: **" + suggested_cat + "**（" + suggested_season + "） 確度: " + conf_label
                    if analysis.get("color_info"):
                        info_text += "\n\n色: " + analysis["color_info"]
                    if analysis.get("detail"):
                        info_text += "　｜　" + analysis["detail"]
                else:
                    info_text = "簡易推定: **" + suggested_cat + "**（" + suggested_season + "） 確度: " + conf_label
                    info_text += "\n\n（APIキーを設定するとAIが高精度で判定します）"
                if analysis.get("alternatives"):
                    alt_names = [a[0] for a in analysis["alternatives"]]
                    info_text += "\n\n他の候補: " + "、".join(alt_names)
                info_text += "\n\n違う場合は下のセレクトボックスで変更してください"
                st.info(info_text)

            st.markdown(f'<p style="font-weight:600;">{icon_img(ICON_NAMETAG, 18)}ステップ2: 情報を入力</p>', unsafe_allow_html=True)

            kid_names = [k["name"] for k in kids]
            st.markdown(f'<div class="icon-label">{icon_img(ICON_BABY)}誰の服？</div>', unsafe_allow_html=True)
            c_kid = st.selectbox("誰の服", kid_names, label_visibility="collapsed", key="c_kid")

            # 季節で絞ったカテゴリ
            season_options = list(SEASON_CATEGORIES.keys())
            st.markdown(f'<div class="icon-label">{icon_img(ICON_STAR)}季節</div>', unsafe_allow_html=True)
            default_season_idx = season_options.index(suggested_season) if suggested_season in season_options else 3
            c_season = st.selectbox("季節", season_options, index=default_season_idx,
                                    label_visibility="collapsed", key="c_season")

            cat_options = SEASON_CATEGORIES.get(c_season, ALL_CLOTHING_TYPES)
            default_cat_idx = cat_options.index(suggested_cat) if suggested_cat in cat_options else 0
            st.markdown(f'<div class="icon-label">{icon_img(ICON_CLOTHING)}カテゴリ</div>', unsafe_allow_html=True)
            c_cat = st.selectbox("カテゴリ", cat_options, index=default_cat_idx,
                                 label_visibility="collapsed", key="c_cat")

            st.markdown(f'<div class="icon-label">{icon_img(ICON_NAMETAG)}服の名前（例：白Tシャツ）</div>', unsafe_allow_html=True)
            c_name = st.text_input("服の名前", label_visibility="collapsed", key="c_name")

            st.markdown(f'<div class="icon-label">{icon_img(ICON_RULER)}サイズ</div>', unsafe_allow_html=True)
            c_size = st.selectbox("サイズ", ["80","90","95","100","110","120","130","140","150","160","170"],
                                  label_visibility="collapsed", key="c_size")

            st.markdown(f'<div class="icon-label">{icon_img(ICON_STAR)}色・柄（例：白、ボーダー）</div>', unsafe_allow_html=True)
            c_color = st.text_input("色・柄", label_visibility="collapsed", key="c_color")

            st.markdown(f'<div class="icon-label">{icon_img(ICON_CHART)}購入店（例：ユニクロ）</div>', unsafe_allow_html=True)
            c_shop = st.text_input("購入店", label_visibility="collapsed", key="c_shop")

            st.markdown(f'<div class="icon-label">{icon_img(ICON_CHART)}購入金額（円）</div>', unsafe_allow_html=True)
            c_price = st.number_input("金額", 0, 100000, 0, label_visibility="collapsed", key="c_price")

            if st.button("服を登録する"):
                if c_name:
                    photo_path = ""
                    if photo_source is not None:
                        kid_photo_dir = os.path.join(UP["PHOTO_DIR"], c_kid)
                        os.makedirs(kid_photo_dir, exist_ok=True)
                        fname = datetime.now().strftime("%Y%m%d%H%M%S") + ".jpg"
                        photo_path = os.path.join(kid_photo_dir, fname)
                        if photo_image is not None:
                            photo_image.save(photo_path)
                    clothes.append({
                        "kid": c_kid, "category": c_cat, "season": c_season,
                        "name": c_name, "size": c_size, "color": c_color,
                        "shop": c_shop, "price": c_price, "photo": photo_path,
                        "registered": date.today().strftime("%Y-%m-%d"),
                    })
                    save_clothes(clothes)
                    st.success(c_name + " を登録しました！")
                    st.rerun()
                else:
                    st.warning("服の名前を入力してください")

        st.divider()

        # 季節フィルター
        st.markdown(f'<div class="icon-label">{icon_img(ICON_STAR)}季節で絞り込み</div>', unsafe_allow_html=True)
        view_season = st.selectbox("季節フィルター", ["すべて"] + list(SEASON_CATEGORIES.keys()),
                                   label_visibility="collapsed", key="view_season")

        for kid in kids:
            st.markdown(icon_heading(ICON_BABY, kid["name"] + " の服", level=4, size=20), unsafe_allow_html=True)
            kid_clothes = [c for c in clothes if c["kid"] == kid["name"]]
            if view_season != "すべて":
                kid_clothes = [c for c in kid_clothes if c.get("season", "通年") == view_season]

            if not kid_clothes:
                st.caption("該当する服がありません")
            else:
                # カテゴリごとにグループ化
                cat_groups = {}
                for c in kid_clothes:
                    cat = c["category"]
                    cat_groups.setdefault(cat, []).append(c)

                for cat, items in cat_groups.items():
                    season = items[0].get("season", "通年")
                    st.markdown(
                        f'<p>{icon_img(ICON_CLOTHING, 14)}{cat}（{len(items)}枚）{season_badge(season)}</p>',
                        unsafe_allow_html=True)
                    cols = st.columns(2)
                    for j, c in enumerate(items):
                        with cols[j % 2]:
                            if c.get("photo") and os.path.exists(c["photo"]):
                                st.image(Image.open(c["photo"]), use_container_width=True)
                            else:
                                st.markdown(
                                    '<div style="background:#FFE8E0;border-radius:12px;'
                                    'padding:2rem;text-align:center;margin-bottom:0.5rem;">'
                                    f'{icon_img(ICON_CLOTHING, 32)}<br>'
                                    '<small>写真なし</small></div>',
                                    unsafe_allow_html=True)
                            st.caption(c["name"] + " / サイズ" + c["size"] + " / " + c.get("color",""))
                            if c.get("price"):
                                st.caption("¥" + str(c["price"]))
            st.divider()

        # 季節・カテゴリ修正セクション
        st.markdown(icon_heading(ICON_STAR, "服の季節・カテゴリを修正", level=4, size=20), unsafe_allow_html=True)
        st.caption("登録した服の季節やカテゴリが間違っていたらここで修正できます")

        all_clothes = load_clothes()
        if all_clothes:
            cloth_labels = [f"{c['kid']} / {c['name']} / {c['category']} [{c.get('season','通年')}]"
                           for c in all_clothes]
            selected_idx = st.selectbox("修正する服を選択", range(len(cloth_labels)),
                                        format_func=lambda x: cloth_labels[x], key="edit_cloth")
            if selected_idx is not None:
                target = all_clothes[selected_idx]
                col1, col2 = st.columns(2)
                with col1:
                    new_season = st.selectbox("新しい季節", list(SEASON_CATEGORIES.keys()),
                                              index=list(SEASON_CATEGORIES.keys()).index(target.get("season", "通年"))
                                              if target.get("season", "通年") in SEASON_CATEGORIES else 3,
                                              key="edit_season")
                with col2:
                    new_cat_opts = SEASON_CATEGORIES.get(new_season, ALL_CLOTHING_TYPES)
                    cur_cat = target["category"]
                    new_cat_idx = new_cat_opts.index(cur_cat) if cur_cat in new_cat_opts else 0
                    new_cat = st.selectbox("新しいカテゴリ", new_cat_opts, index=new_cat_idx, key="edit_cat")
                if st.button("修正を保存"):
                    all_clothes[selected_idx]["season"] = new_season
                    all_clothes[selected_idx]["category"] = new_cat
                    save_clothes(all_clothes)
                    st.success("修正しました！")
                    st.rerun()

# ==============================
# TAB 3: CSV分析・予測
# ==============================
with tabs[2]:
    st.markdown(icon_heading(ICON_CHART, "家計データ分析・来月予測"), unsafe_allow_html=True)

    # CSVアップロード
    st.markdown(f'<div class="icon-label">{icon_img(ICON_CSV)}MoneyForward MEのCSVをアップロード</div>', unsafe_allow_html=True)
    uploaded_csvs = st.file_uploader("CSVアップロード", type=["csv"], accept_multiple_files=True,
                                     label_visibility="collapsed")
    if uploaded_csvs:
        for uf in uploaded_csvs:
            save_path = os.path.join(UP["CSV_DIR"], uf.name)
            with open(save_path, "wb") as f:
                f.write(uf.getbuffer())
        st.success(str(len(uploaded_csvs)) + "個のCSVをアップロードしました")

    csv_files = glob.glob(os.path.join(UP["CSV_DIR"], "*.csv"))
    if not csv_files:
        st.info("CSVファイルをアップロードしてください。複数年分まとめてOKです。")
    else:
        st.success(str(len(csv_files)) + "個のCSVファイルを読み込みました")
        monthly, shop_amounts, transactions = parse_csv_files()
        price_per_item = calc_price_per_item(shop_amounts)

        if not monthly:
            st.warning("子ども服のデータが見つかりませんでした。CSVの内容を確認してください。")
        else:
            st.markdown(f'<div class="icon-label">{icon_img(ICON_CHART)}月の上限予算（円）</div>', unsafe_allow_html=True)
            budget = st.number_input("予算", 0, 200000, 15000, step=1000, label_visibility="collapsed", key="budget")
            st.markdown(f'<div class="icon-label">{icon_img(ICON_BELL)}警告ライン（円）</div>', unsafe_allow_html=True)
            warn_line = st.number_input("警告", 0, 200000, 12000, step=1000, label_visibility="collapsed", key="warn")

            st.divider()

            now = datetime.now()
            next_month = now.month % 12 + 1
            next_year = now.year if now.month < 12 else now.year + 1
            past_same = [v for k, v in monthly.items() if int(k[5:7]) == next_month]
            if past_same:
                predicted = round(sum(past_same) / len(past_same))
                basis = "過去" + str(len(past_same)) + "年の" + str(next_month) + "月の平均"
            else:
                all_vals = list(monthly.values())
                predicted = round(sum(all_vals) / len(all_vals))
                basis = "全期間の平均"

            st.markdown(icon_heading(ICON_CHART, "来月（" + str(next_year) + "年" + str(next_month) + "月）の予測", level=4, size=20), unsafe_allow_html=True)
            st.metric("予測支出", "¥" + str(predicted))
            st.metric("予算上限", "¥" + str(budget))
            diff = predicted - budget
            st.metric("余裕", "¥" + str(abs(diff)), delta="超過" if diff > 0 else "余裕あり", delta_color="inverse")
            st.caption("算出根拠: " + basis)

            if predicted >= budget:
                st.error("来月は予算超過の可能性があります。今月中に準備を！")
            elif predicted >= warn_line:
                st.warning("来月は警告ラインに近い見込みです。")
            else:
                st.success("来月は予算内に収まる見込みです。")

            st.divider()
            st.markdown(icon_heading(ICON_CHART, "月別の子ども服支出", level=4, size=20), unsafe_allow_html=True)
            sorted_monthly = dict(sorted(monthly.items()))
            df_chart = pd.DataFrame({"月": list(sorted_monthly.keys()), "支出": list(sorted_monthly.values())}).set_index("月")
            st.bar_chart(df_chart)

            st.divider()
            st.markdown(icon_heading(ICON_CHART, "店舗別の購入分析", level=4, size=20), unsafe_allow_html=True)
            if shop_amounts:
                shop_data = []
                for shop, amts in shop_amounts.items():
                    shop_data.append({"店舗": shop, "購入回数": len(amts),
                                      "1回平均": "¥" + str(round(sum(amts)/len(amts))),
                                      "推定1枚単価": "¥" + str(price_per_item.get(shop, 0)),
                                      "合計": "¥" + str(sum(amts))})
                st.dataframe(pd.DataFrame(shop_data).sort_values("購入回数", ascending=False),
                             use_container_width=True, hide_index=True)
                st.caption("推定1枚単価 = 1回の購入金額 ÷ 2.5枚")

            st.divider()
            st.markdown(icon_heading(ICON_CLOTHING, "今シーズンの必要金額", level=4, size=20), unsafe_allow_html=True)
            kids = load_kids()
            if not kids:
                st.info("子ども設定タブで子どもを登録すると計算できます")
            else:
                recommend = {"上服": 7, "下服": 6, "下着": 10, "パジャマ": 2}
                base_price = (round(sum(price_per_item.values()) / len(price_per_item)) if price_per_item else 1500)
                total_all = 0
                all_clothes_csv = load_clothes()
                cur_m = datetime.now().month
                cur_s_key = get_current_season(cur_m)
                s_name_map = {"spring": "春秋", "summer": "夏", "autumn": "春秋", "winter": "冬"}
                cur_s_name = s_name_map.get(cur_s_key, "通年")
                for kid in kids:
                    st.markdown(f'<p style="font-weight:600;">{icon_img(ICON_BABY, 16)}{kid["name"]}</p>', unsafe_allow_html=True)
                    counts = count_clothes_by_kid(all_clothes_csv, kid["name"], cur_s_name)
                    needs = {"上服": max(0, recommend["上服"] - counts["上服"]),
                             "下服": max(0, recommend["下服"] - counts["下服"]),
                             "下着": max(0, recommend["下着"] - counts["下着"]),
                             "パジャマ": max(0, recommend["パジャマ"] - counts["パジャマ"])}
                    total_kid = sum(n * base_price for n in needs.values())
                    total_all += total_kid
                    cols = st.columns(2)
                    for ci, (label, n) in enumerate(needs.items()):
                        with cols[ci % 2]:
                            st.metric(label + "（現在" + str(counts[label]) + "枚）",
                                      "あと" + str(n) + "枚",
                                      delta="OK" if n == 0 else "¥" + str(n * base_price),
                                      delta_color="normal" if n == 0 else "inverse")
                    st.caption("この子の今季必要額: ¥" + str(total_kid))
                    st.divider()
                st.metric("合計の必要額", "¥" + str(total_all))
                st.caption("1枚あたり ¥" + str(base_price) + " で計算")

            # 季節別おすすめ
            st.divider()
            st.markdown(icon_heading(ICON_STAR, "シーズン別おすすめ準備", level=4, size=20), unsafe_allow_html=True)
            current_month = datetime.now().month
            current_season = get_current_season(current_month)
            next_season = get_next_season(current_season)
            current_info = SEASONAL_NEEDS[current_season]
            next_info = SEASONAL_NEEDS[next_season]

            st.markdown(f"**今シーズン: {current_info['label']}**")
            for item in current_info["items"]:
                st.markdown("- " + item)

            st.markdown(f"**来シーズンの準備: {next_info['label']}**")
            st.info("おすすめ準備アイテム:\n" + "\n".join(["- " + item for item in next_info["items"]]))

            last_year_ym = str(now.year - 1) + "-" + str(now.month).zfill(2)
            if last_year_ym in monthly:
                st.info("去年の" + str(now.month) + "月は ¥" + str(monthly[last_year_ym]) + " 使いました")

            # 買い物チェックリスト
            st.divider()
            st.markdown(icon_heading(ICON_CHART, "買い物チェックリスト", level=4, size=20), unsafe_allow_html=True)
            shopping_items = current_info["items"] + [item + "（来シーズン用）" for item in next_info["items"]]
            for idx, item in enumerate(shopping_items):
                st.checkbox(item, key="shop_check_" + str(idx))

# ==============================
# TAB 4: 写真一覧
# ==============================
with tabs[3]:
    st.markdown(icon_heading(ICON_CAMERA, "服の写真一覧"), unsafe_allow_html=True)
    kids = load_kids()
    clothes = load_clothes()

    if not kids:
        st.info("先に子どもを登録してください")
    else:
        st.markdown(f'<div class="icon-label">{icon_img(ICON_BABY)}表示する子を選択</div>', unsafe_allow_html=True)
        selected_kid = st.selectbox("子ども", ["全員"] + [k["name"] for k in kids],
                                     label_visibility="collapsed", key="photo_kid")

        st.markdown(f'<div class="icon-label">{icon_img(ICON_STAR)}季節</div>', unsafe_allow_html=True)
        selected_season = st.selectbox("季節", ["すべて"] + list(SEASON_CATEGORIES.keys()),
                                        label_visibility="collapsed", key="photo_season")

        st.markdown(f'<div class="icon-label">{icon_img(ICON_CLOTHING)}カテゴリ</div>', unsafe_allow_html=True)
        all_cats = ["すべて"] + ALL_CLOTHING_TYPES
        selected_cat = st.selectbox("カテゴリ", all_cats, label_visibility="collapsed", key="photo_cat")

        filtered = clothes
        if selected_kid != "全員":
            filtered = [c for c in filtered if c["kid"] == selected_kid]
        if selected_season != "すべて":
            filtered = [c for c in filtered if c.get("season", "通年") == selected_season]
        if selected_cat != "すべて":
            filtered = [c for c in filtered if c["category"] == selected_cat]

        if not filtered:
            st.info("該当する服がありません")
        else:
            st.caption(str(len(filtered)) + "枚の服が登録されています")
            cols = st.columns(2)
            for j, c in enumerate(filtered):
                with cols[j % 2]:
                    if c.get("photo") and os.path.exists(c["photo"]):
                        st.image(Image.open(c["photo"]), use_container_width=True)
                    else:
                        st.markdown(
                            '<div style="background:#FFE8E0;border-radius:12px;'
                            'padding:2rem;text-align:center;margin-bottom:0.5rem;">'
                            f'{icon_img(ICON_CLOTHING, 32)}<br>'
                            '<small>写真なし</small></div>',
                            unsafe_allow_html=True)
                    season_html = season_badge(c.get("season", "通年"))
                    st.markdown(
                        f'<p style="font-size:0.85rem;">{c["kid"]} / {c["category"]} {season_html}<br>'
                        f'{c["name"]} / サイズ{c["size"]} / {c.get("color","")}</p>',
                        unsafe_allow_html=True)
                    if c.get("price"):
                        st.caption("¥" + str(c["price"]))

# ==============================
# TAB 5: LINE通知設定
# ==============================
with tabs[4]:
    # === Claude API キー設定 ===
    st.markdown(icon_heading(ICON_CAMERA, "AI写真解析の設定"), unsafe_allow_html=True)
    st.markdown("Claude Vision APIを設定すると、写真から服の種類を**高精度で自動判定**できます。\n\n"
                "（設定しなくても簡易判定は利用できます）")

    with st.expander("Claude APIキーの取得方法"):
        st.markdown(
            "**ステップ1**: [console.anthropic.com](https://console.anthropic.com) にアクセス\n\n"
            "**ステップ2**: アカウントを作成（Googleログインなど）\n\n"
            "**ステップ3**: 左メニューの「API Keys」を開く\n\n"
            "**ステップ4**: 「Create Key」をクリック\n\n"
            "**ステップ5**: キーをコピーして下にペースト！\n\n"
            "費用: 写真1枚あたり約0.5〜1円程度です")

    saved_claude_key = load_claude_api_key()
    claude_api_key = st.text_input("Claude APIキー", value=saved_claude_key, type="password",
                                    placeholder="sk-ant-api03-... をペースト", key="claude_key_input")

    col_ck_save, col_ck_test = st.columns(2)
    with col_ck_save:
        if st.button("APIキーを保存", key="save_claude_key"):
            if claude_api_key:
                save_claude_api_key(claude_api_key)
                st.success("APIキーを保存しました！写真登録時にAI判定が有効になります")
            else:
                st.warning("APIキーを入力してください")
    with col_ck_test:
        if st.button("接続テスト", key="test_claude_key"):
            if claude_api_key:
                try:
                    client = anthropic.Anthropic(api_key=claude_api_key)
                    msg = client.messages.create(
                        model="claude-haiku-4-5-20251001",
                        max_tokens=50,
                        messages=[{"role": "user", "content": "OK?"}],
                    )
                    st.success("接続成功！AI写真解析が利用できます")
                except Exception as e:
                    st.error("接続失敗: " + str(e))
            else:
                st.warning("先にAPIキーを入力してください")

    if saved_claude_key:
        st.success("AI写真解析: 有効")
    else:
        st.caption("AI写真解析: 未設定（簡易判定モードで動作中）")

    st.divider()

    # === LINE通知設定 ===
    st.markdown(icon_heading(ICON_BELL, "LINE通知設定"), unsafe_allow_html=True)
    st.markdown("サイズアウトが近づいたら、LINEでお知らせを受け取れます！\n\n"
                "**LINE Notify** を使って、Kids Closetから直接LINEに通知を送ります。")
    st.divider()

    st.markdown(icon_heading(ICON_BELL, "LINE Notifyトークンの取得方法", level=4, size=20), unsafe_allow_html=True)
    with st.expander("設定手順を見る"):
        st.markdown(
            "**ステップ1**: [LINE Notify](https://notify-bot.line.me/) にアクセス\n\n"
            "**ステップ2**: LINEアカウントでログイン\n\n"
            "**ステップ3**: 右上のメニューから「マイページ」を開く\n\n"
            "**ステップ4**: 「トークンを発行する」をクリック\n\n"
            "**ステップ5**: トークン名に「Kids Closet」と入力\n\n"
            "**ステップ6**: 通知を受け取るトークルームを選択\n\n"
            "**ステップ7**: 「発行する」をクリックしてトークンをコピー\n\n"
            "**ステップ8**: 下の入力欄にペースト！")

    st.divider()
    st.markdown(icon_heading(ICON_BELL, "トークン設定", level=4, size=20), unsafe_allow_html=True)
    saved_token = load_line_token()
    line_token = st.text_input("LINE Notifyトークン", value=saved_token, type="password",
                                placeholder="ここにトークンをペースト")

    col_save, col_test = st.columns(2)
    with col_save:
        if st.button("トークンを保存"):
            if line_token:
                save_line_token(line_token)
                st.success("トークンを保存しました！")
            else:
                st.warning("トークンを入力してください")
    with col_test:
        if st.button("テスト通知を送る"):
            if line_token:
                success, status = send_line_notify(line_token, "\nKids Closetからのテスト通知です！\n接続成功！")
                if success:
                    st.success("テスト通知を送信しました！LINEを確認してね！")
                else:
                    st.error("送信に失敗しました（ステータス: " + str(status) + "）")
            else:
                st.warning("先にトークンを入力してください")

    st.divider()
    st.markdown(icon_heading(ICON_BELL, "サイズアウト通知チェック", level=4, size=20), unsafe_allow_html=True)
    kids_for_notify = load_kids()
    if not kids_for_notify:
        st.info("先に「子ども設定」タブで子どもを登録してください")
    else:
        for kid in kids_for_notify:
            pred = predict_sizeout(kid.get("height", 120), kid.get("birthday", "2016-01-01"), kid.get("size", "120"))
            shoe_pred = predict_shoe_sizeout(kid.get("birthday", "2016-01-01"), kid.get("shoe_size", "18"))
            cost = estimate_sizeout_cost(kid)

            st.markdown(f'<p style="font-weight:600;">{icon_img(ICON_BABY, 16)}{kid["name"]}</p>', unsafe_allow_html=True)
            # 服の予測
            if pred["color"] == "red":
                st.error("【服】" + pred["status"] + "（あと約" + str(pred["months"]) + "ヶ月）")
            elif pred["color"] == "orange":
                st.warning("【服】" + pred["status"] + "（あと約" + str(pred["months"]) + "ヶ月）")
            else:
                st.success("【服】" + pred["status"] + "（あと約" + str(pred["months"]) + "ヶ月）")
            # 靴の予測
            if shoe_pred["color"] == "red":
                st.error("【靴】" + shoe_pred["status"] + "（あと約" + str(shoe_pred["months"]) + "ヶ月）")
            elif shoe_pred["color"] == "orange":
                st.warning("【靴】" + shoe_pred["status"] + "（あと約" + str(shoe_pred["months"]) + "ヶ月）")
            else:
                st.success("【靴】" + shoe_pred["status"] + "（あと約" + str(shoe_pred["months"]) + "ヶ月）")
            # 費用の目安
            if pred["color"] in ["red", "orange"] or shoe_pred["color"] in ["red", "orange"]:
                st.info("買い替え費用の目安: 服 ¥" + str(cost["clothes_cost"]) +
                        " + 靴 ¥" + str(cost["shoe_cost"]) +
                        " = **合計 ¥" + str(cost["total"]) + "**")
            st.divider()

        if st.button("今すぐ通知チェック＆送信"):
            token = line_token if line_token else load_line_token()
            if not token:
                st.warning("LINE Notifyトークンが設定されていません")
            else:
                results = check_and_notify_sizeout(kids_for_notify, token)
                if not results:
                    st.success("現在サイズアウトが近い子どもはいません。安心！")
                else:
                    log = load_notify_log()
                    for r in results:
                        if r["sent"]:
                            st.success(r["kid"] + "の通知を送信しました！（" + r["status"] + "）")
                        else:
                            st.error(r["kid"] + "の通知送信に失敗（" + str(r["response"]) + "）")
                        log.append(r)
                    save_notify_log(log)
