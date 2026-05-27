# 阿里云 ECS 部署说明

这份说明面向当前项目的首版上线，目标是：

- 让项目长期运行在云端，不依赖本地电脑常开
- 通过公网 IP 或域名访问
- 保留 `/` 官网、`/hospital-ai` 数字人页面和 `/rhinitis-ai` 专病页面

## 推荐部署形态

当前阶段建议使用：

- `阿里云 ECS`
- `Docker + Docker Compose`
- `Nginx` 反向代理

原因：

- 最稳定、最容易掌控
- 适合当前这个 FastAPI + 静态模板项目
- 后续你要接 HTTPS、域名、监控、CI/CD 都方便扩展

## 地域建议

如果你希望最快先跑起来：

- 选 `中国香港` 或 `新加坡`

好处：

- 通常不需要先完成中国大陆 ICP 备案
- 可以先用公网 IP 或域名直接访问

如果你后面想正式面向中国大陆用户长期提供服务：

- 可以迁到 `杭州` 等中国大陆地域
- 但正式域名上线前通常需要完成 ICP 备案

## ECS 建议规格

首版测试建议：

- `2 vCPU`
- `2GB 或 4GB 内存`
- `Ubuntu 22.04 LTS`

## 安全组

至少放行：

- `22` SSH
- `80` HTTP

如果后面接 HTTPS，再放行：

- `443` HTTPS

## 服务器初始化

登录服务器后执行：

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker
docker --version
docker compose version
```

## 拉取项目

```bash
git clone https://github.com/kingcharleslzy-ai/doctor-avatar.git
cd doctor-avatar
cp .env.example .env
```

然后编辑 `.env`，至少填：

- `DOUBAO_REALTIME_API_KEY`（新版豆包语音控制台）

数字人页面主流程只依赖豆包实时语音。

豆包端到端实时语音第二版可先在服务器上验证：

```bash
npm run validate:doubao-cloud
```

通过后再启动站点并检查：

```bash
curl -s http://127.0.0.1:8000/api/app-config
```

确认 `doubao_realtime.configured` 为 `true`。

## 启动

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

## 访问

启动成功后：

- 官网：`http://你的公网IP/`
- 数字人页面：`http://你的公网IP/hospital-ai`
- 专病页面：`http://你的公网IP/rhinitis-ai`

## 查看日志

```bash
docker compose -f docker-compose.prod.yml logs -f app
docker compose -f docker-compose.prod.yml logs -f nginx
```

## 更新部署

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

## 域名与 HTTPS

建议顺序：

1. 先用公网 IP 跑通
2. 再绑定域名
3. 再接 HTTPS

如果你后面要正式接入域名：

- 域名解析到 ECS 公网 IP
- Nginx `server_name` 改成你的域名
- 再接证书

当前仓库已经提供 HTTPS 准备文件：

- [deploy/HTTPS_SETUP.md](D:\charles\Documents\doctor-avatar\deploy\HTTPS_SETUP.md)
- [default.https.conf.example](D:\charles\Documents\doctor-avatar\deploy\nginx\default.https.conf.example)

拿到证书后，可以直接按上面的说明切换到 HTTPS 版 Nginx 配置。

## 当前项目页面

项目现在支持：

- `/` MedFlow 官网
- `/hospital-ai` 医疗数字人实时语音问诊页
- `/rhinitis-ai` 耳鼻喉专病 AI 页面

## 推荐后续工作

1. 先完成 ECS 首次部署
2. 验证豆包实时语音和问诊资料库
3. 再接域名和 HTTPS
4. 最后再做 CI/CD 自动发布
