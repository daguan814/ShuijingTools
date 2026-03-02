# 水镜共享中心

一个轻量的内网共享工具：文本管理 + 临时文件中转，适合在多台电脑之间快速传递内容。

## 功能
- 文本管理：新增、删除、收藏、拖拽分栏
- 文件中转：上传、下载、删除
- 回收站：文本与文件还原、清空
- 前端锁屏密码访问

## 技术架构
- 后端：Flask（`main.py`）
- API 组织：`Controller/api_router.py`（Blueprint）
- 业务层：`Service/`
- 数据层：`db/database.py`（MySQL）
- 前端：同进程托管（`frontend/` 静态资源由 Flask 直接提供）
- 部署：单容器 Docker（不使用 docker-compose）

## 目录结构
- `main.py`：应用入口
- `Controller/`：API 路由层（蓝图）
- `Service/`：业务逻辑
- `db/`：数据库连接与初始化
- `frontend/`：前端静态资源
- `Dockerfile.backend`：镜像构建文件

## 运行
```bash
pip install -r requirements.txt
python main.py
```

默认监听 `https://0.0.0.0:8080`（当 `SSL_CERT_FILE`/`SSL_KEY_FILE` 可用时），否则回退 HTTP。

## 免责声明
请勿用于存储敏感或重要文件，建议定期清理 `uploads/`。
