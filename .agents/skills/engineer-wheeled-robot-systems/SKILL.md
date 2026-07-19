---
name: engineer-wheeled-robot-systems
description: 设计、从零创建、诊断、验证和迭代基于 ROS 2（兼容 ROS 1）的轮式机器人完整软件闭环，覆盖差速/滑移、阿克曼、麦克纳姆、全向轮、舵轮和特殊轮式底盘，支持 C++/Python、MCU/Jetson/工控机、Gazebo/Isaac Sim/MuJoCo 与 SSH 实机。用户提供机器人底盘、硬件、传感器、通信接口、技术栈、仿真器、任务、故障现象或现有仓库时使用；不用于腿式、飞行、水面/水下机器人，也不替代机械、电气和功能安全专业审批。
---

# 轮式机器人工程闭环

## 核心原则

把机器人视为带物理反馈和安全约束的闭环系统，不把问题简化成单个 ROS 节点。始终沿以下链路工作：

传感器与执行器 → 驱动与时间戳 → ROS 接口与 TF → 状态估计与环境表达 → 感知 → 任务决策与规划 → 控制与约束 → 执行器反馈 → 安全与可观测性。

优先采用 ROS 2 原生架构。仅在现有设备或依赖确实要求时保留 ROS 1，并把桥接边界、消息所有权和迁移计划写清楚。

只把可复现的日志、配置、源码、运行图、测量值或测试结果称为证据。把未验证内容标为假设，并说明验证方法。

## 先路由任务

1. 判断任务模式：
   - 从零建设：创建仿真、实机或仿真实机共用的软件方案。
   - 故障诊断：定位任意软件层级的问题并在获准时修复。
   - 系统评审：审查现有架构、性能、安全、可维护性并提出迭代建议。
2. 收集会改变方案的最小信息。读取 [system-intake-and-routing.md](references/system-intake-and-routing.md)。
   - 把硬件设备、技术栈、项目方向和执行边界写入结构化输入。
   - 运行 `scripts/validate_project_intake.py <intake.json> --pretty`，根据目标交付等级主动补问。
   - 每个非显然值保留来源；测试默认值不能进入实机运动配置。
3. 识别底盘运动学。读取 [wheeled-kinematics.md](references/wheeled-kinematics.md)。
4. 建立系统接口契约，再选择具体包和算法。读取 [ros-architecture-and-interfaces.md](references/ros-architecture-and-interfaces.md)。
5. 只加载与当前问题有关的其他参考文件，不要一次加载全部资料。

缺失信息不会改变安全性或主要架构时，采用显式默认值继续；会改变运动模型、硬件接口、部署权限或安全边界时，立即暂停并询问用户。

## 执行安全闸门

按最高影响等级执行，不要因已建立 SSH 连接而提升权限：

| 等级 | 范围 | 默认行为 |
|---|---|---|
| G0 | 文档、源码、配置、离线数据分析 | 可直接执行 |
| G1 | 本地或隔离仿真、单元/集成测试 | 可直接执行，说明资源消耗 |
| G2 | 实机只读诊断、日志、ROS 图、状态读取 | 用户已授权连接后可执行 |
| G3 | 构建、部署、参数写入、服务重启、固件操作 | 操作前确认精确目标、回滚和停机影响 |
| G4 | 轮子转动、制动释放、闭环运动、执行器测试 | 每次明确授权；验证急停、限速、超时停机、场地和人员安全 |

禁止绕过急停、安全控制器、主机指纹、权限边界或硬件联锁。禁止在对话、命令行或日志中暴露密码、令牌、私钥。涉及实机时读取 [ssh-real-robot-safety.md](references/ssh-real-robot-safety.md)。

## 从零建设

先声明目标和当前交付等级：L1 架构级、L2 可构建仿真、L3 可部署但默认禁动的实机项目或 L4 已验证实机。L4 必须有运行证据，不能由配置文件推断。

按顺序交付：

1. 需求与假设：冻结结构化输入及哈希，列出系统边界、任务场景、验收指标、已知未知项和逐字段来源。
   - 同时创建 `generation_trace.json`。每个输入事实只能标为 `used`、`question`、`blocked` 或 `intentionally_unused`；`used` 必须指向生成文件证据。
   - 运行 `scripts/validate_generation_trace.py <intake.json> <generation_trace.json> --project-root <generated-project>`，防止已确认设备、接口或目标在生成中静默丢失。
2. 运动学与硬件映射：轮型、自由度、执行器、传感器、计算节点、通信总线、供电与安全链。
3. 闭环架构：节点/组件、进程和主机分布、Topic/Service/Action、TF、QoS、频率、时间源、生命周期和故障降级。
4. 仓库结构：description、hardware、bringup、localization、perception、navigation、control、simulation、monitoring、tests 等包及依赖方向。
5. 仿真模型：几何、惯量、碰撞、摩擦、执行器和传感器噪声；保持仿真实机接口一致。
6. 分阶段实现：先描述与 TF，再底盘和里程计，再传感器与状态估计，再 SLAM/定位，再导航/决策，最后性能和安全验证。
7. 验证矩阵：静态检查、单元测试、launch 测试、仿真场景、故障注入、HIL、低速实机、任务级验收。

为每个仿真/实机 profile 生成 `runtime_graph.json`，列出组件角色、生产/消费接口、健康与授权门，以及从运动请求到执行器反馈/状态估计的必达路径。L2 必须运行 `scripts/validate_runtime_graph.py <runtime_graph.json>`；仅存在 URDF、world、bridge 和 launch 文件不能算“可构建仿真”。特别检查机器人是否生成、传感器是否出数、状态估计是否启动、安全门能否在该 profile 合法变为健康、最终命令是否到达执行器以及反馈是否回流。

硬件合同必须是单一事实源，并传播到 URDF/Xacro、控制器、固件、状态估计、传感器外参、仿真和启动配置。若某能力因输入或依赖缺失只能部分实现，在 `solution.json` 中把声明标为 `partial`、`blocked` 或 `planned`，不得写成完成。

硬件与时序读取 [hardware-embedded-and-time.md](references/hardware-embedded-and-time.md)，仿真读取 [description-simulation-and-sim2real.md](references/description-simulation-and-sim2real.md)，感知定位读取 [perception-localization-and-mapping.md](references/perception-localization-and-mapping.md)，决策控制读取 [decision-navigation-and-control.md](references/decision-navigation-and-control.md)。

## 故障诊断

1. 固化现象：期望、实际、首次发生时间、复现步骤、影响范围和最近变更。
2. 建立时间线：启动顺序、节点状态、Topic 频率、时间戳、TF 延迟、资源和网络变化。
3. 从执行器反馈向上追踪，或从任务失败点向下追踪；不要同时随意修改多个层级。
4. 为每个假设定义可证伪检查，先运行成本低、风险低、区分度高的检查。
5. 找到根因后实施最小修复，加入回归测试，并验证没有破坏仿真实机一致性。

读取 [diagnosis-and-verification.md](references/diagnosis-and-verification.md)。先运行工作区盘点脚本以减少猜测：

~~~text
python scripts/inspect_ros_workspace.py <workspace-or-repo> --pretty
~~~

## 系统评审与迭代

按严重程度排序输出：

- P0：可导致失控、碰撞、硬件损坏、数据不可恢复或安全链失效。
- P1：阻断核心任务或造成高概率运行失败。
- P2：性能、鲁棒性、测试、部署或维护性明显不足。
- P3：优化机会和长期演进建议。

每条建议包含证据、影响、建议变更、验证方法、回滚方式和依赖条件。不要只罗列最佳实践。

## 使用确定性脚本

- 使用 scripts/inspect_ros_workspace.py 生成 ROS 仓库静态清单和源码证据。
- 使用 scripts/validate_project_intake.py 检查输入完整性、来源和 L1-L4 交付条件，并生成需要向用户提出的问题。
- 使用 scripts/validate_robot_contract.py 检查系统契约、TF、接口、频率和安全超时。
- 使用 scripts/validate_generation_trace.py 检查每个输入事实的生成处置和文件证据。
- 使用 scripts/validate_runtime_graph.py 检查各 profile 的命令—执行—反馈闭环、唯一所有者和健康/授权门。
- 使用 scripts/compare_solution_to_inventory.py 将方案声明与真实仓库清单逐项对照。

脚本只做静态分析，不连接机器人、不执行 ROS 节点、不修改被分析仓库。详细评测流程读取 [evaluation-and-source-comparison.md](references/evaluation-and-source-comparison.md)。

## 输出契约

无论采用哪种模式，最终结果至少包含：

1. 任务结论或推荐方案。
2. 已确认事实、假设和仍需用户提供的信息。
3. 选择的底盘、ROS、语言、计算平台、通信、仿真和算法分支及理由。
4. 闭环架构与关键接口契约。
5. 分阶段实施或诊断步骤。
6. 风险、安全等级、回滚和停止条件。
7. 可运行的验证命令、预期结果和验收标准。
8. 若检查现有仓库，提供文件路径和行号级证据。

## 完成判据

区分“输入足以生成某等级”和“产物已经达到该等级”。只有在接口契约自洽、运行图闭合、关键闭环有反馈、超时能安全停机、仿真或测试证据满足验收指标、遗留风险已明确时，才声明完成。真实机器人未验证时明确写出“仅完成离线/仿真验证”，不得暗示实机可用。

维护或扩展本 Skill 时读取 [sources.md](references/sources.md)，保留来源、版本和许可证边界。
