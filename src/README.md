# Paper Research Tool - 模块化版本

## 项目结构

```
src/
├── config.py                 # ✅ 配置和常量
├── main.py                   # ✅ 主入口文件
├── run_research_gui.py       # 📄 原始单文件代码（保留作为参考）
├── README.md                 # ✅ 项目说明
├── REFACTORING_GUIDE.md      # ✅ 重构指南
├── STRUCTURE.md              # ✅ 代码结构说明
├── MIGRATION_STATUS.md       # ✅ 迁移状态
├── utils/                    # ✅ 工具函数模块
│   ├── __init__.py
│   ├── path_utils.py
│   ├── file_utils.py
│   └── version_utils.py
├── services/                 # ✅ 服务层模块
│   ├── __init__.py
│   ├── ssh_service.py        # ✅ SSH服务
│   ├── ollama_service.py     # ✅ Ollama服务
│   ├── api_service.py        # ✅ API服务
│   └── update_service.py     # ✅ 更新服务
└── gui/                      # ✅ GUI组件框架
    ├── __init__.py
    ├── main_window.py        # ✅ 主窗口
    ├── research_tab.py       # ⏳ 论文调研标签页（框架完成，功能待迁移）
    ├── crawler_tab.py        # ⏳ 论文爬虫标签页（框架完成，功能待迁移）
    ├── model_management_tab.py # ⏳ 模型管理标签页（框架完成，功能待迁移）
    └── help_tab.py           # ✅ 帮助标签页（完整实现）
```

## 已完成模块

### ✅ 配置模块 (`config.py`)
- 版本信息
- 默认模型列表
- 路径配置
- 可选依赖检查

### ✅ 工具函数模块 (`utils/`)
- `path_utils.py` - 路径处理工具
- `file_utils.py` - JSON文件操作
- `version_utils.py` - 版本比较

### ✅ 服务层模块 (`services/`)
- `ssh_service.py` - SSH连接、隧道、命令执行
- `api_service.py` - 在线API和Ollama API调用
- `update_service.py` - GitHub更新检查和下载

## 待实现模块

### ⏳ Ollama服务 (`services/ollama_service.py`)
需要从原代码提取：
- Ollama服务启动/停止
- 模型管理（下载、删除、列表）
- 连接测试

### ⏳ GUI组件 (`gui/`)
- 主窗口管理
- 各个功能标签页
- 组件间通信

## 使用方式

### 当前状态
- 原始代码：`run_research_gui.py` 仍然可用
- 新模块：可以逐步迁移使用

### 示例：使用SSH服务

```python
from services.ssh_service import SSHService

ssh = SSHService(log_callback=print)
if ssh.connect("user", "host", 22, "password"):
    success, output, code = ssh.execute_command("ls -la")
    ssh.establish_tunnel(11435, "localhost", 11434)
    ssh.disconnect()
```

### 示例：使用API服务

```python
from services.api_service import APIService

api = APIService(log_callback=print)
response = api.call_online_api(
    api_url="https://api.siliconflow.cn/v1/chat/completions",
    api_key="your_key",
    model_name="moonshotai/Kimi-K2-Instruct-0905",
    prompt="Hello"
)
tokens = api.extract_tokens(response, "online")
text = api.extract_response_text(response, "online")
```

### 示例：检查更新

```python
from services.update_service import UpdateService

update = UpdateService(log_callback=print)
release_data = update.check_for_updates()
if release_data:
    path = update.download_update(release_data)
    if path:
        script = update.create_update_script("PaperResearchTool.exe")
```

## 重构进度

- [x] 配置模块 (`config.py`)
- [x] 工具函数模块 (`utils/`)
- [x] SSH服务 (`services/ssh_service.py`)
- [x] Ollama服务 (`services/ollama_service.py`)
- [x] API服务 (`services/api_service.py`)
- [x] 更新服务 (`services/update_service.py`)
- [x] 主窗口框架 (`gui/main_window.py`)
- [x] 主入口文件 (`main.py`)
- [ ] GUI标签页组件（待逐步迁移）
  - [ ] 论文调研标签页
  - [ ] 论文爬虫标签页
  - [ ] 模型管理标签页
  - [ ] 帮助标签页

## 当前状态

✅ **已完成核心模块化重构**

所有核心模块和GUI框架已创建完成：
- ✅ 配置和工具函数模块
- ✅ 完整的服务层（SSH、Ollama、API、更新）
- ✅ 主窗口框架
- ✅ 所有GUI标签页框架
- ✅ 主入口文件

⏳ **待完成功能迁移**

GUI标签页的功能逻辑需要从原代码逐步迁移：
- ⏳ 论文调研标签页（在线API配置、Ollama配置、表格处理、Prompt配置、调研逻辑）
- ⏳ 论文爬虫标签页（ArXiv分类选择、爬虫逻辑）
- ⏳ 模型管理标签页（模型列表刷新、下载、删除逻辑）
- ✅ 帮助标签页（已完成）

## 下一步

1. 逐步迁移GUI组件功能
2. 集成测试各个模块
3. 优化代码和文档
4. 完整功能验证

详细的重构指南请参考 `REFACTORING_GUIDE.md`  
代码结构说明请参考 `STRUCTURE.md`

