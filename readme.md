# 水镜云盘

一个前后端分离的多用户网盘式文件存储项目。当前版本完成：

- 用户输入用户名进入自己的存储空间；
- 每个用户拥有独立、隔离的文件目录；
- 网盘式目录浏览，展示文件/文件夹、修改日期和大小；
- 支持把文件或整个文件夹拖入网页，并按原目录结构上传到当前目录；
- 批量选择后进行移动、删除、下载。

当前预置用户：

- `shuijing`
- `txt`

## 目录结构

```text
.
├── backend/               Flask REST API
│   ├── app.py             应用入口与中间件
│   ├── config.py          环境配置
│   ├── database.py        MySQL 连接与建表
│   ├── auth_service.py    用户登录与会话
│   ├── file_service.py    用户文件系统隔离逻辑
│   ├── routes/            API 路由
│   └── storage/           各用户存储目录（运行时生成）
├── frontend/              独立前端
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── legacy/                旧版单体和前端，仅作历史参考
└── requirements.txt
```

## 技术架构

- 后端：Flask + MySQL
- 前端：原生 HTML/CSS/JavaScript，独立部署
- 认证：无密码用户名登录，服务端生成不透明 token
- 文件存储：按用户的 `storage_key` 生成物理目录，接口层统一做路径穿越校验

数据库表：

- `storage_users`：用户与存储目录标识
- `user_sessions`：登录会话

首次启动会自动创建数据库、表，并写入 `shuijing`、`txt` 两个用户。

## 本地运行

先安装依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

启动后端：

```bash
python3 -m backend.app
```

后端默认监听 `http://127.0.0.1:8080`，只提供 API。

如果本机暂时没有 MySQL，可以用 SQLite 直接预览：

```bash
DB_DRIVER=sqlite \
SQLITE_DB_PATH=/tmp/shuijingtools_preview.db \
STORAGE_ROOT=/tmp/shuijingtools_preview_storage \
python3 -m backend.app
```

另开一个终端启动前端静态服务：

```bash
python3 -m http.server 5173 -d frontend
```

浏览器打开 `http://127.0.0.1:5173`。

生产环境可用 gunicorn 启动：

```bash
gunicorn -w 4 -b 0.0.0.0:8080 backend.wsgi:app
```

前端默认请求 `http://127.0.0.1:8080`。如果你的后端地址不同，可以在 `frontend/index.html` 加载 `app.js` 之前加入：

```js
window.STORAGE_API_BASE = 'http://你的后端地址';
```

或在 `frontend/app.js` 顶部修改 `API_BASE` 的默认值。

## 环境变量

后端支持以下环境变量：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DB_HOST` | `127.0.0.1` | MySQL 地址 |
| `DB_PORT` | `3306` | MySQL 端口 |
| `DB_USER` | `root` | MySQL 用户 |
| `DB_PASSWORD` | `Lhf134652` | MySQL 密码 |
| `DB_NAME` | `shuijingTools` | 数据库名 |
| `DB_DRIVER` | `mysql` | `mysql` 或 `sqlite` |
| `SQLITE_DB_PATH` | `backend/shuijingtools.db` | SQLite 文件路径 |
| `APP_HOST` | `0.0.0.0` | API 监听地址 |
| `APP_PORT` | `8080` | API 端口 |
| `STORAGE_ROOT` | `backend/storage` | 用户文件根目录 |
| `MAX_CONTENT_LENGTH` | `10737418240` | 单次请求大小限制，默认 10 GB |

## API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/auth/login` | 用户名登录，返回 token |
| `GET` | `/api/auth/me` | 当前用户 |
| `POST` | `/api/auth/logout` | 退出登录 |
| `GET` | `/api/files?path=` | 列出目录 |
| `POST` | `/api/files/upload` | 上传文件/目录结构 |
| `POST` | `/api/files/mkdir` | 新建文件夹 |
| `POST` | `/api/files/move` | 批量移动 |
| `POST` | `/api/files/batch-delete` | 批量删除 |
| `POST` | `/api/files/batch-download` | 批量下载为 ZIP |
| `GET` | `/api/files/download?path=` | 下载文件 |
| `GET` | `/api/files/preview?path=` | 浏览器内联预览文件 |
| `POST` | `/api/files/delete` | 删除文件或文件夹 |

除登录和健康检查外，API 都需要请求头：

```http
Authorization: Bearer <token>
```
