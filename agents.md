
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
- 前端目录：`/vol2/1000/backup/docker/nginx/html`
- Nginx 配置：`/vol2/1000/backup/docker/nginx/conf.d/default.conf`
- Nginx 证书目录：`/vol2/1000/backup/证书文档/Nginx`
- Nginx 容器可读证书目录：`/vol2/1000/backup/docker/nginx/conf.d/certs`
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
4. 通过 `https://shuijing.site:8080` 访问。

## 部署步骤（Windows 本机执行，使用 SFTP）

### A. 预清理与目录准备
```powershell
ssh -i "C:\Users\lu873\Documents\id_rsa_macos" -p 12222 root@shuijing.site "mkdir -p /vol2/1000/backup/docker/nginx/html /vol2/1000/backup/docker/shuijingtools-api /vol2/1000/backup/docker/nginx/conf.d/certs && rm -rf /vol2/1000/backup/docker/nginx/html/* && rm -rf /vol2/1000/backup/docker/shuijingtools-api/Controller /vol2/1000/backup/docker/shuijingtools-api/db /vol2/1000/backup/docker/shuijingtools-api/Service /vol2/1000/backup/docker/shuijingtools-api/main.py /vol2/1000/backup/docker/shuijingtools-api/requirements.txt /vol2/1000/backup/docker/shuijingtools-api/Dockerfile.backend /vol2/1000/backup/docker/shuijingtools-api/.dockerignore"
```

### B. SFTP 同步前端
```powershell
@"
cd /vol2/1000/backup/docker/nginx/html
lcd C:\Users\lu873\PycharmProjects\ShuijingTools
put -r frontend/*
bye
"@ | Set-Content -Path .\.deploy_frontend.sftp -Encoding ascii

sftp -i "C:\Users\lu873\Documents\id_rsa_macos" -P 12222 -b .\.deploy_frontend.sftp root@shuijing.site
```

### C. SFTP 同步后端
```powershell
@"
cd /vol2/1000/backup/docker/shuijingtools-api
lcd C:\Users\lu873\PycharmProjects\ShuijingTools
put main.py
put requirements.txt
put Dockerfile.backend
put .dockerignore
mkdir Controller
mkdir db
mkdir Service
put -r Controller/* Controller/
put -r db/* db/
put -r Service/* Service/
bye
"@ | Set-Content -Path .\.deploy_backend.sftp -Encoding ascii

sftp -i "C:\Users\lu873\Documents\id_rsa_macos" -P 12222 -b .\.deploy_backend.sftp root@shuijing.site
```

### D. 写入 Nginx HTTPS 配置（shuijing.site）
```powershell
@'
server {
    listen 8080 ssl;
    server_name shuijing.site;
    client_max_body_size 1g;

    ssl_certificate /etc/nginx/conf.d/certs/shuijing.site.crt;
    ssl_certificate_key /etc/nginx/conf.d/certs/shuijing.site.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:10m;

    location /api/ {
        proxy_pass http://shuijing_backend:8081/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        root /usr/share/nginx/html;
        index index.html;
        try_files $uri $uri/ /index.html;
    }
}
'@ | Set-Content -Path .\.default.conf -Encoding ascii

@"
cd /vol2/1000/backup/docker/nginx/conf.d
lcd C:\Users\lu873\PycharmProjects\ShuijingTools
put .default.conf default.conf
bye
"@ | Set-Content -Path .\.deploy_conf.sftp -Encoding ascii

sftp -i "C:\Users\lu873\Documents\id_rsa_macos" -P 12222 -b .\.deploy_conf.sftp root@shuijing.site
```

### E. 证书复制、后端重建、容器重启、Nginx 重载
```powershell
ssh -i "C:\Users\lu873\Documents\id_rsa_macos" -p 12222 root@shuijing.site "cp -f '/vol2/1000/backup/证书文档/Nginx/shuijing.site.crt' /vol2/1000/backup/docker/nginx/conf.d/certs/shuijing.site.crt && cp -f '/vol2/1000/backup/证书文档/Nginx/shuijing.site.key' /vol2/1000/backup/docker/nginx/conf.d/certs/shuijing.site.key"

ssh -i "C:\Users\lu873\Documents\id_rsa_macos" -p 12222 root@shuijing.site "docker build -t shuijing-backend:latest -f /vol2/1000/backup/docker/shuijingtools-api/Dockerfile.backend /vol2/1000/backup/docker/shuijingtools-api"

ssh -i "C:\Users\lu873\Documents\id_rsa_macos" -p 12222 root@shuijing.site "docker rm -f shuijing_backend >/dev/null 2>&1 || true; docker run -d --name shuijing_backend --restart always --network shuijing_net -p 8081:8081 -e DB_HOST=192.168.100.109 -e DB_USER=root -e DB_PASSWORD=Lhf134652 -e DB_NAME=shuijingTools -v /vol2/1000/backup/docker/shuijingtools-api/uploads:/app/uploads shuijing-backend:latest"

ssh -i "C:\Users\lu873\Documents\id_rsa_macos" -p 12222 root@shuijing.site "chmod -R a+rX /vol2/1000/backup/docker/nginx/html && docker exec nginx nginx -t && docker exec nginx nginx -s reload"
```

### F. 清理本机临时批处理文件
```powershell
Remove-Item .\.deploy_frontend.sftp, .\.deploy_backend.sftp, .\.deploy_conf.sftp, .\.default.conf -Force -ErrorAction SilentlyContinue
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
