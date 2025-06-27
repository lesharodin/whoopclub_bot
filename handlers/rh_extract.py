import sqlite3
import difflib
import datetime
import pandas as pd


def score_from_gap(gap):
    if gap <= 0.02:
        return 10
    elif gap <= 0.05:
        return 8
    elif gap <= 0.10:
        return 6
    elif gap <= 0.20:
        return 4
    elif gap <= 0.30:
        return 2
    else:
        return 0

async def process_race_db(race_db_path: str, bot_db: sqlite3.Connection):
    rh = sqlite3.connect(race_db_path)
    cursor_rh = rh.cursor()

    # Загружаем таблицы из базы RotorHazard
    pilots = pd.read_sql("SELECT id, name FROM pilot", rh)
    heat_nodes = pd.read_sql("SELECT heat_id, pilot_id FROM heat_node", rh)
    heats = pd.read_sql("SELECT id, note FROM heat", rh)
    laps = pd.read_sql("SELECT pilot_id, race_id, lap_time_stamp, lap_time, deleted FROM saved_race_lap", rh)
    races = pd.read_sql("SELECT pilot_id, race_id FROM saved_pilot_race", rh)

    # Убираем deleted и первый круг (по времени в раунде)
    laps = laps[laps["deleted"] == 0].copy()
    laps["lap_order"] = laps.sort_values("lap_time_stamp").groupby(["pilot_id", "race_id"]).cumcount()
    laps = laps[laps["lap_order"] > 0]
    laps["lap_time_sec"] = laps["lap_time"] / 1000

    # Группы
    groups = heat_nodes.merge(heats, left_on="heat_id", right_on="id")[["pilot_id", "note"]]
    pilot_data = pilots.merge(groups, left_on="id", right_on="pilot_id", how="left")

    # Дата тренировки по первой записи
    training_date = datetime.datetime.now().strftime("%Y-%m-%d")

    results = []

    for _, pilot_row in pilot_data.iterrows():
        pid = pilot_row["id"]
        pname = pilot_row["name"]
        group = pilot_row["note"]

        pilot_laps = laps[laps["pilot_id"] == pid].copy()
        if pilot_laps.empty:
            continue

        # Лучший круг
        best_lap_row = pilot_laps.loc[pilot_laps["lap_time_sec"].idxmin()]
        best_lap = best_lap_row["lap_time_sec"]
        best_lap_race_id = best_lap_row["race_id"]
        best_lap_order = best_lap_row["lap_order"] + 1

        # Лучшая серия из 3 подряд
        pilot_laps_sorted = pilot_laps.sort_values(by=["race_id", "lap_order"]).reset_index(drop=True)
        best_3_sum = None
        best_3_race_id = None
        best_3_start = None
        for i in range(len(pilot_laps_sorted) - 2):
            a, b, c = pilot_laps_sorted.loc[i:i+2, "lap_time_sec"]
            s = a + b + c
            if best_3_sum is None or s < best_3_sum:
                best_3_sum = s
                best_3_race_id = pilot_laps_sorted.loc[i, "race_id"]
                best_3_start = pilot_laps_sorted.loc[i, "lap_order"] + 1

        total_laps = len(pilot_laps)
        total_rounds = races[races["pilot_id"] == pid]["race_id"].nunique()
        avg_lap = pilot_laps["lap_time_sec"].mean()
        stability = round(best_lap / avg_lap, 3) if avg_lap else None

        results.append({
            "pilot_id": pid,
            "pilot_name": pname,
            "group": group,
            "best_lap": best_lap,
            "best_lap_race_id": best_lap_race_id,
            "best_lap_order": best_lap_order,
            "best_3_laps": best_3_sum,
            "best_3_race_id": best_3_race_id,
            "best_3_start_order": best_3_start,
            "total_laps": total_laps,
            "total_rounds": total_rounds,
            "stability": stability,
        })

    df = pd.DataFrame(results)

    # Подсчёт очков по группам
    scored = []
    for group, group_df in df.groupby("group"):
        g = group_df.copy()
        min_best = g["best_lap"].min()
        min_3 = g["best_3_laps"].min()
        max_laps = g["total_laps"].max()

        g["score_best"] = g["best_lap"].apply(lambda x: score_from_gap((x / min_best) - 1))
        g["score_3laps"] = g["best_3_laps"].apply(lambda x: score_from_gap((x / min_3) - 1))
        g["score_total_laps"] = g["total_laps"].apply(lambda x: score_from_gap(1 - (x / max_laps)))

        # +1 за лидерство
        g.loc[g["best_lap"] == min_best, "score_best"] += 1
        g.loc[g["best_3_laps"] == min_3, "score_3laps"] += 1
        g.loc[g["total_laps"] == max_laps, "score_total_laps"] += 1

        g["score_participation"] = 10
        g["score_dominance"] = (
            (g["best_lap"] == min_best) &
            (g["best_3_laps"] == min_3) &
            (g["total_laps"] == max_laps)
        ).astype(int) * 10

        g["score_total"] = (
            g["score_best"] + g["score_3laps"] +
            g["score_total_laps"] + g["score_participation"] +
            g["score_dominance"]
        )

        scored.append(g)

    df_scores = pd.concat(scored)

    # Сопоставление с user_id по OSD (приблизительно)
    users = pd.read_sql("SELECT user_id, nickname AS OSD FROM users", bot_db)
    def match_osd(name):
        match = difflib.get_close_matches(name.lower(), users["OSD"].str.lower(), n=1, cutoff=0.8)
        if match:
            return users.loc[users["OSD"].str.lower() == match[0], "user_id"].values[0]
        return None

    df_scores["user_id"] = df_scores["pilot_name"].apply(match_osd)

    # Сохраняем в базу
    for _, row in df_scores.iterrows():
        cursor = bot_db.cursor()
        cursor.execute("""
            INSERT INTO training_scores (
                training_date, user_id, pilot_name, group_name,
                best_lap, best_lap_race_id, best_lap_order,
                best_3_laps, best_3_race_id, best_3_start_order,
                total_laps, total_rounds, stability,
                score_best, score_3laps, score_total_laps,
                score_participation, score_dominance, score_total
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            training_date,
            row["user_id"],
            row["pilot_name"],
            row["group"],
            row["best_lap"],
            row["best_lap_race_id"],
            row["best_lap_order"],
            row["best_3_laps"],
            row["best_3_race_id"],
            row["best_3_start_order"],
            row["total_laps"],
            row["total_rounds"],
            row["stability"],
            row["score_best"],
            row["score_3laps"],
            row["score_total_laps"],
            row["score_participation"],
            row["score_dominance"],
            row["score_total"],
        ))
        bot_db.commit()
