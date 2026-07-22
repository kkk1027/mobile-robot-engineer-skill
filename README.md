# 轮式机器人工程闭环 Skill

面向 Codex 的项目专用 Skill：以 ROS 2 为主、兼容既有 ROS 1，支持轮式移动机器人的从零构建、设备驱动补齐、功能集成、仿真/台架验证、实机诊断与迭代。

它将机器人视为从感知、状态估计、决策与规划、命令仲裁、控制执行，到反馈和安全的完整闭环，而非若干可随意拼接的 ROS 节点。

## 能做什么

- 根据底盘、传感器、计算平台、ROS 版本和目标场景，建立仿真或默认禁动的实机软件方案。
- 将已有驱动、算法、功能包与 ROS 工作区整合为有客户需求追踪和验收证据的产品。
- 当只有串口、CAN、USB、EtherCAT 或厂商 SDK 驱动时，补齐稳定 ROS 接口、假硬件/台架测试、诊断与安全默认值。
- 定位 ROS 图、TF、QoS、时间同步、控制链、网络、驱动和参数配置问题，并给出可验证的修复与演进建议。
- 在用户明确授权后，通过 OpenSSH alias 对真实机器人进行只读诊断；部署、配置写入和运动均有独立安全闸门。

当前覆盖差速、阿克曼、全向/麦克纳姆、舵轮等轮式运动学；计算平台可选 MCU、Jetson、工控机或多机架构；仿真可选 Gazebo、Isaac Sim、MuJoCo 等。

## 快速开始

本仓库本身就是项目专用 Skill 仓库。在仓库根目录启动 Codex，或将下列目录带入你的机器人项目：

```text
.agents/skills/engineer-wheeled-robot-systems/
```

向智能体说明目标，并提供已知事实及其来源。例如：

```text
使用 engineer-wheeled-robot-systems：
为四轮差速 ROS 2 Humble 机器人集成现有底盘驱动、2D 雷达定位和导航。
计算平台为 Jetson + MCU；先在 Gazebo 验证；实机仅允许 SSH 只读诊断。
客户要求是室内自主巡检与可验证的急停/超时停止。
```

若信息会影响运动学、硬件接口、安全链或实机权限，Skill 会先提问，而不会用默认值静默替代。默认值只能用于明确标识的仿真或台架测试。

## 推荐输入

先给出已知信息；未知项可以明确写“未知”。

| 类别 | 关键内容 |
| --- | --- |
| 目标 | 客户场景、优先级、量化验收条件、不可接受行为 |
| 底盘 | 轮式类型、轮距/轴距、轮径、最大速度、编码器与驱动器 |
| 硬件 | 传感器、MCU/Jetson/工控机、总线、供电、安全链、急停 |
| 软件 | ROS 版本、Ubuntu/中间件、现有包/驱动、仿真器、源码路径与提交 |
| 接口 | Topic/Service/Action、TF、单位、坐标系、时间戳、QoS、频率 |
| 约束 | 可读取与可修改目录、许可证、仿真/台架/实机范围、G0–G4 授权 |
| 实机连接 | 用户预先配置的 SSH alias、机器人身份、维护窗口；不要提供私钥或密码 |

## 四种工作模式

1. **从零构建**：输出硬件合同、架构、仿真/实机工程骨架、运行闭环和分级交付证据。
2. **单功能开发**：将已有设备驱动封装为可独立测试、默认禁动的 ROS 功能模块。
3. **功能集成与产品化**：以模块清单、接口契约和客户需求追踪，将独立能力逐步集成为整机产品。
4. **诊断与迭代**：沿“命令生成 → 仲裁/安全 → 控制器 → 驱动 → 执行器 → 反馈”的链路排障并提出回归验证。

功能集成默认将原有模块固定为只读，在 `product_adapters`、`product_capabilities`、`product_bringup` 中实现适配与编排；修改原模块必须取得用户授权并有回归计划。

## 二次开发的基本流程

```text
源码/驱动资产盘点
  → 模块清单与复用结论
  → 客户需求追踪
  → 接口、TF、命令权威者契约
  → 最小垂直切片
  → 仿真/故障注入/台架/HIL
  → 低速实机与客户场景验收
```

关键产物为：

- `inventory.json`：ROS 工作区静态资产盘点。
- `module_manifest.json`：模块来源、成熟度、复用结论、接口与验证证据。
- `integration_contract.json`：模块连接、TF 所有权、适配器与唯一命令权威者。
- `requirements_trace.json`：客户需求到模块、接口、验证和证据的闭环。
- `runtime_graph.json`：运行时“运动请求—执行器—反馈—状态估计—安全门”闭环。

详细规则见 [二次开发与集成参考](.agents/skills/engineer-wheeled-robot-systems/references/secondary-development-and-integration.md)。

## 内置校验工具

以下脚本默认只做静态检查：不启动 ROS、不连接机器人、不修改用户源码。

```text
scripts/inspect_ros_workspace.py
scripts/create_module_manifest.py
scripts/validate_module_manifest.py
scripts/validate_integration_contract.py
scripts/validate_requirements_trace.py
scripts/validate_project_intake.py
scripts/validate_generation_trace.py
scripts/validate_robot_contract.py
scripts/validate_runtime_graph.py
scripts/validate_runtime_observation.py
scripts/validate_action_trace.py
scripts/validate_fault_injection.py
scripts/validate_evidence_bundle.py
```

以当前仓库中的测试为例：

```bash
python -m unittest discover -s tests -v
python -m compileall -q .agents/skills/engineer-wheeled-robot-systems/scripts
```

Windows 可将 `python` 替换为 `py -3`；Linux/macOS 按本机 Python 解释器调整。

## 实机安全边界

| 等级 | 操作 | 是否可直接执行 |
| --- | --- | --- |
| G0 | 文档、源码、离线日志、静态校验 | 可以 |
| G1 | 本地构建、仿真、单元/集成测试 | 可以，需说明资源影响 |
| G2 | SSH 只读诊断、日志、ROS 图、状态读取 | 用户明确授权连接后可以 |
| G3 | 部署、参数写入、服务重启、固件变更 | 每次先确认目标、影响与回滚 |
| G4 | 使能、移动、转向及任何执行器动作 | 每次明确授权，并确认急停、限速、超时、场地与人员安全 |

SSH 连接不是 G3/G4 授权。禁止绕过急停、安全控制器、制动、watchdog、权限与硬件保护；禁止使用 `StrictHostKeyChecking=no`，禁止读取或打印私钥、密码、Token。交给实机操作智能体前，请先阅读 [实机交接文档](docs/AGENT_HANDOFF_REAL_ROBOT.md)。交给仿真验证智能体前，请阅读 [仿真验证任务说明](docs/EXECUTION_AGENT_SIMULATION_VALIDATION.md)。

用于下一轮复杂功能集成与验收的执行提示词见 [P04 动态巡检任务书](docs/EXECUTION_AGENT_P04_DYNAMIC_PATROL.md)。

## 目录

```text
.agents/skills/engineer-wheeled-robot-systems/
  SKILL.md                  # 主工作流与安全门
  references/               # 按需加载的领域参考
  scripts/                  # 静态盘点与契约校验工具
tests/                       # 工具测试与通用集成样例
evals/                       # 通用场景与去敏评测结果
docs/AGENT_HANDOFF_REAL_ROBOT.md
```

## 交付声明

Skill 用 L1–L4 表示整机交付与实机安全证据，用 M0–M5 表示模块集成熟度。二者不可混用：仿真可用不等于实机可动；有源码或能编译也不等于产品功能完成。只有需求、接口、测试、运行证据和安全停止路径都闭合后，才可声明对应能力完成。

## 许可

仓库尚未声明开源许可证。公开可见不自动授予再分发或商用许可；计划采用前请由仓库维护者补充许可证并审阅第三方依赖许可证。
