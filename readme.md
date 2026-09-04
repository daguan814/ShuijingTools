# 水镜云盘（ShuijingTools）

一个轻量的多用户文件存储网站，采用 Flask、MySQL 和原生 HTML/CSS/JavaScript 构建。每个用户拥有独立目录，可以在网页中浏览、上传、预览、移动、删除和下载文件。



## 功能

- 输入已有用户名进入对应存储空间；
- 文件与文件夹分用户隔离存储；
- 浏览目录、查看修改时间和普通文件大小；
- 文件夹显示直接下一层的文件夹数、文件数以及全部内容总大小；
- 上传单个文件、多个文件或完整文件夹；
- 支持拖放上传并保留目录结构；
- 新建文件夹、单项重命名、批量移动和批量删除；
- 文件列表较长时，路径、上传和批量操作工具栏会固定在页面顶部；
- 删除内容进入按用户隔离的回收站，输入管理密码后可恢复；
- 常见图片、文档、文本、音视频文件在线预览；
- 单个文件使用浏览器原生下载，支持条件请求和 Range；
- 多文件或文件夹在服务器临时生成 ZIP 后下载；
- 自动记录按用户隔离的文件操作日志，支持按日期与操作类型组合筛选、结果统计和分页；
- 日志采用简洁表格布局，滚动时固定表头；
- 同一浏览器连续登录失败5次后锁定5小时；
- 显示用户已用空间和服务器磁盘容量。

当前预置用户：`shuijing`、`txt`。

> 当前登录方式仅校验用户名，不要求密码。不要将未知用户名加入数据库。

## 目录结构

```text
.
├── backend/                       Flask API
│   ├── app.py                     应用、中间件、CORS 和预览入口
│   ├── config.py                  环境配置
│   ├── database.py                MySQL/SQLite 初始化和查询
│   ├── auth_service.py            登录会话
│   ├── file_service.py            文件隔离、路径校验和 ZIP 生成
│   ├── log_service.py             用户文件操作日志
│   ├── recycle_service.py         回收站移动与恢复
│   ├── routes/                    API 路由
│   └── storage/                   本地预览存储（生产环境不使用）
├── frontend/                      静态前端
├── deploy/                        Nginx、systemd 和部署说明
├── tests/                         集成测试
├── .env.example                   环境变量示例
└── requirements.txt               固定版本的 Python 依赖
```

## 存储模型

生产文件保存在：

```text
/vol2/1000/backup/ShuijingTools/storage/<username>/
```

例如：

```text
storage/
├── shuijing/
└── txt/
```

用户名只能包含英文字母、数字、下划线和短横线，最长64个字符。后端会校验所有相对路径，拒绝绝对路径、`..` 和逃逸用户目录的访问。

文件夹大小不在目录列表中实时计算，以免递归扫描大量文件导致页面卡顿；普通文件仍显示实际大小。

## 下载机制

下载分为两步：

1. 前端携带登录令牌调用 `/api/files/download/prepare`；
2. 后端返回5分钟有效的签名下载链接，浏览器使用原生下载访问该链接。

只选择一个普通文件时直接返回原文件。选择多个项目或文件夹时，后端在系统临时目录生成 ZIP，响应结束后自动删除临时文件。这避免了旧版本在服务器和浏览器中同时保存数百 MB Blob 的问题。

前端 JS/CSS 使用版本参数并由 Nginx 设置重新验证缓存，部署新版本后不会继续调用已删除的旧接口。

## 本地开发

### 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 使用 SQLite 启动后端

```bash
DB_DRIVER=sqlite \
SQLITE_DB_PATH=/tmp/shuijingtools_preview.db \
STORAGE_ROOT=/tmp/shuijingtools_preview_storage \
SECRET_KEY=local-development-secret \
FLASK_DEBUG=1 \
python3 -m backend.app
```

### 启动前端

```bash
python3 -m http.server 5173 -d frontend
```

浏览器打开 `http://127.0.0.1:5173`。前端会请求 `http://127.0.0.1:8080` 的本地 API。

## 环境变量

复制 `.env.example` 并填写生产值。真实 `.env` 已被 Git 忽略，权限应设置为 `600`。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DB_HOST` | `127.0.0.1` | 数据库地址 |
| `DB_PORT` | `3306` | 数据库端口 |
| `DB_USER` | `root` | 数据库用户，生产环境应使用专用账户 |
| `DB_PASSWORD` | 空 | 数据库密码 |
| `DB_NAME` | `shuijingTools` | 数据库名称 |
| `DB_DRIVER` | `mysql` | `mysql` 或 `sqlite` |
| `SQLITE_DB_PATH` | `backend/shuijingtools.db` | SQLite 文件位置 |
| `APP_HOST` | `0.0.0.0` | 开发服务器监听地址 |
| `APP_PORT` | `8080` | 开发服务器端口 |
| `STORAGE_ROOT` | `backend/storage` | 用户文件根目录 |
| `RECYCLE_ROOT` | `recycle_bin` | 回收站文件根目录 |
| `RECYCLE_BIN_PASSWORD` | 空 | 恢复回收站内容所需的管理密码 |
| `MAX_CONTENT_LENGTH` | `10737418240` | 单次请求最大10GB |
| `SECRET_KEY` | 无安全默认值 | 生产签名密钥，必须配置 |
| `ALLOWED_ORIGINS` | `http://127.0.0.1:5173` | 逗号分隔的 CORS 来源 |

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/health` | 健康检查 |
| `POST` | `/api/auth/login` | 使用用户名登录 |
| `GET` | `/api/auth/me` | 当前用户和容量信息 |
| `POST` | `/api/auth/logout` | 注销当前会话 |
| `GET` | `/api/files?path=` | 列出目录 |
| `POST` | `/api/files/upload` | 上传文件或文件夹 |
| `POST` | `/api/files/mkdir` | 新建文件夹 |
| `POST` | `/api/files/move` | 批量移动 |
| `POST` | `/api/files/rename` | 重命名单个文件或文件夹 |
| `POST` | `/api/files/delete` | 删除单个路径 |
| `POST` | `/api/files/batch-delete` | 批量删除 |
| `POST` | `/api/files/download/prepare` | 生成短期下载链接 |
| `GET` | `/api/files/download/ticket/<ticket>` | 下载原文件或 ZIP |
| `GET` | `/api/files/download?path=` | 直接下载接口 |
| `GET` | `/api/files/preview?path=` | API 内联预览 |
| `POST` | `/api/files/preview/start` | 创建预览会话 |
| `GET` | `/preview/<path>` | 使用预览会话打开文件 |
| `GET` | `/api/logs` | 查询当前用户的文件操作日志，可使用 `date`、`action`、`page`、`page_size` 筛选和分页 |
| `GET` | `/api/recycle` | 查询当前用户的回收站 |
| `POST` | `/api/recycle/<id>/restore` | 使用回收站密码恢复项目 |

除健康检查、登录和签名下载链接外，API 需要：

```http
Authorization: Bearer <token>
```

## 测试

```bash
SECRET_KEY=test-secret \
DB_DRIVER=sqlite \
SQLITE_DB_PATH=/tmp/shuijingtools_test.db \
STORAGE_ROOT=/tmp/shuijingtools_test_storage \
python -m unittest discover -s tests -v
```

测试覆盖用户名目录、单文件下载、批量 ZIP 和用户文件隔离。

## 生产部署

生产环境由以下组件组成：

- Nginx 容器 `shuijing-nginx`：TLS、静态前端和反向代理；
- systemd 服务 `shuijing-tools.service`：运行两个 Gunicorn worker；
- MySQL 容器：保存用户、会话和文件操作日志；
- `storage/`：保存用户真实文件。
- `recycle_bin/`：保存用户删除后等待恢复的文件。

后端与 Nginx 的长请求超时均为600秒。完整更新命令和回滚说明见 `deploy/README.md`。

## 数据安全

以下生产目录是持久化数据，部署或清理代码时绝对不能删除：

```text
/vol2/1000/backup/ShuijingTools/storage
/vol2/1000/backup/ShuijingTools/recycle_bin
/vol2/1000/backup/docker/mysql
```

同时谨慎处理：

```text
/vol2/1000/backup/ShuijingTools/deploy/nginx/certs
/vol2/1000/backup/ShuijingTools/logs
```

不要在生产项目根目录运行 `git clean -fdx`，也不要对整个项目根目录使用 `rsync --delete`。数据库结构变更前应先导出数据库或创建数据快照。
