---
name: engineer-wheeled-robot-systems
description: 设计、二次开发、集成、验证、诊断和迭代基于 ROS 2（兼容 ROS 1）的轮式移动机器人软件闭环。用于从零构建机器人、把用户已有驱动/功能包集成为面向客户需求的整机产品、为仅有驱动的设备补齐单功能例程与测试、解决 ROS 机器人软件问题，或评审轮式机器人架构。覆盖感知、定位、决策、规划、控制、执行器反馈、安全、仿真、Jetson/工控机/MCU 与 SSH 实机边界。
---

# 轮式机器人工程闭环

把机器人视为受运动学、硬件和安全约束的闭环产品系统，而不是可任意拼接的 ROS 节点集合：

~~~text
客户需求 → 能力/接口 → 感知与状态估计 → 决策与规划 → 命令仲裁 → 控制与执行器 → 反馈、安全与验收
~~~

优先采用 ROS 2 原生架构。ROS 1 仅保留给现有依赖，并明确桥接边界、消息所有权与替换计划。

## 路由

1. 判断工作模式。
   - 从零构建：根据硬件和技术栈创建架构、仿真或实机项目。
   - 单功能开发：用户只有设备驱动或底层库时，先补齐可独立验证的 ROS 功能基线。
   - 功能集成与产品化：用户已有多个驱动、算法或功能包，需要组成满足客户验收的整机产品。
   - 故障诊断与迭代：定位运行问题、修复获准范围内的代码，或提出有证据的演进建议。
2. 收集会改变方案的最小信息。读取 [system-intake-and-routing.md](references/system-intake-and-routing.md)。记录硬件、技术栈、项目方向、执行边界和每项事实来源。
3. 识别底盘运动学。读取 [wheeled-kinematics.md](references/wheeled-kinematics.md)。
4. 建立接口与所有权契约，再选择实现。读取 [ros-architecture-and-interfaces.md](references/ros-architecture-and-interfaces.md)。
5. 若是单功能开发或功能集成，读取 [secondary-development-and-integration.md](references/secondary-development-and-integration.md)，按其中的模块清单、集成契约和需求追踪流程工作。
6. 若任务是排障、性能退化或验收失败，先按 [wheeled-robot-problem-taxonomy.md](references/wheeled-robot-problem-taxonomy.md) 归类，再提出最低风险的证伪检查；不要直接调参。
7. 只读取当前任务需要的其余参考文件；不要一次加载全部资料。

硬件与时序读取 [hardware-embedded-and-time.md](references/hardware-embedded-and-time.md)，仿真与 sim-to-real 读取 [description-simulation-and-sim2real.md](references/description-simulation-and-sim2real.md)，感知定位读取 [perception-localization-and-mapping.md](references/perception-localization-and-mapping.md)，决策控制读取 [decision-navigation-and-control.md](references/decision-navigation-and-control.md)。

信息缺失但会改变运动学、硬件接口、安全链或实机权限时，暂停并询问。测试默认值只能用于声明的仿真或台架范围，不能静默进入实机运动配置。

## 执行安全门

| 等级 | 范围 | 默认行为 |
|---|---|---|
| G0 | 文档、源码、配置、离线数据分析 | 可直接执行 |
| G1 | 本地构建、仿真、单元/集成测试 | 可直接执行，说明资源影响 |
| G2 | 实机只读诊断、日志、ROS 图、状态读取 | 用户明确授权连接后执行 |
| G3 | 部署、参数写入、重启、固件或服务变更 | 执行前确认精确目标、回滚和影响 |
| G4 | 使能、移动、转向、抓取等实机执行器动作 | 每次明确授权；验证急停、限速、超时、场地和人员安全 |

禁止绕过物理急停、安全控制器、制动、权限边界或硬件保护。SSH 实机任务读取 [ssh-real-robot-safety.md](references/ssh-real-robot-safety.md)。

## 从零构建

声明交付等级：L1 架构级、L2 可构建仿真、L3 可部署但默认禁动的实机项目、L4 已验证实机。L4 必须有运行证据。

1. 冻结结构化输入及哈希，维护 `generation_trace.json`。每个事实只能标为 `used`、`question`、`blocked` 或 `intentionally_unused`；`used` 必须有产物证据。
2. 建立硬件合同：运动学、执行器、传感器、计算节点、总线、供电与安全链。
3. 设计分层仓库：description、hardware、control、sensing、state_estimation、perception_mapping、navigation_decision、bringup、monitoring_safety、simulation_tests。
4. 定义 Topic/Service/Action、TF、QoS、频率、时间源、生命周期、故障降级和唯一命令仲裁者。
5. 先描述/TF，再底盘/里程计，再传感器/估计，再导航/决策，最后性能和安全验证。
6. 对每个仿真或实机 profile 写 `runtime_graph.json`，验证运动请求到执行器、反馈到状态估计以及健康/授权门的可达闭环。
7. L2 运行后记录 `runtime_observation.json`：实际节点/生命周期、发布订阅者、TF 所有者、QoS、墙钟频率、RTF、diagnostics 和 profile。任何 required active 组件都必须在关键流中，或显式标为 `observability_only`/`disabled`。
8. 含导航、巡检、探索、回充或跟随任务时记录 `action_trace.json`，关联 goal、来源、取消、错误码、恢复和最终状态；不能只以“节点仍 active”判定任务成功。
9. 为 L2 交付提供启动、TF/传感器、唯一最终命令/超时、任务 action、故障注入或性能阈值的自动集成测试；运行环境不可用时生成测试并标为 `planned`，不得声称已通过。

使用 `validate_project_intake.py`、`validate_generation_trace.py`、`validate_robot_contract.py`、`validate_runtime_graph.py`、`validate_runtime_observation.py` 和 `validate_action_trace.py`。运行证据规则读取 [runtime-evidence-and-regression.md](references/runtime-evidence-and-regression.md)。硬件合同必须同步传播到 URDF/Xacro、控制器、固件、状态估计、仿真和启动配置。

## 单功能开发

当用户只有串口、CAN、USB、EtherCAT 或厂商 SDK 驱动时，先交付一个默认禁动的功能基线，不要直接把驱动接入整机。

1. 明确设备职责、传输协议、单位、时间戳、故障语义、供电与安全边界。
2. 在 `hardware` 或专用驱动包中封装稳定 ROS 接口；高频实时闭环仍留在 MCU 或驱动器。
3. 提供参数合同、生命周期/连接状态、diagnostics、最小 launch、假硬件或录制数据测试，以及断连/超时测试。
4. 以台架或仿真证明单功能正确，再进入集成；真实执行器默认保持禁止运动。
5. 将模块登记为 `new_driver` 或 `new_capability`，由模块清单验证器确认其测试与安全默认值。

## 功能集成与产品化

集成模式允许在用户授权范围内读取已有源码、配置、测试和运行证据；它与从零盲测不同。先记录来源提交、许可证、修改权限和允许目录。默认策略是固定/只读原模块，在 `product_adapters`、`product_capabilities` 和 `product_bringup` 中新增适配与编排；直接修改原模块必须获得用户授权。

按顺序执行：

1. 对每个来源工作区运行 `inspect_ros_workspace.py`，保留清单和证据。
2. 运行 `create_module_manifest.py <inventory.json>` 生成候选 `module_manifest.json`；补充真实职责、接口方向、成熟度、修改策略和复用结论。
3. 运行 `validate_module_manifest.py`。把模块分类为 `reusable`、`needs_adapter`、`needs_implementation` 或 `blocked`，不要把源码存在等同于可用。
4. 将客户需求写入 `requirements_trace.json`：需求 → 模块 → 接口 → 验证 → 证据。P0/P1 需求没有集成级验证时不得声明完成。
5. 写 `integration_contract.json`：模块连接、消息类型、单位/坐标/时间语义、QoS、命名空间、TF 所有者、适配器和唯一命令权威者。运行 `validate_integration_contract.py` 与 `validate_requirements_trace.py`。
6. 先以最小垂直切片集成：一个需求、必要传感、状态、决策/命令、安全、执行器反馈和验收测试。通过后再增加下一项能力。
7. 按模块单测 → 仿真集成 → 故障注入 → 台架/HIL → 低速实机 → 客户场景验收升级。用证据更新需求状态；保留回滚版本。

`runtime_graph.json` 仍用于检查设计期闭环；`runtime_observation.json` 用于检查已启动实例的实际连接、频率和性能；`integration_contract.json` 用于检查模块之间的静态兼容性。三者不可互相替代。

## 诊断与系统评审

要求现象、复现步骤、期望、首次失败时间、最近变更和证据。沿着“命令生成 → 仲裁/安全 → 控制器 → 驱动/制动 → 执行器 → 反馈/状态估计”追踪。为每个根因假设定义最低风险的证伪检查和回归测试。读取 [diagnosis-and-verification.md](references/diagnosis-and-verification.md)。

评审时按 P0–P3 分级，给出证据、影响、最小修复、验证与回滚。不要仅以包名、文件数或代码重合度评价集成质量。

## 确定性脚本

- `inspect_ros_workspace.py`：生成 ROS 工作区静态清单和去敏源码证据。
- `validate_project_intake.py`：检查输入完整性、来源和 L1–L4 输入条件。
- `validate_generation_trace.py`：检查输入事实在生成物中的处置和证据。
- `validate_robot_contract.py`：检查运动学、TF、接口、频率和安全超时。
- `validate_runtime_graph.py`：检查 profile 的请求—执行器—反馈—状态估计—安全门闭环。
- `validate_runtime_observation.py`：检查实际运行 profile 的关键流、活跃组件处置、动态 TF 所有者、观测频率和 RTF。
- `validate_action_trace.py`：检查导航/探索/跟随等 action 的来源、终态、取消和错误证据。
- `create_module_manifest.py`：从源码清单生成可人工补全的模块资产清单。
- `validate_module_manifest.py`：检查模块复用结论、修改边界、驱动基线和验证证据。
- `validate_integration_contract.py`：检查模块连接、适配器、TF 所有权和唯一命令权威者。
- `validate_requirements_trace.py`：检查客户需求至模块、接口、测试和证据的闭环。
- `compare_solution_to_inventory.py`：仅用于评测时的语义对照。

脚本默认只做静态分析，不连接机器人、不启动 ROS 节点，也不修改用户源码。评测流程读取 [evaluation-and-source-comparison.md](references/evaluation-and-source-comparison.md)。

## 完成条件

完成不是“每个包能编译”或“所有节点 active”。只有当目标需求具备可追溯实现和验收证据、设计图和运行事实都闭合、关键 action 有终态、命令能安全停止、性能结论来自实测 profile、实机等级与证据一致时，才可以声明整机功能完成。未验证能力明确标为 `planned`、`partial` 或 `blocked`。
