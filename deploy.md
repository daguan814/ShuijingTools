这份文档用于后续自动部署。每次用户说“帮我部署/同步”，按本文件直接执行。

## 服务器连接信息
- SSH Key: `C:\Users\lu873\Documents\id_rsa_macos`
- SSH Host: `root@shuijing.site`
- SSH Port: `12222`

连接命令：
```powershell
ssh -i "C:\Users\lu873\Documents\id_rsa_macos" -p 12222 root@shuijing.site
```

## 线上目录约定
- 项目代码目录：`/vol2/1000/backup/docker/shuijingtools-app`
- 证书源目录：`/vol2/1000/backup/证书文档/Nginx`
- 容器内证书目录：`/app/ssl`
- 上传目录（宿主机挂载）：`/vol2/1000/backup/docker/shuijingtools-app/uploads`

## 命名规范
- 项目名：`shuijingtools`
- 容器名：`shuijingtools`（部署时容器名等于项目名）
- 镜像名：`shuijingtools:latest`
- 数据库容器（复用已有）：`mysql`

## 部署目标
1. 自动连接服务器并部署。
2. 服务器重启后网站可自动恢复。
3. 只需看本文件即可完成部署。
4. 通过 `https://shuijing.site:8080` 访问。

## 部署步骤（Windows 本机执行，使用 SFTP + docker run）

### 0. 本机预清理（避免上传无用文件）
```powershell
if (Test-Path .\__pycache__) { Remove-Item .\__pycache__ -Recurse -Force }
if (Test-Path .\Controller\__pycache__) { Remove-Item .\Controller\__pycache__ -Recurse -Force }
if (Test-Path .\Service\__pycache__) { Remove-Item .\Service\__pycache__ -Recurse -Force }
if (Test-Path .\db\__pycache__) { Remove-Item .\db\__pycache__ -Recurse -Force }
Remove-Item .\.deploy_app.sftp -Force -ErrorAction SilentlyContinue
```

### A. 预清理与目录准备
```powershell
ssh -i "C:\Users\lu873\Documents\id_rsa_macos" -p 12222 root@shuijing.site "mkdir -p /vol2/1000/backup/docker/shuijingtools-app /vol2/1000/backup/docker/shuijingtools-app/uploads && rm -rf /vol2/1000/backup/docker/shuijingtools-app/Controller /vol2/1000/backup/docker/shuijingtools-app/db /vol2/1000/backup/docker/shuijingtools-app/Service /vol2/1000/backup/docker/shuijingtools-app/frontend /vol2/1000/backup/docker/shuijingtools-app/main.py /vol2/1000/backup/docker/shuijingtools-app/requirements.txt /vol2/1000/backup/docker/shuijingtools-app/Dockerfile.backend /vol2/1000/backup/docker/shuijingtools-app/.dockerignore /vol2/1000/backup/docker/shuijingtools-app/readme.md"
```

### B. SFTP 同步项目文件
```powershell
@"
cd /vol2/1000/backup/docker/shuijingtools-app
lcd C:\Users\lu873\PycharmProjects\ShuijingTools
put main.py
put requirements.txt
put Dockerfile.backend
put .dockerignore
put readme.md
mkdir Controller
mkdir db
mkdir Service
mkdir frontend
put Controller/api_router.py Controller/api_router.py
put db/database.py db/database.py
put Service/auth_service.py Service/auth_service.py
put Service/file_favorite_service.py Service/file_favorite_service.py
put Service/text_service.py Service/text_service.py
put Service/trash_service.py Service/trash_service.py
put frontend/index.html frontend/index.html
put frontend/app.js frontend/app.js
put frontend/styles.css frontend/styles.css
mkdir frontend/static
mkdir frontend/static/bootstrap
mkdir frontend/static/bootstrap/css
mkdir frontend/static/bootstrap/js
mkdir frontend/static/bootstrap-icons
mkdir frontend/static/bootstrap-icons/fonts
put -r frontend/static/bootstrap/css/* frontend/static/bootstrap/css/
put -r frontend/static/bootstrap/js/* frontend/static/bootstrap/js/
put -r frontend/static/bootstrap-icons/* frontend/static/bootstrap-icons/
put -r frontend/static/bootstrap-icons/fonts/* frontend/static/bootstrap-icons/fonts/
put frontend/static/icon.svg frontend/static/icon.svg
bye
"@ | Set-Content -Path .\.deploy_app.sftp -Encoding ascii

sftp -i "C:\Users\lu873\Documents\id_rsa_macos" -P 12222 -b .\.deploy_app.sftp root@shuijing.site
```

### C. 重建镜像
```powershell
ssh -i "C:\Users\lu873\Documents\id_rsa_macos" -p 12222 root@shuijing.site "cd /vol2/1000/backup/docker/shuijingtools-app && docker build -t shuijingtools:latest -f Dockerfile.backend ."
```

### D. 删除旧容器并启动新容器（带 SSL）
```powershell
ssh -i "C:\Users\lu873\Documents\id_rsa_macos" -p 12222 root@shuijing.site "docker rm -f shuijingtools-frontend shuijingtools-backend >/dev/null 2>&1 || true"

ssh -i "C:\Users\lu873\Documents\id_rsa_macos" -p 12222 root@shuijing.site "docker rm -f shuijingtools >/dev/null 2>&1 || true"

ssh -i "C:\Users\lu873\Documents\id_rsa_macos" -p 12222 root@shuijing.site "docker run -d --name shuijingtools --restart always -p 8080:8080 -e DB_HOST=192.168.100.109 -e DB_USER=root -e DB_PASSWORD='Lhf134652' -e DB_NAME=shuijingTools -e SSL_CERT_FILE=/app/ssl/shuijing.site.crt -e SSL_KEY_FILE=/app/ssl/shuijing.site.key -v /vol2/1000/backup/docker/shuijingtools-app/uploads:/app/uploads -v '/vol2/1000/backup/证书文档/Nginx':/app/ssl:ro shuijingtools:latest"
```

### E. 清理本机临时批处理文件
```powershell
Remove-Item .\.deploy_app.sftp -Force -ErrorAction SilentlyContinue
```

### F. 远端清理缓存目录（可选但建议）
```powershell
ssh -i "C:\Users\lu873\Documents\id_rsa_macos" -p 12222 root@shuijing.site "find /vol2/1000/backup/docker/shuijingtools-app -type d -name '__pycache__' -prune -exec rm -rf {} +"
```

## 开机自动恢复检查（必须保持）
```bash
systemctl is-enabled docker
systemctl is-active docker
docker inspect -f '{{.Name}} restart={{.HostConfig.RestartPolicy.Name}}' shuijingtools mysql
```
要求：
- docker 服务：`enabled` + `active`
- 两个容器策略：`always`

如需一次性修复策略：
```bash
docker update --restart always shuijingtools mysql
```

## 验证命令
```bash
curl -k -s -o /dev/null -w 'front:%{http_code}\n' https://127.0.0.1:8080/
curl -k -s -o /dev/null -w 'api:%{http_code}\n' https://127.0.0.1:8080/api/health
```
预期：都为 `200`。
