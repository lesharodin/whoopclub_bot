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
def extract_training_date(db_path: str) -> str:
    rh = sqlite3.connect(db_path)
    try:
        df = pd.read_sql("SELECT MIN(date(start_time_formatted)) as date FROM saved_race_meta", rh)
        return df.iloc[0]["date"]
    finally:
        rh.close()
async def process_race_db(race_db_path: str, bot_db: sqlite3.Connection):
    import sqlite3
    import difflib
    import pandas as pd

    rh = sqlite3.connect(race_db_path)
    cursor_rh = rh.cursor()

    # Загружаем таблицы из базы RotorHazard
    pilots = pd.read_sql("SELECT id, name FROM pilot", rh)
    heat_nodes = pd.read_sql("SELECT heat_id, pilot_id FROM heat_node", rh)
    heats = pd.read_sql("SELECT id, note FROM heat", rh)
    laps = pd.read_sql("SELECT pilot_id, race_id, lap_time_stamp, lap_time, deleted FROM saved_race_lap", rh)
    races = pd.read_sql("SELECT pilot_id, race_id FROM saved_pilot_race", rh)
    races_meta = pd.read_sql("SELECT id AS race_id, round_id FROM saved_race_meta", rh)

    # Убираем deleted и первый круг (по времени в раунде)
    laps = laps[laps["deleted"] == 0].copy()
    laps["lap_order"] = laps.sort_values("lap_time_stamp").groupby(["pilot_id", "race_id"]).cumcount()
    laps = laps[laps["lap_order"] > 0]
    laps["lap_time_sec"] = laps["lap_time"] / 1000

    # Группы
    groups = heat_nodes.merge(heats, left_on="heat_id", right_on="id")[["pilot_id", "note"]]
    pilot_data = pilots.merge(groups, left_on="id", right_on="pilot_id", how="left")

    training_date = extract_training_date(race_db_path)

    # 🔥 Только квалификационные группы
    pilot_data_qual = pilot_data[pilot_data["note"].isin(["Группа 1", "Группа 2"])].copy()
    results = []

    for _, pilot_row in pilot_data_qual.iterrows():
        pid = pilot_row["id"]
        pname = pilot_row["name"]
        group = pilot_row["note"]

        pilot_laps = laps[laps["pilot_id"] == pid].copy()
        if pilot_laps.empty:
            continue

        best_lap_row = pilot_laps.loc[pilot_laps["lap_time_sec"].idxmin()]
        best_lap = best_lap_row["lap_time_sec"]
        race_id = best_lap_row["race_id"]
        best_lap_round = races_meta.loc[races_meta["race_id"] == race_id, "round_id"].values[0]
        best_lap_order = best_lap_row["lap_order"] + 1

        pilot_laps_sorted = pilot_laps.sort_values(by=["race_id", "lap_order"]).reset_index(drop=True)
        best_3_sum = None
        best_3_round = None
        best_3_start = None
        for i in range(len(pilot_laps_sorted) - 2):
            a, b, c = pilot_laps_sorted.loc[i:i+2, "lap_time_sec"]
            s = a + b + c
            if best_3_sum is None or s < best_3_sum:
                best_3_sum = s
                race_id_3 = pilot_laps_sorted.loc[i, "race_id"]
                best_3_round = races_meta.loc[races_meta["race_id"] == race_id_3, "round_id"].values[0]
                best_3_start = pilot_laps_sorted.loc[i, "lap_order"] + 1

        total_laps = len(pilot_laps)
        total_rounds = races[races["pilot_id"] == pid]["race_id"].nunique()
        avg_lap = pilot_laps["lap_time_sec"].mean()
        stability = round(best_lap / avg_lap, 3) if avg_lap else None

        results.append({
            "pilot_id": pid,
            "pilot_name": pname,
            "group_name": group,
            "best_lap": best_lap,
            "best_lap_race_id": best_lap_round,
            "best_lap_order": best_lap_order,
            "best_3_laps": best_3_sum,
            "best_3_race_id": best_3_round,
            "best_3_start_order": best_3_start,
            "total_laps": total_laps,
            "total_rounds": total_rounds,
            "stability": stability,
        })

    df = pd.DataFrame(results)

    # Подсчёт очков по группам
    scored = []
    for group, group_df in df.groupby("group_name"):
        g = group_df.copy()
        min_best = g["best_lap"].min()
        min_3 = g["best_3_laps"].min()
        max_laps = g["total_laps"].max()

        g["score_best"] = g["best_lap"].apply(lambda x: score_from_gap((x / min_best) - 1))
        g["score_3laps"] = g["best_3_laps"].apply(lambda x: score_from_gap((x / min_3) - 1))
        g["score_total_laps"] = g["total_laps"].apply(lambda x: score_from_gap(1 - (x / max_laps)))

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

    # Сопоставление с user_id
    users = pd.read_sql("SELECT user_id, nickname AS OSD FROM users", bot_db)
    def match_osd(name):
        match = difflib.get_close_matches(name.lower(), users["OSD"].str.lower(), n=1, cutoff=0.8)
        if match:
            return users.loc[users["OSD"].str.lower() == match[0], "user_id"].values[0]
        return None

    df_scores["user_id"] = df_scores["pilot_name"].apply(match_osd)

    # Финалы
    final_results = []
    finals_df = pilot_data[pilot_data["note"].isin(["Группа 3", "Группа 4"])]
    if not finals_df.empty:
        base_groups = df_scores[["pilot_name", "group_name"]]
        mapping = {}
        for fin_group in ["Группа 3", "Группа 4"]:
            pilots_in_final = set(pilot_data[pilot_data["note"] == fin_group]["name"])
            overlap = {
                group: len(pilots_in_final & set(base_groups[base_groups["group_name"] == group]["pilot_name"]))
                for group in base_groups["group_name"].unique()
            }
            assigned = max(overlap.items(), key=lambda x: x[1])[0] if overlap else "Неизвестно"
            mapping[fin_group] = assigned

        for fin_group, actual_group in mapping.items():
            final_pilots = pilot_data[pilot_data["note"] == fin_group]
            pilot_ids = final_pilots["id"].tolist()
            pilot_names = final_pilots.set_index("id")["name"].to_dict()

            # Получим race_id, которые принадлежат только heat'ам финалов (Группа 3/4)
            final_heat_ids = heats[heats["note"] == fin_group]["id"].tolist()
            final_race_ids = (
                pd.read_sql("SELECT id, heat_id FROM saved_race_meta", rh)
                .query("heat_id in @final_heat_ids")["id"].tolist()
            )

            fin_laps = laps[
                (laps["pilot_id"].isin(pilot_ids)) &
                (laps["race_id"].isin(final_race_ids))
            ].copy()
            race_results = []
            for race_id, group_laps in fin_laps.groupby("race_id"):
                race_rows = []
                for pid, plaps in group_laps.groupby("pilot_id"):
                    plaps_sorted = plaps.sort_values("lap_order")
                    if len(plaps_sorted) < 3:
                        continue
                    first3 = plaps_sorted.iloc[:3]
                    time_to_3 = first3["lap_time_sec"].sum()
                    race_rows.append((pid, time_to_3))
                race_rows.sort(key=lambda x: x[1])
                for pos, (pid, _) in enumerate(race_rows):
                    race_results.append({
                        "pilot_id": pid,
                        "pilot_name": pilot_names[pid],
                        "group_name": actual_group,
                        "score_final": pos + 1
                    })

            if race_results:
                df_final = pd.DataFrame(race_results)
                df_final = df_final.groupby(["pilot_id", "pilot_name", "group_name"]).agg({
                    "score_final": "sum"
                }).reset_index()
                df_final["score_final_total"] = df_final["score_final"]
                final_results.append(df_final)

    if final_results:
        df_final_total = pd.concat(final_results)
        df_scores = df_scores.merge(
            df_final_total[["pilot_id", "group_name", "score_final_total"]],
            on=["pilot_id", "group_name"], how="left"
        )

    # Сохраняем
    for _, row in df_scores.iterrows():
        cursor = bot_db.cursor()
        cursor.execute("""
            INSERT INTO training_scores (
                training_date, user_id, pilot_name, group_name,
                best_lap, best_lap_race_id, best_lap_order,
                best_3_laps, best_3_race_id, best_3_start_order,
                total_laps, total_rounds, stability,
                score_best, score_3laps, score_total_laps,
                score_participation, score_dominance, score_total, score_final_total
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            training_date,
            row["user_id"],
            row["pilot_name"],
            row["group_name"],
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
            row.get("score_final_total"),
        ))
        bot_db.commit()