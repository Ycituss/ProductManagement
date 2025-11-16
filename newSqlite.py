import sqlite3

# 创建数据库连接（如果文件不存在，会自动创建）
conn = sqlite3.connect('ecommerce.db')
cursor = conn.cursor()

# 执行所有创建表的SQL语句
sql_statements = [
    """CREATE TABLE users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        is_admin BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE permission_groups (
        group_id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_name TEXT NOT NULL UNIQUE,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE user_groups (
        user_id INTEGER,
        group_id INTEGER,
        PRIMARY KEY (user_id, group_id),
        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
        FOREIGN KEY (group_id) REFERENCES permission_groups(group_id) ON DELETE CASCADE
    )""",

    """CREATE TABLE products (
        uid TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        short_name TEXT,
        sku TEXT NOT NULL,
        cost REAL NOT NULL,
        developer_id INTEGER NOT NULL,
        category TEXT NOT NULL,
        permission_group_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (developer_id) REFERENCES users(user_id),
        FOREIGN KEY (permission_group_id) REFERENCES permission_groups(group_id)
    )""",

    """CREATE TABLE product_aliases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_uid TEXT NOT NULL,
        alias TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (product_uid) REFERENCES products(uid) ON DELETE CASCADE
    )""",

    """CREATE TABLE product_3D_weight (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_uid TEXT NOT NULL,
        danse REAL,
        duose REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (product_uid) REFERENCES products(uid) ON DELETE CASCADE
    )""",

    """CREATE TABLE product_images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_uid TEXT NOT NULL,
        image_url TEXT NOT NULL,
        is_local BOOLEAN DEFAULT 1,
        is_deleted BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (product_uid) REFERENCES products(uid) ON DELETE CASCADE
    )""",

    """CREATE TABLE product_images_cos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        image_id TEXT NOT NULL,
        image_url TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (image_id) REFERENCES product_images(id) ON DELETE CASCADE
    )""",

    """CREATE TABLE product_file (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_uid TEXT NOT NULL,
        file_url TEXT NOT NULL,
        original_filename TEXT NOT NULL,
        is_deleted BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (product_uid) REFERENCES products(uid) ON DELETE CASCADE
    )""",

    """CREATE TABLE product_file_cos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_id TEXT NOT NULL,
        file_url TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (file_id) REFERENCES product_file(id) ON DELETE CASCADE
    )""",

    """CREATE TABLE product_packages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_uid TEXT NOT NULL,
        length REAL,
        width REAL,
        height REAL,
        weight REAL,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (product_uid) REFERENCES products(uid) ON DELETE CASCADE
    )""",

    """CREATE TABLE product_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_uid TEXT NOT NULL,
        platform TEXT NOT NULL,
        shop TEXT NOT NULL,
        listing_time TIMESTAMP NOT NULL,
        title TEXT NOT NULL,
        link_type TEXT NOT NULL,
        price_type TEXT CHECK(price_type IN ('supply', 'sale')) NOT NULL,
        price REAL NOT NULL,
        platform_skc TEXT,
        listed_by INTEGER NOT NULL,
        is_deleted BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (product_uid) REFERENCES products(uid) ON DELETE CASCADE,
        FOREIGN KEY (listed_by) REFERENCES users(user_id)
    )"""
]

# 执行所有SQL语句
for statement in sql_statements:
    cursor.execute(statement)

# 提交更改并关闭连接
conn.commit()
conn.close()

print("数据库已成功创建为 ecommerce.db 文件")