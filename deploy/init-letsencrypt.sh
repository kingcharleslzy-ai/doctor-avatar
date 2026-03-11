#!/bin/bash
# 一次性初始化 Let's Encrypt 证书
# 用法：cd /root/doctor-avatar && bash deploy/init-letsencrypt.sh your@email.com

set -e

EMAIL=${1:?"用法: bash deploy/init-letsencrypt.sh your@email.com"}
DOMAINS="liyong828.com www.liyong828.com doctor.liyong828.com"
CERT_DIR="./data/certbot/conf/live/liyong828.com"
COMPOSE="docker compose -f docker-compose.prod.yml"

echo "==> 创建临时自签名证书（让 nginx 能先启动）"
mkdir -p "$CERT_DIR"
openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
  -keyout "$CERT_DIR/privkey.pem" \
  -out "$CERT_DIR/fullchain.pem" \
  -subj "/CN=localhost" 2>/dev/null

echo "==> 启动 nginx"
$COMPOSE up -d nginx
sleep 3

echo "==> 申请 Let's Encrypt 证书"
$COMPOSE run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  --email "$EMAIL" \
  --agree-tos --no-eff-email \
  -d liyong828.com -d www.liyong828.com -d doctor.liyong828.com

echo "==> 重载 nginx（使用真实证书）"
$COMPOSE exec nginx nginx -s reload

echo "==> 完成！配置自动续期（每天凌晨 2 点检查）"
(crontab -l 2>/dev/null; echo "0 2 * * * cd /root/doctor-avatar && docker compose -f docker-compose.prod.yml run --rm certbot renew --quiet && docker compose -f docker-compose.prod.yml exec nginx nginx -s reload") | crontab -

echo "==> HTTPS 配置完毕，访问 https://doctor.liyong828.com 验证"
