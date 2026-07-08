# qilinshuzhi.com 中国内地服务器迁移记录

## 目标架构

- `qilinshuzhi.com` / `www.qilinshuzhi.com`：杭州 ECS，承载完整网站和后端。
- `liyong828.com` / `www.liyong828.com`：马来西亚 ECS，只保留数字人页面 `/hospital-ai`。

## 当前杭州 ECS

- 实例：`i-bp15ohkipfk86u3cwuf4`
- 地域：华东1（杭州）
- 公网 IP：`112.124.42.19`
- 私网 IP：`172.21.6.188`
- SSH alias：`aliyun-qilinshuzhi-cn`
- 项目目录：`/root/doctor-avatar`
- app 端口：`127.0.0.1:8000`
- Nginx 配置：
  - `/etc/nginx/conf.d/00-default-deny.conf`
  - `/etc/nginx/conf.d/qilinshuzhi.conf`

## 已完成

- 已安装 Docker、Docker Compose、Nginx、Certbot、Git。
- 已创建 3G swap，降低 2G 内存构建镜像时的失败概率。
- 已克隆项目到 `/root/doctor-avatar`。
- 已上传生产 `.env`。
- 已构建并启动 app 容器。
- 已配置 host Nginx，把 `qilinshuzhi.com` 代理到 `127.0.0.1:8000`。
- 已加默认拒绝配置，直接访问 IP 或错误 Host 不返回默认欢迎页。

## 验证命令

```bash
ssh aliyun-qilinshuzhi-cn
cd /root/doctor-avatar
docker compose -f docker-compose.prod.yml -f docker-compose.host-proxy.yml ps
curl -fsS http://127.0.0.1:8000/health
curl -fsS -H 'Host: qilinshuzhi.com' http://127.0.0.1/health
nginx -t
```

预期健康检查结果：

```json
{"status":"ok"}
```

## DNS 和备案顺序

备案未完成前，不要把 `qilinshuzhi.com` 正式公开解析到杭州服务器并开放网站访问。

依据：

- 阿里云文档说明，备案前通常不需要添加网站域名解析，部分省份还需要先关闭解析。
- 阿里云文档说明，网站未取得备案号前不允许对外开通 Web 服务，否则可能被阿里云监测系统阻断。

参考：

- https://help.aliyun.com/zh/icp-filing/basic-icp-service/support/for-the-record-domain-faq
- https://help.aliyun.com/zh/icp-filing/the-influence-of-the-record-during-the-site-visit

建议顺序：

1. 在阿里云备案系统里选择杭州 ECS 实例 `i-bp15ohkipfk86u3cwuf4` 作为网站服务器。
2. 按备案流程填写主体、网站、负责人、域名等信息。
3. 备案通过后，在阿里云云解析里把：
   - `qilinshuzhi.com` A 记录指向 `112.124.42.19`
   - `www.qilinshuzhi.com` A 记录指向 `112.124.42.19`
4. DNS 生效后签发 HTTPS 证书。
5. HTTPS 验证通过后，再从马来西亚服务器移除 `qilinshuzhi.com`，让马来西亚只承接 `liyong828.com`。

## 后续需要改造

当前 `.github/workflows/deploy.yml` 仍然是 push `main` 自动触发马来西亚 self-hosted runner。正式推送迁移改动前，需要先拆分部署目标：

- 马来西亚部署：只安装 `liyong828.com` 数字人 Nginx 配置。
- 杭州部署：只安装 `qilinshuzhi.com` 网站 Nginx 配置。
- 推荐改成 `workflow_dispatch` 手动选择目标，避免 push 时误部署到错误服务器。

## HTTPS

DNS 指到杭州服务器并符合备案要求后，再执行证书签发：

```bash
ssh aliyun-qilinshuzhi-cn
mkdir -p /var/www/letsencrypt
certbot certonly --webroot \
  -w /var/www/letsencrypt \
  -d qilinshuzhi.com \
  -d www.qilinshuzhi.com
```

拿到证书后，把杭州 Nginx 从 HTTP 配置切换为 HTTPS 配置并 reload。
