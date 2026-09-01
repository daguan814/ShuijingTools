# 项目维护注意事项

这是 `ShuijingTools` 云盘项目。后续任何 Agent 更新或部署时，必须遵守以下数据安全规则。

## 生产服务器

- SSH：`shuijing.site:12222`
- 部署目录：`/vol2/1000/backup/ShuijingTools`
- 后端服务：`shuijing-tools.service`
- Nginx 容器：`shuijing-nginx`
- 对外地址：`https://shuijing.site:8080`

## 绝对不要删除或清空的持久化数据

这些目录保存用户数据，更新代码、重启系统、重装前端时都不能删除：

```text
/vol2/1000/backup/ShuijingTools/storage
/vol2/1000/backup/docker/mysql
```

解释：

- `storage`：所有用户的真实文件和文件夹。
- `/vol2/1000/backup/docker/mysql`：MySQL 数据卷，保存用户和登录会话。

以下路径也应谨慎处理：

```text
/vol2/1000/backup/ShuijingTools/deploy/nginx/certs
/vol2/1000/backup/ShuijingTools/logs
```

`certs` 是 SSL 证书，`logs` 是运行日志，不要作为临时目录清理。

## 更新规则

1. 只更新代码目录：

   ```text
   backend/
   frontend/
   deploy/
   requirements.txt
   readme.md
   ```

2. 更新文件时优先使用 `rsync`，并且不要对整个项目根目录使用 `--delete`。

3. 禁止在服务器项目目录执行：

   ```bash
   rm -rf /vol2/1000/backup/ShuijingTools
   rm -rf /vol2/1000/backup/ShuijingTools/storage
   rm -rf /vol2/1000/backup/docker/mysql
   git clean -fdx
   ```

4. 更新后端后执行：

   ```bash
   sudo systemctl restart shuijing-tools.service
   ```

5. 更新前端后，Nginx 会直接读取新的 `frontend/`，通常不需要重启容器。如果改了 Nginx 配置：

   ```bash
   docker exec shuijing-nginx nginx -s reload
   ```

6. 如果必须做可能影响数据或数据库的操作，先备份：

   ```text
   /vol2/1000/backup/ShuijingTools/storage
   /vol2/1000/backup/docker/mysql
   ```

## 本地开发目录

本地 `backend/storage/` 只是本地预览使用的存储目录，会被 `.gitignore` 忽略。

不要把本地的 `backend/storage/` 误认为生产数据。生产数据在上面的服务器路径中。

## 数据库变更

如果以后需要修改数据库：

- 优先做加法迁移，新增表或新增列。
- 不要直接删除用户表、会话表。
- 操作前备份 MySQL 数据目录或导出数据库。
