import os
import subprocess
import sys
import threading
import time
import socket
import winreg as reg
from flask import Flask
from pystray import Icon, MenuItem, Menu
from PIL import Image, ImageDraw
import requests  # 用于获取因特网 IP 地址
import pyperclip  # 用于复制到剪切板

# Flask 应用部分
app = Flask(__name__)

@app.route('/')
def home():
    return "<h1>本地启动服务已运行</h1>"

@app.route('/open')
def open_target_app():
    """启动指定应用"""
    APP_PATH = r"E:\实用工具\右键管理ContextMenuManager.exe"  # 需要启动的应用路径
    subprocess.Popen(APP_PATH)
    return "<h2>应用已启动</h2>"

# 使用本地的 icon.png 图标
def create_icon_image():
    """从本地文件加载图标"""
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
    return Image.open(icon_path)

def on_quit(icon, item):
    """退出托盘图标和 Flask 服务"""
    icon.stop()
    os._exit(0)

# 获取电脑的局域网 IP 地址（可选）
def get_local_ip():
    """获取本机局域网 IP 地址"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        s.connect(('10.254.254.254', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

# 获取当前因特网 IP 地址
def get_internet_ip():
    """通过访问公共服务获取因特网 IP 地址"""
    try:
        response = requests.get('https://api.ipify.org?format=json')
        return response.json()['ip']
    except requests.exceptions.RequestException as e:
        print(f"Error getting internet IP: {e}")
        return "无法获取IP"

# 将因特网 IP 地址复制到剪切板
def copy_ip_to_clipboard(icon, item):
    """将因特网 IP 地址复制到剪切板"""
    internet_ip = get_internet_ip()  # 获取因特网 IP
    pyperclip.copy(internet_ip)  # 复制到剪切板
    print(f"已将 IP 地址 {internet_ip} 复制到剪切板")
    icon.notify(f"已将 IP 地址 {internet_ip} 复制到剪切板")  # 可选，显示通知

# 启动 Flask 服务
def start_flask():
    """启动 Flask 服务，绑定到局域网 IP 地址"""
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

# 创建注册表的自启动项
def set_autostart(enable):
    """设置或取消开机自启动"""
    key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "MyApp"  # 自启动项的名称
    bat_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Start_App.bat")  # 指定Start_App.bat路径

    # 打开注册表并编辑
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, key, 0, reg.KEY_WRITE) as registry_key:
            if enable:
                reg.SetValueEx(registry_key, app_name, 0, reg.REG_SZ, bat_path)
            else:
                reg.DeleteValue(registry_key, app_name)
    except Exception as e:
        print(f"Error while setting autostart: {e}")

# 检查自启动是否已启用
def is_autostart_enabled():
    """检查当前是否启用了开机自启动"""
    key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "MyApp"
    
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, key) as registry_key:
            value, _ = reg.QueryValueEx(registry_key, app_name)
            return True if value else False
    except FileNotFoundError:
        return False

# 右键菜单回调：切换开机自启动
def toggle_autostart(icon, item):
    """切换开机自启动"""
    is_enabled = is_autostart_enabled()
    set_autostart(not is_enabled)  # 切换状态
    # 更新菜单显示
    icon.menu = create_tray_menu(not is_enabled)
    print(f"开机自启动已{'启用' if not is_enabled else '禁用'}")

# 创建托盘菜单
def create_tray_menu(is_autostart_enabled):
    """创建托盘右键菜单"""
    menu_items = [
        MenuItem('退出', on_quit),
        MenuItem(f"{'☑︎已启用' if is_autostart_enabled else '🔲未启用'}开机自启动", toggle_autostart),
        MenuItem('复制当前IP地址到剪切板', copy_ip_to_clipboard)  # 新增的菜单项
    ]
    return Menu(*menu_items)

# 启动托盘图标
def create_tray():
    """启动系统托盘图标"""
    # 获取当前是否启用了自启动
    is_enabled = is_autostart_enabled()
    icon_image = create_icon_image()  # 加载图标图片
    icon = Icon("test", icon_image, menu=create_tray_menu(is_enabled))
    icon.run()

# 启动 Flask 服务和系统托盘图标
if __name__ == '__main__':
    # 打印电脑的局域网 IP 地址，方便手机访问
    local_ip = get_local_ip()
    print(f"请在手机浏览器中访问: http://{local_ip}:5000/open")

    # 在后台启动 Flask 服务
    flask_thread = threading.Thread(target=start_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # 启动系统托盘图标
    create_tray()
