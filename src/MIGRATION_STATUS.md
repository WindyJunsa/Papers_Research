# 代码迁移状态

## 已完成模块 ✅

### 1. 配置和工具模块
- ✅ `config.py` - 配置和常量
- ✅ `utils/path_utils.py` - 路径处理
- ✅ `utils/file_utils.py` - 文件操作
- ✅ `utils/version_utils.py` - 版本比较

### 2. 服务层模块
- ✅ `services/ssh_service.py` - SSH连接、隧道、命令执行
- ✅ `services/ollama_service.py` - Ollama服务管理、模型操作
- ✅ `services/api_service.py` - 在线API和Ollama API调用
- ✅ `services/update_service.py` - GitHub更新检查

### 3. GUI框架
- ✅ `gui/main_window.py` - 主窗口框架
- ✅ `gui/research_tab.py` - 论文调研标签页框架
- ✅ `gui/crawler_tab.py` - 论文爬虫标签页框架
- ✅ `gui/model_management_tab.py` - 模型管理标签页框架
- ✅ `gui/help_tab.py` - 帮助标签页（完整实现）

### 4. 主入口
- ✅ `main.py` - 应用程序启动入口

## 待完成功能 ⏳

### GUI组件功能迁移

#### `gui/research_tab.py`
需要从 `run_research_gui.py` 迁移：
- [ ] 在线API配置界面（`create_online_api_tab`）
- [ ] Ollama配置界面（`create_ollama_tab`）
- [ ] 表格配置（`create_table_config`）
- [ ] Prompt配置（`create_right_content`）
- [ ] 并发配置
- [ ] 批处理配置
- [ ] 用量监控显示
- [ ] 调研逻辑（`start_research`, `analyze_row`, `process_table`等）

#### `gui/crawler_tab.py`
需要从 `run_research_gui.py` 迁移：
- [ ] ArXiv分类选择树（`create_crawler_tab`）
- [ ] 时间范围选择（日历组件）
- [ ] 输出文件配置
- [ ] 爬虫逻辑（`start_crawler`, `crawl_arxiv`等）

#### `gui/model_management_tab.py`
需要从 `run_research_gui.py` 迁移：
- [ ] 模型列表刷新（`fetch_models_from_ollama`）
- [ ] 模型下载（`pull_model_with_progress`）
- [ ] 模型删除（`delete_selected_model`）
- [ ] 模型列表显示逻辑

## 迁移策略

### 阶段1：基础框架 ✅
- 创建模块结构
- 实现服务层
- 创建GUI框架

### 阶段2：功能迁移（进行中）
- 逐步迁移各个标签页的功能
- 保持与原代码功能一致
- 使用新的服务层模块

### 阶段3：优化和测试
- 代码优化
- 功能测试
- 文档完善

## 使用方式

### 当前可用
- 所有服务层模块可以直接使用
- GUI框架已创建，可以运行（功能待完善）

### 运行新版本
```bash
python src/main.py
```

### 运行原版本（完整功能）
```bash
python src/run_research_gui.py
```

## 注意事项

1. **保持兼容**：新模块与原代码可以共存
2. **逐步迁移**：功能可以逐步从原代码迁移到新模块
3. **测试验证**：每次迁移后需要测试功能完整性
4. **文档更新**：及时更新文档说明

