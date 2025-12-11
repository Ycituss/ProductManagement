import io
import os
import re
import shutil
import tempfile
import uuid
import time
import zipfile
from io import BytesIO
from pathlib import Path
import random
import openpyxl
import pandas as pd


from apscheduler.schedulers.background import BackgroundScheduler
import pytz
from werkzeug.datastructures import FileStorage

import tencent_cos
import excel_export

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, abort, \
    send_from_directory, send_file, render_template_string
import sqlite3
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timezone, timedelta
from pypinyin import lazy_pinyin


app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # 请更改为安全的随机密钥，建议使用环境变量

# Base62字符集（0-9, a-z, A-Z）
BASE62 = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

# 配置上传文件夹
UPLOAD_FOLDER = 'static/uploads'
UPLOAD_FOLDER_3MF = 'static/uploads/3mf'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', '3mf', 'stl'}
ALLOWED_EXTENSIONS_3MF = {'3mf', 'stl'} # 允许的文件扩展名
ALLOWED_EXTENSIONS_EXCEL = {'xlsx', 'xls'} # 允许的文件扩展名
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['UPLOAD_FOLDER_3MF'] = UPLOAD_FOLDER_3MF
# 确保上传文件夹存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(UPLOAD_FOLDER_3MF, exist_ok=True)


# 数据库初始化函数
def init_database():
    conn = sqlite3.connect('ecommerce.db')
    cursor = conn.cursor()

    # 检查用户表是否存在
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    if not cursor.fetchone():
        # 如果表不存在，执行创建表的SQL语句
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

        for statement in sql_statements:
            cursor.execute(statement)

        # 创建默认管理员账户和权限组
        admin_password = generate_password_hash('admin250213.')
        cursor.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, 1)",
                       ('admin', admin_password))

        # 创建默认权限组
        cursor.execute("INSERT INTO permission_groups (group_name, description) VALUES (?, ?)",
                       ('仅自己可查看', '仅自己拥有产品查看权限'))
        cursor.execute("INSERT INTO permission_groups (group_name, description) VALUES (?, ?)",
                       ('所有人可查看', '所有人都可以查看自己开发的产品'))

        conn.commit()

    conn.close()


# 数据库连接辅助函数
def get_db_connection():
    conn = sqlite3.connect('ecommerce.db')
    conn.row_factory = sqlite3.Row
    return conn


# 检查文件扩展名是否允许
def allowed_file(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_file_3mf(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS_3MF

def allowed_file_excel(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS_EXCEL


# 生成基于时间戳和UUID的唯一标识符
def base62_encode(num):
    """将整数编码为Base62字符串"""
    if num == 0:
        return BASE62[0]

    arr = []
    base = 62
    while num:
        num, rem = divmod(num, base)
        arr.append(BASE62[rem])

    # 反转数组并连接成字符串
    return ''.join(arr[::-1])


def generate_product_uid():
    """生成11字符的唯一产品标识符：P + 4字符Base62时间戳 + 6字符随机字符串"""
    # 获取当前时间戳并编码为Base62（4字符）
    timestamp = int(time.time())
    ts_encoded = base62_encode(timestamp)

    # 确保时间戳编码为4字符（不足时填充）
    ts_part = ts_encoded.zfill(4)[-4:]

    # 生成6字符随机字符串
    random_part = ''.join(random.choices(BASE62, k=6))

    # 组合成最终标识符
    return f"P{ts_part}{random_part}"

# ===== 备份数据库函数 =====
def backup_database():
    # 数据库文件路径（确保和您的项目一致）
    DB_FILE = 'ecommerce.db'             # 当前目录下的数据库文件
    BACKUP_DIR = 'backups'               # 备份存放的文件夹

    # 检查数据库文件是否存在
    if not os.path.exists(DB_FILE):
        print(f"[错误] 数据库文件 '{DB_FILE}' 不存在！")
        return False, f"数据库文件 '{DB_FILE}' 不存在！"

    # 如果备份文件夹不存在，则创建
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        print(f"[信息] 创建备份文件夹：{BACKUP_DIR}")

    # 生成带时间戳的备份文件名
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_filename = f"ecommerce_{timestamp}.db"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)
    backup_path_cos = 'backup/' + backup_filename

    try:
        # 执行文件复制（备份）
        shutil.copy2(DB_FILE, backup_path)
        tencent_cos.upload_to_cos(backup_path, backup_path_cos)
        print(f"[成功] 数据库已备份到：{backup_path}")
        return True, f"数据库已备份到：{backup_path}"
    except Exception as e:
        print(f"[错误] 备份失败：{e}")
        return False, f"备份失败：{e}"

# 定时备份数据库
def start_scheduler():
    # 创建后台调度器
    scheduler = BackgroundScheduler(timezone=pytz.timezone('Asia/Shanghai'))  # 北京时间

    # 添加定时任务：每天 20:00 执行 backup_database
    scheduler.add_job(
        backup_database,
        'cron',
        hour=20,
        minute=0,
        timezone='Asia/Shanghai'
    )

    # 启动调度器
    scheduler.start()
    print("定时任务已启动：每天北京时间 20:00 执行数据库备份")


# 登录检查装饰器
def login_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    decorated_function.__name__ = f.__name__
    return decorated_function


# 管理员检查装饰器
def admin_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not session.get('is_admin', False):
            flash('需要管理员权限', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)

    decorated_function.__name__ = f.__name__
    return decorated_function


# 用户权限检查装饰器 - 确保用户拥有该产品
def user_owns_product(f):
    def decorated_function(uid, *args, **kwargs):
        if 'user_id' not in session:
            abort(403)

        conn = get_db_connection()
        product = conn.execute('SELECT developer_id FROM products WHERE uid = ?', (uid,)).fetchone()
        conn.close()

        if not product:
            abort(404)

        if not session.get('is_admin') and product['developer_id'] != session['user_id']:
            abort(403)

        return f(uid, *args, **kwargs)

    decorated_function.__name__ = f.__name__
    return decorated_function

# 用户权限检查装饰器 - 确保用户拥有该链接
def user_owns_link(f):
    def decorated_function(link_id, *args, **kwargs):
        if 'user_id' not in session:
            abort(403)

        conn = get_db_connection()
        link = conn.execute('SELECT listed_by FROM product_links WHERE id = ? AND is_deleted = 0', (link_id,)).fetchone()
        conn.close()

        if not link:
            abort(404)

        if not session.get('is_admin') and link['listed_by'] != session['username']:
            abort(403)

        return f(link_id, *args, **kwargs)

    decorated_function.__name__ = f.__name__
    return decorated_function

# 路由定义
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['user_id']
            session['username'] = user['username']
            session['is_admin'] = bool(user['is_admin'])

            # 获取用户权限组
            conn = get_db_connection()
            groups = conn.execute('''
                SELECT pg.group_name 
                FROM permission_groups pg
                JOIN user_groups ug ON pg.group_id = ug.group_id
                WHERE ug.user_id = ?
            ''', (session['user_id'],)).fetchall()
            conn.close()

            session['groups'] = [group['group_name'] for group in groups]

            flash('登录成功！', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('用户名或密码错误！', 'error')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('已退出登录', 'info')
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()

    # 获取基本统计信息
    total_products = conn.execute('SELECT COUNT(*) as count FROM products').fetchone()['count']
    recent_products = conn.execute('''
        SELECT * FROM products 
        ORDER BY created_at DESC 
        LIMIT 5
    ''').fetchall()

    # 根据用户权限获取可查看的产品
    if session.get('is_admin'):
        user_products = conn.execute('SELECT * FROM products ORDER BY created_at DESC').fetchall()
    elif '开发者' in session.get('groups', []):
        user_products = conn.execute('''
            SELECT p.* FROM products p
            WHERE p.developer_id = ?
            ORDER BY p.created_at DESC
        ''', (session['user_id'],)).fetchall()
    else:
        # 普通用户只能查看公开产品或自己有权限的产品
        user_products = conn.execute('SELECT * FROM products ORDER BY created_at DESC LIMIT 10').fetchall()

    conn.close()

    return render_template('dashboard.html',
                           total_products=total_products,
                           recent_products=recent_products,
                           user_products=user_products)


@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        if new_password != confirm_password:
            flash('新密码和确认密码不匹配！', 'error')
        else:
            conn = get_db_connection()
            user = conn.execute('SELECT * FROM users WHERE user_id = ?', (session['user_id'],)).fetchone()
            conn.close()

            if user and check_password_hash(user['password'], current_password):
                new_password_hash = generate_password_hash(new_password)
                conn = get_db_connection()
                conn.execute('UPDATE users SET password = ? WHERE user_id = ?',
                             (new_password_hash, session['user_id']))
                conn.commit()
                conn.close()

                flash('密码修改成功！', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('当前密码错误！', 'error')

    return render_template('change_password.html')


@app.route('/add_user', methods=['GET', 'POST'])
@admin_required
def add_user():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        is_admin = 'is_admin' in request.form

        # 检查用户名是否已存在
        conn = get_db_connection()
        existing_user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if existing_user:
            flash('用户名已存在！', 'error')
            conn.close()
        else:
            password_hash = generate_password_hash(password)
            conn.execute('INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)',
                         (username, password_hash, 1 if is_admin else 0))
            conn.commit()
            conn.close()

            flash('用户添加成功！', 'success')
            return redirect(url_for('admin_panel'))

    return render_template('add_user.html')


@app.route('/products')
@login_required
def products():
    conn = get_db_connection()
    search_term = request.args.get('search', '')
    category = request.args.get('category', '')
    page = request.args.get('page', 1, type=int)
    per_page = 30  # 每页显示6个产品卡片

    # 构建 COUNT 查询（仅统计产品，无需关联 users 表）
    count_query = '''
        SELECT COUNT(*) as total
        FROM products p
        WHERE 1=1
    '''
    count_params = []

    if search_term:
        count_query += ' AND (p.name LIKE ? OR p.short_name LIKE ? OR p.sku LIKE ?)'
        count_params.extend([f'%{search_term}%', f'%{search_term}%', f'%{search_term}%'])

    if category:
        count_query += ' AND p.category = ?'
        count_params.append(category)

    if not session.get('is_admin'):
        if '开发者' in session.get('groups', []):
            count_query += ' AND p.developer_id = ?'
            count_params.append(session['user_id'])
        else:
            # 普通用户默认只能查看部分产品，这里假设可以查看所有产品
            pass

    # 计算总数
    total_products = conn.execute(count_query, count_params).fetchone()['total']

    # 构建主查询
    query = '''
        SELECT p.*, u.username AS developer_username
        FROM products p
        LEFT JOIN users u ON p.developer_id = u.user_id
        WHERE 1=1
    '''
    params = []

    if search_term:
        query += ' AND (p.name LIKE ? OR p.short_name LIKE ? OR p.sku LIKE ?)'
        params.extend([f'%{search_term}%', f'%{search_term}%', f'%{search_term}%'])

    if category:
        query += ' AND p.category = ?'
        params.append(category)

    if not session.get('is_admin'):
        query += ' AND (p.developer_id = ? OR p.permission_group_id = ?)'
        params.extend([session['user_id'], 2])

    query += ' ORDER BY p.created_at DESC'

    # 分页
    offset = (page - 1) * per_page
    products_query = f"{query} LIMIT ? OFFSET ?"
    # products = conn.execute(products_query, params + [per_page, offset]).fetchall()

    # 获取所有分类
    categories = conn.execute('SELECT DISTINCT category FROM products').fetchall()

    # 获取查询结果后，转换为普通字典列表
    products = []
    raw_products = conn.execute(products_query, params + [per_page, offset]).fetchall()
    for row in raw_products:
        product = dict(row)  # 转换为字典（可修改）

        # 时间转换逻辑（添加到字典中）
        if isinstance(product['created_at'], str):
            naive_created_at = datetime.strptime(product['created_at'], '%Y-%m-%d %H:%M:%S')
            utc_time = naive_created_at.replace(tzinfo=timezone.utc)
            product['created_at'] = utc_time.astimezone(timezone(timedelta(hours=8)))

        if isinstance(product['updated_at'], str):
            naive_updated_at = datetime.strptime(product['updated_at'], '%Y-%m-%d %H:%M:%S')
            utc_time = naive_updated_at.replace(tzinfo=timezone.utc)
            product['updated_at'] = utc_time.astimezone(timezone(timedelta(hours=8)))

        products.append(product)  # 添加到列表
    # 组织产品及其图片
    products_with_images = []
    for product in products:
        # 获取该产品的所有图片
        product_images = conn.execute('''
            SELECT * FROM product_images 
            WHERE product_uid = ? AND is_deleted = 0
            ORDER BY created_at ASC
        ''', (product['uid'],)).fetchall()
        products_with_images.append({
            'product': product,
            'images': product_images
        })

    products_with_packages = []
    for product in products:
        product_packages = conn.execute('''
            SELECT * FROM product_packages 
            WHERE product_uid = ? 
            ORDER BY created_at ASC
        ''', (product['uid'],)).fetchall()
        products_with_packages.append({
            'product': product,
            'packages': product_packages
        })

    user_list = conn.execute('SELECT * FROM users ORDER BY user_id').fetchall()

    permission_list = conn.execute('SELECT * FROM permission_groups ORDER BY group_id').fetchall()

    product_3D_weight = conn.execute('SELECT * FROM product_3D_weight').fetchall()

    products_with_files = conn.execute('SELECT * FROM product_file WHERE is_deleted = 0').fetchall()

    product_with_links = conn.execute('SELECT * FROM product_links WHERE is_deleted = 0').fetchall()
    # 统计链接数量
    product_link_count = {}
    for link in product_with_links:
        uid = link['product_uid']
        if uid in product_link_count:
            product_link_count[uid] += 1
        else:
            product_link_count[uid] = 1

    conn.close()

    # 计算总页数
    total_pages = (total_products + per_page - 1) // per_page

    current_time = datetime.now().strftime('%Y-%m-%dT%H:%M')  # 格式必须为 2024-11-11T15:15

    return render_template('products.html',
                           products=products,
                           products_with_images=products_with_images,
                           products_with_files=products_with_files,
                           products_with_packages=products_with_packages,
                           product_3D_weight=product_3D_weight,
                           product_link_count = product_link_count,
                           user_list = user_list,
                           permission_list = permission_list,
                           search_term=search_term,
                           category=category,
                           categories=[cat['category'] for cat in categories],
                           page=page,
                           per_page=per_page,
                           total_pages=total_pages,
                           total_products=total_products,
                           current_time=current_time)


@app.route('/add_product', methods=['GET', 'POST'])
@login_required
def add_product():
    if request.method == 'POST':
        # 自动生成唯一标识符
        uid = generate_product_uid()

        name = request.form['name']
        short_name = request.form.get('short_name', '')
        # sku = request.form['sku']
        sku = uid
        cost = float(request.form['cost'])
        developer_id = session['user_id']
        category = request.form['category']
        permission_group_id = request.form.get('permission_group_id')
        duose = request.form.get('duose')
        danse = request.form.get('danse')

        # 检查SKU是否已存在
        conn = get_db_connection()
        existing_sku = conn.execute('SELECT * FROM products WHERE sku = ?', (sku,)).fetchone()
        if existing_sku:
            flash('SKU已存在！请使用不同的SKU。', 'error')
            conn.close()
        else:
            try:
                # 插入产品信息
                conn.execute('''
                    INSERT INTO products (uid, name, short_name, sku, cost, developer_id, category, permission_group_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (uid, name, short_name, sku, cost, developer_id, category, permission_group_id))
                conn.commit()

                # 插入3D重量信息
                conn.execute('''
                                    INSERT INTO product_3D_weight (product_uid, danse, duose)
                                    VALUES (?, ?, ?)
                                ''', (uid, danse, duose))
                conn.commit()

                # 处理图片上传
                if 'images' in request.files:
                    files = request.files.getlist('images')
                    for file in files:
                        if file and file.filename != '' and allowed_file(file.filename):
                            filename = f"{os.path.splitext(file.filename)[1].lower()}"
                            unique_filename = f"{uuid.uuid4()}{filename}"  # 生成唯一文件名
                            file_dir = os.path.join(app.config['UPLOAD_FOLDER'], uid)
                            os.makedirs(file_dir, exist_ok=True)  # 创建目录（如果不存在）

                            # 保存文件
                            filepath = os.path.join(file_dir, unique_filename)
                            # filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                            file.save(filepath)
                            print(f"Saved new image to: {filepath}")  # 调试信息

                            # 构建相对路径（如 uploads/UUID_原文件名.png）
                            relative_path = unique_filename

                            # 将图片信息保存到 product_images 表中
                            conn.execute('''
                                INSERT INTO product_images (product_uid, image_url, is_local)
                                VALUES (?, ?, 1)
                            ''', (uid, relative_path))
                            conn.commit()
                            file_id = conn.execute('''
                                SELECT id 
                                FROM product_images
                                WHERE image_url = ?
                            ''', (relative_path,)).fetchone()
                            image_path_cos = 'image/' + name + '/' + name + str(
                                file_id['id']) + Path(
                                relative_path).suffix.lower()
                            image_path_url = tencent_cos.upload_to_cos(filepath, image_path_cos)

                            conn.execute('''
                                            INSERT INTO product_images_cos (image_id, image_url)
                                            VALUES (?, ?)
                                        ''', (file_id['id'], image_path_url))
                            conn.commit()

                            print(f"Added new image to product_uid: {uid}")  # 调试信息

                conn.close()

                flash('产品添加成功！', 'success')
                return redirect(url_for('products'))
            except Exception as e:
                conn.close()
                flash(f'添加产品时出错：{str(e)}', 'error')

    # 获取权限组列表（用于下拉选择）
    conn = get_db_connection()
    permission_groups = conn.execute('SELECT * FROM permission_groups').fetchall()
    product_3D_weight = conn.execute('SELECT * FROM product_3D_weight').fetchall()
    conn.close()

    return render_template('add_product.html',
                           permission_groups = permission_groups,
                           product_3D_weight = product_3D_weight)


@app.route('/edit_product/<uid>', methods=['GET', 'POST'])
@login_required
@user_owns_product
def edit_product(uid):
    conn = get_db_connection()
    product = conn.execute('SELECT * FROM products WHERE uid = ?', (uid,)).fetchone()
    if not product:
        conn.close()
        flash('产品不存在！', 'error')
        return redirect(url_for('products'))

    if request.method == 'POST':
        name = request.form['name']
        short_name = request.form.get('short_name', '')
        sku = request.form['sku']
        cost = float(request.form['cost'])
        category = request.form['category']
        permission_group_id = request.form.get('permission_group_id')
        duose = request.form.get('duose')
        danse = request.form.get('danse')

        # 检查SKU是否与其他产品冲突
        existing_sku = conn.execute('SELECT * FROM products WHERE sku = ? AND uid != ?', (sku, uid)).fetchone()
        if existing_sku:
            flash('SKU已存在！请使用不同的SKU。', 'error')
            conn.close()
        else:
            conn.execute('''
                UPDATE products 
                SET name = ?, short_name = ?, sku = ?, cost = ?, category = ?, permission_group_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE uid = ?
            ''', (name, short_name, sku, cost, category, permission_group_id, uid))
            conn.commit()

            # 查询是否存在记录
            existing = conn.execute('''
                SELECT 1 FROM product_3D_weight 
                WHERE product_uid = ?
            ''', (uid,)).fetchone()

            if existing:
                # 更新
                conn.execute('''
                    UPDATE product_3D_weight 
                    SET danse = ?, duose = ?
                    WHERE product_uid = ?
                ''', (danse, duose, uid))
            else:
                # 插入
                conn.execute('''
                    INSERT INTO product_3D_weight (product_uid, danse, duose)
                    VALUES (?, ?, ?)
                ''', (uid, danse, duose))
            conn.commit()

            # 处理图片上传
            if 'images' in request.files:
                files = request.files.getlist('images')
                for file in files:
                    if file and file.filename != '' and allowed_file(file.filename):
                        filename = f"{os.path.splitext(file.filename)[1].lower()}"
                        unique_filename = f"{uuid.uuid4()}{filename}"  # 生成唯一文件名
                        file_dir = os.path.join(app.config['UPLOAD_FOLDER'], product['uid'])
                        os.makedirs(file_dir, exist_ok=True)  # 创建目录（如果不存在）

                        # 保存文件
                        filepath = os.path.join(file_dir, unique_filename)
                        # filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                        file.save(filepath)
                        print(f"Saved new image to: {filepath}")  # 调试信息

                        # 构建相对路径（如 uploads/UUID_原文件名.png）
                        relative_path = unique_filename

                        # 将图片信息保存到 product_images 表中
                        conn.execute('''
                            INSERT INTO product_images (product_uid, image_url, is_local)
                            VALUES (?, ?, 1)
                        ''', (uid, relative_path))
                        conn.commit()
                        file_id = conn.execute('''
                            SELECT id 
                            FROM product_images
                            WHERE image_url = ?
                        ''', (relative_path,)).fetchone()
                        image_path_cos = 'image/' + product['name'] + '/' + product['name'] + str(file_id['id']) + Path(
                            relative_path).suffix.lower()
                        image_path_url = tencent_cos.upload_to_cos(filepath, image_path_cos)

                        conn.execute('''
                                        INSERT INTO product_images_cos (image_id, image_url)
                                        VALUES (?, ?)
                                    ''', (file_id['id'], image_path_url))
                        conn.commit()

                        print(f"Added new image to product_uid: {uid}")  # 调试信息

            conn.close()

            flash('产品修改成功！', 'success')
            return redirect(url_for('products'))

    # 获取权限组列表
    permission_groups = conn.execute('SELECT * FROM permission_groups').fetchall()
    product_3D_weight = conn.execute('SELECT * FROM product_3D_weight').fetchall()
    conn.close()

    return render_template('edit_product.html',
                           product=product,
                           permission_groups=permission_groups,
                           product_3D_weight=product_3D_weight)


@app.route('/delete_product/<uid>', methods=['GET', 'POST'])
@login_required
@user_owns_product
def delete_product(uid):
    if request.method == 'POST':
        conn = get_db_connection()
        conn.execute('DELETE FROM products WHERE uid = ?', (uid,))
        conn.commit()
        conn.close()

        flash('产品删除成功！', 'success')
        return redirect(url_for('products'))

    # 获取产品信息用于确认删除
    conn = get_db_connection()
    product = conn.execute('SELECT * FROM products WHERE uid = ?', (uid,)).fetchone()
    conn.close()

    if not product:
        flash('产品不存在！', 'error')
        return redirect(url_for('products'))

    return render_template('confirm_delete.html', product=product)


@app.route('/api/product/<uid>')
@login_required
def get_product_details(uid):
    conn = get_db_connection()

    # 检查产品访问权限
    product = conn.execute('SELECT * FROM products WHERE uid = ?', (uid,)).fetchone()

    if not product:
        conn.close()
        return jsonify({'error': '产品不存在'}), 404

    # 权限检查
    if not session.get('is_admin'):
        if '开发者' in session.get('groups', []):
            if product['developer_id'] != session['user_id']:
                conn.close()
                return jsonify({'error': '无权访问此产品'}), 403
        else:
            # 普通用户权限检查
            pass

    # 获取相关数据
    aliases = conn.execute('SELECT * FROM product_aliases WHERE product_uid = ?', (uid,)).fetchall()
    images = conn.execute('SELECT * FROM product_images WHERE product_uid = ? AND is_deleted = 0', (uid,)).fetchall()
    packages = conn.execute('SELECT * FROM product_packages WHERE product_uid = ?', (uid,)).fetchall()
    links = conn.execute('''
        SELECT pl.*, u.username as listed_by_name 
        FROM product_links pl
        LEFT JOIN users u ON pl.listed_by = u.user_id
        WHERE pl.product_uid = ? AND is_deleted = 0
        ORDER BY pl.created_at DESC
    ''', (uid,)).fetchall()

    product_data = dict(product)
    product_data['aliases'] = [dict(alias) for alias in aliases]
    product_data['images'] = [dict(image) for image in images]
    product_data['packages'] = [dict(pkg) for pkg in packages]
    product_data['links'] = [dict(link) for link in links]

    conn.close()

    return jsonify(product_data)


@app.route('/admin')
@login_required
@admin_required
def admin_panel():
    conn = get_db_connection()

    # 获取所有用户
    users = conn.execute('''
        SELECT u.*, CASE WHEN u.is_admin THEN '是' ELSE '否' END as is_admin_text
        FROM users u
        ORDER BY u.created_at DESC
    ''').fetchall()

    # 获取所有权限组
    groups = conn.execute('SELECT * FROM permission_groups ORDER BY group_name').fetchall()

    # 获取用户组关联
    user_groups_data = conn.execute('''
        SELECT ug.user_id, u.username, pg.group_id, pg.group_name
        FROM user_groups ug
        JOIN users u ON ug.user_id = u.user_id
        JOIN permission_groups pg ON ug.group_id = pg.group_id
        ORDER BY u.username, pg.group_name
    ''').fetchall()

    conn.close()

    return render_template('admin.html',
                           users=users,
                           groups=groups,
                           user_groups_data=user_groups_data)


# 静态文件访问，例如上传的图片
@app.route('/uploads/<product_uid>/<filename>')
def uploaded_file(filename, product_uid):
    file_dir = os.path.join(app.config['UPLOAD_FOLDER'], product_uid)
    return send_from_directory(file_dir, filename)


@app.route('/delete_image/<int:image_id>', methods=['POST'])
@login_required
def delete_image(image_id):
    conn = get_db_connection()

    # 获取要删除的图片记录
    image = conn.execute('''
        SELECT * FROM product_images WHERE id = ?
    ''', (image_id,)).fetchone()

    if not image:
        conn.close()
        return jsonify({'error': '图片不存在！'}), 404  # 返回 JSON 格式的错误信息

    # 获取图片的相对路径
    image_url = image['image_url']

    # 删除服务器上的物理图片文件
    # try:
    #     file_path = os.path.join(app.config['UPLOAD_FOLDER'], image['product_uid'], image_url.split('/')[-1])
    #     if os.path.exists(file_path):
    #         os.remove(file_path)
    #         print(f"Deleted image file: {file_path}")  # 调试信息
    # except Exception as e:
    #     print(f"Error deleting image file: {e}")  # 调试信息

    # 从数据库中删除图片记录
    conn.execute('''
        UPDATE product_images SET is_deleted = 1 WHERE id = ?
    ''', (image_id,))
    conn.commit()
    conn.close()

    # 返回 JSON 格式的成功信息
    return jsonify({'success': '图片已成功删除！'})

@app.route('/delete_file/<int:file_id>', methods=['POST'])
@login_required
def delete_file(file_id):
    conn = get_db_connection()

    # 获取要删除的图片记录
    file = conn.execute('''
        SELECT * FROM product_file WHERE id = ? AND is_deleted = 0
    ''', (file_id,)).fetchone()

    if not file:
        conn.close()
        return jsonify({'error': '文件不存在！'}), 404  # 返回 JSON 格式的错误信息

    # 获取图片的相对路径
    file_url = file['file_url']

    # 删除服务器上的物理图片文件
    # try:
    #     file_path = os.path.join(app.config['UPLOAD_FOLDER_3MF'], file_url.split('/')[-1])
    #     if os.path.exists(file_path):
    #         os.remove(file_path)
    #         print(f"Deleted file: {file_path}")  # 调试信息
    # except Exception as e:
    #     print(f"Error deleting file: {e}")  # 调试信息

    # 从数据库中删除图片记录
    conn.execute('''
        UPDATE product_file SET is_deleted = 1 WHERE id = ?
    ''', (file_id,))
    conn.commit()
    conn.close()

    # 返回 JSON 格式的成功信息
    return jsonify({'success': '文件已成功删除！'})



@app.route('/add_image/<product_uid>', methods=['POST'])
@login_required
def add_image(product_uid):
    conn = get_db_connection()

    if 'images' not in request.files:
        conn.close()
        flash('未选择任何图片！', 'error')
        return redirect(url_for('products'))

    product = conn.execute('SELECT uid, name FROM products WHERE uid = ?', (product_uid,)).fetchone()
    print(product['uid'])

    files = request.files.getlist('images')
    for file in files:
        if file and file.filename != '' and allowed_file(file.filename):
            filename = f"{os.path.splitext(file.filename)[1].lower()}"
            unique_filename = f"{uuid.uuid4()}{filename}"  # 生成唯一文件名
            file_dir = os.path.join(app.config['UPLOAD_FOLDER'], product['uid'])
            os.makedirs(file_dir, exist_ok=True)  # 创建目录（如果不存在）

            # 保存文件
            filepath = os.path.join(file_dir, unique_filename)
            # filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(filepath)
            print(f"Saved new image to: {filepath}")  # 调试信息

            # 构建相对路径（如 uploads/UUID_原文件名.png）
            relative_path = unique_filename

            # 将图片信息保存到 product_images 表中
            conn.execute('''
                INSERT INTO product_images (product_uid, image_url, is_local)
                VALUES (?, ?, 1)
            ''', (product_uid, relative_path))
            conn.commit()
            file_id = conn.execute('''
                SELECT id 
                FROM product_images
                WHERE image_url = ?
            ''', (relative_path,)).fetchone()
            image_path_cos = 'image/' + product['name'] + '/' + product['name'] + str(file_id['id']) + Path(relative_path).suffix.lower()
            image_path_url = tencent_cos.upload_to_cos(filepath, image_path_cos)

            conn.execute('''
                            INSERT INTO product_images_cos (image_id, image_url)
                            VALUES (?, ?)
                        ''', (file_id['id'], image_path_url))
            conn.commit()

            print(f"Added new image to product_uid: {product_uid}")  # 调试信息

    conn.close()
    flash('新图片已成功上传！', 'success')
    return redirect(url_for('products'))  # 或者返回到产品详情页

@app.route('/product_links')
@login_required
def product_links():
    conn = get_db_connection()

    # 获取筛选条件
    platform = request.args.get('platform', '')  # 平台
    shop = request.args.get('shop', '')          # 店铺
    start_date = request.args.get('start_date', '')  # 起始日期
    end_date = request.args.get('end_date', '')      # 结束日期
    min_price = request.args.get('min_price', '')    # 最低价格
    max_price = request.args.get('max_price', '')    # 最高价格
    listed_by = request.args.get('listed_by', '')    # 上架人
    platform_skc = request.args.get('platform_skc', '')  # 平台 SKU
    product_uid = request.args.get('product_uid', '')  # 链接绑定的产品 UID

    # 获取排序条件
    sort_field = request.args.get('sort_field', 'created_at')  # 默认按创建日期排序
    sort_order = request.args.get('sort_order', 'DESC')        # 默认按降序排序

    # 基础查询
    query = '''
        SELECT pl.*,
               p.name AS product_name,
               u.username AS listed_by_username
        FROM product_links pl
        LEFT JOIN products p ON pl.product_uid = p.uid
        LEFT JOIN users u ON pl.listed_by = u.user_id
        WHERE 1=1 AND is_deleted = 0
    '''
    params = []

    # 动态添加筛选条件
    if platform:
        query += ' AND pl.platform LIKE ?'
        params.append(f'%{platform}%')

    if shop:
        query += ' AND pl.shop LIKE ?'
        params.append(f'%{shop}%')

    if start_date:
        query += ' AND pl.listing_time >= ?'
        params.append(start_date)

    if end_date:
        query += ' AND pl.listing_time <= ?'
        params.append(end_date)

    if min_price:
        query += ' AND pl.price >= ?'
        params.append(float(min_price))

    if max_price:
        query += ' AND pl.price <= ?'
        params.append(float(max_price))

    if listed_by:
        query += ' AND pl.listed_by = ?'
        params.append(listed_by)

    if platform_skc:
        query += ' AND pl.platform_skc LIKE ?'
        params.append(f'%{platform_skc}%')

    if product_uid:
        query += ' AND pl.product_uid = ?'
        params.append(product_uid)

    # 动态添加排序条件
    query += f' ORDER BY {sort_field} {sort_order}'

    # 执行查询
    product_links_data = conn.execute(query, params).fetchall()

    conn.close()

    return render_template('product_links.html', product_links=product_links_data, session = session)

@app.route('/add_link', methods=['GET', 'POST'])
@login_required
def add_link():
    conn = get_db_connection()

    # 获取表单数据
    product_uid = request.form['product_uid']
    platform = request.form['platform']
    shop = request.form['shop']
    listing_time = request.form['listing_time']
    title = request.form['title']
    link_type = request.form['link_type']
    price_type = request.form['price_type']
    price = request.form['price']
    platform_skc = request.form['platform_skc']

    # ✅ 自动获取当前登录用户的 ID
    listed_by = session.get('username')

    existing_sku = conn.execute('SELECT * FROM product_links WHERE platform_skc = ? AND is_deleted = 0 LIMIT 1', (platform_skc, )).fetchone()
    if existing_sku:
        flash('这条链接已存在！', 'error')
        conn.close()
        return redirect(url_for('products'))

    # 插入新链接记录
    conn.execute('''
        INSERT INTO product_links 
        (product_uid, platform, shop, listing_time, title, link_type, price_type, price, platform_skc, listed_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (product_uid, platform, shop, listing_time, title, link_type, price_type, price, platform_skc, listed_by))

    conn.commit()
    conn.close()

    flash('链接已成功添加！', 'success')
    return redirect(url_for('products'))  # 或者返回到产品详情页

@app.route('/edit_link/<int:link_id>', methods=['GET', 'POST'])
@login_required
@user_owns_link
def edit_link(link_id):
    conn = get_db_connection()

    # 获取表单数据
    product_uid = request.form['edit_product_uid']
    platform = request.form['edit_platform']
    shop = request.form['edit_shop']
    listing_time = request.form['edit_listing_time']
    title = request.form['edit_title']
    link_type = request.form['edit_link_type']
    price_type = request.form['edit_price_type']
    price = request.form['edit_price']
    platform_skc = request.form['edit_platform_skc']  # 可选字段

    # ✅ 自动获取当前登录用户的 ID
    listed_by = session.get('username')

    existing_link = conn.execute('SELECT * FROM product_links WHERE platform_skc = ? AND id != ? AND is_deleted = 0', (platform_skc, link_id)).fetchall()
    if existing_link:
        flash('这条链接已存在！', 'error')
        conn.close()
        return redirect(url_for('product_links'))

    # 插入新链接记录
    conn.execute('''
        UPDATE product_links 
        SET platform = ?, shop = ?, listing_time = ?, title = ?, link_type = ?, price_type = ?, price = ?, platform_skc = ?, listed_by = ?
        WHERE id = ?
    ''', (platform, shop, listing_time, title, link_type, price_type, price, platform_skc, listed_by, link_id))

    conn.commit()
    conn.close()

    flash('链接已修改成功！', 'success')
    return redirect(url_for('product_links'))  # 或者返回到产品详情页


@app.route('/add_packages', methods=['POST'])
@login_required
def add_packages():
    conn = get_db_connection()

    # 获取表单数据
    product_uid = request.form['product_uid']
    length = request.form['length']
    width = request.form['width']
    height = request.form['height']
    weight = request.form['weight']
    description = request.form['description']

    # 插入新链接记录
    conn.execute('''
        INSERT INTO product_packages 
        (product_uid, length, width, height, weight, description)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (product_uid, length, width, height, weight, description))

    conn.commit()
    conn.close()

    flash('规格详情已成功添加！', 'success')
    return redirect(url_for('products'))  # 或者返回到产品详情页

@app.route('/delete_link/<int:link_id>', methods=['POST'])
@login_required
@user_owns_link
def delete_link(link_id):
    conn = get_db_connection()

    # 查询要删除的链接，获取其上架人 (listed_by) 和产品信息（可选）
    link = conn.execute('''
        SELECT pl.*, u.username AS listed_by_username
        FROM product_links pl
        LEFT JOIN users u ON pl.listed_by = u.user_id
        WHERE pl.id = ? AND is_deleted = 0
    ''', (link_id,)).fetchone()

    if not link:
        flash('链接不存在！', 'error')
        conn.close()
        return redirect(url_for('product_links'))

    # 执行删除操作
    conn.execute('UPDATE product_links SET is_deleted = 1 WHERE id = ?', (link_id,))
    conn.commit()
    conn.close()

    flash('链接已成功删除！', 'success')
    return redirect(url_for('product_links'))

@app.route('/upload_attachment/<product_uid>', methods=['POST'])
@login_required
def upload_attachment(product_uid):
    if 'file' not in request.files:
        flash('未选择文件！', 'error')
        return redirect(url_for('products'))

    files = request.files.getlist('file')

    for file in files:
        if file.filename == '':
            flash('未选择文件！', 'error')
            return redirect(url_for('products'))

        if file and allowed_file_3mf(file.filename):
            # 获取当前时间戳（格式：YYYYMMDDHHMMSS）
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')

            # 获取产品名称（从数据库中查询）
            conn = get_db_connection()
            product = conn.execute('SELECT name FROM products WHERE uid = ?', (product_uid,)).fetchone()
            conn.close()

            if not product:
                flash('产品不存在！', 'error')
                return redirect(url_for('products'))

            product_name = product['name']

            # 获取原始文件名
            # original_filename = f"{os.path.splitext(file.filename)[1].lower()}"
            original_filename = str(file.filename)

            print(file.filename)

            # 构造新的文件名：产品名_时间戳_原始文件名
            new_filename = f"{product_name}_{timestamp}_{original_filename}"

            # 将文件信息保存在 product_file 表中
            conn = get_db_connection()
            conn.execute('''
            INSERT INTO product_file (product_uid, file_url, original_filename)
            VALUES (?, ?, ?)
            ''', (product_uid, new_filename, original_filename))
            conn.commit()

            print(f"Added new file to product_uid: {product_uid}")  # 调试信息

            # 保存文件到 upload/3mf/ 文件夹
            file_path = os.path.join(UPLOAD_FOLDER_3MF, new_filename)
            file.save(file_path)

            file_id = conn.execute('''
                            SELECT id 
                            FROM product_file
                            WHERE file_url = ?
                        ''', (new_filename,)).fetchone()
            file_path_cos = 'file_3mf/' + product_name + '/' + timestamp + original_filename
            file_path_url = tencent_cos.upload_to_cos(file_path, file_path_cos)

            conn.execute('''
                            INSERT INTO product_file_cos (file_id, file_url)
                            VALUES (?, ?)
                        ''', (file_id['id'], file_path_url))
            conn.commit()

            conn.close()

            flash('附件上传成功！', 'success')
            return redirect(url_for('products'))
        else:
            flash('只允许上传 3MF,STL 文件！', 'error')
            return redirect(url_for('products'))


@app.route('/download/<int:file_id>/<string:file_type>/<string:product_uid>')
@login_required
def download_file(file_id, file_type, product_uid):
    if file_type == 'file':
        conn = get_db_connection()
        file = conn.execute('''
            SELECT file_url, original_filename 
            FROM product_file
            WHERE id = ? AND is_deleted = 0
        ''', (file_id,)).fetchone()
        conn.close()

        if file:
            # 构建文件真实路径
            file_path = os.path.join(app.config['UPLOAD_FOLDER_3MF'], file['file_url'])

            # 发送文件并指定下载文件名
            return send_file(
                file_path,
                as_attachment=True,  # 强制下载而非预览
                download_name=file['original_filename'],  # 浏览器显示的文件名
            )
        else:
            flash('文件不存在', 'error')
            return redirect(url_for('products'))

    elif file_type == 'image':
        conn = get_db_connection()
        file = conn.execute('''
                SELECT image_url, product_uid 
                FROM product_images 
                WHERE id = ? AND is_deleted = 0
            ''', (file_id,)).fetchone()

        product = conn.execute('''
                SELECT  name
                FROM products
                WHERE uid = ?
            ''', (file['product_uid'],)).fetchone()
        conn.close()

        filename = product['name'] + str(file_id) + Path(file['image_url']).suffix.lower()

        if file:
            # 构建文件真实路径
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], file['product_uid'], file['image_url'])

            # 发送文件并指定下载文件名
            return send_file(
                file_path,
                as_attachment=True,  # 强制下载而非预览
                download_name=filename,  # 浏览器显示的文件名
            )
        else:
            flash('文件不存在', 'error')
            return redirect(url_for('products'))

    elif file_type == 'all_image':
        conn = get_db_connection()

        # 获取产品名称
        product = conn.execute('''
               SELECT name FROM products WHERE uid = ?
           ''', (product_uid,)).fetchone()

        if not product:
            conn.close()
            flash('文件不存在', 'error')
            return redirect(url_for('products'))


        images = conn.execute('''
               SELECT image_url FROM product_images 
               WHERE product_uid = ? AND is_deleted = 0
           ''', (product_uid,)).fetchall()
        conn.close()

        # 创建 ZIP 文件
        # 使用内存中的 ZIP（无需保存到硬盘）
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for idx, img in enumerate(images):
                # 构建文件真实路径
                img_path = os.path.join(app.config['UPLOAD_FOLDER'], product_uid, img['image_url'])

                # 检查文件是否存在
                if os.path.exists(img_path):
                    # 自定义 ZIP 内的文件名
                    ext = Path(img['image_url']).suffix.lower()
                    zip_filename = f"{product['name']}_{idx + 1}{ext}"

                    # 将文件添加到 ZIP
                    zip_file.write(img_path, arcname=zip_filename)

        # 5. 返回 ZIP 文件
        zip_buffer.seek(0)  # 重置指针
        return send_file(
            zip_buffer,
            as_attachment = True,
            download_name = f"{product['name']} 所有图片.zip",  # 浏览器显示的 ZIP 文件名
            mimetype = "application/zip"
        )


@app.route('/manual_backup', methods=['GET'])
@login_required
@admin_required
def manual_backup():

    # 调用备份函数
    success, message = backup_database()

    # 提示用户备份结果
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')

    # 备份完成后，重定向回某个页面，比如后台首页 / 管理页面
    return redirect(url_for('admin_panel'))

@app.route('/reset_password/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def reset_password(user_id):

    # 指定重置后的密码（明文，比如默认密码为 123456）
    new_password_plain = '123456'  # 您可以修改为任意默认密码
    new_password_hash = generate_password_hash(new_password_plain)  # 加密密码

    conn = get_db_connection()  # 假定您有一个获取数据库连接的函数
    try:
        # 更新指定 user_id 的用户的密码哈希
        conn.execute(
            'UPDATE users SET password = ? WHERE user_id = ?',
            (new_password_hash, user_id)
        )
        username = conn.execute(
            'SELECT username FROM users WHERE user_id = ?',
            (user_id,)
        ).fetchone()[0]
        conn.commit()
        flash(f'用户 {username} 的密码已重置为：{new_password_plain}', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'重置密码失败：{e}', 'error')
    finally:
        conn.close()

    if user_id == session['user_id']:
        return redirect(url_for('logout'))

    # 重定向回管理员页面
    return redirect(url_for('admin_panel'))

@app.route('/get_image_link/<int:image_id>')
@login_required
def get_image_link(image_id):
    conn = get_db_connection()
    image_link = conn.execute('''
           SELECT image_url
           FROM product_images_cos
           WHERE image_id = ? 
       ''', (image_id,)).fetchone()
    conn.close()

    return image_link['image_url']

@app.route('/get_lingxing_excel_jump/<string:uid>')
def get_lingxing_excel_jump(uid):
    """
       返回一个自动下载 Excel 文件并跳转的页面
       """
    # 手动生成真实的下载 URL
    download_url = url_for('get_lingxing_excel', uid=uid, _external=False)

    # 使用 render_template_string 来安全地插入 URL
    html = f'''
        <!DOCTYPE html>
        <html>
        <body>
          <script>
            // 下载文件
            var a = document.createElement('a');
            a.href = '{download_url}';
            a.download = true;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);

            // 打开新标签页
            window.open('https://erp.lingxing.com/erp/productManage', '_blank');

            // ✅ 因为当前窗口是 JS 打开的，可以关闭
            setTimeout(function() {{
              window.close();  // 安全！
            }}, 2000);  // 等2秒确保下载和跳转完成
          </script>
        </body>
        </html>
        '''
    # print(html)  # 调试：查看输出是否正确
    return render_template_string(html)

@app.route('/get_lingxing_excel/<string:uid>')
@login_required
def get_lingxing_excel(uid):
    conn = get_db_connection()
    product = conn.execute('''
            SELECT *
            FROM products
            WHERE uid = ?
        ''', (uid,)).fetchone()
    product_image = conn.execute('''
                SELECT *
                FROM product_images
                WHERE product_uid = ?
            ''', (uid,)).fetchone()
    if product_image:
        product_image_link = conn.execute('''
                        SELECT *
                        FROM product_images_cos
                        WHERE image_id = ?
                    ''', (product_image['id'],)).fetchone()
    product_package = conn.execute('''
                    SELECT *
                    FROM product_packages
                    WHERE product_uid = ?
                ''', (uid,)).fetchone()
    conn.close()

    name = product['name']
    cost = product['cost']
    if product_image_link:
        image = product_image_link['image_url']
    else:
        image = ''
    if product_package:
        length = product_package['length']
        width = product_package['width']
        height = product_package['height']
        weight = product_package['weight']
    else:
        length = ''
        width = ''
        height = ''
        weight = ''

    source_file = './static/lingxing/lingxing.xlsx'
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    target_file = f'./static/lingxing/{name}_{timestamp}.xlsx'
    shutil.copy(source_file, target_file)
    workbook = openpyxl.load_workbook(target_file)

    sheet_product = workbook['产品']

    sheet_product['A2'] = uid
    sheet_product['B2'] = name
    sheet_product['Y2'] = cost
    sheet_product['V2'] = image
    sheet_product['AI2'] = length
    sheet_product['AJ2'] = width
    sheet_product['AK2'] = height
    sheet_product['AL2'] = 'cm'
    sheet_product['AG2'] = weight
    sheet_product['AH2'] = 'g'

    workbook.save(target_file)

    return send_file(
                    target_file,
                    as_attachment=True,  # 强制下载而非预览
                    download_name=f'{name}_{timestamp}.xlsx',  # 浏览器显示的文件名
                )


@app.route('/get_lingxing_excel_all')
@login_required
def get_lingxing_excel_all():
    conn = get_db_connection()

    # 查询每个产品只取一行数据（每个产品只出现一次）
    products = conn.execute('''
        SELECT
            p.uid,
            p.name,
            p.cost,
            (SELECT pic.image_url
             FROM product_images pi
             JOIN product_images_cos pic ON pic.image_id = pi.id
             WHERE pi.product_uid = p.uid AND pi.is_deleted = 0
             LIMIT 1) AS image_url,

            (SELECT pp.length FROM product_packages pp WHERE pp.product_uid = p.uid LIMIT 1) AS length,
            (SELECT pp.width  FROM product_packages pp WHERE pp.product_uid = p.uid LIMIT 1) AS width,
            (SELECT pp.height FROM product_packages pp WHERE pp.product_uid = p.uid LIMIT 1) AS height,
            (SELECT pp.weight FROM product_packages pp WHERE pp.product_uid = p.uid LIMIT 1) AS weight
        FROM products p
    ''').fetchall()

    if not products:
        conn.close()
        return "没有找到任何产品数据", 404

    # 模板文件路径
    source_file = './static/lingxing/lingxing.xlsx'
    if not os.path.exists(source_file):
        conn.close()
        return "Excel 模板文件 lingxing.xlsx 不存在", 500

    # 生成输出文件路径
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    output_filename = f'lingxing_all_products_{timestamp}.xlsx'
    output_path = os.path.join('./static/lingxing/', output_filename)

    # 复制模板
    shutil.copy(source_file, output_path)

    # 加载 Excel
    workbook = openpyxl.load_workbook(output_path)
    sheet = workbook['产品']  # 假设模板中有个叫“产品”的 sheet

    start_row = 2  # 假设第1行为标题行

    for idx, product in enumerate(products):
        row = start_row + idx

        sheet[f'A{row}'] = product['uid']
        sheet[f'B{row}'] = product['name']
        sheet[f'Y{row}'] = product['cost']
        sheet[f'V{row}'] = product['image_url'] or ''

        sheet[f'AI{row}'] = product['length'] or ''
        sheet[f'AJ{row}'] = product['width'] or ''
        sheet[f'AK{row}'] = product['height'] or ''
        sheet[f'AL{row}'] = 'cm' if any([product['length'], product['width'], product['height']]) else ''
        sheet[f'AG{row}'] = product['weight'] or ''
        sheet[f'AH{row}'] = 'g' if product['weight'] else ''

    # 保存并关闭
    workbook.save(output_path)
    conn.close()

    # 返回文件
    return send_file(
        output_path,
        as_attachment=True,
        download_name=output_filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

def add_product_bg(name, short_name, danse, duose, image_path):
    # 自动生成唯一标识符
    uid = generate_product_uid()
    sku = uid
    cost = float(danse*0.15 + danse*0.2)
    developer_id = session['user_id']
    category = '1'
    permission_group_id = 1
    # 检查SKU是否已存在
    conn = get_db_connection()
    existing_sku = conn.execute('SELECT * FROM products WHERE sku = ?', (sku,)).fetchone()
    existing_name = conn.execute('SELECT * FROM products WHERE name = ?', (name,)).fetchone()
    if existing_sku or existing_name:
        return ('产品已存在！', 'error')
        conn.close()
    else:
        try:
            # 插入产品信息
            conn.execute('''
                INSERT INTO products (uid, name, short_name, sku, cost, developer_id, category, permission_group_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (uid, name, short_name, sku, cost, developer_id, category, permission_group_id))
            conn.commit()

            # 插入3D重量信息
            conn.execute('''
                                INSERT INTO product_3D_weight (product_uid, danse, duose)
                                VALUES (?, ?, ?)
                            ''', (uid, danse, duose))
            conn.commit()

            # 处理图片上传
            # 读取文件内容并创建 FileStorage 对象
            with open(image_path, 'rb') as f:
                file_content = f.read()

            # 创建类似上传文件的 FileStorage 对象
            file = FileStorage(
                stream=io.BytesIO(file_content),
                filename="temp1.xlsx",
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            if file and file.filename != '' and allowed_file_excel(file.filename):
                filename = f"{os.path.splitext(file.filename)[1].lower()}"
                unique_filename = f"{uuid.uuid4()}{filename}"  # 生成唯一文件名
                file_dir = os.path.join(app.config['UPLOAD_FOLDER'], uid)
                os.makedirs(file_dir, exist_ok=True)  # 创建目录（如果不存在）

                # 保存文件
                filepath = os.path.join(file_dir, unique_filename)
                # filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(filepath)
                print(f"Saved new image to: {filepath}")  # 调试信息

                # 构建相对路径（如 uploads/UUID_原文件名.png）
                relative_path = unique_filename

                # 将图片信息保存到 product_images 表中
                conn.execute('''
                    INSERT INTO product_images (product_uid, image_url, is_local)
                    VALUES (?, ?, 1)
                ''', (uid, relative_path))
                conn.commit()
                file_id = conn.execute('''
                    SELECT id 
                    FROM product_images
                    WHERE image_url = ?
                ''', (relative_path,)).fetchone()
                image_path_cos = 'image/' + name + '/' + name + str(
                    file_id['id']) + Path(
                    relative_path).suffix.lower()
                image_path_url = tencent_cos.upload_to_cos(filepath, image_path_cos)

                conn.execute('''
                                INSERT INTO product_images_cos (image_id, image_url)
                                VALUES (?, ?)
                            ''', (file_id['id'], image_path_url))
                conn.commit()

                print(f"Added new image to product_uid: {uid}")  # 调试信息

            conn.close()

            return ('产品添加成功！', 'success')
            return redirect(url_for('products'))
        except Exception as e:
            conn.close()
            return (f'添加产品时出错：{str(e)}', 'error')

def get_image_path(image_list, key_me):
    for key, image_path in image_list:
        if key_me == key:
            return image_path
    return None


@app.route('/add_excel', methods=['GET', 'POST'])
@login_required
def add_excel():
    # ===================== POST 请求处理（文件上传） =====================
    if request.method == 'POST':
        # 检查文件是否提交
        if 'file' not in request.files:
            flash('未选择文件！', 'error')
            return redirect(url_for('add_excel'))

        files = request.files.getlist('file')
        if not files or all(f.filename == '' for f in files):
            flash('未选择文件！', 'error')
            return redirect(url_for('add_excel'))

        # 处理每个文件
        for file in files:
            if file.filename == '':
                continue

            # 修复1：用 filename.lower() 而不是 file.lower()
            if not file.filename.lower().endswith('.xlsx'):
                continue

            # 修复2：清理临时文件
            import atexit
            import os
            import uuid

            with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
                file.save(tmp_file.name)
                temp_path = tmp_file.name

            # 注册清理函数
            def cleanup_temp():
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            atexit.register(cleanup_temp)

            try:
                # 处理Excel数据
                images = excel_export.extract_dispimg_optimized(temp_path)
                df = pd.read_excel(temp_path, usecols="A:D")

                for index, row in df.iterrows():
                    row_num = index + 2  # Excel行号从1开始，加上标题行
                    a_value = row.iloc[0] if len(row) > 0 else None
                    b_value = row.iloc[1] if len(row) > 1 else None
                    c_value = row.iloc[2] if len(row) > 2 else None
                    d_value = row.iloc[3] if len(row) > 3 else None
                    e_value = get_image_path(images, f'E{row_num}') or ''  # 修复3：处理None
                    add_product_bg(a_value, b_value, c_value, d_value, e_value)

                flash(f'文件 {file.filename} 处理成功！', 'success')
            except Exception as e:
                flash(f'处理文件 {file.filename} 时出错：{str(e)}', 'error')

        # ===================== 关键修复：跳转到与表单无关的页面 =====================
        return redirect(url_for('products'))  # 跳转到产品列表页，与/add_product一致！

    # ===================== GET 请求处理（显示表单） =====================
    return render_template('add_excel.html')







if __name__ == '__main__':
    init_database()
    start_scheduler()
    # app.run(debug=True)
    app.run(host='0.0.0.0', port=213)