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

- `cloud_mail_api_base`: Cloud Mail API 地址
- `cloud_mail_admin_email`: 管理员邮箱
- `cloud_mail_admin_password`: 管理员密码
- `cloud_mail_role_name`: 可选，创建用户角色名
- `proxy`: 可选，HTTP 代理
- `web_port`: Web 启动端口（1-65535，默认 5000）

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

浏览器访问：

- `http://127.0.0.1:<你的端口>`

---

## 接口

- `GET /` 首页
- `POST /api/register` 批量注册
  - body: `{ "count": 5 }`
- `GET /api/export.csv?rows=<url-encoded-json>` 导出 CSV

---

## 注意

- 单次数量限制为 `1-200`
- 调用 Cloud Mail API 失败时，页面会显示错误原因
