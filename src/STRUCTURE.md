# 代码结构说明

## 模块化架构

本项目采用模块化设计，将原本的单文件代码（6920行）重构为清晰的模块结构。

## 目录结构

```
src/
├── config.py                    # 配置模块：常量、版本、路径
├── main.py                      # 主入口文件
├── run_research_gui.py          # 原始代码（保留作为参考）
│
├── utils/                       # 工具函数模块
│   ├── __init__.py
│   ├── path_utils.py           # 路径处理工具
│   ├── file_utils.py           # 文件操作工具
│   └── version_utils.py        # 版本比较工具
│
├── services/                    # 服务层模块（业务逻辑）
│   ├── __init__.py
│   ├── ssh_service.py          # SSH服务：连接、隧道、命令执行
│   ├── ollama_service.py        # Ollama服务：服务管理、模型操作
│   ├── api_service.py           # API服务：在线API和Ollama API调用
│   └── update_service.py        # 更新服务：GitHub更新检查
│
└── gui/                         # GUI组件模块
    ├── __init__.py
    ├── main_window.py           # 主窗口：窗口管理、服务初始化
    ├── research_tab.py          # 论文调研标签页（待实现）
    ├── crawler_tab.py           # 论文爬虫标签页（待实现）
    ├── model_management_tab.py  # 模型管理标签页（待实现）
    └── help_tab.py              # 帮助标签页（待实现）
```

## 模块职责

### 配置模块 (`config.py`)
- 版本信息和GitHub配置
- 默认模型列表
- 路径配置函数
- 可选依赖检查

### 工具函数模块 (`utils/`)
- **path_utils.py**: 应用目录、用户数据目录、Ollama命令路径
- **file_utils.py**: JSON文件读写操作
- **version_utils.py**: 版本号比较逻辑

### 服务层模块 (`services/`)
- **ssh_service.py**: 
  - SSH连接管理
  - 端口转发隧道
  - 远程命令执行
  
- **ollama_service.py**:
  - Ollama路径检测
  - 服务启动/停止
  - 模型列表、下载、删除
  - 连接测试
  
- **api_service.py**:
  - 在线API调用（硅基流动等）
  - Ollama API调用
  - 响应解析和Token提取
  
- **update_service.py**:
  - GitHub Release检查
  - 更新文件下载
  - 自动更新脚本生成

### GUI组件模块 (`gui/`)
- **main_window.py**: 
  - 主窗口管理
  - 服务初始化
  - 配置加载/保存
  - 标签页容器
  
- **research_tab.py** (待实现):
  - 论文调研功能界面
  - 在线API配置
  - Ollama配置
  - 表格处理
  - Prompt配置
  
- **crawler_tab.py** (待实现):
  - ArXiv论文爬虫界面
  - 分类选择
  - 时间范围设置
  
- **model_management_tab.py** (待实现):
  - 模型列表显示
  - 模型下载/删除
  
- **help_tab.py** (待实现):
  - 使用指南
  - 更新检查

## 设计原则

1. **单一职责**: 每个模块只负责一个明确的功能领域
2. **低耦合**: 模块间通过接口通信，减少直接依赖
3. **高内聚**: 相关功能集中在同一模块内
4. **可扩展**: 易于添加新功能而不影响现有代码
5. **可测试**: 服务层可以独立测试

## 使用示例

### 使用SSH服务
```python
from services.ssh_service import SSHService

ssh = SSHService(log_callback=print)
if ssh.connect("user", "host", 22, "password"):
    success, output, code = ssh.execute_command("ls -la")
    ssh.establish_tunnel(11435, "localhost", 11434)
```

### 使用Ollama服务
```python
from services.ollama_service import OllamaService

ollama = OllamaService(ssh_service=ssh, log_callback=print)
path = ollama.find_ollama_path("username")
if path:
    ollama.start_service(11435)
    models = ollama.list_models()
```

### 使用API服务
```python
from services.api_service import APIService

api = APIService(log_callback=print)
response = api.call_online_api(
    api_url="https://api.siliconflow.cn/v1/chat/completions",
    api_key="key",
    model_name="model",
    prompt="Hello"
)
```

## 迁移计划

1. ✅ 配置和工具函数模块
2. ✅ 服务层核心模块
3. ⏳ GUI组件逐步迁移
4. ⏳ 完整功能测试
5. ⏳ 文档完善

## 注意事项

- 原始代码 `run_research_gui.py` 保留作为参考
- 新模块可以逐步替换原代码功能
- 保持向后兼容，确保功能完整性

