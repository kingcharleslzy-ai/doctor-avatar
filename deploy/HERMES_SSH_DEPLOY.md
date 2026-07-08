# Hermes Root SSH 部署

这套方案让 Hermes 用 SSH 登录阿里云服务器的完整 root shell，并保留一个一键部署脚本。

## 1. 在 Hermes 生成专用 SSH key

不要复用 GitHub key。建议单独生成一个只用于阿里云部署的 key：

```bash
ssh-keygen -t ed25519 -f ~/.ssh/hermes_doctor_avatar_aliyun -C "hermes-doctor-avatar-aliyun"
```

## 2. 把 workflow 推到 main

这个仓库新增了一个手动 workflow：`.github/workflows/install-hermes-ssh-deploy-key.yml`。

推送到 `main` 后，它会出现在 GitHub Actions 里。

## 3. 在阿里云服务器安装 Hermes root 公钥

用 GitHub CLI：

```bash
gh workflow run install-hermes-ssh-deploy-key.yml \
  -f public_key="$(cat ~/.ssh/hermes_doctor_avatar_aliyun.pub)"
```

或者在 GitHub 网页里打开 `Install Hermes SSH Root Key`，点 `Run workflow`，把下面命令输出的一整行公钥粘进去：

```bash
cat ~/.ssh/hermes_doctor_avatar_aliyun.pub
```

workflow 会在阿里云 self-hosted runner 上执行，把公钥作为普通 root 登录 key 安装到 `/root/.ssh/authorized_keys`，并写入 `/etc/ssh/sshd_config.d/99-hermes-root-login.conf` 以启用 root 公钥登录、放宽 SSH 入口限制、允许主机防火墙的 22/tcp。

## 4. 配置 Hermes 的 SSH alias

当前有两台阿里云服务器：

- `aliyun-doctor-avatar`：马来西亚服务器，保留 `liyong828.com` 数字人页面。
- `aliyun-qilinshuzhi-cn`：杭州服务器，承接 `qilinshuzhi.com` 完整网站。

把下面内容加到 Hermes 的 `~/.ssh/config`：

```sshconfig
Host aliyun-doctor-avatar
  HostName 47.250.168.45
  User root
  Port 22
  IdentityFile ~/.ssh/hermes_doctor_avatar_aliyun
  IdentitiesOnly yes

Host aliyun-qilinshuzhi-cn
  HostName 112.124.42.19
  User root
  Port 22
  IdentityFile ~/.ssh/hermes_doctor_avatar_aliyun
  IdentitiesOnly yes
```

## 5. 从 Hermes 登录 root shell

```bash
ssh aliyun-doctor-avatar
ssh aliyun-qilinshuzhi-cn
```

登录后就是完整 root 权限。

如果通过阿里云 Workbench 添加登录凭据，页面里的 `SSH密钥认证 > 私钥` 是给 Workbench 自己登录服务器时使用的私钥，不是让你填写公钥的位置。要授权 Hermes 登录，正确做法是先用 Workbench 免密或密码登录服务器，然后把 Hermes 的公钥追加到 root 的 `authorized_keys`：

```bash
mkdir -p /root/.ssh
chmod 700 /root/.ssh
cat >> /root/.ssh/authorized_keys <<'EOF'
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEIcGdNBPRoPhgdulxhcvN552fiNllQS4fT+koC7EOAC hermes-doctor-avatar-aliyun
EOF
chmod 600 /root/.ssh/authorized_keys
chown -R root:root /root/.ssh
```

验证杭州服务器 root 登录：

```bash
ssh aliyun-qilinshuzhi-cn 'whoami && hostname && curl -fsS http://127.0.0.1:8000/health'
```

## 6. 从 Hermes 一键部署

当前 `scripts/hermes_ssh_deploy.sh` 仍然指向 `aliyun-doctor-avatar`，也就是马来西亚服务器。杭州服务器迁移完成前，不要用这个脚本部署 `qilinshuzhi.com`；应先拆分部署脚本或显式传入目标服务器。

使用本仓库的本地辅助脚本：

```bash
scripts/hermes_ssh_deploy.sh
```

它等价于：

```bash
ssh aliyun-doctor-avatar 'bash /root/doctor-avatar/deploy/server/hermes-deploy-command'
```

部署命令会在阿里云上执行这些动作：

- 同步 `/root/doctor-avatar` 到 `origin/main`
- 重建并重启 app 容器
- 同步医生资料库快照
- 导入鼻炎证据库快照
- 重载 host nginx
- 检查本机 `/health`

## 注意

这个 SSH key 拥有完整 root 权限。建议只使用专门生成的 `~/.ssh/hermes_doctor_avatar_aliyun`，不要复用 GitHub key；如果这台机器或私钥丢失，需要立刻从 `/root/.ssh/authorized_keys` 删除对应公钥。
