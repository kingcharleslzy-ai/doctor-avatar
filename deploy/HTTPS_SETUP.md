# HTTPS 上线说明

这份说明面向当前线上地址：

- `liyong828.com`
- `www.liyong828.com`
- `doctor.liyong828.com`

目标是：

- 保留当前 Docker + Nginx 架构
- 为公网站点接入 HTTPS
- 不影响现有自动部署

## 当前项目已准备好的部分

仓库已经预留：

- `docker-compose.prod.yml` 已映射 `443:443`
- `deploy/nginx/certs/` 目录会挂载到容器内 `/etc/nginx/certs`
- `deploy/nginx/default.https.conf.example` 提供 HTTPS 版 Nginx 配置示例

## 推荐做法

当前最省事的做法是：

1. 先申请一个 `liyong828.com` 的证书
2. 把证书文件放到服务器 `deploy/nginx/certs/`
3. 用 HTTPS 示例配置替换当前 `default.conf`
4. 重启容器

## 证书文件准备

无论你是从阿里云证书服务还是其他 CA 拿证书，最终需要两份 PEM 文件：

- `fullchain.pem`
- `privkey.pem`

服务器上的放置路径建议为：

```bash
/root/doctor-avatar/deploy/nginx/certs/fullchain.pem
/root/doctor-avatar/deploy/nginx/certs/privkey.pem
```

## 切换到 HTTPS 配置

登录服务器后执行：

```bash
cd /root/doctor-avatar
cp deploy/nginx/default.https.conf.example deploy/nginx/default.conf
docker compose -f docker-compose.prod.yml up -d --build
```

## 防火墙 / 安全组

确认服务器已经放行：

- `80`
- `443`

## 验证

完成后验证：

```bash
curl -I http://liyong828.com
curl -I https://liyong828.com
curl -I https://www.liyong828.com
```

理想结果：

- `http://` 自动跳转到 `https://`
- `https://` 返回 `200` 或应用本身的正常响应

## 回滚

如果切换 HTTPS 后 Nginx 起不来，可以回滚到当前 HTTP 配置：

```bash
cd /root/doctor-avatar
git checkout -- deploy/nginx/default.conf
docker compose -f docker-compose.prod.yml up -d --build
```
