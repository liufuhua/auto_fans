# Playwright 迁移安装说明

场景：把最近 3 次 Git 提交里的代码迁移到另一台已经部署过本项目的电脑。

## 需要额外处理的内容

### 1. 安装/同步 Python 依赖

这次代码新增了 `playwright` Python 依赖。

如果目标电脑的部署流程会自动根据 `api/pyproject.toml` 或 `api/uv.lock` 同步依赖，可以跳过这一项。

如果不会自动同步，需要在目标电脑的 `api` 目录执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

### 2. 安装 Playwright Chromium 浏览器

Playwright 的 Python 包安装后，还需要安装浏览器文件。这个通常不会随代码迁移自动完成。

在目标电脑的 `api` 目录执行：

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

## 检查

安装后可以执行：

```powershell
.\.venv\Scripts\python.exe -m compileall app
```

然后启动项目，在执行结果页触发评论校验。校验过程日志会写入：

```text
logs/playwright-YYYYMMDD-HHMMSS.txt
```
