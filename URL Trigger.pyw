# -*- coding: utf-8 -*-
import os
import sys
import subprocess
import json
import datetime
import threading
import socket
import requests
import pyperclip

# PySide6 GUI
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QTextEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QGroupBox, QFrame, QCheckBox,
    QFileDialog, QMessageBox, QStatusBar, QMenuBar, QMenu, QSplitter,
    QTabWidget, QScrollArea, QSizePolicy, QGraphicsDropShadowEffect,
    QProgressBar, QDialog
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect, Signal, QThread
from PySide6.QtGui import QFont, QIcon, QColor, QPalette, QPixmap, QPainter, QLinearGradient, QBrush

# Flask 相关
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
import logging

if getattr(sys, 'frozen', False):
    # PyInstaller 打包后运行 (onefile 模式)
    # 模板等数据文件在临时解压目录中
    APP_DIR = sys._MEIPASS
    # 配置文件和日志放在 exe 同级目录，方便读写
    DATA_DIR = os.path.dirname(sys.executable)
else:
    # 开发环境
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = APP_DIR

CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
LOG_FILE = os.path.join(DATA_DIR, "logs.json")

# 模板目录
TEMPLATE_DIR = os.path.join(APP_DIR, "index")

DEFAULT_PASSWORD = "admin123"
BACKUP_PASSWORD = "Administrator"
DEFAULT_PORT = 5000

# 全局变量
web_server_thread = None
web_server_stop = threading.Event()
flask_server = None  # 保存 Flask 服务器实例


# =========================
# 配置文件管理
# =========================

def load_config():
    if not os.path.exists(CONFIG_FILE):
        config = {
            "app_path": r"C:\Windows\notepad.exe",
            "apps": [
                {"name": "notepad", "path": r"C:\Windows\notepad.exe"}
            ],
            "admin_password": DEFAULT_PASSWORD,
            "port": DEFAULT_PORT,
            "auto_start_web": True
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        return config

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    # 向后兼容：如果旧配置有 app_path 但没有 apps，自动迁移
    if "app_path" in config and "apps" not in config:
        config["apps"] = [
            {"name": "default", "path": config["app_path"]}
        ]
        save_config(config)
    elif "apps" not in config:
        config["apps"] = []
        save_config(config)

    return config


def get_secret_key():
    """获取或生成持久的 Flask 密钥，存储在 config.json 中"""
    config = load_config()
    if "secret_key" not in config:
        config["secret_key"] = os.urandom(24).hex()
        save_config(config)
    return config["secret_key"]


def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)


# =========================
# 日志记录
# =========================

def load_logs():
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except:
            return []


def save_logs(logs):
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=4, ensure_ascii=False)


def log_access(ip, path, action=""):
    log_entry = {
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ip": ip,
        "path": path,
        "action": action
    }
    logs = load_logs()
    logs.append(log_entry)
    save_logs(logs)


# =========================
# 工具功能
# =========================

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


# =========================
# Web 服务器 (Flask)
# =========================

# Flask 应用
flask_app = Flask(__name__, template_folder=TEMPLATE_DIR)
flask_app.secret_key = get_secret_key()
flask_app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(days=7)
flask_app.config['SESSION_COOKIE_NAME'] = 'url_trigger_session'
flask_app.config['SESSION_COOKIE_HTTPONLY'] = True
flask_app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
reset_tokens = {}  # 存储重置令牌


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


@flask_app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        config = load_config()
        username = request.form.get('username')
        password = request.form.get('password')
        if username == 'admin' and password == config['admin_password']:
            session['logged_in'] = True
            session.permanent = True
            log_access(request.remote_addr, '/login', '管理员登录')
            return redirect(url_for('admin'))
        error = '账号或密码错误'
    return render_template('login.html', error=error, error_message=error or '')


@flask_app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))


@flask_app.route('/admin')
@login_required
def admin():
    config = load_config()
    logs = load_logs()
    global web_server_thread, flask_server
    server_running = web_server_thread is not None and web_server_thread.is_alive()
    return render_template(
        'admin.html',
        local_ip=get_local_ip(),
        total_visits=len(logs),
        port=config.get('port', DEFAULT_PORT),
        app_path=config.get('app_path', ''),
        backup_password=BACKUP_PASSWORD,
        server_running=server_running,
        auto_start_web=config.get('auto_start_web', True)
    )


@flask_app.route('/')
def index():
    return redirect('/admin')


# API 路由
@flask_app.route('/api/logs', methods=['GET'])
@login_required
def api_logs():
    logs = load_logs()
    limit = request.args.get('limit', type=int)
    if limit:
        logs = logs[-limit:]
    return jsonify({'logs': list(reversed(logs))})


@flask_app.route('/api/logs', methods=['DELETE'])
@login_required
def api_clear_logs():
    save_logs([])
    log_access('admin', '/api/logs', '清空日志')
    return jsonify({'success': True})


@flask_app.route('/api/verify_backup', methods=['POST'])
def api_verify_backup():
    data = request.json
    if data.get('backup_password') == BACKUP_PASSWORD:
        token = os.urandom(16).hex()
        reset_tokens[token] = True
        return jsonify({'success': True, 'reset_token': token})
    return jsonify({'success': False})


@flask_app.route('/api/reset_password', methods=['POST'])
def api_reset_password():
    data = request.json
    token = data.get('token')
    if token in reset_tokens:
        config = load_config()
        config['admin_password'] = data['new_password']
        save_config(config)
        del reset_tokens[token]
        log_access('admin', '/api/reset_password', '重置密码')
        return jsonify({'success': True})
    return jsonify({'success': False})


@flask_app.route('/api/change_password', methods=['POST'])
@login_required
def api_change_password():
    data = request.json
    config = load_config()
    if data['current_password'] != config['admin_password']:
        return jsonify({'success': False, 'message': '当前密码错误'})
    if len(data['new_password']) < 4:
        return jsonify({'success': False, 'message': '密码长度不能少于4位'})
    config['admin_password'] = data['new_password']
    save_config(config)
    log_access('admin', '/api/change_password', '修改密码')
    return jsonify({'success': True})


@flask_app.route('/api/config/app_path', methods=['POST'])
@login_required
def api_save_app_path():
    data = request.json
    config = load_config()
    config['app_path'] = data['app_path']
    save_config(config)
    log_access('admin', '/api/config/app_path', '修改程序路径')
    return jsonify({'success': True})


@flask_app.route('/api/config/port', methods=['POST'])
@login_required
def api_save_port():
    data = request.json
    port = data.get('port', DEFAULT_PORT)
    if is_port_in_use(port) and port != flask_app.config.get('PORT', DEFAULT_PORT):
        return jsonify({'success': False, 'message': f'端口 {port} 已被占用'})
    config = load_config()
    config['port'] = port
    save_config(config)
    log_access('admin', '/api/config/port', '修改服务端口')
    return jsonify({'success': True, 'message': '端口设置已保存，重启服务后生效'})


@flask_app.route('/api/config/auto_start', methods=['POST'])
@login_required
def api_save_auto_start():
    data = request.json
    auto_start = data.get('auto_start', True)
    config = load_config()
    config['auto_start_web'] = auto_start
    save_config(config)
    log_access('admin', '/api/config/auto_start', '修改自动启动设置')
    return jsonify({'success': True, 'message': f'自动启动已{"开启" if auto_start else "关闭"}'})


@flask_app.route('/api/server/start', methods=['POST'])
@login_required
def api_start_server():
    global web_server_thread
    if web_server_thread is not None and web_server_thread.is_alive():
        return jsonify({'success': False, 'message': '服务已在运行中'})
    success, msg = start_web_server()
    if success:
        log_access('admin', '/api/server/start', '启动 Web 服务')
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'message': msg})


@flask_app.route('/api/server/stop', methods=['POST'])
@login_required
def api_stop_server():
    global web_server_thread
    if web_server_thread is None or not web_server_thread.is_alive():
        return jsonify({'success': False, 'message': '服务未运行'})
    stop_web_server()
    log_access('admin', '/api/server/stop', '停止 Web 服务')
    return jsonify({'success': True, 'message': 'Web 服务已停止'})


@flask_app.route('/api/launch_app', methods=['POST'])
@login_required
def api_launch_app():
    config = load_config()
    path = config['app_path']
    if os.path.exists(path):
        subprocess.Popen(path)
        log_access('admin', '/api/launch_app', '启动程序')
        return jsonify({'success': True, 'message': f'已启动: {path}'})
    return jsonify({'success': False, 'message': f'程序不存在: {path}'})


@flask_app.route('/api/status')
def api_status():
    return jsonify({'status': 'running', 'port': flask_app.config.get('PORT', DEFAULT_PORT)})


@flask_app.route('/api/check_login')
def api_check_login():
    """检查当前登录状态"""
    return jsonify({'logged_in': 'logged_in' in session})


@flask_app.route('/open/<app_name>')
def open_app(app_name):
    """根据子域名启动对应的应用程序"""
    config = load_config()
    apps = config.get('apps', [])

    # 查找匹配的应用
    target = None
    for app in apps:
        if app['name'] == app_name:
            target = app
            break

    if not target:
        available = [app['name'] for app in apps]
        return jsonify({
            'success': False,
            'message': f'应用 "{app_name}" 不存在',
            'available_apps': available
        }), 404

    path = target['path']
    if os.path.exists(path):
        subprocess.Popen(path)
        log_access(request.remote_addr, f'/open/{app_name}', f'启动应用: {app_name}')
        return jsonify({'success': True, 'message': f'已启动: {app_name} ({path})'})
    return jsonify({'success': False, 'message': f'程序不存在: {path}'}), 404


@flask_app.route('/open')
def open_app_list():
    """显示所有可用的应用启动页"""
    return render_template('open.html')


@flask_app.route('/api/apps', methods=['GET'])
@login_required
def api_get_apps():
    """获取所有应用列表"""
    config = load_config()
    apps = config.get('apps', [])
    return jsonify({'success': True, 'apps': apps})


@flask_app.route('/api/apps', methods=['POST'])
@login_required
def api_add_app():
    """添加新应用"""
    data = request.json
    name = data.get('name', '').strip()
    path = data.get('path', '').strip()

    if not name:
        return jsonify({'success': False, 'message': '应用名称不能为空'})
    if not path:
        return jsonify({'success': False, 'message': '程序路径不能为空'})

    config = load_config()
    apps = config.get('apps', [])

    # 检查名称是否重复
    for app in apps:
        if app['name'] == name:
            return jsonify({'success': False, 'message': f'应用名称 "{name}" 已存在'})

    apps.append({'name': name, 'path': path})
    config['apps'] = apps
    save_config(config)
    log_access('admin', '/api/apps', f'添加应用: {name}')
    return jsonify({'success': True, 'message': f'应用 "{name}" 已添加'})


@flask_app.route('/api/apps/<app_name>', methods=['DELETE'])
@login_required
def api_delete_app(app_name):
    """删除应用"""
    config = load_config()
    apps = config.get('apps', [])

    new_apps = [app for app in apps if app['name'] != app_name]
    if len(new_apps) == len(apps):
        return jsonify({'success': False, 'message': f'应用 "{app_name}" 不存在'})

    config['apps'] = new_apps
    save_config(config)
    log_access('admin', f'/api/apps/{app_name}', f'删除应用: {app_name}')
    return jsonify({'success': True, 'message': f'应用 "{app_name}" 已删除'})


@flask_app.route('/api/apps/<app_name>', methods=['PUT'])
@login_required
def api_update_app(app_name):
    """修改应用（名称和/或路径）"""
    data = request.json
    new_name = data.get('name', '').strip()
    path = data.get('path', '').strip()

    if not path:
        return jsonify({'success': False, 'message': '程序路径不能为空'})

    config = load_config()
    apps = config.get('apps', [])

    # 查找目标应用
    target = None
    for app in apps:
        if app['name'] == app_name:
            target = app
            break

    if not target:
        return jsonify({'success': False, 'message': f'应用 "{app_name}" 不存在'})

    # 如果修改了名称，检查是否重复
    if new_name and new_name != app_name:
        for app in apps:
            if app['name'] == new_name:
                return jsonify({'success': False, 'message': f'应用名称 "{new_name}" 已存在'})
        target['name'] = new_name

    target['path'] = path
    config['apps'] = apps
    save_config(config)
    log_action = f'修改应用: {app_name}'
    if new_name and new_name != app_name:
        log_action += f' -> {new_name}'
    log_access('admin', f'/api/apps/{app_name}', log_action)
    return jsonify({'success': True, 'message': f'应用已更新'})


def run_web_server(port, stop_event):
    """运行 Flask 服务器"""
    global flask_server
    from werkzeug.serving import make_server
    flask_app.config['PORT'] = port
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)  # 减少日志输出
    try:
        flask_server = make_server('0.0.0.0', port, flask_app, threaded=True)
        flask_server.serve_forever()
    except OSError as e:
        if 'address already in use' in str(e).lower():
            print(f"错误: 端口 {port} 已被占用")
        else:
            raise


def start_web_server():
    """启动 Web 服务器线程"""
    global web_server_thread, web_server_stop
    config = load_config()
    port = config.get('port', DEFAULT_PORT)
    
    if is_port_in_use(port):
        return False, f"端口 {port} 已被占用，请检查是否有其他服务在使用"
    
    web_server_stop.clear()
    web_server_thread = threading.Thread(target=run_web_server, args=(port, web_server_stop), daemon=True)
    web_server_thread.start()
    return True, f"Web 服务器已启动在端口 {port}"


def stop_web_server():
    """停止 Web 服务器"""
    global web_server_stop, flask_server
    web_server_stop.set()
    if flask_server:
        flask_server.shutdown()
        flask_server = None


# =========================
# 样式常量
# =========================

class AppStyle:
    """应用程序样式常量"""
    # 颜色
    PRIMARY = "#4F46E5"
    PRIMARY_HOVER = "#4338CA"
    SECONDARY = "#6366F1"
    SUCCESS = "#10B981"
    SUCCESS_HOVER = "#059669"
    DANGER = "#EF4444"
    DANGER_HOVER = "#DC2626"
    WARNING = "#F59E0B"
    INFO = "#3B82F6"

    # 背景
    BG_DARK = "#1E1E2E"
    BG_CARD = "#2A2A3C"
    BG_INPUT = "#333347"
    BG_HOVER = "#3A3A4C"

    # 文字
    TEXT_PRIMARY = "#FFFFFF"
    TEXT_SECONDARY = "#A0A0B8"
    TEXT_MUTED = "#6B6B80"

    # 边框
    BORDER = "#3F3F55"
    BORDER_FOCUS = "#4F46E5"

    # 字体
    FONT_FAMILY = "Microsoft YaHei UI, Segoe UI, sans-serif"
    FONT_SIZE_SMALL = 11
    FONT_SIZE_NORMAL = 13
    FONT_SIZE_LARGE = 15
    FONT_SIZE_TITLE = 18
    FONT_SIZE_HEADER = 22

    # 圆角
    RADIUS_SMALL = 6
    RADIUS_MEDIUM = 10
    RADIUS_LARGE = 14

    # 间距
    SPACING_SMALL = 8
    SPACING_MEDIUM = 12
    SPACING_LARGE = 16
    SPACING_XLARGE = 24


def apply_style(widget, style_type="card"):
    """应用样式到控件"""
    if style_type == "card":
        widget.setStyleSheet(f"""
            QFrame, QGroupBox {{
                background-color: {AppStyle.BG_CARD};
                border: 1px solid {AppStyle.BORDER};
                border-radius: {AppStyle.RADIUS_MEDIUM}px;
            }}
        """)
    elif style_type == "input":
        widget.setStyleSheet(f"""
            QLineEdit {{
                background-color: {AppStyle.BG_INPUT};
                color: {AppStyle.TEXT_PRIMARY};
                border: 1px solid {AppStyle.BORDER};
                border-radius: {AppStyle.RADIUS_SMALL}px;
                padding: 8px 12px;
                font-size: {AppStyle.FONT_SIZE_NORMAL}px;
            }}
            QLineEdit:focus {{
                border: 1px solid {AppStyle.BORDER_FOCUS};
            }}
            QLineEdit:disabled {{
                background-color: {AppStyle.BG_DARK};
                color: {AppStyle.TEXT_MUTED};
            }}
        """)
    elif style_type == "primary_button":
        widget.setStyleSheet(f"""
            QPushButton {{
                background-color: {AppStyle.PRIMARY};
                color: {AppStyle.TEXT_PRIMARY};
                border: none;
                border-radius: {AppStyle.RADIUS_SMALL}px;
                padding: 8px 20px;
                font-size: {AppStyle.FONT_SIZE_NORMAL}px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {AppStyle.PRIMARY_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {AppStyle.PRIMARY};
            }}
            QPushButton:disabled {{
                background-color: {AppStyle.BG_INPUT};
                color: {AppStyle.TEXT_MUTED};
            }}
        """)
    elif style_type == "success_button":
        widget.setStyleSheet(f"""
            QPushButton {{
                background-color: {AppStyle.SUCCESS};
                color: {AppStyle.TEXT_PRIMARY};
                border: none;
                border-radius: {AppStyle.RADIUS_SMALL}px;
                padding: 8px 20px;
                font-size: {AppStyle.FONT_SIZE_NORMAL}px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {AppStyle.SUCCESS_HOVER};
            }}
            QPushButton:disabled {{
                background-color: {AppStyle.BG_INPUT};
                color: {AppStyle.TEXT_MUTED};
            }}
        """)
    elif style_type == "danger_button":
        widget.setStyleSheet(f"""
            QPushButton {{
                background-color: {AppStyle.DANGER};
                color: {AppStyle.TEXT_PRIMARY};
                border: none;
                border-radius: {AppStyle.RADIUS_SMALL}px;
                padding: 8px 20px;
                font-size: {AppStyle.FONT_SIZE_NORMAL}px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {AppStyle.DANGER_HOVER};
            }}
            QPushButton:disabled {{
                background-color: {AppStyle.BG_INPUT};
                color: {AppStyle.TEXT_MUTED};
            }}
        """)
    elif style_type == "secondary_button":
        widget.setStyleSheet(f"""
            QPushButton {{
                background-color: {AppStyle.BG_INPUT};
                color: {AppStyle.TEXT_PRIMARY};
                border: 1px solid {AppStyle.BORDER};
                border-radius: {AppStyle.RADIUS_SMALL}px;
                padding: 8px 20px;
                font-size: {AppStyle.FONT_SIZE_NORMAL}px;
            }}
            QPushButton:hover {{
                background-color: {AppStyle.BG_HOVER};
                border-color: {AppStyle.PRIMARY};
            }}
            QPushButton:disabled {{
                background-color: {AppStyle.BG_DARK};
                color: {AppStyle.TEXT_MUTED};
            }}
        """)
    elif style_type == "table":
        widget.setStyleSheet(f"""
            QTableWidget {{
                background-color: {AppStyle.BG_INPUT};
                color: {AppStyle.TEXT_PRIMARY};
                border: 1px solid {AppStyle.BORDER};
                border-radius: {AppStyle.RADIUS_SMALL}px;
                gridline-color: {AppStyle.BORDER};
                selection-background-color: {AppStyle.PRIMARY};
                font-size: {AppStyle.FONT_SIZE_SMALL}px;
            }}
            QTableWidget::item {{
                padding: 6px;
            }}
            QHeaderView::section {{
                background-color: {AppStyle.BG_CARD};
                color: {AppStyle.TEXT_SECONDARY};
                padding: 8px;
                border: none;
                border-bottom: 2px solid {AppStyle.PRIMARY};
                font-weight: bold;
                font-size: {AppStyle.FONT_SIZE_SMALL}px;
            }}
            QScrollBar:vertical {{
                background-color: {AppStyle.BG_DARK};
                width: 10px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {AppStyle.BORDER};
                border-radius: 5px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {AppStyle.PRIMARY};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
            QTableCornerButton::section {{
                background-color: {AppStyle.BG_CARD};
                border: none;
            }}
        """)
    elif style_type == "label":
        widget.setStyleSheet(f"""
            QLabel {{
                color: {AppStyle.TEXT_PRIMARY};
                font-size: {AppStyle.FONT_SIZE_NORMAL}px;
            }}
        """)
    elif style_type == "label_secondary":
        widget.setStyleSheet(f"""
            QLabel {{
                color: {AppStyle.TEXT_SECONDARY};
                font-size: {AppStyle.FONT_SIZE_SMALL}px;
            }}
        """)
    elif style_type == "groupbox":
        widget.setStyleSheet(f"""
            QGroupBox {{
                background-color: {AppStyle.BG_CARD};
                border: 1px solid {AppStyle.BORDER};
                border-radius: {AppStyle.RADIUS_MEDIUM}px;
                margin-top: 12px;
                padding-top: 16px;
                font-weight: bold;
                font-size: {AppStyle.FONT_SIZE_LARGE}px;
                color: {AppStyle.TEXT_PRIMARY};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 16px;
                padding: 0 8px;
                color: {AppStyle.SECONDARY};
            }}
        """)
    elif style_type == "checkbox":
        widget.setStyleSheet(f"""
            QCheckBox {{
                color: {AppStyle.TEXT_SECONDARY};
                font-size: {AppStyle.FONT_SIZE_NORMAL}px;
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 2px solid {AppStyle.BORDER};
                border-radius: 4px;
                background-color: {AppStyle.BG_INPUT};
            }}
            QCheckBox::indicator:checked {{
                background-color: {AppStyle.PRIMARY};
                border-color: {AppStyle.PRIMARY};
            }}
            QCheckBox::indicator:hover {{
                border-color: {AppStyle.PRIMARY};
            }}
        """)
    elif style_type == "status_bar":
        widget.setStyleSheet(f"""
            QStatusBar {{
                background-color: {AppStyle.BG_DARK};
                color: {AppStyle.TEXT_SECONDARY};
                border-top: 1px solid {AppStyle.BORDER};
                font-size: {AppStyle.FONT_SIZE_SMALL}px;
            }}
        """)
    elif style_type == "menu":
        widget.setStyleSheet(f"""
            QMenuBar {{
                background-color: {AppStyle.BG_DARK};
                color: {AppStyle.TEXT_PRIMARY};
                border-bottom: 1px solid {AppStyle.BORDER};
                padding: 4px;
                font-size: {AppStyle.FONT_SIZE_NORMAL}px;
            }}
            QMenuBar::item {{
                padding: 6px 12px;
                border-radius: {AppStyle.RADIUS_SMALL}px;
            }}
            QMenuBar::item:selected {{
                background-color: {AppStyle.BG_HOVER};
            }}
            QMenu {{
                background-color: {AppStyle.BG_CARD};
                color: {AppStyle.TEXT_PRIMARY};
                border: 1px solid {AppStyle.BORDER};
                border-radius: {AppStyle.RADIUS_SMALL}px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 24px 6px 12px;
                border-radius: {AppStyle.RADIUS_SMALL}px;
            }}
            QMenu::item:selected {{
                background-color: {AppStyle.PRIMARY};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {AppStyle.BORDER};
                margin: 4px 8px;
            }}
        """)
    elif style_type == "window":
        widget.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {AppStyle.BG_DARK};
                color: {AppStyle.TEXT_PRIMARY};
                font-family: {AppStyle.FONT_FAMILY};
            }}
        """)


# =========================
# 登录窗口
# =========================

class LoginDialog(QDialog):
    """登录对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.success_callback = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("管理员登录 - URL Trigger")
        self.setFixedSize(420, 320)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(AppStyle.SPACING_LARGE)
        layout.setContentsMargins(30, 30, 30, 30)

        # 标题
        title_label = QLabel("URL Trigger")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet(f"""
            QLabel {{
                color: {AppStyle.TEXT_PRIMARY};
                font-size: {AppStyle.FONT_SIZE_HEADER}px;
                font-weight: bold;
                padding: 10px 0;
            }}
        """)
        layout.addWidget(title_label)

        # 副标题
        subtitle_label = QLabel("管理员登录")
        subtitle_label.setAlignment(Qt.AlignCenter)
        subtitle_label.setStyleSheet(f"""
            QLabel {{
                color: {AppStyle.TEXT_SECONDARY};
                font-size: {AppStyle.FONT_SIZE_NORMAL}px;
                margin-bottom: 10px;
            }}
        """)
        layout.addWidget(subtitle_label)

        # 账号输入
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("请输入账号")
        self.username_input.setText("admin")
        apply_style(self.username_input, "input")
        layout.addWidget(self.username_input)

        # 密码输入
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("请输入密码")
        self.password_input.setEchoMode(QLineEdit.Password)
        apply_style(self.password_input, "input")
        layout.addWidget(self.password_input)

        # 错误提示
        self.error_label = QLabel("")
        self.error_label.setStyleSheet(f"""
            QLabel {{
                color: {AppStyle.DANGER};
                font-size: {AppStyle.FONT_SIZE_SMALL}px;
                padding: 5px 0;
            }}
        """)
        self.error_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.error_label)

        # 按钮区
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(AppStyle.SPACING_MEDIUM)

        self.login_btn = QPushButton("登 录")
        self.login_btn.clicked.connect(self.login)
        apply_style(self.login_btn, "primary_button")
        self.login_btn.setMinimumHeight(40)
        btn_layout.addWidget(self.login_btn)

        self.forgot_btn = QPushButton("忘记密码")
        self.forgot_btn.clicked.connect(self.forgot_password)
        apply_style(self.forgot_btn, "secondary_button")
        self.forgot_btn.setMinimumHeight(40)
        btn_layout.addWidget(self.forgot_btn)

        layout.addLayout(btn_layout)

        # 回车键登录
        self.password_input.returnPressed.connect(self.login)

    def login(self):
        config = load_config()
        username = self.username_input.text().strip()
        password = self.password_input.text()

        if username == "admin" and password == config["admin_password"]:
            self.accept()
            if self.success_callback:
                self.success_callback()
        else:
            self.error_label.setText("账号或密码错误")
            self.password_input.clear()
            self.password_input.setFocus()

    def forgot_password(self):
        self.hide()
        ForgotDialog(self.parent())


class ForgotDialog(QDialog):
    """忘记密码对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("忘记密码")
        self.setFixedSize(420, 220)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(AppStyle.SPACING_LARGE)
        layout.setContentsMargins(30, 30, 30, 30)

        # 标题
        title_label = QLabel("忘记密码")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet(f"""
            QLabel {{
                color: {AppStyle.TEXT_PRIMARY};
                font-size: {AppStyle.FONT_SIZE_TITLE}px;
                font-weight: bold;
                padding: 10px 0;
            }}
        """)
        layout.addWidget(title_label)

        # 提示
        hint_label = QLabel("请输入备用密码进行验证")
        hint_label.setAlignment(Qt.AlignCenter)
        hint_label.setStyleSheet(f"""
            QLabel {{
                color: {AppStyle.TEXT_SECONDARY};
                font-size: {AppStyle.FONT_SIZE_SMALL}px;
            }}
        """)
        layout.addWidget(hint_label)

        # 备用密码输入
        self.backup_input = QLineEdit()
        self.backup_input.setPlaceholderText("请输入备用密码")
        self.backup_input.setEchoMode(QLineEdit.Password)
        apply_style(self.backup_input, "input")
        layout.addWidget(self.backup_input)

        # 错误提示
        self.error_label = QLabel("")
        self.error_label.setStyleSheet(f"""
            QLabel {{
                color: {AppStyle.DANGER};
                font-size: {AppStyle.FONT_SIZE_SMALL}px;
            }}
        """)
        self.error_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.error_label)

        # 验证按钮
        self.verify_btn = QPushButton("验证")
        self.verify_btn.clicked.connect(self.verify)
        apply_style(self.verify_btn, "primary_button")
        self.verify_btn.setMinimumHeight(40)
        layout.addWidget(self.verify_btn)

        self.backup_input.returnPressed.connect(self.verify)

    def verify(self):
        if self.backup_input.text() == BACKUP_PASSWORD:
            self.close()
            ResetPasswordDialog(self.parent())
        else:
            self.error_label.setText("备用密码错误")


class ResetPasswordDialog(QDialog):
    """重置密码对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("重置密码")
        self.setFixedSize(420, 280)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(AppStyle.SPACING_LARGE)
        layout.setContentsMargins(30, 30, 30, 30)

        # 标题
        title_label = QLabel("重置密码")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet(f"""
            QLabel {{
                color: {AppStyle.TEXT_PRIMARY};
                font-size: {AppStyle.FONT_SIZE_TITLE}px;
                font-weight: bold;
                padding: 10px 0;
            }}
        """)
        layout.addWidget(title_label)

        # 新密码
        self.new_input = QLineEdit()
        self.new_input.setPlaceholderText("请输入新密码")
        self.new_input.setEchoMode(QLineEdit.Password)
        apply_style(self.new_input, "input")
        layout.addWidget(self.new_input)

        # 确认密码
        self.confirm_input = QLineEdit()
        self.confirm_input.setPlaceholderText("请再次输入新密码")
        self.confirm_input.setEchoMode(QLineEdit.Password)
        apply_style(self.confirm_input, "input")
        layout.addWidget(self.confirm_input)

        # 提示信息
        self.msg_label = QLabel("")
        self.msg_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.msg_label)

        # 重置按钮
        self.reset_btn = QPushButton("修改密码")
        self.reset_btn.clicked.connect(self.reset)
        apply_style(self.reset_btn, "primary_button")
        self.reset_btn.setMinimumHeight(40)
        layout.addWidget(self.reset_btn)

        self.confirm_input.returnPressed.connect(self.reset)

    def reset(self):
        new = self.new_input.text()
        confirm = self.confirm_input.text()

        if new != confirm:
            self.msg_label.setText("两次密码不一致")
            self.msg_label.setStyleSheet(f"color: {AppStyle.DANGER}; font-size: {AppStyle.FONT_SIZE_SMALL}px;")
        elif len(new) < 4:
            self.msg_label.setText("密码长度不能少于4位")
            self.msg_label.setStyleSheet(f"color: {AppStyle.DANGER}; font-size: {AppStyle.FONT_SIZE_SMALL}px;")
        else:
            config = load_config()
            config["admin_password"] = new
            save_config(config)
            log_access("local", "/reset_password", "重置密码")
            self.msg_label.setText("密码修改成功！")
            self.msg_label.setStyleSheet(f"color: {AppStyle.SUCCESS}; font-size: {AppStyle.FONT_SIZE_SMALL}px;")
            QTimer.singleShot(1500, self.close)


class EditAppDialog(QDialog):
    """编辑应用对话框"""
    def __init__(self, parent, old_name, old_path, on_save):
        super().__init__(parent)
        self.old_name = old_name
        self.old_path = old_path
        self.on_save = on_save
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("编辑应用")
        self.setFixedSize(520, 280)
        # 先设置 WindowFlags，再设置 Modal（顺序很重要）
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(AppStyle.SPACING_MEDIUM)
        layout.setContentsMargins(24, 24, 24, 24)

        # 标题
        title_label = QLabel("编辑应用")
        title_label.setStyleSheet(f"""
            QLabel {{
                color: {AppStyle.TEXT_PRIMARY};
                font-size: {AppStyle.FONT_SIZE_TITLE}px;
                font-weight: bold;
                padding-bottom: 10px;
            }}
        """)
        layout.addWidget(title_label)

        # 应用名称
        name_layout = QHBoxLayout()
        name_label = QLabel("应用名称:")
        name_label.setMinimumWidth(80)
        name_label.setStyleSheet(f"color: {AppStyle.TEXT_SECONDARY}; font-size: {AppStyle.FONT_SIZE_NORMAL}px;")
        name_layout.addWidget(name_label)

        self.name_input = QLineEdit()
        self.name_input.setText(self.old_name)
        apply_style(self.name_input, "input")
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)

        # 程序路径
        path_layout = QHBoxLayout()
        path_label = QLabel("程序路径:")
        path_label.setMinimumWidth(80)
        path_label.setStyleSheet(f"color: {AppStyle.TEXT_SECONDARY}; font-size: {AppStyle.FONT_SIZE_NORMAL}px;")
        path_layout.addWidget(path_label)

        self.path_input = QLineEdit()
        self.path_input.setText(self.old_path)
        apply_style(self.path_input, "input")
        path_layout.addWidget(self.path_input)

        browse_btn = QPushButton("浏览")
        browse_btn.clicked.connect(self.browse)
        apply_style(browse_btn, "secondary_button")
        browse_btn.setMaximumWidth(70)
        path_layout.addWidget(browse_btn)
        layout.addLayout(path_layout)

        layout.addStretch()

        # 按钮区
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(AppStyle.SPACING_MEDIUM)

        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self.save)
        apply_style(self.save_btn, "primary_button")
        self.save_btn.setMinimumHeight(38)
        btn_layout.addWidget(self.save_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        apply_style(cancel_btn, "secondary_button")
        cancel_btn.setMinimumHeight(38)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

        self.name_input.setFocus()
        self.name_input.selectAll()

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择程序", "", "可执行文件 (*.exe);;所有文件 (*.*)"
        )
        if path:
            self.path_input.setText(path)

    def save(self):
        name = self.name_input.text().strip()
        path = self.path_input.text().strip()

        if not name:
            QMessageBox.warning(self, "错误", "应用名称不能为空")
            return
        if not path:
            QMessageBox.warning(self, "错误", "程序路径不能为空")
            return

        config = load_config()
        apps = config.get("apps", [])

        # 如果修改了名称，检查是否重复
        if name != self.old_name:
            for app in apps:
                if app["name"] == name:
                    QMessageBox.warning(self, "错误", f'应用名称 "{name}" 已存在')
                    return

        # 更新应用
        for app in apps:
            if app["name"] == self.old_name:
                app["name"] = name
                app["path"] = path
                break

        config["apps"] = apps
        save_config(config)
        log_access("local", "/api/apps", f"编辑应用: {self.old_name} -> {name}")

        self.on_save()
        self.accept()


# =========================
# 主窗口
# =========================

class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.logged_in = False
        self.web_running = False
        self.monitor_timer = None
        self.init_ui()
        self.auto_start_web()
        self.load_ip_info()
        self.refresh_logs()
        self.refresh_app_list()

    def init_ui(self):
        self.setWindowTitle("URL Trigger - 应用管理系统")
        self.resize(1100, 850)
        self.setMinimumSize(900, 700)
        apply_style(self, "window")

        # 中心部件 - 使用滚动区域包裹所有内容
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # 滚动区域样式
        scroll_area.setStyleSheet(f"""
            QScrollArea {{
                background-color: {AppStyle.BG_DARK};
                border: none;
            }}
            QScrollBar:vertical {{
                background-color: {AppStyle.BG_DARK};
                width: 12px;
                border-radius: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {AppStyle.BORDER};
                border-radius: 6px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {AppStyle.PRIMARY};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
            QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {{
                border: none;
            }}
        """)

        central_widget = QWidget()
        scroll_area.setWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(AppStyle.SPACING_MEDIUM)
        main_layout.setContentsMargins(AppStyle.SPACING_LARGE, AppStyle.SPACING_MEDIUM,
                                       AppStyle.SPACING_LARGE + 8, AppStyle.SPACING_MEDIUM)

        # 使用分割器允许调整区域大小
        splitter = QSplitter(Qt.Vertical)

        # 上部区域：服务信息 + 服务器控制 + 应用管理
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setSpacing(AppStyle.SPACING_MEDIUM)
        top_layout.setContentsMargins(0, 0, 0, 0)

        # 服务信息卡片
        self.info_card = self.create_info_card()
        top_layout.addWidget(self.info_card)

        # 服务器控制卡片
        self.server_card = self.create_server_card()
        top_layout.addWidget(self.server_card)

        # 应用管理卡片
        self.app_card = self.create_app_card()
        top_layout.addWidget(self.app_card)

        splitter.addWidget(top_widget)

        # 下部区域：日志
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(0, 0, 0, 0)

        self.log_card = self.create_log_card()
        log_layout.addWidget(self.log_card)

        splitter.addWidget(log_widget)

        # 设置分割器比例（给上部更多空间）
        splitter.setSizes([550, 350])
        main_layout.addWidget(splitter)

        self.setCentralWidget(scroll_area)

        # 菜单栏
        self.create_menu()

        # 状态栏
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        apply_style(self.statusbar, "status_bar")
        self.update_status()

    def create_info_card(self):
        """创建服务信息卡片"""
        card = QGroupBox(" 服务信息 ")
        apply_style(card, "groupbox")

        layout = QVBoxLayout(card)
        layout.setSpacing(AppStyle.SPACING_MEDIUM)

        # IP 信息
        self.local_ip_label = QLabel("")
        self.local_ip_label.setStyleSheet(f"""
            QLabel {{
                color: {AppStyle.TEXT_PRIMARY};
                font-size: {AppStyle.FONT_SIZE_NORMAL}px;
                background-color: #2a2a3c;
                padding: 4px 8px;
                border-radius: 4px;
            }}
        """)
        layout.addWidget(self.local_ip_label)

        self.backend_url_label = QLabel("")
        self.backend_url_label.setStyleSheet(f"""
            QLabel {{
                color: {AppStyle.TEXT_PRIMARY};
                font-size: {AppStyle.FONT_SIZE_NORMAL}px;
                background-color: #2a2a3c;
                padding: 4px 8px;
                border-radius: 4px;
            }}
        """)
        layout.addWidget(self.backend_url_label)

        self.server_status_label = QLabel("")
        self.server_status_label.setStyleSheet(f"""
            QLabel {{
                color: {AppStyle.TEXT_SECONDARY};
                font-size: {AppStyle.FONT_SIZE_SMALL}px;
                background-color: #2a2a3c;
                padding: 4px 8px;
                border-radius: 4px;
            }}
        """)
        layout.addWidget(self.server_status_label)

        # 按钮行
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(AppStyle.SPACING_SMALL)

        refresh_ip_btn = QPushButton("刷新IP")
        refresh_ip_btn.clicked.connect(self.load_ip_info)
        apply_style(refresh_ip_btn, "secondary_button")
        refresh_ip_btn.setMinimumHeight(34)
        btn_layout.addWidget(refresh_ip_btn)

        copy_ip_btn = QPushButton("复制局域网IP")
        copy_ip_btn.clicked.connect(self.copy_local_ip)
        apply_style(copy_ip_btn, "secondary_button")
        copy_ip_btn.setMinimumHeight(34)
        btn_layout.addWidget(copy_ip_btn)

        btn_layout.addStretch()

        open_app_page_btn = QPushButton("打开应用启动页")
        open_app_page_btn.clicked.connect(self.open_quick_app_page)
        apply_style(open_app_page_btn, "primary_button")
        open_app_page_btn.setMinimumHeight(34)
        btn_layout.addWidget(open_app_page_btn)

        open_admin_btn = QPushButton("打开管理员页面")
        open_admin_btn.clicked.connect(self.open_browser)
        apply_style(open_admin_btn, "success_button")
        open_admin_btn.setMinimumHeight(34)
        btn_layout.addWidget(open_admin_btn)

        layout.addLayout(btn_layout)

        return card

    def create_server_card(self):
        """创建服务器控制卡片"""
        card = QGroupBox(" Web 服务器控制 ")
        apply_style(card, "groupbox")

        layout = QVBoxLayout(card)
        layout.setSpacing(AppStyle.SPACING_MEDIUM)

        # 端口设置行
        port_layout = QHBoxLayout()

        port_label = QLabel("服务端口:")
        apply_style(port_label, "label")
        port_label.setStyleSheet(f"""
            QLabel {{
                color: {AppStyle.TEXT_PRIMARY};
                font-size: {AppStyle.FONT_SIZE_NORMAL}px;
                background-color: #2a2a3c;
                padding: 4px 8px;
                border-radius: 4px;
            }}
        """)
        port_layout.addWidget(port_label)

        self.port_input = QLineEdit()
        self.port_input.setFixedWidth(80)
        apply_style(self.port_input, "input")
        port_layout.addWidget(self.port_input)

        save_port_btn = QPushButton("保存端口")
        save_port_btn.clicked.connect(self.save_port)
        apply_style(save_port_btn, "primary_button")
        save_port_btn.setMinimumHeight(34)
        port_layout.addWidget(save_port_btn)

        port_hint = QLabel("(修改后需重启服务)")
        port_hint.setStyleSheet(f"""
            QLabel {{
                color: {AppStyle.TEXT_MUTED};
                font-size: {AppStyle.FONT_SIZE_SMALL}px;
                background-color: #2a2a3c;
                padding: 4px 8px;
                border-radius: 4px;
            }}
        """)
        port_layout.addWidget(port_hint)

        port_layout.addStretch()
        layout.addLayout(port_layout)

        # 加载端口配置
        config = load_config()
        self.port_input.setText(str(config.get('port', DEFAULT_PORT)))

        # 控制按钮行
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(AppStyle.SPACING_MEDIUM)

        self.start_btn = QPushButton("启动 Web 服务")
        self.start_btn.clicked.connect(self.start_web)
        apply_style(self.start_btn, "success_button")
        self.start_btn.setMinimumHeight(38)
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("停止 Web 服务")
        self.stop_btn.clicked.connect(self.stop_web)
        self.stop_btn.setEnabled(False)
        apply_style(self.stop_btn, "danger_button")
        self.stop_btn.setMinimumHeight(38)
        btn_layout.addWidget(self.stop_btn)

        layout.addLayout(btn_layout)

        return card

    def create_app_card(self):
        """创建应用管理卡片"""
        card = QGroupBox(" 应用管理 (/open/应用名) ")
        apply_style(card, "groupbox")

        layout = QVBoxLayout(card)
        layout.setSpacing(AppStyle.SPACING_MEDIUM)

        # 添加应用行
        add_layout = QHBoxLayout()
        add_layout.setSpacing(AppStyle.SPACING_SMALL)

        name_label = QLabel("名称:")
        name_label.setStyleSheet(f"""
            QLabel {{
                color: {AppStyle.TEXT_PRIMARY};
                font-size: {AppStyle.FONT_SIZE_NORMAL}px;
                background-color: #2a2a3c;
                padding: 4px 8px;
                border-radius: 4px;
            }}
        """)
        add_layout.addWidget(name_label)

        self.new_app_name_input = QLineEdit()
        self.new_app_name_input.setPlaceholderText("应用名称")
        self.new_app_name_input.setFixedWidth(130)
        apply_style(self.new_app_name_input, "input")
        add_layout.addWidget(self.new_app_name_input)

        path_label = QLabel("路径:")
        path_label.setStyleSheet(f"""
            QLabel {{
                color: {AppStyle.TEXT_PRIMARY};
                font-size: {AppStyle.FONT_SIZE_NORMAL}px;
                background-color: #2a2a3c;
                padding: 4px 8px;
                border-radius: 4px;
            }}
        """)
        add_layout.addWidget(path_label)

        self.new_app_path_input = QLineEdit()
        self.new_app_path_input.setPlaceholderText("程序路径")
        apply_style(self.new_app_path_input, "input")
        add_layout.addWidget(self.new_app_path_input)

        browse_btn = QPushButton("浏览")
        browse_btn.clicked.connect(self.browse_new_app)
        apply_style(browse_btn, "secondary_button")
        browse_btn.setMaximumWidth(70)
        browse_btn.setMinimumHeight(34)
        add_layout.addWidget(browse_btn)

        add_btn = QPushButton("添加")
        add_btn.clicked.connect(self.add_app)
        apply_style(add_btn, "primary_button")
        add_btn.setMinimumHeight(34)
        add_layout.addWidget(add_btn)

        layout.addLayout(add_layout)

        # 应用列表表格（至少展示5行，超出部分内部滚动）
        self.app_table = QTableWidget()
        self.app_table.setColumnCount(3)
        self.app_table.setHorizontalHeaderLabels(["应用名称", "程序路径", "访问URL"])
        self.app_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.app_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.app_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.app_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.app_table.setSelectionMode(QTableWidget.SingleSelection)
        self.app_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.app_table.verticalHeader().setVisible(False)
        # 设置行高以确保至少展示5行：表头约28px，每行约28px，5行=140px，加上表头共约168px
        self.app_table.verticalHeader().setDefaultSectionSize(28)
        self.app_table.setMinimumHeight(170)
        self.app_table.setMaximumHeight(250)
        apply_style(self.app_table, "table")
        layout.addWidget(self.app_table)

        # 操作按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(AppStyle.SPACING_MEDIUM)
        btn_layout.addStretch()

        edit_btn = QPushButton("编辑选中")
        edit_btn.clicked.connect(self.edit_app)
        apply_style(edit_btn, "secondary_button")
        edit_btn.setMinimumHeight(34)
        btn_layout.addWidget(edit_btn)

        delete_btn = QPushButton("删除选中")
        delete_btn.clicked.connect(self.delete_app)
        apply_style(delete_btn, "danger_button")
        delete_btn.setMinimumHeight(34)
        btn_layout.addWidget(delete_btn)

        layout.addLayout(btn_layout)

        return card

    def create_log_card(self):
        """创建日志卡片"""
        card = QGroupBox(" 最近访问记录 ")
        apply_style(card, "groupbox")

        layout = QVBoxLayout(card)
        layout.setSpacing(AppStyle.SPACING_MEDIUM)

        # 统计信息行
        stats_layout = QHBoxLayout()

        self.total_visits_label = QLabel("总访问次数: 0")
        self.total_visits_label.setStyleSheet(f"""
            QLabel {{
                color: {AppStyle.SECONDARY};
                font-size: {AppStyle.FONT_SIZE_NORMAL}px;
                font-weight: bold;
                background-color: #2a2a3c;
                padding: 4px 8px;
                border-radius: 4px;
            }}
        """)
        stats_layout.addWidget(self.total_visits_label)

        stats_layout.addStretch()

        layout.addLayout(stats_layout)

        # 搜索、刷新、实时监控横排分布
        control_layout = QHBoxLayout()
        control_layout.setSpacing(AppStyle.SPACING_MEDIUM)

        # 搜索模块
        search_group = QGroupBox(" 搜索 ")
        apply_style(search_group, "groupbox")
        search_layout = QHBoxLayout(search_group)
        search_layout.setContentsMargins(8, 8, 8, 8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入关键词搜索...")
        apply_style(self.search_input, "input")
        self.search_input.textChanged.connect(self.filter_logs)
        search_layout.addWidget(self.search_input)

        control_layout.addWidget(search_group, 2)

        # 刷新日志模块
        refresh_group = QGroupBox(" 刷新日志 ")
        apply_style(refresh_group, "groupbox")
        refresh_layout = QHBoxLayout(refresh_group)
        refresh_layout.setContentsMargins(8, 8, 8, 8)

        refresh_btn = QPushButton("刷新日志")
        refresh_btn.clicked.connect(self.refresh_logs)
        apply_style(refresh_btn, "secondary_button")
        refresh_btn.setMinimumHeight(34)
        refresh_layout.addWidget(refresh_btn)

        clear_btn = QPushButton("清空日志")
        clear_btn.clicked.connect(self.clear_logs)
        apply_style(clear_btn, "danger_button")
        clear_btn.setMinimumHeight(34)
        refresh_layout.addWidget(clear_btn)

        control_layout.addWidget(refresh_group, 1)

        # 实时监控模块
        monitor_group = QGroupBox(" 实时监控 ")
        apply_style(monitor_group, "groupbox")
        monitor_layout = QHBoxLayout(monitor_group)
        monitor_layout.setContentsMargins(8, 8, 8, 8)

        self.monitor_checkbox = QCheckBox("启用实时监控")
        self.monitor_checkbox.setStyleSheet(f"""
            QCheckBox {{
                color: {AppStyle.TEXT_SECONDARY};
                font-size: {AppStyle.FONT_SIZE_NORMAL}px;
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 2px solid {AppStyle.BORDER};
                border-radius: 4px;
                background-color: {AppStyle.BG_INPUT};
            }}
            QCheckBox::indicator:checked {{
                background-color: {AppStyle.PRIMARY};
                border-color: {AppStyle.PRIMARY};
            }}
            QCheckBox::indicator:hover {{
                border-color: {AppStyle.PRIMARY};
            }}
        """)
        self.monitor_checkbox.toggled.connect(self.toggle_monitor)
        monitor_layout.addWidget(self.monitor_checkbox)

        control_layout.addWidget(monitor_group, 1)

        layout.addLayout(control_layout)

        # 日志表格（至少展示5行，超出部分内部滚动）
        self.log_table = QTableWidget()
        self.log_table.setColumnCount(4)
        self.log_table.setHorizontalHeaderLabels(["时间", "IP", "路径", "操作"])
        self.log_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.log_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.log_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.log_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.log_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.log_table.setSelectionMode(QTableWidget.SingleSelection)
        self.log_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.log_table.verticalHeader().setVisible(False)
        # 设置行高以确保至少展示5行：表头约28px，每行约28px，5行=140px，加上表头共约168px
        self.log_table.verticalHeader().setDefaultSectionSize(28)
        self.log_table.setMinimumHeight(170)
        self.log_table.setMaximumHeight(280)
        apply_style(self.log_table, "table")
        layout.addWidget(self.log_table)

        return card

    def create_menu(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        apply_style(menubar, "menu")

        # 菜单
        menu = menubar.addMenu("菜单")

        login_action = menu.addAction("管理员登录")
        login_action.triggered.connect(self.login)

        menu.addSeparator()

        refresh_action = menu.addAction("刷新日志")
        refresh_action.triggered.connect(self.refresh_logs)

        clear_action = menu.addAction("清空日志")
        clear_action.triggered.connect(self.clear_logs)

        menu.addSeparator()

        exit_action = menu.addAction("退出")
        exit_action.triggered.connect(self.quit)

    # =========================
    # 功能方法
    # =========================

    def auto_start_web(self):
        """自动启动 Web 服务"""
        config = load_config()
        if config.get('auto_start_web', True):
            success, msg = start_web_server()
            if success:
                self.web_running = True
                self.start_btn.setEnabled(False)
                self.stop_btn.setEnabled(True)
                self.update_status()
            else:
                QMessageBox.warning(self, "警告", f"Web 服务启动失败:\n{msg}")

    def start_web(self):
        """手动启动 Web 服务"""
        success, msg = start_web_server()
        if success:
            self.web_running = True
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.update_status()
            self.statusbar.showMessage(f"Web 服务已启动 | {msg}")
        else:
            QMessageBox.critical(self, "错误", msg)

    def stop_web(self):
        """停止 Web 服务"""
        stop_web_server()
        self.web_running = False
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.update_status()
        self.statusbar.showMessage("Web 服务已停止")

    def save_port(self):
        """保存服务端口配置"""
        try:
            new_port = int(self.port_input.text())
            if new_port < 1 or new_port > 65535:
                QMessageBox.critical(self, "错误", "端口号必须在 1-65535 之间")
                return

            config = load_config()
            old_port = config.get('port', DEFAULT_PORT)

            if new_port == old_port:
                self.statusbar.showMessage("端口号未改变")
                return

            config['port'] = new_port
            save_config(config)
            log_access("local", "/config/port", "修改服务端口")

            # 如果服务正在运行，提示用户需要重启
            if self.web_running:
                reply = QMessageBox.question(
                    self, "提示",
                    f"端口已保存为 {new_port}\n需要重启服务才能生效。\n是否立即重启服务？",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    stop_web_server()
                    self.web_running = False
                    success, msg = start_web_server()
                    if success:
                        self.web_running = True
                        self.start_btn.setEnabled(False)
                        self.stop_btn.setEnabled(True)
                        self.update_status()
                        self.load_ip_info()
                        self.statusbar.showMessage(f"服务已重启，新端口: {new_port}")
                    else:
                        QMessageBox.critical(self, "错误", f"服务重启失败:\n{msg}\n请手动重启")
                else:
                    self.statusbar.showMessage("端口已保存，重启服务后生效")
            else:
                self.statusbar.showMessage("端口已保存，启动服务后生效")

            self.load_ip_info()

        except ValueError:
            QMessageBox.critical(self, "错误", "端口号必须是数字")

    def update_status(self):
        """更新状态显示"""
        login_status = "已登录" if self.logged_in else "未登录"
        web_status = "Web服务运行中" if self.web_running else "Web服务未启动"
        self.server_status_label.setText(f"服务器状态: {web_status}")
        self.statusbar.showMessage(f"{login_status} | {web_status}")

    def load_ip_info(self):
        local_ip = get_local_ip()
        config = load_config()
        port = config.get('port', DEFAULT_PORT)
        self.local_ip_label.setText(f"局域网IP: {local_ip}")
        self.backend_url_label.setText(f"后台网址: http://{local_ip}:{port}/admin")
        self.update_status()

    def copy_backend_url(self):
        local_ip = get_local_ip()
        config = load_config()
        port = config.get('port', DEFAULT_PORT)
        url = f"http://{local_ip}:{port}/admin"
        pyperclip.copy(url)
        self.statusbar.showMessage(f"已复制后台网址: {url}")

    def copy_local_ip(self):
        ip = get_local_ip()
        pyperclip.copy(ip)
        self.statusbar.showMessage(f"已复制局域网IP: {ip}")

    def browse_new_app(self):
        """浏览选择新应用的路径"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择程序", "", "可执行文件 (*.exe);;所有文件 (*.*)"
        )
        if path:
            self.new_app_path_input.setText(path)

    def add_app(self):
        """添加新应用"""
        name = self.new_app_name_input.text().strip()
        path = self.new_app_path_input.text().strip()

        if not name:
            QMessageBox.warning(self, "错误", "应用名称不能为空")
            return
        if not path:
            QMessageBox.warning(self, "错误", "程序路径不能为空")
            return

        config = load_config()
        apps = config.get("apps", [])

        # 检查名称是否重复
        for app in apps:
            if app["name"] == name:
                QMessageBox.warning(self, "错误", f'应用名称 "{name}" 已存在')
                return

        apps.append({"name": name, "path": path})
        config["apps"] = apps
        save_config(config)
        log_access("local", "/api/apps", f"添加应用: {name}")
        self.statusbar.showMessage(f"应用 '{name}' 已添加")
        self.new_app_name_input.clear()
        self.new_app_path_input.clear()
        self.refresh_app_list()

    def delete_app(self):
        """删除选中的应用"""
        selection = self.app_table.selectedItems()
        if not selection:
            QMessageBox.warning(self, "提示", "请先选择要删除的应用")
            return

        row = selection[0].row()
        name = self.app_table.item(row, 0).text()

        reply = QMessageBox.question(self, "确认", f"确定删除应用 '{name}'？")
        if reply == QMessageBox.No:
            return

        config = load_config()
        apps = config.get("apps", [])
        apps = [app for app in apps if app["name"] != name]
        config["apps"] = apps
        save_config(config)
        log_access("local", "/api/apps", f"删除应用: {name}")
        self.statusbar.showMessage(f"应用 '{name}' 已删除")
        self.refresh_app_list()

    def edit_app(self):
        """编辑选中的应用"""
        selection = self.app_table.selectedItems()
        if not selection:
            QMessageBox.warning(self, "提示", "请先选择要编辑的应用")
            return

        try:
            row = selection[0].row()
            name_item = self.app_table.item(row, 0)
            path_item = self.app_table.item(row, 1)

            if name_item is None or path_item is None:
                QMessageBox.warning(self, "错误", "无法读取选中行数据")
                return

            old_name = name_item.text()
            old_path = path_item.text()

            dialog = EditAppDialog(self, old_name, old_path, self.refresh_app_list)
            dialog.raise_()
            dialog.activateWindow()
            result = dialog.exec()

            if result == QDialog.Accepted:
                self.statusbar.showMessage("编辑成功")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"编辑应用时出错: {str(e)}")

    def refresh_app_list(self):
        """刷新应用列表"""
        self.app_table.setRowCount(0)
        config = load_config()
        apps = config.get("apps", [])
        port = config.get("port", DEFAULT_PORT)
        local_ip = get_local_ip()

        for i, app in enumerate(apps):
            url = f"http://{local_ip}:{port}/open/{app['name']}"
            self.app_table.insertRow(i)
            self.app_table.setItem(i, 0, QTableWidgetItem(app["name"]))
            self.app_table.setItem(i, 1, QTableWidgetItem(app["path"]))
            self.app_table.setItem(i, 2, QTableWidgetItem(url))

    def open_browser(self):
        """在浏览器中打开后台地址"""
        import webbrowser
        local_ip = get_local_ip()
        config = load_config()
        port = config.get('port', DEFAULT_PORT)
        url = f"http://{local_ip}:{port}/admin"
        webbrowser.open(url)
        log_access("local", "/open_browser", "打开浏览器访问后台")
        self.statusbar.showMessage(f"已在浏览器打开: {url}")

    def open_quick_app_page(self):
        """在浏览器中打开快捷应用启动页"""
        import webbrowser
        local_ip = get_local_ip()
        config = load_config()
        port = config.get('port', DEFAULT_PORT)
        url = f"http://{local_ip}:{port}/open"
        webbrowser.open(url)
        log_access("local", "/open_browser", "打开快捷应用启动页")
        self.statusbar.showMessage(f"已在浏览器打开: {url}")

    def clear_logs(self):
        reply = QMessageBox.question(self, "确认", "确定清空所有访问日志?")
        if reply == QMessageBox.Yes:
            save_logs([])
            self.statusbar.showMessage("日志已清空")
            self.refresh_logs()

    def filter_logs(self):
        """根据搜索关键词过滤日志"""
        keyword = self.search_input.text().lower()
        for row in range(self.log_table.rowCount()):
            row_text = ""
            for col in range(self.log_table.columnCount()):
                item = self.log_table.item(row, col)
                if item:
                    row_text += item.text() + " "

            if keyword and keyword not in row_text.lower():
                self.log_table.setRowHidden(row, True)
            else:
                self.log_table.setRowHidden(row, False)

    def toggle_monitor(self):
        """切换实时监控状态"""
        if self.monitor_checkbox.isChecked():
            self.start_monitor()
        else:
            self.stop_monitor()

    def start_monitor(self):
        """启动实时监控"""
        self.refresh_logs()
        self.monitor_timer = QTimer(self)
        self.monitor_timer.timeout.connect(self.refresh_logs)
        self.monitor_timer.start(3000)

    def stop_monitor(self):
        """停止实时监控"""
        if self.monitor_timer:
            self.monitor_timer.stop()
            self.monitor_timer = None

    def refresh_logs(self):
        """刷新最近 20 条日志"""
        self.log_table.setRowCount(0)
        logs = load_logs()
        # 更新总访问次数
        self.total_visits_label.setText(f"总访问次数: {len(logs)}")

        for i, log in enumerate(reversed(logs[-20:])):
            self.log_table.insertRow(i)
            self.log_table.setItem(i, 0, QTableWidgetItem(log["time"]))
            self.log_table.setItem(i, 1, QTableWidgetItem(log["ip"]))
            self.log_table.setItem(i, 2, QTableWidgetItem(log["path"]))
            self.log_table.setItem(i, 3, QTableWidgetItem(log["action"]))

    def login(self):
        if self.logged_in:
            self.statusbar.showMessage("已处于登录状态")
            return
        dialog = LoginDialog(self)
        dialog.success_callback = self.on_login_success
        if dialog.exec() == QDialog.Accepted:
            self.on_login_success()

    def on_login_success(self):
        self.logged_in = True
        self.update_status()
        QMessageBox.information(self, "登录成功", "管理员登录成功")

    def quit(self):
        reply = QMessageBox.question(self, "退出", "确定退出程序?")
        if reply == QMessageBox.Yes:
            if self.web_running:
                stop_web_server()
            self.close()

    def closeEvent(self, event):
        """窗口关闭事件"""
        if self.web_running:
            stop_web_server()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # 使用 Fusion 风格
    main_window = MainApp()
    main_window.show()
    sys.exit(app.exec())
