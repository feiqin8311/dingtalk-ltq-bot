# NapCat.Shell

把 `NapCat.Shell.zip` 解压到这个目录。

解压后目录中应包含：

- `launcher.bat`
- `launcher-win10.bat`，如果你使用 Windows 10
- NapCatQQ 运行所需的其他文件

推荐使用项目目录下的 Windows 脚本启动：

```powershell
.\scripts\windows\start_all.ps1
```

兼容入口 `.\start_all.ps1` 仍然可用，但内部已经转发到 `scripts/windows/start_all.ps1`。

如果你的机器需要 Windows 10 启动器，请在 `.env` 中设置：

```env
NAPCAT_LAUNCHER_PATH=NapCat.Shell\launcher-win10.bat
```
