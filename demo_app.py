import streamlit as st
import sqlite3
import uuid
import requests
import random
import json
import math
import time
from datetime import datetime, timedelta

# ========================
# SQLite 初期化
# ========================
def init_db():
    conn = sqlite3.connect("game.db")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            lives INTEGER,
            last_recharge TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            timestamp TEXT,
            log TEXT
        )
    """)
    conn.commit()
    return conn

# ========================
# Cookie に user_id を保存
# ========================
def get_or_set_user_id():
    if "user_id" not in st.session_state:
        # Cookie から読み取り
        query_params = st.query_params
        if "uid" in query_params:
            st.session_state.user_id = query_params["uid"]
        else:
            # 初回なら新規発行して query_params に保存
            new_id = str(uuid.uuid4())
            st.session_state.user_id = new_id
            st.query_params["uid"] = new_id
    return st.session_state.user_id

# ========================
# ユーザー管理
# ========================
def get_or_create_user(conn, user_id):
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()

    if row is None:
        cur.execute(
            "INSERT INTO users (user_id, lives, last_recharge) VALUES (?, ?, ?)",
            (user_id, 5, datetime.now().isoformat())
        )
        conn.commit()
        return {"user_id": user_id, "lives": 5, "last_recharge": datetime.now().isoformat()}
    else:
        return {
            "user_id": row[0],
            "lives": row[1],
            "last_recharge": row[2]
        }

def update_user(conn, user):
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET lives=?, last_recharge=? WHERE user_id=?",
        (user["lives"], user["last_recharge"], user["user_id"])
    )
    conn.commit()

def add_history(conn, user_id, log, max_size=10):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO history (user_id, timestamp, log) VALUES (?, ?, ?)",
        (user_id, datetime.now().isoformat(), log)
    )
    conn.commit()
    #履歴件数の取得
    cur.execute("SELECT id FROM history WHERE user_id=? ORDER BY id DESC", (user_id,))
    rows = cur.fetchall()
    #max_sizeを超えていたら古いものを削除
    if len(rows) > max_size:
        # 超過分を取得（古い方）
        ids_to_delete = [row[0] for row in rows[max_size:]]
        cur.executemany("DELETE FROM history WHERE id=?", [(i,) for i in ids_to_delete])
        conn.commit()

def get_history(conn, user_id):
    cur = conn.cursor()
    cur.execute("SELECT timestamp, log FROM history WHERE user_id=? ORDER BY id DESC", (user_id,))
    return cur.fetchall()

# ========================
# アプリ本体
# ========================

#cookieに渡すデータ：st.session_state["game_data"]に集約されている
#基本的にはそことuser(cookie)のやり取りおよびuserのアウトプットだけを考えれば良いはず（オブジェクト化）

def main():
    # --- cookieデータに基づくユーザデータ取得 ---
    conn = init_db() #dbの初期化
    user_id = get_or_set_user_id() #user_idをcookieから取得
    user = get_or_create_user(conn, user_id) #user_id毎にユーザーデータを保管する

    st.set_page_config(
        page_title="衛星トラッキングデモ",
        layout="wide"   # <- ここで全幅レイアウトに変更
    )

    # --- Cookieのセーブフラグ管理 ---
    cookie_save_needed_flag = False
    def save_game_data_to_cookie():
        st.session_state["game_data"]["lives"] = st.session_state["lives"]
        st.session_state["game_data"]["last_recharge"] = st.session_state["last_recharge"].isoformat()
        st.session_state["game_data"]["history"] = st.session_state["history"]
        # user["game_data"] = json.dumps(st.session_state["game_data"])
        return True

    # ----------------------
    # 状態量初期化
    # ----------------------
    API_KEY = st.secrets["N2YO_API_KEY"]
    MAX_LIVES = 5
    HISTORY_MAX_SIZE = 10
    RECOVER_INTERVAL = timedelta(hours=1)

    if "game_data" not in st.session_state:
        st.session_state["game_data"] = {
            "user_id": user["user_id"], 
            "lives": user["lives"],
            "last_recharge": user["last_recharge"],
            "history": get_history(conn, user_id)
        }
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
    if "history_renew_flag" not in st.session_state:
        st.session_state["history_renew_flag"] = False

    # --- history ---のサイズ調整
    if len(st.session_state["history"]) > HISTORY_MAX_SIZE:
        st.session_state["history"] = st.session_state["history"][-HISTORY_MAX_SIZE:]

    # --- タイトル ---
    st.title("衛星トラックゲーム デモ")

    # --- ライフの回復 ---
    now = datetime.now()
    elapsed = now - st.session_state["last_recharge"]

    recovered = elapsed // RECOVER_INTERVAL  # 1時間ごとに1回復
    if recovered > 0:
        st.session_state["lives"] = min(MAX_LIVES, st.session_state["lives"] + recovered)
        st.session_state["last_recharge"] = st.session_state["last_recharge"] + RECOVER_INTERVAL * recovered
        cookie_save_needed_flag = save_game_data_to_cookie()

    if st.session_state["lives"] == 5:
        minutes, seconds = 0, 0
    else:
        next_recover = st.session_state["last_recharge"] + RECOVER_INTERVAL
        remaining = next_recover - now
        minutes, seconds = divmod(int(remaining.total_seconds()), 60)
    life_placeholder = st.subheader(f"残りライフ❤️ : {st.session_state['lives']}/{MAX_LIVES} ({str(minutes).zfill(2)}:{str(seconds).zfill(2)})")

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
                        cookie_save_needed_flag = save_game_data_to_cookie()
                        st.session_state["track_flag"] = False
                        st.session_state["link_flag"] = True
                        if st.session_state["lives"] == 4:
                            st.session_state["last_recharge"] = datetime.now()
                        st.success(f"{len(st.session_state['sat_list'])} 個の衛星とリンクしました！")

                        if len(st.session_state["sat_list"]) <= 20:
                            sat_index_list = [int(x) for x in range(len(st.session_state["sat_list"]))]
                        else:
                            sat_index_list = random.sample(range(len(st.session_state["sat_list"])), k=20)
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
                if len(st.session_state["sat_list"]) <= 20:
                    sat_index_list = [int(x) for x in range(len(st.session_state["sat_list"]))]
                else:
                    sat_index_list = random.sample(range(len(st.session_state["sat_list"])), k=20)
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
                        st.session_state["history"].append([date_history, score_history])
                        st.session_state["history_renew_flag"] = True
                        cookie_save_needed_flag = save_game_data_to_cookie()
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
            cookie_save_needed_flag = save_game_data_to_cookie()

    # --- cookieの保存 ---
    if cookie_save_needed_flag == True:
        update_user(conn, {
            "user_id": st.session_state["user_id"],
            "lives": st.session_state["game_data"]["lives"],
            "last_recharge": st.session_state["game_data"]["last_recharge"],
        })
    if st.session_state["history_renew_flag"] == True:
        date_history, score_history = st.session_state["history"][-1]
        add_history(conn, user_id, score_history, max_size=HISTORY_MAX_SIZE)
        st.session_state["history_renew_flag"] = False


if __name__ == "__main__":
    main()