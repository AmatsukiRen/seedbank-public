# SeedBank

给 AI 完整的一生。此目录包含 Python 核心、Qt Quick 桌面界面和命令行入口。

在仓库根目录安装：`python -m pip install -e "./tools/seed[desktop,channels]"`。
桌面入口：`python packaging/windows_entry.py`。命令行：`python tools/seed/seed.py`。

目前交付完整源码仓库的可编辑安装和 Windows 程序包，保留仓库中的
`eggs/open.egg`。尚未发布独立 PyPI 包；非可编辑安装需另外设置
`SEEDBANK_EGG` 指向开放种子目录。Python 3.11+，Windows x64 桌面为当前目标。

详见仓库中的 `docs/getting-started.md`、`docs/development.md` 和 `LICENSE`。
角色图与 Live2D 模型不属于代码的 MIT 授权，第三方模型由用户自行选择。
