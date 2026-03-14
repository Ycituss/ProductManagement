import sqlite3
from werkzeug.security import generate_password_hash


def add_cost_config_table():
    conn = sqlite3.connect('ecommerce.db')
    cursor = conn.cursor()

    try:
        # 检查表是否已存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cost_config'")
        if cursor.fetchone():
            print("cost_config 表已存在，无需创建")
            return

        # 创建 cost_config 表
        cursor.execute('''
            CREATE TABLE cost_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_code TEXT NOT NULL UNIQUE,
                danse_unit_cost REAL NOT NULL DEFAULT 0.12,
                duose_unit_cost REAL NOT NULL DEFAULT 0.13,
                description TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER,
                FOREIGN KEY (created_by) REFERENCES users(user_id)
            )
        ''')

        # 获取 admin 用户的 user_id
        cursor.execute("SELECT user_id FROM users WHERE username = 'admin'")
        admin = cursor.fetchone()
        admin_id = admin[0] if admin else 1

        # 插入默认配置
        cursor.execute('''
            INSERT INTO cost_config (config_code, danse_unit_cost, duose_unit_cost, description, created_by)
            VALUES (?, ?, ?, ?, ?)
        ''', ('250213', 0.12, 0.13, '系统初始默认成本配置', admin_id))

        conn.commit()
        print("✓ cost_config 表创建成功！")

    except Exception as e:
        conn.rollback()
        print(f"✗ 创建表失败：{str(e)}")

    finally:
        conn.close()


if __name__ == '__main__':
    add_cost_config_table()