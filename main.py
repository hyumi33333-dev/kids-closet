import streamlit as st
import json
import os
import pandas as pd
from datetime import date, datetime
from PIL import Image
import glob

# ==============================
# 設定
# ==============================
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(BASE_DIR, "data")
CSV_DIR   = os.path.join(DATA_DIR, "csv")
PHOTO_DIR = os.path.join(BASE_DIR, "photos")
KIDS_FILE    = os.path.join(DATA_DIR, "kids.json")
CLOTHES_FILE = os.path.join(DATA_DIR, "clothes.json")

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
# ページ設定 (centered for mobile)
# ==============================
st.set_page_config(page_title="Kids Closet", layout="centered")

# ==============================
# モバイル向けCSS
# ==============================
st.markdown("""
<style>
/* モバイル全体のフォントサイズ・パディング調整 */
@media (max-width: 768px) {
    .block-container {
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
        padding-top: 1rem !important;
    }
    /* タブのタッチターゲットを大きく */
    .stTabs [data-baseweb="tab-list"] button {
        font-size: 0.95rem;
        padding: 0.6rem 0.4rem;
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
/* 全画面幅でボタンを見やすく */
.stButton > button {
    min-height: 2.5rem;
}
/* カード風の服表示 */
.clothing-card {
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    padding: 0.5rem;
    margin-bottom: 0.5rem;
}
</style>
""", unsafe_allow_html=True)

st.title("Kids Closet")
st.caption("子どもの成長記録・服の管理・衣類費の予測")

tabs = st.tabs(["子ども設定", "服の管理", "CSV分析・予測", "写真一覧"])

# ==============================
# TAB 1: 子ども設定
# ==============================
with tabs[0]:
    st.subheader("お子さまの情報")
    kids = load_kids()

    with st.expander("子どもを追加する", expanded=len(kids) == 0):
        # モバイル: 縦一列レイアウト（st.columns(2) を廃止）
        new_name   = st.text_input("名前（例：長男）")
        new_gender = st.selectbox("性別", ["男の子", "女の子"])
        new_bday   = st.date_input(
            "誕生日",
            value=date(2016, 1, 1),
            min_value=date(2000, 1, 1),
            max_value=date.today()
        )
        new_height    = st.number_input("現在の身長 (cm)", 50, 200, 120)
        new_size      = st.selectbox("現在着ているサイズ",
                                     ["80","90","95","100","110","120","130","140","150","160","170"])
        new_tops      = st.number_input("上服の枚数", 0, 50, 5)
        new_bottoms   = st.number_input("下服の枚数", 0, 50, 5)
        new_underwear = st.number_input("下着の枚数", 0, 50, 7)
        new_pajamas   = st.number_input("パジャマの枚数", 0, 20, 2)

        if st.button("追加する"):
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
                st.success(new_name + " を追加しました")
                st.rerun()
            else:
                st.warning("名前を入力してください")

    if kids:
        st.divider()
        for i, kid in enumerate(kids):
            # モバイル: 縦一列レイアウト（3カラム -> 単一カラム）
            st.markdown("### " + kid["name"] + "（" + kid.get("gender","") + "）")
            bday = kid.get("birthday", "")
            try:
                age_days = (date.today() - datetime.strptime(bday, "%Y-%m-%d").date()).days
                age_y = int(age_days // 365)
                age_m = int((age_days % 365) // 30)
                st.caption("誕生日: " + bday + "（" + str(age_y) + "歳" + str(age_m) + "ヶ月）")
            except Exception:
                st.caption("誕生日: " + bday)
            st.caption("身長: " + str(kid.get("height","?")) + "cm　サイズ: " + str(kid.get("size","?")))

            pred = predict_sizeout(
                kid.get("height", 120),
                kid.get("birthday", "2016-01-01"),
                kid.get("size", "120")
            )
            st.markdown("**サイズアウト予測**")
            if pred["color"] == "red":
                st.error(pred["status"])
            elif pred["color"] == "orange":
                st.warning(pred["status"])
            else:
                st.success(pred["status"])
            st.caption(
                "次のサイズ(" + str(pred["next_size"]) + "cm)まで "
                "あと " + str(pred["cm_to_next"]) + "cm・約 " + str(pred["months"]) + "ヶ月"
            )

            st.markdown("**今の服の枚数**")
            col_a, col_b = st.columns(2)
            with col_a:
                st.caption("上服: " + str(kid.get("tops", 0)) + "枚")
                st.caption("下服: " + str(kid.get("bottoms", 0)) + "枚")
            with col_b:
                st.caption("下着: " + str(kid.get("underwear", 0)) + "枚")
                st.caption("パジャマ: " + str(kid.get("pajamas", 0)) + "枚")

            if st.button("削除", key="del_" + str(i)):
                kids.pop(i)
                save_kids(kids)
                st.rerun()

            st.divider()

# ==============================
# TAB 2: 服の管理
# ==============================
with tabs[1]:
    st.subheader("服の登録・管理")
    kids    = load_kids()
    clothes = load_clothes()

    if not kids:
        st.info("先に「子ども設定」タブで子どもを追加してください")
    else:
        with st.expander("服を登録する"):
            # モバイル: 縦一列レイアウト（2カラム -> 単一カラム）
            kid_names = [k["name"] for k in kids]
            c_kid   = st.selectbox("誰の服？", kid_names, key="c_kid")
            c_cat   = st.selectbox("カテゴリ",
                                    ["上服", "下服", "下着（肌着）", "下着（パンツ）", "パジャマ", "その他"])
            c_name  = st.text_input("服の名前（例：白Tシャツ）")
            c_size  = st.selectbox("サイズ",
                                    ["80","90","95","100","110","120","130","140","150","160","170"])
            c_color = st.text_input("色・柄（例：白、ボーダー）")
            c_shop  = st.text_input("購入店（例：ユニクロ）")
            c_price = st.number_input("購入金額（円）", 0, 100000, 0)
            c_photo = st.file_uploader("写真（任意）", type=["jpg", "jpeg", "png"])

            if st.button("服を登録する"):
                if c_name:
                    photo_path = ""
                    if c_photo:
                        kid_photo_dir = os.path.join(PHOTO_DIR, c_kid)
                        os.makedirs(kid_photo_dir, exist_ok=True)
                        fname = datetime.now().strftime("%Y%m%d%H%M%S") + "_" + c_photo.name
                        photo_path = os.path.join(kid_photo_dir, fname)
                        with open(photo_path, "wb") as f:
                            f.write(c_photo.read())

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
                    st.success(c_name + " を登録しました")
                    st.rerun()
                else:
                    st.warning("服の名前を入力してください")

        st.divider()

        for kid in kids:
            st.markdown("### " + kid["name"] + " の服")
            kid_clothes = [c for c in clothes if c["kid"] == kid["name"]]

            if not kid_clothes:
                st.caption("まだ服が登録されていません")
            else:
                cats = ["上服", "下服", "下着（肌着）", "下着（パンツ）", "パジャマ", "その他"]
                for cat in cats:
                    cat_clothes = [c for c in kid_clothes if c["category"] == cat]
                    if not cat_clothes:
                        continue
                    st.caption(cat + "（" + str(len(cat_clothes)) + "枚）")
                    # モバイル: 2カラムグリッド（4カラム -> 2カラム）
                    cols = st.columns(2)
                    for j, c in enumerate(cat_clothes):
                        with cols[j % 2]:
                            if c.get("photo") and os.path.exists(c["photo"]):
                                st.image(Image.open(c["photo"]), use_container_width=True)
                            else:
                                st.caption("写真なし")
                            st.caption(c["name"] + "\nサイズ: " + c["size"] + "　" + c.get("color",""))
                            if c.get("price"):
                                st.caption("¥" + str(c["price"]))
            st.divider()

# ==============================
# TAB 3: CSV分析・予測
# ==============================
with tabs[2]:
    st.subheader("家計データ分析・来月予測")
    st.info(
        "CSVファイルの置き場所: " + CSV_DIR + "\n\n"
        "MoneyForward MEからダウンロードしたCSVをこのフォルダに入れてください。"
        "複数年分まとめて入れてOKです。"
    )

    csv_files = glob.glob(os.path.join(CSV_DIR, "*.csv"))
    if not csv_files:
        st.warning("CSVファイルがまだありません。上記フォルダにCSVを入れてからページを更新してください。")
    else:
        st.success(str(len(csv_files)) + "個のCSVファイルを読み込みました")
        monthly, shop_amounts, transactions = parse_csv_files()
        price_per_item = calc_price_per_item(shop_amounts)

        if not monthly:
            st.warning("子ども服のデータが見つかりませんでした。CSVの内容を確認してください。")
        else:
            # モバイル: 予算設定を縦一列に
            budget    = st.number_input("月の上限予算（円）", 0, 200000, 15000, step=1000)
            warn_line = st.number_input("警告ライン（円）",   0, 200000, 12000, step=1000)

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

            st.subheader("来月（" + str(next_year) + "年" + str(next_month) + "月）の予測")
            # モバイル: 3カラム -> 縦にメトリクスを並べる
            st.metric("予測支出", "¥" + str(predicted))
            st.metric("予算上限", "¥" + str(budget))
            diff = predicted - budget
            st.metric(
                "余裕",
                "¥" + str(abs(diff)),
                delta="超過" if diff > 0 else "余裕あり",
                delta_color="inverse"
            )
            st.caption("算出根拠: " + basis)

            if predicted >= budget:
                st.error("来月は予算超過の可能性があります。今月中に準備を！")
            elif predicted >= warn_line:
                st.warning("来月は警告ラインに近い見込みです。")
            else:
                st.success("来月は予算内に収まる見込みです。")

            st.divider()

            st.subheader("月別の子ども服支出")
            sorted_monthly = dict(sorted(monthly.items()))
            df_chart = pd.DataFrame({
                "月":   list(sorted_monthly.keys()),
                "支出": list(sorted_monthly.values()),
            }).set_index("月")
            st.bar_chart(df_chart)

            st.divider()

            st.subheader("店舗別の購入分析（単価推定）")
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
                st.caption("推定1枚単価 = 1回の購入金額 ÷ 2.5枚（平均購入枚数の仮定）")

            st.divider()

            st.subheader("今シーズンの必要金額算出")
            kids = load_kids()
            if not kids:
                st.info("子ども設定タブで子どもを登録すると必要金額が計算できます")
            else:
                recommend  = {"上服": 7, "下服": 6, "下着": 10, "パジャマ": 2}
                base_price = (round(sum(price_per_item.values()) / len(price_per_item))
                              if price_per_item else 1500)

                total_all = 0
                for kid in kids:
                    st.markdown("**" + kid["name"] + "**")
                    needs = {
                        "上服":     max(0, recommend["上服"]     - kid.get("tops",      0)),
                        "下服":     max(0, recommend["下服"]     - kid.get("bottoms",   0)),
                        "下着":     max(0, recommend["下着"]     - kid.get("underwear", 0)),
                        "パジャマ": max(0, recommend["パジャマ"] - kid.get("pajamas",   0)),
                    }
                    total_kid = sum(n * base_price for n in needs.values())
                    total_all += total_kid

                    # モバイル: 4カラム -> 2カラム
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
                    st.caption("この子の今季必要額（目安）: ¥" + str(total_kid))
                    st.divider()

                st.metric("合計の必要額", "¥" + str(total_all))
                st.caption("1枚あたり ¥" + str(base_price) + " で計算（購入履歴から自動算出）")

# ==============================
# TAB 4: 写真一覧
# ==============================
with tabs[3]:
    st.subheader("服の写真一覧")
    kids    = load_kids()
    clothes = load_clothes()

    if not kids:
        st.info("先に子どもを登録してください")
    else:
        selected_kid = st.selectbox(
            "表示する子を選択",
            ["全員"] + [k["name"] for k in kids]
        )
        selected_cat = st.selectbox(
            "カテゴリ",
            ["全て", "上服", "下服", "下着（肌着）", "下着（パンツ）", "パジャマ", "その他"]
        )

        filtered = clothes
        if selected_kid != "全員":
            filtered = [c for c in filtered if c["kid"] == selected_kid]
        if selected_cat != "全て":
            filtered = [c for c in filtered if c["category"] == selected_cat]

        if not filtered:
            st.info("該当する服がありません")
        else:
            st.caption(str(len(filtered)) + "枚の服が登録されています")
            # モバイル: 4カラム -> 2カラム
            cols = st.columns(2)
            for j, c in enumerate(filtered):
                with cols[j % 2]:
                    if c.get("photo") and os.path.exists(c["photo"]):
                        st.image(Image.open(c["photo"]), use_container_width=True)
                    else:
                        st.caption("写真なし")
                    st.caption(
                        c["kid"] + " / " + c["category"] + "\n" +
                        c["name"] + " / サイズ" + c["size"] + "\n" +
                        c.get("color","") + " / " + c.get("shop","")
                    )
                    if c.get("price"):
                        st.caption("¥" + str(c["price"]))
