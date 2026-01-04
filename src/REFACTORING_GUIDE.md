# 代码重构指南

本文档说明如何完成代码重构，将单文件代码拆分为模块化结构。

## 目录结构

```
src/
├── config.py                 # 配置和常量
├── main.py                   # 主入口文件
├── utils/                    # 工具函数
│   ├── __init__.py
│   ├── path_utils.py
│   ├── file_utils.py
│   └── version_utils.py
├── services/                 # 服务层
│   ├── __init__.py
│   ├── ssh_service.py        # SSH服务
│   ├── ollama_service.py     # Ollama服务（待创建）
│   ├── api_service.py        # API服务
│   └── update_service.py     # 更新服务
└── gui/                      # GUI组件
    ├── __init__.py
    ├── main_window.py        # 主窗口（待创建）
    ├── research_tab.py       # 论文调研标签页（待创建）
    ├── crawler_tab.py        # 爬虫标签页（待创建）
    ├── model_management_tab.py # 模型管理标签页（待创建）
    └── help_tab.py           # 帮助标签页（待创建）
```

## 已完成模块

### 1. 配置模块 (`config.py`)
- ✅ 版本信息
- ✅ 默认模型列表
- ✅ 路径配置
- ✅ 可选依赖检查

### 2. 工具函数模块 (`utils/`)
- ✅ `path_utils.py` - 路径处理
- ✅ `file_utils.py` - 文件操作
- ✅ `version_utils.py` - 版本比较

### 3. 服务层模块 (`services/`)
- ✅ `ssh_service.py` - SSH连接和隧道
- ✅ `api_service.py` - API调用
- ✅ `update_service.py` - 更新检查

## 待完成模块

### 1. Ollama服务 (`services/ollama_service.py`)
需要从原代码中提取以下功能：
- `start_ollama_services()` - 启动Ollama服务
- `test_ollama_connection()` - 测试连接
- `stop_ollama_model()` - 停止模型
- `install_ollama()` - 安装Ollama
- `pull_model_with_progress()` - 下载模型
- `fetch_models_from_ollama()` - 获取模型列表

### 2. GUI组件模块 (`gui/`)

#### `gui/main_window.py`
主窗口类，包含：
- 窗口初始化
- 标签页管理
- 状态管理
- 配置加载/保存

#### `gui/research_tab.py`
论文调研标签页，包含：
- 在线API配置
- Ollama配置
- 表格配置
- Prompt配置
- 并发配置
- 批处理配置
- 监控显示

#### `gui/crawler_tab.py`
论文爬虫标签页，包含：
- ArXiv分类选择
- 时间范围选择
- 输出文件配置

#### `gui/model_management_tab.py`
模型管理标签页，包含：
- 模型列表显示
- 模型下载
- 模型删除

#### `gui/help_tab.py`
帮助标签页，包含：
- 使用指南
- 联系方式
- 更新检查按钮

## 重构步骤

### 步骤1：创建Ollama服务
1. 从 `run_research_gui.py` 中提取Ollama相关方法
2. 创建 `services/ollama_service.py`
3. 实现OllamaService类

### 步骤2：创建GUI组件
1. 创建 `gui/__init__.py`
2. 逐个创建各个标签页组件
3. 将原代码中的方法迁移到对应组件

### 步骤3：创建主窗口
1. 创建 `gui/main_window.py`
2. 将ResearchGUI类重构为MainWindow
3. 整合各个标签页组件

### 步骤4：创建主入口
1. 创建 `main.py`
2. 简化启动逻辑

### 步骤5：测试和修复
1. 测试各个模块功能
2. 修复导入错误
3. 确保功能完整性

## 注意事项

1. **保持向后兼容**：确保重构后的功能与原代码一致
2. **依赖管理**：注意模块间的依赖关系
3. **日志系统**：统一使用回调函数处理日志
4. **配置管理**：使用config.py统一管理配置
5. **错误处理**：保持原有的错误处理逻辑

## 代码风格

- 使用类型提示（Type Hints）
- 添加文档字符串（Docstrings）
- 遵循PEP 8代码规范
- 使用有意义的变量和函数名

## 测试建议

重构完成后，建议：
1. 单元测试各个服务模块
2. 集成测试GUI组件
3. 端到端测试完整流程

