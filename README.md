# URL Trigger - 基于 URL 的远程应用启动系统

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.0+-green.svg)](https://flask.palletsprojects.com/)
[![PySide6](https://img.shields.io/badge/PySide6-6.5+-lightgrey.svg)](https://doc.qt.io/qtforpython/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 项目简介

URL Trigger 是一个基于 Python 的桌面应用管理系统，允许您通过局域网内的 URL 远程启动 Windows 应用程序。它结合了 PySide6 桌面客户端和 Flask Web 管理后台，提供了一个现代化的应用管理解决方案。

### 核心功能

- **远程应用启动** - 通过访问特定 URL (如 `http://ip:port/open/应用名`) 远程启动任何已配置的应用程序
- **双端管理界面** - 提供 PySide6 桌面客户端和 Flask Web 管理后台两种管理方式
- **应用集中管理** - 轻松添加、编辑、删除可远程启动的应用程序
- **访问日志记录** - 完整记录所有访问和操作日志，支持实时监控和搜索
- **安全认证机制** - 管理员登录认证 + 备用密码重置机制
- **自动启动服务** - 支持 Web 服务开机自启动
- **现代 UI 设计** - 暗色主题界面，响应式布局设计

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    URL Trigger 系统                      │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────┐              ┌──────────────────┐    │
│  │ PySide6 GUI  │              │  Flask Web Server│    │
│  │  桌面客户端   │◄────同步────►│   管理后台        │    │
│  └──────────────┘              └──────────────────┘    │
│         │                              │               │
│         ▼                              ▼               │
│  ┌──────────────┐              ┌──────────────────┐    │
│  │ config.json  │              │    logs.json     │    │
│  │  配置文件     │              │    日志文件       │    │
│  └──────────────┘              └──────────────────┘    │
│                                                         │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │  局域网设备访问       │
              │  /open/应用名        │
              │  /admin 管理后台     │
              └──────────────────────┘
```

## 功能特性

### 桌面客户端 (PySide6)

- 应用管理和配置界面
- Web 服务启动/停止控制
- 端口配置和自动启动设置
- 实时日志监控和搜索
- 应用列表管理（添加/编辑/删除）
- 局域网 IP 显示和复制

### Web 管理后台 (Flask)

**数据概览**
- 局域网 IP 地址显示
- 服务端口和访问统计
- 最近访问记录

**访问日志**
- 完整访问记录查看
- 日志搜索过滤
- 日志清空功能

**应用管理**
- 添加新应用（名称 + 程序路径）
- 编辑现有应用
- 删除应用
- 应用访问地址展示

**系统设置**
- 服务端口修改
- 自动启动开关
- Web 服务启停控制
- 管理员密码修改
- 备用密码查看

### 应用启动页

- 所有可用应用展示
- 一键启动应用
- 访问链接复制

## 快速开始

### 环境要求

- **操作系统**: Windows 10/11
- **Python**: 3.8 或更高版本
- **网络**: 局域网环境（用于远程访问）

### 安装步骤

1. **克隆项目**

```bash
git clone https://github.com/your-username/url-trigger.git
cd url-trigger
```

2. **安装依赖**

```bash
pip install -r requirements.txt
```

依赖包包括：
- `flask>=2.0.0` - Web 框架
- `requests>=2.25.0` - HTTP 请求库
- `pyperclip>=1.8.0` - 剪贴板操作
- `PySide6>=6.5.0` - GUI 框架

3. **启动应用**

```bash
python "URL Trigger.pyw"
```

### 默认配置

- **管理员账号**: `admin`
- **默认密码**: `admin123`
- **备用密码**: `Administrator`
- **默认端口**: `5000` (可通过配置修改)

> **重要**: 首次启动后请立即修改默认密码以确保安全！

## 使用指南

### 方式一：使用桌面客户端

1. 运行 `URL Trigger.pyw` 启动桌面客户端
2. 输入管理员密码登录（默认: `admin123`）
3. Web 服务会自动启动（可通过配置关闭）
4. 在"应用管理"区域添加应用：
   - 输入应用名称（如 `notepad`）
   - 选择程序路径（如 `C:\Windows\notepad.exe`）
   - 点击"添加"按钮
5. 复制显示的 URL 或在浏览器中打开

### 方式二：使用 Web 管理后台

1. 在浏览器中访问 `http://your-ip:port/admin`
2. 使用管理员账号登录
3. 在"应用管理"页面添加和管理应用
4. 查看访问日志和系统统计

### 远程启动应用

在局域网内的任何设备上访问：

```
http://your-ip:port/open/应用名
```

例如：
- `http://192.168.1.100:8080/open/飞书` - 启动飞书
- `http://192.168.1.100:8080/open/八爪鱼` - 启动八爪鱼 RPA

### 应用启动页

访问 `http://your-ip:port/open` 可以看到所有可用应用的启动面板。

## 项目结构

```
URL Trigger/
├── URL Trigger.pyw       # 主程序文件（PySide6 + Flask）
├── config.json           # 配置文件（应用、密码、端口等）
├── logs.json             # 访问日志文件
├── requirements.txt      # Python 依赖列表
├── icon.png              # 应用图标
├── icon.ico              # Windows 图标
└── templates/            # Web 模板目录
    ├── admin.html        # 管理后台页面
    ├── login.html        # 登录页面
    └── open.html         # 应用启动页
```

## 配置说明

### config.json 配置文件

```json
{
    "apps": [
        {
            "name": "应用名称",
            "path": "程序完整路径"
        }
    ],
    "admin_password": "管理员密码",
    "port": 8080,
    "auto_start_web": true,
    "secret_key": "Flask 会话密钥"
}
```

**配置项说明：**
- `apps` - 可远程启动的应用列表
- `admin_password` - Web 管理后台密码
- `port` - Web 服务监听端口
- `auto_start_web` - 是否自动启动 Web 服务
- `secret_key` - Flask 会话加密密钥（自动生成）

## API 接口

### 认证相关

- `POST /login` - 管理员登录
- `GET /logout` - 退出登录
- `GET /api/check_login` - 检查登录状态

### 应用管理

- `GET /api/apps` - 获取应用列表
- `POST /api/apps` - 添加应用
- `PUT /api/apps/<app_name>` - 更新应用
- `DELETE /api/apps/<app_name>` - 删除应用

### 日志管理

- `GET /api/logs` - 获取访问日志
- `DELETE /api/logs` - 清空日志

### 系统配置

- `POST /api/config/port` - 修改服务端口
- `POST /api/config/auto_start` - 修改自动启动设置
- `POST /api/change_password` - 修改管理员密码

### 服务控制

- `POST /api/server/start` - 启动 Web 服务
- `POST /api/server/stop` - 停止 Web 服务

## 安全说明

1. **密码安全**
   - 首次使用后立即修改默认密码
   - 定期更换管理员密码
   - 妥善保管备用密码

2. **网络安全**
   - 仅在可信的局域网环境中使用
   - 建议使用防火墙限制端口访问
   - 不要将服务暴露到公网

3. **应用权限**
   - 只添加可信的应用程序
   - 谨慎授予高权限程序的远程访问

## 打包为可执行文件

使用 PyInstaller 打包为独立的 Windows 可执行文件：

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --icon=icon.ico "URL Trigger.pyw"
```

打包后的 exe 文件可以独立运行，无需安装 Python 环境。

## 常见问题

**Q: Web 服务无法启动？**
A: 检查端口是否被占用，可在配置文件中修改端口号。

**Q: 忘记密码怎么办？**
A: 使用备用密码 `Administrator` 进行验证重置，或直接修改 `config.json` 中的 `admin_password`。

**Q: 如何修改默认端口？**
A: 在桌面客户端的"服务端口"处修改并保存，或直接编辑 `config.json` 文件。

**Q: 可以从外网访问吗？**
A: 本项目设计为局域网使用。如需外网访问，请配置端口转发或使用内网穿透工具，但务必做好安全防护。

## 技术栈

- **后端**: Python 3, Flask
- **前端**: PySide6 (Qt6), HTML5, CSS3, JavaScript
- **数据存储**: JSON 文件
- **网络**: HTTP/REST API

## 开发计划

- [ ] 支持 Linux/macOS 系统
- [ ] 添加定时任务功能
- [ ] 支持应用分组和标签
- [ ] 增加更多统计图表
- [ ] 支持 HTTPS 加密连接
- [ ] 移动端适配

## 许可证

本项目仅供学习和研究使用。

## 作者

URL Trigger 开发者

---

如果这个项目对您有帮助，欢迎给一个 Star ⭐
