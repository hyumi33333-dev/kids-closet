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
    return {"status": status, "color": color, "months": months_to_next,
            "next_size": next_boundary, "cm_to_next": cm_to_next}

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
    files = glob.glob(os.path.join(CSV_DIR, "*.csv"))
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
def analyze_clothing_image(image):
    # TODO: Connect to Claude Vision API for auto-detection
    width, height = image.size
    aspect_ratio = width / height
    if aspect_ratio > 1.3:
        suggested = "半袖Tシャツ"; confidence = "中"
    elif aspect_ratio < 0.7:
        suggested = "長ズボン"; confidence = "中"
    else:
        suggested = "薄手トップス"; confidence = "低"
    return {"suggested_category": suggested, "confidence": confidence}

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

def check_and_notify_sizeout(kids, token):
    results = []
    for kid in kids:
        pred = predict_sizeout(kid.get("height", 120), kid.get("birthday", "2016-01-01"), kid.get("size", "120"))
        if pred["color"] in ["red", "orange"]:
            msg = ("\n" + kid["name"] + "の服がまもなくサイズアウトします！\n"
                   "現在サイズ: " + str(kid.get("size", "?")) + "cm\n"
                   "次のサイズ: " + str(pred["next_size"]) + "cm\n"
                   "あと約" + str(pred["months"]) + "ヶ月\n\nKids Closetで確認してね！")
            success, status = send_line_notify(token, msg)
            results.append({"kid": kid["name"], "status": pred["status"],
                            "sent": success, "response": status,
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
st.set_page_config(page_title="Kids Closet", page_icon="", layout="centered")

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
# タイトル
# ==============================
st.title("Kids Closet")
st.markdown(
    f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:4px;">'
    f'<img src="data:image/png;base64,{ICON_LOGO}" width="52" height="52">'
    f'<span style="font-size:2rem;font-weight:800;color:#FF6B6B;">Kids Closet</span>'
    f'</div>'
    f'<p style="color:#999;font-size:0.9rem;margin-top:0;">子どもの成長記録・服の管理・衣類費の予測</p>',
    unsafe_allow_html=True
)

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

        st.markdown(f'<div class="icon-label">{icon_img(ICON_CLOTHING)}上服の枚数</div>', unsafe_allow_html=True)
        new_tops = st.number_input("上服", 0, 50, 5, label_visibility="collapsed", key="new_tops")

        st.markdown(f'<div class="icon-label">{icon_img(ICON_PANTS)}下服の枚数</div>', unsafe_allow_html=True)
        new_bottoms = st.number_input("下服", 0, 50, 5, label_visibility="collapsed", key="new_bottoms")

        st.markdown(f'<div class="icon-label">{icon_img(ICON_UNDERWEAR)}下着の枚数</div>', unsafe_allow_html=True)
        new_underwear = st.number_input("下着", 0, 50, 7, label_visibility="collapsed", key="new_underwear")

        st.markdown(f'<div class="icon-label">{icon_img(ICON_PAJAMAS)}パジャマの枚数</div>', unsafe_allow_html=True)
        new_pajamas = st.number_input("パジャマ", 0, 20, 2, label_visibility="collapsed", key="new_pajamas")

        if st.button("追加する"):
            if new_name:
                kids.append({"name": new_name, "gender": new_gender,
                             "birthday": new_bday.strftime("%Y-%m-%d"), "height": new_height,
                             "size": new_size, "tops": new_tops, "bottoms": new_bottoms,
                             "underwear": new_underwear, "pajamas": new_pajamas})
                save_kids(kids)
                st.success(new_name + " を追加しました！")
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
                f'{icon_img(ICON_CLOTHING, 14)}サイズ: {kid.get("size","?")}</p>',
                unsafe_allow_html=True)

            pred = predict_sizeout(kid.get("height", 120), kid.get("birthday", "2016-01-01"), kid.get("size", "120"))
            st.markdown(f'<p style="font-weight:600;">{icon_img(ICON_CHART, 16)}サイズアウト予測</p>', unsafe_allow_html=True)
            if pred["color"] == "red":
                st.error(pred["status"])
            elif pred["color"] == "orange":
                st.warning(pred["status"])
            else:
                st.success(pred["status"])
            st.caption("次のサイズ(" + str(pred["next_size"]) + "cm)まで あと " +
                       str(pred["cm_to_next"]) + "cm・約 " + str(pred["months"]) + "ヶ月")

            st.markdown(f'<p style="font-weight:600;">{icon_img(ICON_CLOTHING, 16)}今の服の枚数</p>', unsafe_allow_html=True)
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown(f'<span style="font-size:0.85rem;">{icon_img(ICON_CLOTHING, 14)}上服: {kid.get("tops", 0)}枚</span>', unsafe_allow_html=True)
                st.markdown(f'<span style="font-size:0.85rem;">{icon_img(ICON_PANTS, 14)}下服: {kid.get("bottoms", 0)}枚</span>', unsafe_allow_html=True)
            with col_b:
                st.markdown(f'<span style="font-size:0.85rem;">{icon_img(ICON_UNDERWEAR, 14)}下着: {kid.get("underwear", 0)}枚</span>', unsafe_allow_html=True)
                st.markdown(f'<span style="font-size:0.85rem;">{icon_img(ICON_PAJAMAS, 14)}パジャマ: {kid.get("pajamas", 0)}枚</span>', unsafe_allow_html=True)

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
                analysis = analyze_clothing_image(photo_image)
                suggested_cat = analysis["suggested_category"]
                suggested_season = guess_season_from_category(suggested_cat)
                st.info("AI推定: **" + suggested_cat + "**（" + suggested_season + "）信頼度: " + analysis["confidence"] +
                        "\n\n下で確認・変更できます！")

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
                        kid_photo_dir = os.path.join(PHOTO_DIR, c_kid)
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
            save_path = os.path.join(CSV_DIR, uf.name)
            with open(save_path, "wb") as f:
                f.write(uf.getbuffer())
        st.success(str(len(uploaded_csvs)) + "個のCSVをアップロードしました")

    csv_files = glob.glob(os.path.join(CSV_DIR, "*.csv"))
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
                for kid in kids:
                    st.markdown(f'<p style="font-weight:600;">{icon_img(ICON_BABY, 16)}{kid["name"]}</p>', unsafe_allow_html=True)
                    needs = {"上服": max(0, recommend["上服"] - kid.get("tops", 0)),
                             "下服": max(0, recommend["下服"] - kid.get("bottoms", 0)),
                             "下着": max(0, recommend["下着"] - kid.get("underwear", 0)),
                             "パジャマ": max(0, recommend["パジャマ"] - kid.get("pajamas", 0))}
                    total_kid = sum(n * base_price for n in needs.values())
                    total_all += total_kid
                    cols = st.columns(2)
                    for ci, (label, n) in enumerate(needs.items()):
                        with cols[ci % 2]:
                            st.metric(label, "あと" + str(n) + "枚",
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
            if pred["color"] == "red":
                st.error("**" + kid["name"] + "**: " + pred["status"] + "（あと約" + str(pred["months"]) + "ヶ月）")
            elif pred["color"] == "orange":
                st.warning("**" + kid["name"] + "**: " + pred["status"] + "（あと約" + str(pred["months"]) + "ヶ月）")
            else:
                st.success("**" + kid["name"] + "**: " + pred["status"] + "（あと約" + str(pred["months"]) + "ヶ月）")

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
