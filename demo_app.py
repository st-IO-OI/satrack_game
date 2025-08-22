import streamlit as st
from streamlit_cookies_manager import EncryptedCookieManager
import uuid
import requests
import random
import json
import math
import time
from datetime import datetime, timedelta

st.set_page_config(
    page_title="衛星トラッキングデモ",
    layout="wide"   # <- ここで全幅レイアウトに変更
)

# # セッションステート（図鑑保持用）
# if "pokedex" not in st.session_state:
#     st.session_state.pokedex = []

# --- ユーザーデータの管理 ---

cookies = EncryptedCookieManager(
    prefix="satellite_game",
    password=st.secrets["cookie_password"],  # デプロイ時は secrets で管理
    max_age_days=30
)

if not cookies.ready():
    st.stop()

# すでにcookieがあるか確認
if "user_id" in cookies:
    user_id = cookies["user_id"]
else:
    user_id = str(uuid.uuid4())  # 新規ユーザーならUUID発行
    cookies["user_id"] = user_id
    # cookies.save()

# session_stateにcookieデータを保存
if user_id not in st.session_state:
    st.session_state[user_id] = cookies["user_id"]

# cookieにゲームデータがあるか確認
if "game_data" not in cookies:
    init_data = {
        "lives": 5,
        "last_recharge": datetime.now().isoformat(),
        "history": []
    }
    cookies["game_data"] = json.dumps(init_data)
    # cookies.save()

# session_stateにcookie上のゲームデータを保存
if "game_data" not in st.session_state:
    st.session_state["game_data"] = json.loads(cookies["game_data"])
    print(st.session_state["game_data"] )

# ----------------------
# 状態量初期化
# ----------------------
API_KEY = st.secrets["N2YO_API_KEY"]
MAX_LIVES = 5
HISTORY_MAX_SIZE = 10
RECOVER_INTERVAL = timedelta(hours=1)

if "lives" not in st.session_state:
    st.session_state["lives"] = st.session_state["game_data"]["lives"]  # 最大ライフ5
if "last_recharge" not in st.session_state:
    st.session_state["last_recharge"] = datetime.fromisoformat(st.session_state["game_data"]["last_recharge"])
if "position_data" not in st.session_state:
    st.session_state["position_data"] = "ー"  # 位置データを管理
if "link_data" not in st.session_state:
    st.session_state["link_data"] = "ー" #リンクデータを保管
if "track_data" not in st.session_state:
    st.session_state["track_data"] = "ー" #トラックデータを保管
if "score_link" not in st.session_state:
    st.session_state["score_link"] = 0 #リンクスコアを保管
if "score_track" not in st.session_state:
    st.session_state["score_track"] = 0 #トラックスコアを保管
if "score_total" not in st.session_state:
    st.session_state["score_total"] = st.session_state["score_link"] + st.session_state["score_track"] #トータルスコアを保管
if "link_flag" not in st.session_state:
    st.session_state["link_flag"] = False
if "track_flag" not in st.session_state:
    st.session_state["track_flag"] = False
if "history" not in st.session_state:
    st.session_state["history"] = st.session_state["game_data"]["history"]

# --- history ---のサイズ調整
if len(st.session_state["history"]) > HISTORY_MAX_SIZE:
    dist_size = len(st.session_state["history"]) - HISTORY_MAX_SIZE
    for i in range(HISTORY_MAX_SIZE):
        st.session_state["history"][i] = st.session_state["history"][i+dist_size]
    for i in range(dist_size):
        st.session_state["history"].pop(-1)

# --- タイトル ---
st.title("衛星トラックゲーム デモ")

# --- ライフの回復 ---
now = datetime.now()
elapsed = now - st.session_state["last_recharge"]

recovered = elapsed // RECOVER_INTERVAL  # 1時間ごとに1回復
if recovered > 0:
    st.session_state["lives"] = min(MAX_LIVES, st.session_state["lives"] + recovered)
    st.session_state["last_recharge"] = st.session_state["last_recharge"] + RECOVER_INTERVAL * recovered

if st.session_state["lives"] == 5:
    minutes, seconds = 0, 0
else:
    next_recover = st.session_state["last_recharge"] + RECOVER_INTERVAL
    remaining = next_recover - now
    minutes, seconds = divmod(int(remaining.total_seconds()), 60)
life_placeholder = st.subheader(f"残りライフ❤️ : {st.session_state['lives']}/{MAX_LIVES} ({str(minutes).zfill(2)}:{str(seconds).zfill(2)})")

# --- cookieへの保存 ---
st.session_state["game_data"]["lives"] = st.session_state["lives"]
st.session_state["game_data"]["last_recharge"] = st.session_state["last_recharge"].isoformat()
st.session_state["game_data"]["history"] = st.session_state["history"]
cookies["game_data"] = json.dumps(st.session_state["game_data"])
cookies.save()

# --- 表示の左右分割 ---
col_left, col_center, col_right = st.columns([4, 1, 4])  # 左:操作, 右:結果

# --- 現在位置の入力 ---
with col_left:
    st.subheader("現在地を入力してください")
    lat = st.number_input("緯度 (例: 35.0)", value=35.0, format="%.4f")
    lon = st.number_input("経度 (例: 139.0)", value=139.0, format="%.4f")
    alt_m = st.number_input("高度 (例: 20 (m))", value=0.0, format="%.1f")

    current_position = f"現在地: (緯度{round(lat, 4)}˚, 経度{round(lon, 4)}˚, 高度{round(alt_m, 4)}m)"
    st.session_state["position_data"] = current_position

    alt_km = alt_m / 1000 #kmに換算する

# ----------------------
# プレースホルダー作成
# ----------------------

with col_right:
    st.subheader("現在位置📍")
    position_placeholder = st.empty() #リンクデータの表示領域
    st.subheader("衛星リンク📡")
    link_placeholder = st.empty() #リンクデータの表示領域
    st.subheader("衛星トラック⚡️")
    track_placeholder = st.empty() #トラックデータの表示領域
    st.subheader("スコア")
    score_placeholder = st.empty() #スコアの表示領域
    additional_placeholder = st.empty() #追加データの表示領域
    st.subheader("履歴")
    history_placeholder = st.empty() #過去データの表示領域

    position_placeholder.write(f"{st.session_state['position_data']}")
    link_placeholder.write(f"{st.session_state['link_data']}")
    track_placeholder.write(f"{st.session_state['track_data']}")
    score_placeholder.write(f"リンクスコア: {st.session_state['score_link']}\n\nトラックスコア: {st.session_state['score_track']}\n\nトータルスコア: {st.session_state['score_total']}")
    history_texts = []
    for index in range(len(st.session_state["history"])):
        date, score = st.session_state["history"][index]
        history_texts.append(f"{date} : {score}\n")
    history_placeholder.write("\n".join(history_texts))

    # st.subheader("履歴")
    # if st.session_state["history"]:
    #     for entry in st.session_state["history"]:
    #         st.write(entry)
    # else:
    #     st.write("ー")


# =======================
# 衛星リスト取得
# =======================

with col_left:
    if st.session_state["lives"] > 0:
        if st.button("現在地から見える衛星を探す"):
            if st.session_state["link_flag"] == True:
                st.warning("リンクできるのは1度のみです")
            else:
                with st.spinner("衛星リンク中…"):
                    url = f"https://api.n2yo.com/rest/v1/satellite/above/{lat}/{lon}/{alt_km}/90/0/&apiKey={API_KEY}"
                    response = requests.get(url)

                if response.status_code == 200:
                    data = response.json()
                    sat_list = data.get("above", [])
                    st.session_state["sat_list"] = sat_list
                    st.session_state["lives"] -= 1
                    st.session_state["track_flag"] = False
                    st.session_state["link_flag"] = True
                    if st.session_state["lives"] == 4:
                        st.session_state["last_recharge"] = datetime.now()
                    st.success(f"{len(sat_list)} 個の衛星とリンクしました！")

                    if len(sat_list) <= 20:
                        sat_index_list = [int(x) for x in range(len(sat_list))]
                    else:
                        sat_index_list = random.sample(range(len(sat_list)), k=20)
                    sat_index_list.sort()
                    st.session_state["sat_random_index_list"] = sat_index_list

                    if sat_list:
                        link_placeholder_texts = []
                        # link_placeholder_texts.append("### 衛星一覧（上位20件）")
                        for index in sat_index_list:
                            sat = sat_list[index]
                            link_placeholder_texts.append(f"**{sat['satname']}**  " + f"(ID: {sat['satid']}, 打ち上げ: {sat['launchDate']})\n")
                        st.session_state["link_data"] = "\n".join(link_placeholder_texts)
                        link_placeholder.write(st.session_state["link_data"])
                    else:
                        st.warning("衛星が見つかりませんでした。")

                else:
                    st.error("APIリクエストに失敗しました。APIキーやリクエスト制限を確認してください。")
    else:
        next_recover = st.session_state["last_recharge"] + RECOVER_INTERVAL
        remaining = next_recover - now
        minutes, seconds = divmod(int(remaining.total_seconds()), 60)
        st.error(f"ライフが足りません。次の回復まで {minutes}分 {seconds}秒")


# =======================
# リンクスコア計算
# =======================
with col_left:
    if "sat_list" in st.session_state and st.session_state["sat_list"]:
        # 基本スコア計算（リンク取得分）
        basic_score = 0
        for sat in st.session_state["sat_list"]:
            satname = sat['satname']
            # 高度による簡易スコア
            if "STARLINK" in satname.upper():
                basic_score += 2
            elif "ISS" in satname.upper():
                basic_score += 3
            else:
                basic_score += 1
        st.session_state["score_link"] = basic_score
        st.session_state["score_total"] = st.session_state["score_link"] + st.session_state["score_track"]
        score_placeholder.write(f"リンクスコア: {st.session_state['score_link']}\nトラックスコア: {st.session_state['score_track']}\nトータルスコア: {st.session_state['score_total']}")
        st.write(f"リンクスコア: {basic_score} 点")
        # =======================
        # トラック選択
        # =======================
        if not "sat_random_index_list" in st.session_state:
            if len(sat_list) <= 20:
                sat_index_list = [int(x) for x in range(len(sat_list))]
            else:
                sat_index_list = random.sample(range(len(sat_list)), k=20)
            sat_index_list.sort()
            st.session_state["sat_random_index_list"] = sat_index_list
        else:
            sat_index_list = st.session_state["sat_random_index_list"]

        sat_names = []
        for index in sat_index_list:
            sat = st.session_state['sat_list'][index]
            sat_names.append(f"{sat['satname']} (ID:{sat['satid']})")

        sat_options = [(sat['satname'], sat['satid']) 
                    for index in sat_index_list 
                    for sat in [st.session_state['sat_list'][index]]
                    ]
        choice = st.selectbox(
            "トラックする衛星を選んでください", 
            sat_options, 
            format_func=lambda x: f"{x[0]} (ID:{x[1]})"
            )


        if st.button("トラック！"):
            if st.session_state["link_flag"] == False:
                st.warning("衛星とのリンクが完了していません")
            elif st.session_state["track_flag"] == True:
                st.warning("衛星のトラックできるのは1度のみです")
            else:
                # 衛星IDを取得
                sat_name, sat_id = choice
                st.write(f"選んだ衛星: {sat_name}, ID: {sat_id}")

                # 衛星位置を取得
                with st.spinner("衛星トラック中…"):
                    url = f"https://api.n2yo.com/rest/v1/satellite/positions/{sat_id}/{lat}/{lon}/{alt_km}/1/&apiKey={API_KEY}"
                    response = requests.get(url)

                if response.status_code == 200:
                    sat_data = response.json()
                    pos = sat_data.get("positions", [])[0]

                    sat_lat = pos["satlatitude"]
                    sat_lon = pos["satlongitude"]

                    # 距離計算（簡易：地表での距離）
                    def haversine(lat1, lon1, lat2, lon2):
                        R = 6371.0  # 地球半径 km
                        phi1, phi2 = math.radians(lat1), math.radians(lat2)
                        dphi = math.radians(lat2 - lat1)
                        dlambda = math.radians(lon2 - lon1)
                        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
                        return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a))

                    distance = haversine(lat, lon, sat_lat, sat_lon)
                    track_placeholder_texts = []
                    track_placeholder_texts.append(f"選んだ衛星: {sat_name}, ID: {sat_id}\n")
                    track_placeholder_texts.append(f"衛星位置: 緯度 {sat_lat:.2f}, 経度 {sat_lon:.2f}\n")
                    track_placeholder_texts.append(f"観測地点との距離: 約 {distance:.1f} km\n")
                    st.write(f"観測地点との距離: 約 {distance:.1f} km")
                    st.session_state["track_data"] = "\n".join(track_placeholder_texts)
                    track_placeholder.write(st.session_state["track_data"])
                    # 距離スコア判定
                    if distance < 1000:
                        track_score = 3000 - distance
                    elif distance < 3000:
                        track_score = 2000 - (distance-1000) / 2
                    elif distance < 7000:
                        track_score = 1000 - (distance-3000) / 4
                    else:
                        track_score = 0

                    # キャラクターボーナス（例）
                    bonus_multiplier = 1.0
                    # if distance <= 1000:
                    #     bonus_multiplier *= 1.2
                    # launch_year = int(st.session_state["sat_list"][sat_index]["launchDate"][:4])
                    # if launch_year < 1970:
                    #     bonus_multiplier *= 1.5
                    # if "ISS" in st.session_state["sat_list"][sat_index]["satname"].upper():
                    #     bonus_multiplier *= 1.1

                    total_track_score = int(track_score * bonus_multiplier)
                    st.session_state["track_flag"] = True
                    # トータルスコア
                    st.session_state["score_track"] = total_track_score
                    total_score = st.session_state["score_link"] + st.session_state["score_track"]
                    st.session_state["score_total"] = total_score
                    score_text = []
                    score_text.append(f"リンクスコア: {st.session_state['score_link']}\n")
                    score_text.append(f"トラックスコア: {st.session_state['score_track']}\n")
                    score_text.append(f"トータルスコア: {st.session_state['score_total']}\n")
                    score_text_sum = "\n".join(score_text)
                    score_placeholder.write(score_text_sum)
                    st.write(f"トラックスコア: {total_track_score} 点")
                    st.write(f"トータルスコア: {total_score} 点")
                    # 履歴へ残す
                    date_history = datetime.now().isoformat()
                    score_history = f"リンクスコア: {st.session_state['score_link']}\t\tトラックスコア: {st.session_state['score_track']}\t\tトータルスコア: {st.session_state['score_total']}"
                    st.session_state["history"].append((date_history, score_history))

                    # クールタイム開始
                    st.session_state["last_play_time"] = time.time()
                else:
                    st.error("APIエラー: 衛星位置を取得できませんでした。")


with col_left:
    if st.button("もう一回プレイする"):
        st.success("データはリセットされました。")
        st.session_state["track_flag"] = False
        st.session_state["link_flag"] = False
        st.session_state["link_data"] = "ー"
        st.session_state["track_data"] = "ー"
        st.session_state["score_link"] = 0
        st.session_state["score_track"] = 0
        st.session_state["score_total"] = 0
        link_placeholder.write("ー") #リンクデータの表示領域
        track_placeholder.write("ー") #トラックデータの表示領域
        score_placeholder.write("ー") #スコアの表示領域
        # additional_placeholder.write("-") #追加データの表示領域

# # --- キャッチボタン ---
# if st.button("キャッチ！"):
#     if target["id"] not in [obj["id"] for obj in st.session_state.pokedex]:
#         st.session_state.pokedex.append(target)
#         st.success(f"{target['name']} を捕獲しました！")
#     else:
#         st.info(f"{target['name']} はすでに捕獲済みです")

# # --- 図鑑表示 ---
# st.subheader("📖 捕獲したオブジェクト")
# if st.session_state.pokedex:
#     for obj in st.session_state.pokedex:
#         st.write(f"- {obj['name']} ({obj['type']}, レア度: {obj['rarity']})")
# else:
#     st.write("まだ捕獲していません")


