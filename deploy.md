# ShuijingTools 部署文档

这份文档用于后续自动部署。用户说“帮我部署/同步代码到远程”时，按本文件执行；如远端镜像源或基础镜像状态不同，可按“构建变通”章节处理。

## 当前环境

- 本地项目目录：`/Users/shuijing/Documents/Code/ShuijingTools`
- SSH Host：`root@shuijing.site`
- SSH Port：`12222`
- SSH Key：`/Users/shuijing/Documents/id_rsa_macos`
- 远端项目目录：`/vol2/1000/backup/docker/shuijingtools-app`
- 上传目录：`/vol2/1000/backup/docker/shuijingtools-app/uploads`
- 证书目录：`/vol2/1000/backup/证书文档/Nginx`
- 容器内证书目录：`/app/ssl`
- 容器名：`shuijingtools`
- 镜像名：`shuijingtools:latest`
- 备份镜像名：`shuijingtools:backup-before-deploy`
- 数据库容器：`mysql`
- 访问地址：`https://shuijing.site:8080`

## 重要规则

- 不上传 `.git/`、`.idea/`、`.venv/`、`__pycache__/`、`*.pyc`、`uploads/`、`SSL/`。
- `uploads/` 是线上持久数据目录，部署时必须保留。
- 替换容器前必须先构建镜像成功。
- 每次替换容器前，先把旧 `shuijingtools:latest` 标记为 `shuijingtools:backup-before-deploy`。
- `shuijingtools` 和 `mysql` 都应保持 `--restart always`。

## 连接检查

```bash
ssh -i /Users/shuijing/Documents/id_rsa_macos -p 12222 -o IdentitiesOnly=yes root@shuijing.site \
  'whoami && hostname && docker --version'
```

预期能看到：

- 用户：`root`
- 主机：`ShuijingNAS`
- Docker 版本正常输出

## 本地同步前检查

```bash
cd /Users/shuijing/Documents/Code/ShuijingTools
git status --short --branch
git ls-files '*__pycache__*' '*.pyc'
```

如果 `git ls-files` 还能看到 `.pyc`，先从 Git 索引移除：

```bash
git rm --cached $(git ls-files '*__pycache__*' '*.pyc')
```

`.gitignore` 和 `.dockerignore` 至少应包含：

```gitignore
__pycache__/
*.py[cod]
*$py.class
.deploy_app.sftp
uploads/
SSL/
```

## 同步代码到远端

```bash
cd /Users/shuijing/Documents/Code/ShuijingTools

rsync -avz --delete \
  -e 'ssh -i /Users/shuijing/Documents/id_rsa_macos -p 12222 -o IdentitiesOnly=yes' \
  --exclude='.git/' \
  --exclude='.idea/' \
  --exclude='.venv/' \
  --exclude='__pycache__/' \
  --exclude='*.py[cod]' \
  --exclude='*$py.class' \
  --exclude='.deploy_app.sftp' \
  --exclude='uploads/' \
  --exclude='SSL/' \
  /Users/shuijing/Documents/Code/ShuijingTools/ \
  root@shuijing.site:/vol2/1000/backup/docker/shuijingtools-app/
```

远端再清一次缓存：

```bash
ssh -i /Users/shuijing/Documents/id_rsa_macos -p 12222 -o IdentitiesOnly=yes root@shuijing.site \
  'find /vol2/1000/backup/docker/shuijingtools-app -type d -name __pycache__ -prune -exec rm -rf {} +; find /vol2/1000/backup/docker/shuijingtools-app -type f \( -name "*.pyc" -o -name "*.pyo" -o -name "*.pyd" \) -delete'
```

## 构建镜像

优先使用项目内的 `Dockerfile.backend` 原样构建：

```bash
ssh -i /Users/shuijing/Documents/id_rsa_macos -p 12222 -o IdentitiesOnly=yes root@shuijing.site \
  'set -e; cd /vol2/1000/backup/docker/shuijingtools-app; OLD_ID=$(docker image inspect shuijingtools:latest --format "{{.Id}}" 2>/dev/null || true); if [ -n "$OLD_ID" ]; then docker tag "$OLD_ID" shuijingtools:backup-before-deploy; fi; docker build -t shuijingtools:latest -f Dockerfile.backend .'
```

## 构建变通

`Dockerfile.backend` 默认使用：

```dockerfile
FROM python:3.13-slim
```

如果远端 Docker 镜像源拉取 `python:3.13-slim` 失败，但远端已经有 `python:latest`，可临时使用 `python:latest` 构建，不修改仓库文件：

```bash
ssh -i /Users/shuijing/Documents/id_rsa_macos -p 12222 -o IdentitiesOnly=yes root@shuijing.site \
  'set -e; cd /vol2/1000/backup/docker/shuijingtools-app; OLD_ID=$(docker image inspect shuijingtools:latest --format "{{.Id}}" 2>/dev/null || true); if [ -n "$OLD_ID" ]; then docker tag "$OLD_ID" shuijingtools:backup-before-deploy; fi; sed "s/^FROM python:3.13-slim$/FROM python:latest/" Dockerfile.backend | docker build -t shuijingtools:latest -f - .'
```

构建前可确认远端有哪些 Python 镜像：

```bash
ssh -i /Users/shuijing/Documents/id_rsa_macos -p 12222 -o IdentitiesOnly=yes root@shuijing.site \
  'docker images --format "{{.Repository}}:{{.Tag}} {{.ID}} {{.CreatedSince}}" | grep -i python || true'
```

## 替换容器

只有镜像构建成功后才执行：

```bash
ssh -i /Users/shuijing/Documents/id_rsa_macos -p 12222 -o IdentitiesOnly=yes root@shuijing.site \
  'set -euo pipefail
docker rm -f shuijingtools-frontend shuijingtools-backend >/dev/null 2>&1 || true
docker rm -f shuijingtools >/dev/null 2>&1 || true
docker run -d --name shuijingtools --restart always -p 8080:8080 \
  -e DB_HOST=192.168.100.109 \
  -e DB_USER=root \
  -e DB_PASSWORD="Lhf134652" \
  -e DB_NAME=shuijingTools \
  -e SSL_CERT_FILE=/app/ssl/shuijing.site.crt \
  -e SSL_KEY_FILE=/app/ssl/shuijing.site.key \
  -v /vol2/1000/backup/docker/shuijingtools-app/uploads:/app/uploads \
  -v "/vol2/1000/backup/证书文档/Nginx":/app/ssl:ro \
  shuijingtools:latest
docker ps --filter name=shuijingtools --format "{{.Names}} {{.Image}} {{.Status}} {{.Ports}}"'
```

## 验证

```bash
ssh -i /Users/shuijing/Documents/id_rsa_macos -p 12222 -o IdentitiesOnly=yes root@shuijing.site \
  'set -e; sleep 3; docker logs --tail 80 shuijingtools; printf "\n--- checks ---\n"; curl -k -s -o /dev/null -w "front:%{http_code}\n" https://127.0.0.1:8080/; curl -k -s -o /dev/null -w "api:%{http_code}\n" https://127.0.0.1:8080/api/health; printf "\n--- restart policies ---\n"; systemctl is-enabled docker || true; systemctl is-active docker || true; docker inspect -f "{{.Name}} restart={{.HostConfig.RestartPolicy.Name}} state={{.State.Status}}" shuijingtools mysql'
```

预期：

- `front:200`
- `api:200`
- Docker：`enabled`、`active`
- `/shuijingtools restart=always state=running`
- `/mysql restart=always state=running`

公网验证可用：

```bash
printf 'GET /api/health HTTP/1.1\r\nHost: shuijing.site\r\nConnection: close\r\n\r\n' \
  | openssl s_client -connect 8.148.95.251:8080 -servername shuijing.site -quiet 2>/dev/null \
  | sed -n '1,12p'
```

预期包含：

```text
HTTP/1.1 200 OK
{"ok":true}
```

## 回滚

如果新容器启动失败，可回滚到部署前镜像：

```bash
ssh -i /Users/shuijing/Documents/id_rsa_macos -p 12222 -o IdentitiesOnly=yes root@shuijing.site \
  'set -e; docker rm -f shuijingtools >/dev/null 2>&1 || true; docker tag shuijingtools:backup-before-deploy shuijingtools:latest; docker run -d --name shuijingtools --restart always -p 8080:8080 -e DB_HOST=192.168.100.109 -e DB_USER=root -e DB_PASSWORD="Lhf134652" -e DB_NAME=shuijingTools -e SSL_CERT_FILE=/app/ssl/shuijing.site.crt -e SSL_KEY_FILE=/app/ssl/shuijing.site.key -v /vol2/1000/backup/docker/shuijingtools-app/uploads:/app/uploads -v "/vol2/1000/backup/证书文档/Nginx":/app/ssl:ro shuijingtools:latest'
```
