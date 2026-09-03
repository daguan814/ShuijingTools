# 部署说明

> 重要：更新代码时绝对不要删除以下目录：
>
> ```text
> /vol2/1000/backup/ShuijingTools/storage
> /vol2/1000/backup/docker/mysql
> ```
>
> 这两个目录分别保存用户文件和 MySQL 数据。

当前部署目标：

- 服务器：`shuijing.site`
- SSH 端口：`12222`
- 部署目录：`/vol2/1000/backup/ShuijingTools`
- 后端：`systemd` 服务 `shuijing-tools.service`，监听 `127.0.0.1:18080`
- 前端：由 `shuijing-nginx` 容器提供，挂载目录 `frontend`
- 对外入口：`https://shuijing.site:8080`
- 敏感配置：项目根目录 `.env`，权限必须为 `600`，禁止提交 Git

## 更新后端

只同步代码，不使用 `--delete`：

```bash
rsync -az --exclude='__pycache__' --exclude='*.pyc' \
  backend requirements.txt readme.md \
  shuijing@shuijing.site:/vol2/1000/backup/ShuijingTools/

ssh -p 12222 shuijing@shuijing.site \
  'sudo systemctl restart shuijing-tools.service'
```

## 更新前端

只同步 `frontend` 目录，不要动 `storage` 和 `docker/mysql`：

```bash
rsync -az --exclude='.DS_Store' frontend \
  shuijing@shuijing.site:/vol2/1000/backup/ShuijingTools/
```

## Nginx

配置文件位于：

```text
deploy/nginx/conf.d/shuijing.site.conf
```

前端挂载到容器内的 `/srv/frontend`，`/api/` 反向代理到 `127.0.0.1:18080`。

如果修改了 Nginx 配置，需要让容器重新加载：

```bash
ssh -p 12222 shuijing@shuijing.site \
  'docker exec shuijing-nginx nginx -s reload'
```

## 回滚

部署前备份位于服务器：

```text
/vol2/1000/backup/ShuijingTools_backup_*
```

包含旧 `app/`、`vue/`、`deploy/`、`readme.md`、`requirements.txt` 和旧的
`shuijing-tools.service`。
