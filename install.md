# 安装与启动说明

本文档记录本项目三个主要服务的环境安装和启动命令：

- `api`: FastAPI 后端服务
- `web_admin`: Vue 管理后台
- `automation_client`: Appium/ADB 自动化客户端

以下命令默认在项目根目录 `E:\auto_fans` 执行。

## 1. 前置依赖

本机需要先安装：

- Python 3.11
- Node.js / npm
- MySQL
- ADB / Android platform-tools
- Appium
- Git Bash

当前已确认可用的 Python 路径：

```powershell
C:\Users\liufu\AppData\Local\Programs\Python\Python311\python.exe
```

## 2. 安装环境

### 2.1 安装 api 后端环境

```powershell
cd E:\auto_fans\api
C:\Users\liufu\AppData\Local\Programs\Python\Python311\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

### 2.2 安装 web_admin 前端环境

```powershell
cd E:\auto_fans\web_admin
npm install
```

### 2.3 安装 automation_client 自动化客户端环境

```powershell
cd E:\auto_fans\automation_client
C:\Users\liufu\AppData\Local\Programs\Python\Python311\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## 3. 分别启动三个服务

建议分别打开三个 PowerShell 窗口启动。

### 3.1 启动 api

```powershell
cd E:\auto_fans\api
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

后端地址：

```text
http://127.0.0.1:8000/api
```

接口文档：

```text
http://127.0.0.1:8000/api/docs
```

### 3.2 启动 web_admin

```powershell
cd E:\auto_fans\web_admin
npm run dev -- --host 127.0.0.1 --port 5173
```

前端地址：

```text
http://127.0.0.1:5173
```

### 3.3 启动 automation_client

```powershell
cd E:\auto_fans\automation_client
.\.venv\Scripts\python.exe -m app.main --api-base-url http://127.0.0.1:8000/api --appium-server-url http://127.0.0.1:4723 --adb-path adb
```

如果需要由客户端按需启动 Appium Server：

```powershell
cd E:\auto_fans\automation_client
.\.venv\Scripts\python.exe -m app.main --api-base-url http://127.0.0.1:8000/api --appium-server-url http://127.0.0.1:4723 --adb-path adb --manage-appium-servers --appium-batch-size 2
```

本地单轮调试某台设备：

```powershell
cd E:\auto_fans\automation_client
.\.venv\Scripts\python.exe -m app.main --once --device UDID,device_01,8201,发布账号 --api-base-url http://127.0.0.1:8000/api --appium-server-url http://127.0.0.1:4723 --adb-path adb
```

## 4. 一键启动与停止

项目已有一键脚本，会启动 `api`、`web_admin`、`automation_client`，并默认使用 Appium on-demand 模式。

启动：

```powershell
cd E:\auto_fans
.\scripts\start_all.ps1
```

停止：

```powershell
cd E:\auto_fans
.\scripts\finish_all.ps1
```

如果使用打包后的 Windows 启动器：

```powershell
cd E:\auto_fans
.\AutoFans.exe
```

只检查状态：

```powershell
cd E:\auto_fans
.\AndroidAutoStart.exe --status-only
```

## 5. 重新打包 Windows 启动器

桌面客户端打包后输出为：

```text
AutoFans.exe
```

重新生成图标：

```powershell
cd E:\auto_fans
.\automation_client\.venv\Scripts\python.exe .\tools\generate_autofans_icon.py
```

重新打包并复制 exe 到根目录：

```powershell
cd E:\auto_fans
.\launcher\build_exe.ps1 -CopyToRoot
```

## 6. 常用检查命令

检查 api 测试：

```powershell
cd E:\auto_fans\api
.\.venv\Scripts\python.exe -m pytest -q
```

检查 automation_client 测试：

```powershell
cd E:\auto_fans\automation_client
.\.venv\Scripts\python.exe -m pytest -q
```

检查 web_admin 类型与构建：

```powershell
cd E:\auto_fans\web_admin
npm run typecheck
npm run build
```
