# Browser Server Windows 部署方案

基于 Playwright + FastAPI 的浏览器自动化服务，为 OpenClawd 提供 HTTP API 接口。

## 架构设计

```
┌─────────────────┐      HTTP API       ┌─────────────────────────┐
│   OpenClawd     │  ◄───────────────►  │   Browser Server        │
│   (Linux/Mac)   │                     │   (Windows)             │
│                 │   POST /navigate    │   ┌─────────────────┐   │
│   system.run    │   POST /evaluate    │   │  Playwright     │   │
│   fetch tool    │   GET  /text        │   │  + Chromium     │   │
│                 │   POST /screenshot  │   └─────────────────┘   │
└─────────────────┘                     └─────────────────────────┘
           │                                       │
           │        Windows 192.168.31.120:3456    │
           └───────────────────────────────────────┘
```

## 功能特性

- ✅ **页面导航** - 支持 networkidle 等待动态内容
- ✅ **JavaScript 执行** - 获取 X/Twitter 等 SPA 内容
- ✅ **智能等待** - 等待元素/文本出现
- ✅ **全页截图** - 支持 60 秒超长超时
- ✅ **点击输入** - 自动化交互
- ✅ **REST API** - 简单 HTTP 调用
- ✅ **Cookie 持久化** - 复用已登录会话
- ✅ **可见浏览器登录** - 先登录再由 OpenClawd 控制

---

## 一、环境准备

### 1.1 安装 Python

```powershell
# 方式1：使用 winget（推荐）
winget install Python.Python.3.12

# 方式2：官网下载
# https://www.python.org/downloads/windows/
# 安装时勾选 "Add Python to PATH"
```

验证安装：
```powershell
python --version
# Python 3.12.x
```

### 1.2 创建项目目录

```powershell
mkdir C:\BrowserServer
cd C:\BrowserServer

# 创建虚拟环境（推荐）
python -m venv venv
venv\Scripts\activate
```

---

## 二、安装依赖

### 2.1 requirements.txt

创建 `C:\BrowserServer\requirements.txt`：

```txt
fastapi==0.115.0
uvicorn[standard]==0.32.0
playwright==1.49.0
pydantic==2.9.0
python-multipart==0.0.12
pillow==11.0.0
```

### 2.2 安装

```powershell
cd C:\BrowserServer
venv\Scripts\activate

pip install -r requirements.txt

# 安装 Chromium 浏览器（关键！）
playwright install chromium

# 验证安装
playwright --version
```

---

## 三、核心代码

### 3.1 browser_server.py

使用仓库内的 `browser_server.py`（`D:\Code\browser_user\browser_server.py`），或复制到 `C:\BrowserServer` 目录运行。

可用环境变量：

```txt
BROWSER_HOST=0.0.0.0
BROWSER_PORT=3456
BROWSER_USER_DATA_DIR=C:\BrowserServer\user_data
BROWSER_HEADLESS=false
BROWSER_AUTO_START=true
```

---

## 四、启动脚本

### 4.1 开发启动 (start.bat)

使用仓库内的 `start.bat`（`D:\Code\browser_user\start.bat`），或复制到 `C:\BrowserServer` 后运行。

```bat
@echo off
chcp 65001
cls

set ROOT=%~dp0
cd /d %ROOT%

if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate
) else (
    echo Virtual environment not found
    pause
    exit /b 1
)

set BROWSER_HOST=0.0.0.0
set BROWSER_PORT=3456
set BROWSER_USER_DATA_DIR=%ROOT%user_data
set BROWSER_HEADLESS=false

python browser_server.py

pause
```

### 4.2 生产部署（使用 PM2）

```powershell
npm install -g pm2
```

使用仓库内的 `ecosystem.config.js`（`D:\Code\browser_user\ecosystem.config.js`），或复制到 `C:\BrowserServer` 后运行：

```javascript
module.exports = {
  apps: [{
    name: "browser-server",
    script: "./browser_server.py",
    interpreter: "python",
    cwd: "C:\\BrowserServer",
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: "2G",
    env: {
      BROWSER_HOST: "0.0.0.0",
      BROWSER_PORT: "3456",
      BROWSER_USER_DATA_DIR: "C:\\BrowserServer\\user_data",
      BROWSER_HEADLESS: "true",
      PYTHONUNBUFFERED: "1"
    },
    windowsHide: false,
    log_file: "C:\\BrowserServer\\logs\\combined.log",
    out_file: "C:\\BrowserServer\\logs\\out.log",
    err_file: "C:\\BrowserServer\\logs\\error.log",
    log_date_format: "YYYY-MM-DD HH:mm:ss Z"
  }]
};
```

```powershell
# 创建日志目录
mkdir C:\BrowserServer\logs

# 启动服务
pm2 start ecosystem.config.js

# 查看状态
pm2 status
pm2 logs browser-server

# 开机自启
pm2 startup
pm2 save

# 管理命令
pm2 stop browser-server      # 停止
pm2 restart browser-server   # 重启
pm2 delete browser-server    # 删除
```

### 4.3 Windows 服务（替代方案）

如果不想用 PM2，使用 Windows Service：

```powershell
# 使用 nssm 创建服务
# 1. 下载 nssm: https://nssm.cc/download
# 2. 创建服务

nssm install BrowserServer
# Path: C:\BrowserServer\venv\Scripts\python.exe
# Startup directory: C:\BrowserServer
# Arguments: browser_server.py

nssm start BrowserServer
```

---

### 4.4 Cookie 保留与登录流程

1. 使用可见模式启动服务：`BROWSER_HEADLESS=false`
2. 在弹出的浏览器里完成登录
3. 保持服务运行，或停止后用相同 `BROWSER_USER_DATA_DIR` 重启
4. OpenClawd 继续通过 API 操作已登录会话

## 五、测试验证

### 5.1 服务启动测试

```powershell
# 启动服务后测试
curl http://localhost:3456/

# 预期输出
{"service":"Browser Server","version":"1.1.0","status":"running",...}
```

### 5.2 API 测试

```powershell
# 测试1: 健康检查
curl http://localhost:3456/health

# 测试2: 导航到百度
curl -X POST http://localhost:3456/navigate `
  -H "Content-Type: application/json" `
  -d '{"url":"https://www.baidu.com","extra_wait_ms":2000}'

# 测试3: 获取文本
curl http://localhost:3456/text

# 测试4: 截图
curl -X POST http://localhost:3456/screenshot `
  -H "Content-Type: application/json" `
  -d '{"full_page":true}' > screenshot.json

# 解码 base64 图片
# (在 PowerShell 中)
$response = Invoke-RestMethod -Uri "http://localhost:3456/screenshot" -Method POST `
  -ContentType "application/json" -Body '{"full_page":true}'
[System.Convert]::FromBase64String($response.image_base64) | `
  Set-Content screenshot.png -Encoding Byte
```

### 5.3 X/Twitter 动态内容测试

```powershell
# 测试获取 X 热门话题

# 1. 导航
curl -X POST http://localhost:3456/navigate `
  -H "Content-Type: application/json" `
  -d '{"url":"https://x.com/explore/tabs/trending","wait_until":"networkidle","extra_wait_ms":5000}'

# 2. 等待推文元素
curl -X POST http://localhost:3456/wait `
  -H "Content-Type: application/json" `
  -d '{"selector":"article[data-testid=\"tweet\"]","timeout":30000}'

# 3. 执行 JS 获取内容
curl -X POST http://localhost:3456/evaluate `
  -H "Content-Type: application/json" `
  -d '{"script":"() => Array.from(document.querySelectorAll('\"'"'article[data-testid=tweet]'"'"')).slice(0,5).map(t => t.textContent.substring(0,200))"}'

# 4. 截图
curl -X POST http://localhost:3456/screenshot `
  -H "Content-Type: application/json" `
  -d '{"full_page":true}'
```

---

## 六、OpenClawd 集成

### 6.1 配置环境变量

在 OpenClawd 主节点（Linux/Mac）：

```bash
# ~/.bashrc 或 ~/.zshrc
export BROWSER_SERVER_URL="http://192.168.31.120:3456"
```

### 6.2 使用 system.run 调用

```json
{
  "tool": "system.run",
  "params": {
    "command": "curl",
    "args": [
      "-s", "-X", "POST",
      "http://192.168.31.120:3456/navigate",
      "-H", "Content-Type: application/json",
      "-d", "{\"url\":\"https://x.com/explore/tabs/trending\",\"wait_until\":\"networkidle\",\"extra_wait_ms\":5000}"
    ],
    "timeout": 70000
  }
}
```

### 6.3 使用 fetch 工具调用

```json
{
  "tool": "fetch",
  "params": {
    "url": "http://192.168.31.120:3456/navigate",
    "method": "POST",
    "headers": {
      "Content-Type": "application/json"
    },
    "body": {
      "url": "https://x.com/explore/tabs/trending",
      "wait_until": "networkidle",
      "extra_wait_ms": 5000
    }
  }
}
```

### 6.4 完整工作流示例

**获取 X 热门话题的完整流程**：

```json
// 步骤 1: 导航到 X
{
  "tool": "fetch",
  "params": {
    "url": "http://192.168.31.120:3456/navigate",
    "method": "POST",
    "headers": {"Content-Type": "application/json"},
    "body": {
      "url": "https://x.com/explore/tabs/trending",
      "wait_until": "networkidle",
      "extra_wait_ms": 5000
    }
  }
}

// 步骤 2: 等待推文加载
{
  "tool": "fetch",
  "params": {
    "url": "http://192.168.31.120:3456/wait",
    "method": "POST",
    "headers": {"Content-Type": "application/json"},
    "body": {
      "selector": "article[data-testid='tweet']",
      "timeout": 30000
    }
  }
}

// 步骤 3: 执行 JS 获取热门话题
{
  "tool": "fetch",
  "params": {
    "url": "http://192.168.31.120:3456/evaluate",
    "method": "POST",
    "headers": {"Content-Type": "application/json"},
    "body": {
      "script": "() => {\n        const trends = [];\n        document.querySelectorAll('[data-testid=\"trend\"]').forEach(el => {\n          const text = el.textContent?.trim();\n          if (text && text.length > 5) trends.push(text);\n        });\n        return trends.slice(0, 10);\n      }"
    }
  }
}

// 步骤 4: 截图
{
  "tool": "fetch",
  "params": {
    "url": "http://192.168.31.120:3456/screenshot",
    "method": "POST",
    "headers": {"Content-Type": "application/json"},
    "body": {
      "full_page": true,
      "timeout": 60000
    }
  }
}
```

---

## 七、常见问题

### 7.1 Chromium 安装失败

```powershell
# 如果 playwright install chromium 失败，手动安装
python -m playwright install --with-deps chromium

# 或者指定镜像
set PLAYWRIGHT_BROWSERS_PATH=0
playwright install chromium
```

### 7.2 端口占用

```powershell
# 检查端口占用
netstat -ano | findstr :3456

# 更换端口（修改环境变量）
set BROWSER_PORT=3457
```

### 7.3 内存不足

```powershell
# 减少并发，单实例运行
# 在 ecosystem.config.js 中设置
max_memory_restart: '1G'
```

### 7.4 被网站反爬

```powershell
# 方案1: 使用已登录会话
# 设置 BROWSER_HEADLESS=false 登录后复用 user_data_dir

# 方案2: 使用代理
# 在启动参数中添加代理配置
```

---

## 八、API 参考

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 服务状态 |
| GET | `/health` | 健康检查 |
| POST | `/start` | 启动浏览器 |
| POST | `/stop` | 关闭浏览器 |
| POST | `/navigate` | 导航到URL |
| POST | `/evaluate` | 执行JavaScript |
| GET | `/text` | 获取页面文本 |
| POST | `/screenshot` | 截图 |
| POST | `/wait` | 等待元素/文本 |
| POST | `/click` | 点击元素 |
| POST | `/type` | 输入文本 |
| POST | `/scroll` | 滚动页面 |
| POST | `/storage/export` | 导出登录状态 |
| POST | `/connect` | 连接本机 Chrome |

`/start` 请求体示例：

```json
{
  "headless": false,
  "user_data_dir": "C:\\BrowserServer\\user_data",
  "cdp_url": "http://127.0.0.1:9222"
}
```

---

## 九、文件清单

```
C:\BrowserServer\
├── venv\                      # Python 虚拟环境
├── browser_server.py          # 主服务代码
├── requirements.txt           # Python 依赖
├── start.bat                  # 开发启动脚本
├── ecosystem.config.js        # PM2 生产配置
├── logs\                      # 日志目录
│   ├── combined.log
│   ├── out.log
│   └── error.log
├── user_data\                 # 浏览器持久化数据
└── Browser-Server-Windows-Deploy.md  # 本文档
```

---

## 十、下一步

1. ✅ 按文档部署到 Windows
2. ✅ 测试 API 可用性
3. ✅ 在 OpenClawd 中配置调用
4. 🔄 如需优化：
   - 添加代理支持
   - 复用更多登录会话
   - 增加更多交互能力

---

**文档版本**: 1.1.0
**适用系统**: Windows 10/11
**Python版本**: 3.10+
**最后更新**: 2026-02-01
