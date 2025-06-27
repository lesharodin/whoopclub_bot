import sqlite3
import os

DB_PATH = "database/bot.db"

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    os.makedirs("database", exist_ok=True)
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                nickname TEXT NOT NULL,
                system TEXT NOT NULL,
                subscription INTEGER DEFAULT 0       
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trainings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                status TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subscription_notifications (
                subscription_id INTEGER,
                admin_id INTEGER,
                message_id INTEGER
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_notifications (
                slot_id INTEGER,
                admin_id INTEGER,
                message_id INTEGER
            );
        """)        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                training_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                group_name TEXT NOT NULL,
                channel TEXT NOT NULL,
                payment_type TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (training_id) REFERENCES trainings(id)
            )
                       
        """)
        cursor.execute("""
             CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                count INTEGER,
                status TEXT,
                created_at TEXT
    )
""")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS training_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                training_date TEXT NOT NULL,
                user_id INTEGER,
                pilot_name TEXT NOT NULL,
                group_name TEXT,

                best_lap REAL,
                best_lap_race_id INTEGER,
                best_lap_order INTEGER,

                best_3_laps REAL,
                best_3_race_id INTEGER,
                best_3_start_order INTEGER,

                total_laps INTEGER,
                total_rounds INTEGER,
                stability REAL,

                score_best INTEGER,
                score_3laps INTEGER,
                score_total_laps INTEGER,
                score_participation INTEGER,
                score_dominance INTEGER,
                score_total INTEGER,
                score_final_total INTEGER,

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)


    print("✅ Таблицы users, trainings и slots, subscription_usage созданы (если не существовали)")
