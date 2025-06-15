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


    print("✅ Таблицы users, trainings и slots, subscription_usage созданы (если не существовали)")
