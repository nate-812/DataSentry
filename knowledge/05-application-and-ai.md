# 应用层、AI与前端

## 1. Spring Boot API

| 属性 | 内容 |
|---|---|
| 入口 | `com.streamlake.StreamLakeApplication` |
| 部署节点 | data1 |
| 源码目录 | `/opt/StreamLake-Binance/api-server` |
| 端口 | 8080 |
| 健康检查 | `/actuator/health` |
| WebSocket | `RealtimeWSHandler` |
| 定时推送 | `scheduler.RealtimePushScheduler` |

代码调查确认存在6个Controller，包括：

- `KlineController`
- `MarketController`
- 其他Controller未在当前知识中逐一列名

API职责：

- 查询Doris中的历史指标和K线。
- 查询Redis中的风控状态。
- 提供REST和WebSocket。
- 调用AI Engine进行诊断。

2026-06-25观察到：

- `/actuator/health`返回`UP`。
- `/api/kline/latest`可查询并随业务时间推进。

## 2. AI Engine

| 属性 | 内容 |
|---|---|
| 入口 | `ai-engine/main.py` |
| 框架 | FastAPI/Uvicorn |
| 部署节点 | data1 |
| 源码目录 | `/opt/StreamLake-Binance/ai-engine` |
| 端口 | 8000 |
| 健康接口 | `/health` |
| 诊断接口 | `/diagnose` |

启动生命周期中会创建`rag-index-builder`后台线程。Milvus连接失败时捕获异常并降级，不阻止服务启动。

## 3. 现有巨鲸案例检索

这不是运维知识RAG，而是业务案例相似度检索。

### 数据源

- 从Doris `whale_alert`拉取最近1000条。
- 每条告警映射为一个`CaseItem`。
- 不进行自然语言文档切块。

### 向量

- 128维。
- 由手工特征工程构造。
- 包括币种One-hot、时间sin/cos、成交额对数归一化、方向等。
- 最后L2归一化。
- 不使用Embedding模型或LLM生成语义向量。

### Milvus

| 属性 | 内容 |
|---|---|
| Collection | `whale_alert_cases` |
| 主键 | `alert_id` VARCHAR |
| 字段 | direction、severity、summary、embedding等 |
| 向量类型 | FLOAT_VECTOR 128 |
| 索引 | IVF_FLAT |
| 距离 | L2 |
| 更新 | `upsert`按`alert_id`覆盖 |
| 删除 | 未实现 |

### 运维Agent复用结论

不能直接复用：

- 向量空间绑定具体业务特征。
- 不理解架构文档、日志或故障语义。
- Collection Schema也围绕巨鲸告警设计。

可以复用的只有连接Milvus和后台索引任务的工程经验，不是向量和Collection本身。

## 4. Doris AI数据

- Doris存在`ai_diagnosis`表。
- 早期SQL资料表明它用于保存AI报告。
- 完整写入调用链尚未从代码证据中闭合。
- Agent开发时不能假定所有诊断已经自动写入该表。

## 5. 前端

代码侧：

- React 19。
- Vite。
- `vite.config.ts`存在WebSocket代理和静默处理线索。
- 该静默处理用于后端WebSocket未连接时减少开发控制台噪声，不证明生产反向代理已经部署。

服务器侧2026-06-25：

- 未安装Nginx。
- 未发现`dist`产物。
- 未发现Vite或Node进程。
- 未配置80/443前端入口。

结论：

- 前端源码存在。
- 当前云端未部署前端。
- Nginx不是当前已有组件。
- 是否部署前端属于产品范围选择，不是运维故障。

## 6. 应用层巡检

### API

1. 检查8080监听。
2. 调用`/actuator/health`。
3. 单次调用关键只读接口。
4. 比较API业务时间与Doris最新时间。
5. 查看有限错误日志。

### AI

1. 检查8000监听。
2. 调用`/health`。
3. 确认Milvus失败是否为预期降级。
4. 查看后台索引线程是否持续报错。
5. 不因Milvus未启动自动要求启动。

### 前端

只有用户明确需要页面时才检查：

- `package.json`
- 构建产物
- Node/Vite进程
- 静态服务或反向代理
