import streamlit as st
import json
import os
import pandas as pd
from datetime import date, datetime
from PIL import Image
import glob
import requests

# ==============================
# 設定
# ==============================
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(BASE_DIR, "data")
CSV_DIR   = os.path.join(DATA_DIR, "csv")
PHOTO_DIR = os.path.join(BASE_DIR, "photos")
KIDS_FILE       = os.path.join(DATA_DIR, "kids.json")
CLOTHES_FILE    = os.path.join(DATA_DIR, "clothes.json")
LINE_TOKEN_FILE = os.path.join(DATA_DIR, "line_token.json")
NOTIFY_LOG_FILE = os.path.join(DATA_DIR, "notify_log.json")

for d in [DATA_DIR, CSV_DIR, PHOTO_DIR]:
    os.makedirs(d, exist_ok=True)

# ==============================
# データ読み書き
# ==============================
def load_kids():
    if os.path.exists(KIDS_FILE):
        with open(KIDS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []

def save_kids(kids):
    with open(KIDS_FILE, "w", encoding="utf-8") as f:
        json.dump(kids, f, ensure_ascii=False, indent=2)

def load_clothes():
    if os.path.exists(CLOTHES_FILE):
        with open(CLOTHES_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []

def save_clothes(clothes):
    with open(CLOTHES_FILE, "w", encoding="utf-8") as f:
        json.dump(clothes, f, ensure_ascii=False, indent=2)

def load_line_token():
    if os.path.exists(LINE_TOKEN_FILE):
        with open(LINE_TOKEN_FILE, encoding="utf-8") as f:
            data = json.load(f)
            return data.get("token", "")
    return ""

def save_line_token(token):
    with open(LINE_TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump({"token": token}, f, ensure_ascii=False, indent=2)

def load_notify_log():
    if os.path.exists(NOTIFY_LOG_FILE):
        with open(NOTIFY_LOG_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []

def save_notify_log(log):
    with open(NOTIFY_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

# ==============================
# サイズアウト予測
# ==============================
SIZE_CHART = [80, 90, 95, 100, 110, 120, 130, 140, 150, 160, 170]

def predict_sizeout(height_cm, birthday_str, current_size):
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

    return {
        "status":     status,
        "color":      color,
        "months":     months_to_next,
        "next_size":  next_boundary,
        "cm_to_next": cm_to_next,
    }

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
        if shop == "その他":
            continue
        if any(k in content for k in kws):
            return shop
    return "その他"

def parse_csv_files():
    files        = glob.glob(os.path.join(CSV_DIR, "*.csv"))
    monthly      = {}
    shop_amounts = {}
    transactions = []

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
                calc    = str(row.iloc[0])
                date_s  = str(row.iloc[1])
                content = str(row.iloc[2])
                amount  = int(str(row.iloc[3]).replace(",", ""))
                sub_cat = str(row.iloc[6]) if len(row) > 6 else ""
            except Exception:
                continue

            if calc == "0":
                continue
            if amount >= 0:
                continue

            is_kid = (sub_cat in KID_CLOTH_CATS or
                      any(k in content for k in KID_CLOTH_KW) or
                      any(k in sub_cat  for k in KID_CLOTH_KW))
            if not is_kid:
                continue

            amt = abs(amount)
            ym  = date_s[:7].replace("/", "-")
            monthly[ym] = monthly.get(ym, 0) + amt

            shop = detect_shop(content)
            shop_amounts.setdefault(shop, []).append(amt)
            transactions.append({
                "date": date_s, "content": content,
                "amount": amt, "shop": shop, "ym": ym
            })

    return monthly, shop_amounts, transactions

def calc_price_per_item(shop_amounts):
    result   = {}
    assumed  = 2.5
    for shop, amts in shop_amounts.items():
        if amts:
            result[shop] = round(sum(amts) / len(amts) / assumed)
    return result

# ==============================
# 写真から服カテゴリ推定
# ==============================
def analyze_clothing_image(image):
    # TODO: Connect to Claude Vision API for auto-detection
    # 現在はアスペクト比による簡易推定を行う
    width, height = image.size
    aspect_ratio = width / height

    if aspect_ratio > 1.3:
        suggested = "上服"
        confidence = "中"
    elif aspect_ratio < 0.7:
        suggested = "下服"
        confidence = "中"
    else:
        suggested = "上服"
        confidence = "低"

    return {
        "suggested_category": suggested,
        "confidence": confidence,
        "width": width,
        "height": height,
    }

# ==============================
# LINE Notify 機能
# ==============================
def send_line_notify(token, message):
    url = "https://notify-api.line.me/api/notify"
    headers = {"Authorization": "Bearer " + token}
    data = {"message": message}
    try:
        response = requests.post(url, headers=headers, data=data, timeout=10)
        return response.status_code == 200, response.status_code
    except Exception as e:
        return False, str(e)

def check_and_notify_sizeout(kids, token):
    results = []
    for kid in kids:
        pred = predict_sizeout(
            kid.get("height", 120),
            kid.get("birthday", "2016-01-01"),
            kid.get("size", "120")
        )
        if pred["color"] in ["red", "orange"]:
            message = (
                "\n\U0001F514 " + kid["name"] + "の服がまもなくサイズアウトします！\n"
                "現在サイズ: " + str(kid.get("size", "?")) + "cm\n"
                "次のサイズ: " + str(pred["next_size"]) + "cm\n"
                "あと約" + str(pred["months"]) + "ヶ月\n\n"
                "\U0001F449 Kids Closetで確認してね！"
            )
            success, status = send_line_notify(token, message)
            results.append({
                "kid": kid["name"],
                "status": pred["status"],
                "sent": success,
                "response": status,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            })
    return results

# ==============================
# 季節別おすすめ
# ==============================
SEASONAL_NEEDS = {
    "spring": {
        "label": "\U0001F338 春（3〜5月）",
        "months": [3, 4, 5],
        "items": ["薄手の上服", "長ズボン", "薄手カーディガン"],
        "icon": "\U0001F338",
    },
    "summer": {
        "label": "\U0001F33B 夏（6〜8月）",
        "months": [6, 7, 8],
        "items": ["半袖Tシャツ", "短パン", "サンダル", "帽子"],
        "icon": "\U0001F33B",
    },
    "autumn": {
        "label": "\U0001F342 秋（9〜11月）",
        "months": [9, 10, 11],
        "items": ["薄手の上服", "長ズボン", "薄手アウター"],
        "icon": "\U0001F342",
    },
    "winter": {
        "label": "\u2744\ufe0f 冬（12〜2月）",
        "months": [12, 1, 2],
        "items": ["厚手の上服", "長ズボン", "アウター", "防寒具", "手袋・マフラー"],
        "icon": "\u2744\ufe0f",
    },
}

def get_current_season(month):
    if month in [3, 4, 5]:
        return "spring"
    elif month in [6, 7, 8]:
        return "summer"
    elif month in [9, 10, 11]:
        return "autumn"
    else:
        return "winter"

def get_next_season(current):
    order = ["spring", "summer", "autumn", "winter"]
    idx = order.index(current)
    return order[(idx + 1) % 4]

# ==============================
# ページ設定 (centered for mobile)
# ==============================
st.set_page_config(page_title="\U0001F457 Kids Closet \U0001F476", layout="centered")

# ==============================
# カラフルポップCSS
# ==============================
st.markdown("""
<style>
/* グローバルスタイル */
.block-container {
    padding-top: 1rem !important;
}

/* タイトルスタイル */
h1 {
    background: linear-gradient(90deg, #FF6B6B, #FF8E53, #FFC857);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 800 !important;
    font-size: 2.2rem !important;
}

/* サブヘッダーにカラフルアンダーライン */
h2, h3 {
    color: #2D1B14 !important;
}

/* タブスタイル */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background-color: #FFE8E0;
    border-radius: 12px;
    padding: 4px;
}
.stTabs [data-baseweb="tab-list"] button {
    border-radius: 10px !important;
    font-weight: 600;
    padding: 0.5rem 0.6rem;
    font-size: 0.9rem;
}
.stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {
    background-color: #FF6B6B !important;
    color: white !important;
    border-radius: 10px !important;
}

/* ボタンスタイル */
.stButton > button {
    border-radius: 20px !important;
    font-weight: 600;
    min-height: 2.5rem;
    border: none !important;
    background: linear-gradient(135deg, #FF6B6B, #FF8E53) !important;
    color: white !important;
    transition: all 0.3s ease;
    box-shadow: 0 2px 8px rgba(255, 107, 107, 0.3);
}
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(255, 107, 107, 0.4) !important;
}

/* カード風コンテナ */
.clothing-card {
    border: 2px solid #FFD4C4;
    border-radius: 16px;
    padding: 0.8rem;
    margin-bottom: 0.8rem;
    background: white;
    box-shadow: 0 2px 8px rgba(255, 142, 83, 0.1);
}

/* expander スタイル */
.streamlit-expanderHeader {
    font-size: 1rem;
    font-weight: 600;
    border-radius: 12px !important;
    background-color: #FFF0EB !important;
}

/* メトリクス */
[data-testid="stMetricValue"] {
    color: #FF6B6B !important;
    font-weight: 700 !important;
}

/* 成功・警告・エラーのスタイル */
.stAlert {
    border-radius: 12px !important;
}

/* divider */
hr {
    border-color: #FFD4C4 !important;
}

/* セレクトボックス・インプットのスタイル */
.stSelectbox > div > div,
.stTextInput > div > div > input,
.stNumberInput > div > div > input {
    border-radius: 12px !important;
    border-color: #FFD4C4 !important;
}

/* モバイル全体のフォントサイズ・パディング調整 */
@media (max-width: 768px) {
    .block-container {
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
        padding-top: 1rem !important;
    }
    /* タブのタッチターゲットを大きく */
    .stTabs [data-baseweb="tab-list"] button {
        font-size: 0.85rem;
        padding: 0.6rem 0.3rem;
    }
    /* ボタンを大きく・押しやすく */
    .stButton > button {
        min-height: 2.8rem;
        font-size: 1rem;
        width: 100%;
    }
    /* テキスト入力のフォントサイズ（iOS拡大防止） */
    .stTextInput input,
    .stNumberInput input,
    .stSelectbox select,
    .stDateInput input {
        font-size: 16px !important;
    }
    /* メトリクスを見やすく */
    [data-testid="stMetricValue"] {
        font-size: 1.3rem !important;
    }
    /* expanderの押しやすさ */
    .streamlit-expanderHeader {
        font-size: 1rem;
        padding: 0.75rem 0.5rem;
    }
}
</style>
""", unsafe_allow_html=True)

st.title("\U0001F457 Kids Closet \U0001F476")
st.caption("\u2728 子どもの成長記録・服の管理・衣類費の予測 \u2728")

tabs = st.tabs([
    "\U0001F476 子ども設定",
    "\U0001F455 服の管理",
    "\U0001F4CA CSV分析・予測",
    "\U0001F4F8 写真一覧",
    "\U0001F514 通知設定",
])

# ==============================
# TAB 1: 子ども設定
# ==============================
with tabs[0]:
    st.subheader("\U0001F476 お子さまの情報")
    kids = load_kids()

    with st.expander("\u2795 子どもを追加する", expanded=len(kids) == 0):
        new_name   = st.text_input("\U0001F3F7\ufe0f 名前（例：長男）")
        new_gender = st.selectbox("\U0001F31F 性別", ["男の子", "女の子"])
        new_bday   = st.date_input(
            "\U0001F382 誕生日",
            value=date(2016, 1, 1),
            min_value=date(2000, 1, 1),
            max_value=date.today()
        )
        new_height    = st.number_input("\U0001F4CF 現在の身長 (cm)", 50, 200, 120)
        new_size      = st.selectbox("\U0001F455 現在着ているサイズ",
                                     ["80","90","95","100","110","120","130","140","150","160","170"])
        new_tops      = st.number_input("\U0001F455 上服の枚数", 0, 50, 5)
        new_bottoms   = st.number_input("\U0001F456 下服の枚数", 0, 50, 5)
        new_underwear = st.number_input("\U0001FA72 下着の枚数", 0, 50, 7)
        new_pajamas   = st.number_input("\U0001F319 パジャマの枚数", 0, 20, 2)

        if st.button("\u2728 追加する"):
            if new_name:
                kids.append({
                    "name":      new_name,
                    "gender":    new_gender,
                    "birthday":  new_bday.strftime("%Y-%m-%d"),
                    "height":    new_height,
                    "size":      new_size,
                    "tops":      new_tops,
                    "bottoms":   new_bottoms,
                    "underwear": new_underwear,
                    "pajamas":   new_pajamas,
                })
                save_kids(kids)
                st.success("\U0001F389 " + new_name + " を追加しました！")
                st.rerun()
            else:
                st.warning("\u26a0\ufe0f 名前を入力してください")

    if kids:
        st.divider()
        for i, kid in enumerate(kids):
            gender_emoji = "\U0001F466" if kid.get("gender", "") == "男の子" else "\U0001F467"
            st.markdown("### " + gender_emoji + " " + kid["name"] + "（" + kid.get("gender","") + "）")
            bday = kid.get("birthday", "")
            try:
                age_days = (date.today() - datetime.strptime(bday, "%Y-%m-%d").date()).days
                age_y = int(age_days // 365)
                age_m = int((age_days % 365) // 30)
                st.caption("\U0001F382 誕生日: " + bday + "（" + str(age_y) + "歳" + str(age_m) + "ヶ月）")
            except Exception:
                st.caption("\U0001F382 誕生日: " + bday)
            st.caption("\U0001F4CF 身長: " + str(kid.get("height","?")) + "cm　\U0001F455 サイズ: " + str(kid.get("size","?")))

            pred = predict_sizeout(
                kid.get("height", 120),
                kid.get("birthday", "2016-01-01"),
                kid.get("size", "120")
            )
            st.markdown("**\U0001F4C8 サイズアウト予測**")
            if pred["color"] == "red":
                st.error("\U0001F534 " + pred["status"])
            elif pred["color"] == "orange":
                st.warning("\U0001F7E0 " + pred["status"])
            else:
                st.success("\U0001F7E2 " + pred["status"])
            st.caption(
                "\U0001F449 次のサイズ(" + str(pred["next_size"]) + "cm)まで "
                "あと " + str(pred["cm_to_next"]) + "cm・約 " + str(pred["months"]) + "ヶ月"
            )

            st.markdown("**\U0001F9E5 今の服の枚数**")
            col_a, col_b = st.columns(2)
            with col_a:
                st.caption("\U0001F455 上服: " + str(kid.get("tops", 0)) + "枚")
                st.caption("\U0001F456 下服: " + str(kid.get("bottoms", 0)) + "枚")
            with col_b:
                st.caption("\U0001FA72 下着: " + str(kid.get("underwear", 0)) + "枚")
                st.caption("\U0001F319 パジャマ: " + str(kid.get("pajamas", 0)) + "枚")

            if st.button("\U0001F5D1\ufe0f 削除", key="del_" + str(i)):
                kids.pop(i)
                save_kids(kids)
                st.rerun()

            st.divider()

# ==============================
# TAB 2: 服の管理
# ==============================
with tabs[1]:
    st.subheader("\U0001F455 服の登録・管理")
    kids    = load_kids()
    clothes = load_clothes()

    if not kids:
        st.info("\U0001F449 先に「\U0001F476 子ども設定」タブで子どもを追加してください")
    else:
        with st.expander("\U0001F4F7 パシャッと服を登録する", expanded=False):
            st.markdown("##### \U0001F4F8 ステップ1: 写真を撮ろう！")
            st.caption("\U0001F4F1 スマホのカメラで直接撮影するか、写真をアップロードしてね")

            camera_photo = st.camera_input("\U0001F4F7 服の写真を撮る")
            upload_photo = st.file_uploader("\U0001F4C1 または写真をアップロード", type=["jpg", "jpeg", "png"])

            # 写真の処理
            photo_source = None
            photo_image = None
            if camera_photo is not None:
                photo_source = camera_photo
                photo_image = Image.open(camera_photo)
            elif upload_photo is not None:
                photo_source = upload_photo
                photo_image = Image.open(upload_photo)

            suggested_cat = "上服"
            if photo_image is not None:
                st.image(photo_image, caption="\U0001F4F8 撮影した写真", use_container_width=True)
                analysis = analyze_clothing_image(photo_image)
                suggested_cat = analysis["suggested_category"]
                st.info(
                    "\U0001F916 AI推定カテゴリ: **" + suggested_cat + "**"
                    "（信頼度: " + analysis["confidence"] + "）\n\n"
                    "\U0001F447 下のカテゴリ選択で確認・変更してね！"
                )

            st.markdown("##### \u270d\ufe0f ステップ2: 情報を入力")

            kid_names = [k["name"] for k in kids]
            c_kid   = st.selectbox("\U0001F476 誰の服？", kid_names, key="c_kid")

            cat_options = ["上服", "下服", "下着（肌着）", "下着（パンツ）", "パジャマ", "その他"]
            default_cat_idx = cat_options.index(suggested_cat) if suggested_cat in cat_options else 0
            c_cat   = st.selectbox("\U0001F3F7\ufe0f カテゴリ", cat_options, index=default_cat_idx)

            c_name  = st.text_input("\U0001F455 服の名前（例：白Tシャツ）")
            c_size  = st.selectbox("\U0001F4CF サイズ",
                                    ["80","90","95","100","110","120","130","140","150","160","170"])
            c_color = st.text_input("\U0001F3A8 色・柄（例：白、ボーダー）")
            c_shop  = st.text_input("\U0001F6CD\ufe0f 購入店（例：ユニクロ）")
            c_price = st.number_input("\U0001F4B0 購入金額（円）", 0, 100000, 0)

            if st.button("\u2728 服を登録する"):
                if c_name:
                    photo_path = ""
                    if photo_source is not None:
                        kid_photo_dir = os.path.join(PHOTO_DIR, c_kid)
                        os.makedirs(kid_photo_dir, exist_ok=True)
                        fname = datetime.now().strftime("%Y%m%d%H%M%S") + ".jpg"
                        photo_path = os.path.join(kid_photo_dir, fname)
                        if photo_image is not None:
                            photo_image.save(photo_path)

                    clothes.append({
                        "kid":        c_kid,
                        "category":   c_cat,
                        "name":       c_name,
                        "size":       c_size,
                        "color":      c_color,
                        "shop":       c_shop,
                        "price":      c_price,
                        "photo":      photo_path,
                        "registered": date.today().strftime("%Y-%m-%d"),
                    })
                    save_clothes(clothes)
                    st.success("\U0001F389 " + c_name + " を登録しました！")
                    st.rerun()
                else:
                    st.warning("\u26a0\ufe0f 服の名前を入力してください")

        st.divider()

        for kid in kids:
            gender_emoji = "\U0001F466" if kid.get("gender", "") == "男の子" else "\U0001F467"
            st.markdown("### " + gender_emoji + " " + kid["name"] + " の服")
            kid_clothes = [c for c in clothes if c["kid"] == kid["name"]]

            if not kid_clothes:
                st.caption("\U0001F4ED まだ服が登録されていません")
            else:
                cats = ["上服", "下服", "下着（肌着）", "下着（パンツ）", "パジャマ", "その他"]
                cat_emojis = {
                    "上服": "\U0001F455", "下服": "\U0001F456",
                    "下着（肌着）": "\U0001FA72", "下着（パンツ）": "\U0001FA72",
                    "パジャマ": "\U0001F319", "その他": "\U0001F3F7\ufe0f",
                }
                for cat in cats:
                    cat_clothes = [c for c in kid_clothes if c["category"] == cat]
                    if not cat_clothes:
                        continue
                    emoji = cat_emojis.get(cat, "")
                    st.caption(emoji + " " + cat + "（" + str(len(cat_clothes)) + "枚）")
                    cols = st.columns(2)
                    for j, c in enumerate(cat_clothes):
                        with cols[j % 2]:
                            if c.get("photo") and os.path.exists(c["photo"]):
                                st.image(Image.open(c["photo"]), use_container_width=True)
                            else:
                                st.markdown(
                                    '<div style="background:#FFE8E0;border-radius:12px;'
                                    'padding:2rem;text-align:center;margin-bottom:0.5rem;">'
                                    '<span style="font-size:2rem;">\U0001F455</span><br>'
                                    '<small>写真なし</small></div>',
                                    unsafe_allow_html=True
                                )
                            st.caption(c["name"] + "\nサイズ: " + c["size"] + "　" + c.get("color",""))
                            if c.get("price"):
                                st.caption("\U0001F4B0 ¥" + str(c["price"]))
            st.divider()

# ==============================
# TAB 3: CSV分析・予測
# ==============================
with tabs[2]:
    st.subheader("\U0001F4CA 家計データ分析・来月予測")
    st.info(
        "\U0001F4C2 CSVファイルの置き場所: " + CSV_DIR + "\n\n"
        "MoneyForward MEからダウンロードしたCSVをこのフォルダに入れてください。"
        "複数年分まとめて入れてOKです。"
    )

    csv_files = glob.glob(os.path.join(CSV_DIR, "*.csv"))
    if not csv_files:
        st.warning("\U0001F4ED CSVファイルがまだありません。上記フォルダにCSVを入れてからページを更新してください。")
    else:
        st.success("\U0001F389 " + str(len(csv_files)) + "個のCSVファイルを読み込みました")
        monthly, shop_amounts, transactions = parse_csv_files()
        price_per_item = calc_price_per_item(shop_amounts)

        if not monthly:
            st.warning("\U0001F50D 子ども服のデータが見つかりませんでした。CSVの内容を確認してください。")
        else:
            budget    = st.number_input("\U0001F4B0 月の上限予算（円）", 0, 200000, 15000, step=1000)
            warn_line = st.number_input("\u26a0\ufe0f 警告ライン（円）",   0, 200000, 12000, step=1000)

            st.divider()

            now        = datetime.now()
            next_month = now.month % 12 + 1
            next_year  = now.year if now.month < 12 else now.year + 1

            past_same = [v for k, v in monthly.items() if int(k[5:7]) == next_month]
            if past_same:
                predicted = round(sum(past_same) / len(past_same))
                basis     = "過去" + str(len(past_same)) + "年の" + str(next_month) + "月の平均"
            else:
                all_vals  = list(monthly.values())
                predicted = round(sum(all_vals) / len(all_vals))
                basis     = "全期間の平均"

            st.subheader("\U0001F52E 来月（" + str(next_year) + "年" + str(next_month) + "月）の予測")
            st.metric("\U0001F4B8 予測支出", "¥" + str(predicted))
            st.metric("\U0001F3AF 予算上限", "¥" + str(budget))
            diff = predicted - budget
            st.metric(
                "\U0001F4CA 余裕",
                "¥" + str(abs(diff)),
                delta="超過" if diff > 0 else "余裕あり",
                delta_color="inverse"
            )
            st.caption("\U0001F4DD 算出根拠: " + basis)

            if predicted >= budget:
                st.error("\U0001F534 来月は予算超過の可能性があります。今月中に準備を！")
            elif predicted >= warn_line:
                st.warning("\U0001F7E0 来月は警告ラインに近い見込みです。")
            else:
                st.success("\U0001F7E2 来月は予算内に収まる見込みです。")

            st.divider()

            st.subheader("\U0001F4C8 月別の子ども服支出")
            sorted_monthly = dict(sorted(monthly.items()))
            df_chart = pd.DataFrame({
                "月":   list(sorted_monthly.keys()),
                "支出": list(sorted_monthly.values()),
            }).set_index("月")
            st.bar_chart(df_chart)

            st.divider()

            st.subheader("\U0001F6CD\ufe0f 店舗別の購入分析（単価推定）")
            if shop_amounts:
                shop_data = []
                for shop, amts in shop_amounts.items():
                    avg_per_visit = round(sum(amts) / len(amts))
                    est_unit      = price_per_item.get(shop, 0)
                    shop_data.append({
                        "店舗":        shop,
                        "購入回数":    len(amts),
                        "1回平均":     "¥" + str(avg_per_visit),
                        "推定1枚単価": "¥" + str(est_unit),
                        "合計":        "¥" + str(sum(amts)),
                    })
                df_shop = pd.DataFrame(shop_data).sort_values("購入回数", ascending=False)
                st.dataframe(df_shop, use_container_width=True, hide_index=True)
                st.caption("\U0001F4DD 推定1枚単価 = 1回の購入金額 ÷ 2.5枚（平均購入枚数の仮定）")

            st.divider()

            st.subheader("\U0001F9E5 今シーズンの必要金額算出")
            kids = load_kids()
            if not kids:
                st.info("\U0001F449 子ども設定タブで子どもを登録すると必要金額が計算できます")
            else:
                recommend  = {"上服": 7, "下服": 6, "下着": 10, "パジャマ": 2}
                base_price = (round(sum(price_per_item.values()) / len(price_per_item))
                              if price_per_item else 1500)

                total_all = 0
                for kid in kids:
                    gender_emoji = "\U0001F466" if kid.get("gender", "") == "男の子" else "\U0001F467"
                    st.markdown("**" + gender_emoji + " " + kid["name"] + "**")
                    needs = {
                        "上服":     max(0, recommend["上服"]     - kid.get("tops",      0)),
                        "下服":     max(0, recommend["下服"]     - kid.get("bottoms",   0)),
                        "下着":     max(0, recommend["下着"]     - kid.get("underwear", 0)),
                        "パジャマ": max(0, recommend["パジャマ"] - kid.get("pajamas",   0)),
                    }
                    total_kid = sum(n * base_price for n in needs.values())
                    total_all += total_kid

                    items_list = list(needs.items())
                    cols = st.columns(2)
                    for ci, (label, n) in enumerate(items_list):
                        with cols[ci % 2]:
                            st.metric(
                                label,
                                "あと" + str(n) + "枚",
                                delta="OK" if n == 0 else "¥" + str(n * base_price),
                                delta_color="normal" if n == 0 else "inverse"
                            )
                    st.caption("\U0001F4B0 この子の今季必要額（目安）: ¥" + str(total_kid))
                    st.divider()

                st.metric("\U0001F4B0 合計の必要額", "¥" + str(total_all))
                st.caption("\U0001F4DD 1枚あたり ¥" + str(base_price) + " で計算（購入履歴から自動算出）")

            # ==============================
            # 季節別おすすめ（CSV分析タブ内）
            # ==============================
            st.divider()
            st.subheader("\U0001F338\U0001F33B\U0001F342\u2744\ufe0f シーズン別おすすめ準備")

            current_month = datetime.now().month
            current_season = get_current_season(current_month)
            next_season = get_next_season(current_season)
            current_info = SEASONAL_NEEDS[current_season]
            next_info = SEASONAL_NEEDS[next_season]

            st.markdown("#### " + current_info["icon"] + " 今シーズンのおすすめアイテム")
            for item in current_info["items"]:
                st.markdown("- \u2705 " + item)

            st.markdown("#### \U0001F6D2 来シーズンの準備")
            st.info(
                next_info["icon"] + " **" + next_info["label"] + "** に向けて準備を始めましょう！\n\n"
                "おすすめ準備アイテム:\n" +
                "\n".join(["- " + item for item in next_info["items"]])
            )

            # 去年の同月比較
            last_year_ym = str(now.year - 1) + "-" + str(now.month).zfill(2)
            if last_year_ym in monthly:
                st.markdown("#### \U0001F4C5 去年の今頃との比較")
                st.info(
                    "\U0001F4B0 去年の" + str(now.month) + "月は **¥" +
                    str(monthly[last_year_ym]) + "** 使いました"
                )

            # サイズアウト × シーズンタイムライン
            kids_for_timeline = load_kids()
            if kids_for_timeline:
                st.markdown("#### \U0001F4C5 サイズアウト × シーズン タイムライン")
                for kid in kids_for_timeline:
                    pred = predict_sizeout(
                        kid.get("height", 120),
                        kid.get("birthday", "2016-01-01"),
                        kid.get("size", "120")
                    )
                    gender_emoji = "\U0001F466" if kid.get("gender", "") == "男の子" else "\U0001F467"
                    timeline_icon = "\U0001F534" if pred["color"] == "red" else "\U0001F7E0" if pred["color"] == "orange" else "\U0001F7E2"
                    st.markdown(
                        gender_emoji + " **" + kid["name"] + "**: " +
                        timeline_icon + " " + pred["status"] +
                        "（あと約" + str(pred["months"]) + "ヶ月 → " +
                        str(pred["next_size"]) + "cmへ）"
                    )
                    if pred["months"] <= 5:
                        st.caption(
                            "\U0001F6D2 次のサイズの" +
                            "、".join(next_info["items"]) +
                            "を早めに準備しましょう！"
                        )

            # 買い物リスト
            st.divider()
            st.markdown("#### \U0001F6D2 買い物チェックリスト")
            st.caption("\U0001F4DD 必要なアイテムをチェックしていこう！")

            shopping_items = current_info["items"] + [
                item + "（来シーズン用）" for item in next_info["items"]
            ]

            for idx, item in enumerate(shopping_items):
                st.checkbox(item, key="shop_check_" + str(idx))

# ==============================
# TAB 4: 写真一覧
# ==============================
with tabs[3]:
    st.subheader("\U0001F4F8 服の写真一覧")
    kids    = load_kids()
    clothes = load_clothes()

    if not kids:
        st.info("\U0001F449 先に子どもを登録してください")
    else:
        selected_kid = st.selectbox(
            "\U0001F476 表示する子を選択",
            ["全員"] + [k["name"] for k in kids]
        )
        selected_cat = st.selectbox(
            "\U0001F3F7\ufe0f カテゴリ",
            ["全て", "上服", "下服", "下着（肌着）", "下着（パンツ）", "パジャマ", "その他"]
        )

        filtered = clothes
        if selected_kid != "全員":
            filtered = [c for c in filtered if c["kid"] == selected_kid]
        if selected_cat != "全て":
            filtered = [c for c in filtered if c["category"] == selected_cat]

        if not filtered:
            st.info("\U0001F4ED 該当する服がありません")
        else:
            st.caption("\U0001F455 " + str(len(filtered)) + "枚の服が登録されています")
            cols = st.columns(2)
            for j, c in enumerate(filtered):
                with cols[j % 2]:
                    if c.get("photo") and os.path.exists(c["photo"]):
                        st.image(Image.open(c["photo"]), use_container_width=True)
                    else:
                        st.markdown(
                            '<div style="background:#FFE8E0;border-radius:12px;'
                            'padding:2rem;text-align:center;margin-bottom:0.5rem;">'
                            '<span style="font-size:2rem;">\U0001F455</span><br>'
                            '<small>写真なし</small></div>',
                            unsafe_allow_html=True
                        )
                    st.caption(
                        c["kid"] + " / " + c["category"] + "\n" +
                        c["name"] + " / サイズ" + c["size"] + "\n" +
                        c.get("color","") + " / " + c.get("shop","")
                    )
                    if c.get("price"):
                        st.caption("\U0001F4B0 ¥" + str(c["price"]))

# ==============================
# TAB 5: LINE通知設定
# ==============================
with tabs[4]:
    st.subheader("\U0001F514 LINE通知設定")
    st.markdown(
        "サイズアウトが近づいたら、LINEでお知らせを受け取れます！\n\n"
        "**LINE Notify** を使って、Kids Closetから直接LINEに通知を送ります。"
    )

    st.divider()

    st.markdown("#### \U0001F4D6 LINE Notifyトークンの取得方法")
    with st.expander("\U0001F449 設定手順を見る"):
        st.markdown(
            "**ステップ1**: [LINE Notify](https://notify-bot.line.me/) にアクセス\n\n"
            "**ステップ2**: LINEアカウントでログイン\n\n"
            "**ステップ3**: 右上のメニューから「マイページ」を開く\n\n"
            "**ステップ4**: 「トークンを発行する」をクリック\n\n"
            "**ステップ5**: トークン名に「Kids Closet」と入力\n\n"
            "**ステップ6**: 通知を受け取るトークルームを選択（「1:1でLINE Notifyから通知を受け取る」がおすすめ）\n\n"
            "**ステップ7**: 「発行する」をクリックしてトークンをコピー\n\n"
            "**ステップ8**: 下の入力欄にペースト！"
        )

    st.divider()

    st.markdown("#### \U0001F511 トークン設定")
    saved_token = load_line_token()
    line_token = st.text_input(
        "\U0001F511 LINE Notifyトークン",
        value=saved_token,
        type="password",
        placeholder="ここにトークンをペースト"
    )

    col_save, col_test = st.columns(2)
    with col_save:
        if st.button("\U0001F4BE トークンを保存"):
            if line_token:
                save_line_token(line_token)
                st.success("\u2705 トークンを保存しました！")
            else:
                st.warning("\u26a0\ufe0f トークンを入力してください")

    with col_test:
        if st.button("\U0001F4E8 テスト通知を送る"):
            if line_token:
                success, status = send_line_notify(
                    line_token,
                    "\n\U0001F389 Kids Closetからのテスト通知です！\n接続成功！サイズアウト通知を受け取れます \U0001F455"
                )
                if success:
                    st.success("\u2705 テスト通知を送信しました！LINEを確認してね！")
                else:
                    st.error("\u274c 送信に失敗しました（ステータス: " + str(status) + "）\nトークンを確認してください")
            else:
                st.warning("\u26a0\ufe0f 先にトークンを入力してください")

    st.divider()

    st.markdown("#### \U0001F514 サイズアウト通知チェック")
    st.caption("\U0001F4DD 登録済みの子どものサイズアウト予測をチェックして、LINEに通知を送ります")

    kids_for_notify = load_kids()
    if not kids_for_notify:
        st.info("\U0001F449 先に「\U0001F476 子ども設定」タブで子どもを登録してください")
    else:
        # 現在のサイズアウト状況を表示
        st.markdown("##### \U0001F4CB 現在の状況")
        for kid in kids_for_notify:
            pred = predict_sizeout(
                kid.get("height", 120),
                kid.get("birthday", "2016-01-01"),
                kid.get("size", "120")
            )
            icon = "\U0001F534" if pred["color"] == "red" else "\U0001F7E0" if pred["color"] == "orange" else "\U0001F7E2"
            st.markdown(
                icon + " **" + kid["name"] + "**: " + pred["status"] +
                "（あと約" + str(pred["months"]) + "ヶ月）"
            )

        if st.button("\U0001F514 今すぐ通知チェック＆送信"):
            token = line_token if line_token else load_line_token()
            if not token:
                st.warning("\u26a0\ufe0f LINE Notifyトークンが設定されていません")
            else:
                results = check_and_notify_sizeout(kids_for_notify, token)
                if not results:
                    st.success("\u2705 現在サイズアウトが近い子どもはいません。安心！")
                else:
                    log = load_notify_log()
                    for r in results:
                        if r["sent"]:
                            st.success(
                                "\U0001F4E8 " + r["kid"] + "の通知を送信しました！（" +
                                r["status"] + "）"
                            )
                        else:
                            st.error(
                                "\u274c " + r["kid"] + "の通知送信に失敗（" +
                                str(r["response"]) + "）"
                            )
                        log.append(r)
                    save_notify_log(log)

    # 通知履歴
    st.divider()
    st.markdown("#### \U0001F4DC 通知履歴")
    notify_log = load_notify_log()
    if not notify_log:
        st.caption("\U0001F4ED まだ通知履歴はありません")
    else:
        for entry in reversed(notify_log[-10:]):
            status_icon = "\u2705" if entry.get("sent") else "\u274c"
            st.caption(
                status_icon + " " +
                entry.get("time", "?") + " - " +
                entry.get("kid", "?") + ": " +
                entry.get("status", "?")
            )
