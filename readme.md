# 水镜共享中心

一个轻量的内网共享工具：文本管理 + 临时文件中转，适合在多台电脑之间快速传递内容。

## 功能
- 文本管理：新增、删除、收藏、拖拽分栏
- 文件中转：上传、下载、删除
- 回收站：文本与文件还原、清空后永久删除
- 前端锁屏密码访问

## 技术架构
- 后端：FastAPI（`main.py`）
- API 组织：`Controller/api_router.py`（APIRouter）
- 业务层：`Service/`
- 数据层：`db/database.py`（MySQL）
- 前端：前后端分离，代码在 `frontend/`
- 网关：Nginx 统一入口，`/api/*` 反向代理后端

## 目录结构
- `main.py`：应用入口（支持 `python main.py`）
- `Controller/`：API 路由层
- `Service/`：业务逻辑
- `db/`：数据库连接与初始化
- `frontend/`：静态前端（包含 `frontend/static/`）
- `SSL/`：证书文件
- `Dockerfile.backend`：后端镜像构建文件

## 免责声明
请勿用于存储敏感或重要文件，建议定期清理 `uploads/`。
