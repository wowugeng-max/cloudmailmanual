# cloudmailmanual

一个可独立运行的 Cloud Mail 批量注册 Web 小工具。

功能：
- 批量自动创建 Cloud Mail 邮箱（指定数量）
- 自动生成资料：姓名、年龄、生日
- 页面展示结果
- 一键导出 CSV（邮箱、密码、姓名、年龄、生日）

---

## 1. 安装依赖

```bash
pip install -r requirements.txt
```

## 2. 配置

先复制配置模板：

```bash
cp config.example.json config.json
```

Windows PowerShell 可用：

```powershell
Copy-Item config.example.json config.json
```

编辑 `config.json`：

- `mail_profiles`: Cloud Mail 邮箱配置列表，可配置多个 API/管理员账号/域名后缀
- `active_mail_profile_id`: 默认使用的邮箱配置 ID
- `web_port`: Web 启动端口（1-65535，默认 5000）

启动后也可以在页面的“邮箱配置”里维护这些配置。旧版扁平配置字段（如 `cloud_mail_api_base`、`cloud_mail_admin_email`）仍可读取；在 UI 保存后会写入新的 `mail_profiles` 结构。

## 3. 启动

默认启动（端口优先级：`--port` > `config.json.web_port` > `APP_PORT/PORT` > `5000`）：

```bash
python app.py --debug
```

命令行临时指定端口（最高优先级）：

```bash
python app.py --port 8080 --debug
```

环境变量指定端口（低于 `config.json.web_port` 和 `--port`）：

```bash
# Linux / macOS
APP_PORT=8080 python app.py --debug

# Windows PowerShell
$env:APP_PORT = "8080"
python app.py --debug
```

如果使用一键脚本：
- 默认读取 `config.json.web_port`
- 也可手动设置 `WEB_PORT` 覆盖（优先级更高）

macOS 双击启动/停止：

- 双击 `run_web_mac.command`：安装依赖、后台启动服务并打开浏览器
- 双击 `stop_web_mac.command`：停止后台服务
- 日志写入 `run/cloudmailmanual.log`
- PID 写入 `run/cloudmailmanual.pid`

浏览器访问：

- `http://127.0.0.1:<你的端口>`

---

## 接口

- `GET /` 首页
- `POST /api/register` 批量注册
  - body: `{ "count": 5, "profile_id": "default", "domain_suffix": "example.com" }`
- `GET /api/settings/mail-profiles` 读取邮箱配置
- `POST /api/settings/mail-profiles` 保存邮箱配置
- `GET /api/export.csv?rows=<url-encoded-json>` 导出 CSV

---

## 项目结构

- `app.py`: Web 启动入口，保留 `python app.py` 用法
- `cloudmailmanual_app/factory.py`: Flask 应用创建和路由注册
- `cloudmailmanual_app/routes.py`: 页面和 API 路由
- `cloudmailmanual_app/database.py`: SQLite 表初始化
- `cloudmailmanual_app/repositories/`: 本地 SQLite 数据读写
- `cloudmailmanual_app/services/`: 邮箱注册、资料生成、域名主体生成等业务逻辑
- `templates/`: 页面模板

运行结构测试：

```bash
.venv-mac/bin/python -m unittest tests.test_app_structure -v
```

---

## 注意

- 单次数量限制为 `1-200`
- 调用 Cloud Mail API 失败时，页面会显示错误原因
