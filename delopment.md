# delopment.md

这份文档用于后续自动部署。每次用户说“帮我部署/同步”，按本文件直接执行。

## 服务器连接信息
- SSH Key: `C:\Users\Administrator\Documents\id_rsa_macos`
- SSH Host: `root@shuijingnas.xin`
- SSH Port: `12222`

连接命令：
```powershell
ssh -i "C:\Users\Administrator\Documents\id_rsa_macos" -p 12222 root@shuijingnas.xin
```

## 线上目录约定
- 前端目录：`/vol2/1000/backup/docker/nginx/html`
- Nginx 配置：`/vol2/1000/backup/docker/nginx/conf.d/default.conf`
- 后端代码：`/vol2/1000/backup/docker/shuijingtools-api`

## 线上容器约定
- 网关容器：`nginx`
- 后端容器：`shuijing_backend`
- 数据库容器：`mysql`
- 后端镜像：`shuijing-backend:latest`
- Docker 网络：`shuijing_net`

## 部署目标
1. 可以自动连接服务器并部署。
2. 服务器重启后网站可自动恢复。
3. 只需看本文件即可完成部署。

## 部署步骤（Windows 本机执行）

### A. 同步前端（仅前端改动时）
```powershell
cmd /c 'tar -C C:\Users\Administrator\Documents\code\ShuijingTools -cf - frontend | ssh -i C:\Users\Administrator\Documents\id_rsa_macos -p 12222 root@shuijingnas.xin "tar -xf - -C /vol2/1000/backup/docker/nginx/html --strip-components=1 frontend"'
ssh -i "C:\Users\Administrator\Documents\id_rsa_macos" -p 12222 root@shuijingnas.xin "docker exec nginx nginx -s reload"
```

### B. 同步并部署后端（后端改动时）
```powershell
cmd /c 'tar -C C:\Users\Administrator\Documents\code\ShuijingTools -cf - main.py Controller db Service requirements.txt Dockerfile.backend .dockerignore | ssh -i C:\Users\Administrator\Documents\id_rsa_macos -p 12222 root@shuijingnas.xin "rm -rf /vol2/1000/backup/docker/shuijingtools-api/* && tar -xf - -C /vol2/1000/backup/docker/shuijingtools-api"'

ssh -i "C:\Users\Administrator\Documents\id_rsa_macos" -p 12222 root@shuijingnas.xin "docker build -t shuijing-backend:latest -f /vol2/1000/backup/docker/shuijingtools-api/Dockerfile.backend /vol2/1000/backup/docker/shuijingtools-api"

ssh -i "C:\Users\Administrator\Documents\id_rsa_macos" -p 12222 root@shuijingnas.xin "docker rm -f shuijing_backend >/dev/null 2>&1 || true; docker run -d --name shuijing_backend --restart always --network shuijing_net -p 8081:8081 -e DB_HOST=192.168.100.109 -e DB_USER=root -e DB_PASSWORD=Lhf134652 -e DB_NAME=shuijingTools -v /vol2/1000/backup/docker/shuijingtools-api/uploads:/app/uploads shuijing-backend:latest"

ssh -i "C:\Users\Administrator\Documents\id_rsa_macos" -p 12222 root@shuijingnas.xin "docker exec nginx nginx -s reload"
```

## 开机自动恢复检查（必须保持）
```bash
systemctl is-enabled docker
systemctl is-active docker
docker inspect -f '{{.Name}} restart={{.HostConfig.RestartPolicy.Name}}' nginx shuijing_backend mysql
```
要求：
- docker 服务：`enabled` + `active`
- 三个容器策略：`always`

如需一次性修复策略：
```bash
docker update --restart always nginx shuijing_backend mysql
```

## 验证命令
```bash
curl -k -s -o /dev/null -w 'front:%{http_code}\n' https://127.0.0.1:8080/
curl -k -s -o /dev/null -w 'api:%{http_code}\n' https://127.0.0.1:8080/api/health
```
预期：都为 `200`。
