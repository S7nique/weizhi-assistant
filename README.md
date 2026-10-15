# 维知助手

面向Windows的设备手册检索与维修工单应用，支持文字PDF导入、按手册检索、引用留存、工单管理和可选AI解释。

## 环境
Windows 10/11 64位；Python 3.12；Microsoft Edge WebView2。Node.js用于前端测试，运行便携程序无需Python或Node.js。

## 开发
建立.venv并安装requirements.txt中的依赖，运行desktop.py。
前端依赖使用npm ci安装，npm test运行测试；后端使用python -m unittest discover -s tests -p "test_*.py"。
运行scripts/打包手册管理版.py生成Windows便携目录；输出路径以源码目录的上级目录为基准。

## 代码结构
- desktop.py：桌面窗口、本机资源服务和文件接口。
- manual_library.py：PDF解析、SQLite索引、按手册检索和归档。
- ai_client.py：兼容Chat Completions格式的可选模型调用。
- src：界面、内置条目、检索与工单逻辑。
- tests：核心、前端和后台测试，以及自制模拟PDF。

requirements-tools.txt只供重建测试PDF或核对厂家原始资料使用。原始厂家PDF需从资料来源页列出的官方地址另行获取。
密钥由使用者在应用本地设置，仅在本次运行中保留。源码不包含账号凭证和使用者工单。
第三方许可见完整材料中的05_资料来源与许可；本项目自身尚未指定开源许可证。
