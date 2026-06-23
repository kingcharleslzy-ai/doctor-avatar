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

workflow 会在阿里云 self-hosted runner 上执行，把公钥作为普通 root 登录 key 安装到 `/root/.ssh/authorized_keys`，并写入 `/etc/ssh/sshd_config.d/99-hermes-root-login.conf` 以启用 root 公钥登录和放宽 SSH 入口限制。

## 4. 配置 Hermes 的 SSH alias

把下面内容加到 Hermes 的 `~/.ssh/config`：

```sshconfig
Host aliyun-doctor-avatar
  HostName 47.250.168.45
  User root
  Port 22
  IdentityFile ~/.ssh/hermes_doctor_avatar_aliyun
  IdentitiesOnly yes
```

## 5. 从 Hermes 登录 root shell

```bash
ssh aliyun-doctor-avatar
```

登录后就是完整 root 权限。

## 6. 从 Hermes 一键部署

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
