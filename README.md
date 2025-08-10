# VSCode-Tunnel-Manager

A Python CLI wrapper for managing [VS Code tunnel](https://code.visualstudio.com/docs/remote/vscode-server#_connect-using-visual-studio-code-tunnel).

## Overview

`vscode tunnel` is a feature that allows users to connect to a remote server **without SSH or VPN** access. Instead, it authenticates using a GitHub or Microsoft account by way of the **Visual Studio Code CLI** (`code tunnel`). This makes it especially convenient for users who need to access internal servers from external networks.

However, the official CLI currently only supports **interactive device code authentication**, which requires manual input during login. This poses a problem for users who **do not have direct access** to the server's terminal (for example, outside the internal network).

## What This Tool Does

**VSCode-Tunnel-Manager** is a lightweight CLI utility that:

- Automatically downloads and installs the VS Code CLI (if missing)
- Automatically initiates the `code tunnel` login process
- Captures the **device code prompt** and **sends it by way of email** to a pre-configured recipient
- Makes it much easier to perform remote login from outside the server

This enables convenient "offline" or indirect authentication to VS Code tunnels.

## Usage Example

### 1. Create an email app password

Take Gmail for example.

**Step 1 — Enable 2-Step Verification**
1. Go to Google Account Security.
2. Under “Signing in to Google”, enable **2-Step Verification**.
3. Complete the verification setup (phone, authenticator app, etc.).

**Step 2 — Create an App Password**
1. After enabling 2-Step Verification, go back to the **Security** page.
2. Find **“App passwords”** (it only appears if 2-Step Verification is enabled).
3. Sign in again if prompted.
4. Under **“Select app”**, choose:
   - Mail
5. Under **“Select device”**, choose:
   - The device you’re running Python on (or “Other” → give it a name like `PythonScript`).
6. Click **Generate**.
7. Copy the **16-character App Password**.

---

### 2. Use the email app password to login and send emails

```bash
pip install git+https://github.com/Wangmerlyn/VSCode-Tunnel-Manager.git@main

export SMTP_PASSWORD="Your App Password"

vscode_tunnel_manager \
  --host smtp.gmail.com \
  --port 587 \
  --username your-sender-address@gmail.com \
  --from-addr your-sender-address@gmail.com \
  --to-addrs your-receiver-address@gmail.com \
  --subject-prefix "[VS Code Tunnel] " \
  --starttls \
  --working-dir tmp/code_working \
  --tunnel-name "code_tunnel"
```

## Why Not Use Token Login?

Although the CLI documentation mentions the possibility of authenticating using a **credential token**, this feature is **not yet fully supported** in the current release of `code tunnel`. Until then, this CLI app provides a practical workaround for enabling remote tunnel login.
