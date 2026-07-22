# P04：动态巡检、人工接管与安全恢复

本任务用于检验 Skill 能否在一个已能运行的 ROS 2 轮式仿真项目上完成真实功能集成和完整 L2 验收。它不是从零盲测：执行智能体可读取、修改和测试用户明确授权的既有项目；不得读取其他项目、历史评分答案或隐含参考实现。

## 交给执行智能体的文件

1. 整个 Skill 仓库（至少 `SKILL.md`、`references/` 和 `scripts/`）。
2. 用户授权的上一轮仿真项目根目录：`<existing_project_root>`。
3. 本任务书和下面的用户提示词。

若项目根目录、允许修改范围、ROS 环境或隔离 VM 授权未给出，先询问；不要猜测路径、凭据或环境。隔离仿真 VM 只有在用户明确说明主机和项目目录后才可经 SSH 作为 G1 使用；不授权实机、部署、固件或外部账户。

## 复制给执行智能体的用户提示词

```text
使用 $engineer-wheeled-robot-systems，在 <existing_project_root> 的用户授权 ROS 2 仿真项目上实施 P04「动态巡检、人工接管与安全恢复」。这是功能集成任务：先盘点当前源码、运行图和证据，再在最小必要范围内修改。不要读取其他项目、历史评分答案或未授权源码；不要连接真实机器人。

请按以下 12 项输入工作。已知信息不要重复询问；只有会改变运动学、接口、安全、验收或权限结论的未知项才可追问。

1. 项目目标：在室内房间完成可重复的四点巡检；遇到动态障碍时避障或按策略恢复；支持人工接管和恢复自动任务。目标等级为 L2 complete，达不到时如实声明 L2 partial/blocked。
2. 复用范围：允许读取、修改和测试 <existing_project_root> 内所有项目文件；保持现有公开参考机器人模型。新增功能优先放入独立包或适配层，不得复制外部项目实现。
3. 技术栈：Ubuntu 22.04、ROS 2 Humble、Gazebo Classic 11、RViz2、colcon、Python/rclpy；使用安装环境中可用的 Nav2。若 Nav2 或其必要依赖不存在，记录证据并声明 blocked/partial，不得以伪 Action 代替。
4. 底盘与模型：沿用现有官方 TurtleBot3 Waffle Pi 差速参考模型和其仿真传感器/关节配置。若冻结 intake 中存在不同的历史底盘描述，把该模型选择记录为 user_explicit 的 overridden 事实，写明影响；不要将其解释成实车事实。
5. 场景与限制：平面室内房间，至少一个可移动障碍物和一个静态障碍物；只允许 vx/wz 差速运动，不允许横移；速度、加速度和最小障碍距离必须写入 robot contract。
6. 传感器与计算：使用 2D lidar、RGB 相机、IMU、轮式里程计和 /clock；写明 frame、频率、时间源、噪声/仿真范围。相机 /image_raw 是必测接口，不能只证明相机插件存在。
7. 接口与坐标：采用 ROS 2/TF/Nav2 标准命名；定义唯一最终速度命令、人工接管输入、急停/健康门、任务 Action、状态/诊断接口及其 QoS。运行证据必须记录 Action client/server，而非把 Action 伪装成 Topic。
8. 首阶段能力：实际接入 Nav2 NavigateToPose；四点巡检；动态障碍下的等待、绕行或一次受限恢复；人工遥控接管使自动任务暂停/取消；释放后按明确定义恢复或重新派发任务；任务终态可追溯。
9. 仿真 profile：headless 为自动验收 profile；GUI+RViz 为相机与可视化 profile。固定世界、障碍轨迹和随机种子（如适用）。分别记录 RTF、墙钟频率、所需 topic、TF、资源/诊断；GUI 不可仅由 headless 结果代替。
10. 安全与控制：所有速度源只向唯一命令仲裁器发请求；最终执行器命令只能有一个发布者。实现命令超时、软件急停和健康门。急停或超时必须在已观察到非零运动时注入，记录停止时延和零速度结果；软件急停不得描述成物理急停。
11. 开发约束：只使用用户授权项目、系统已安装依赖或明确获准安装的依赖；不输出凭据；不修改无关模块；保留现有能力的回归测试。Python 不承担硬实时闭环。
12. 交付与验证：提交代码、启动命令、自动化测试、所有证据 JSON、日志/探针、SHA-256 证据清单和最终报告。完整 L2 仅在所有下方验收门通过时声明；任何未测相机/GUI、未完成故障注入、缺失 Nav2 Action 或缺失证据文件都必须降级为 partial/blocked。

先输出简短的资产盘点、集成计划、风险和最小垂直切片，再实施。每个阶段只报告有命令、日志、测量或 JSON 支持的结论。
```

## 最低实现与验收门

执行智能体可以选择具体包结构、Nav2 参数、恢复机制和动态障碍实现，但必须满足以下可验证结果：

| 编号 | 验收门 | 通过证据 |
|---|---|---|
| A1 | 真实 Nav2 Action 可用 | `runtime_observation` 中的 Action client/server、`action_trace` 中的 goal 与 terminal 状态 |
| A2 | 正常四点巡检 | headless profile 中四点/周期终态、路径或状态日志 |
| A3 | 动态障碍策略 | 至少一次等待、绕行、受控恢复或明确 abort；记录触发条件与结果 |
| A4 | 人工接管 | 接管时自动请求被暂停/取消，最终命令仍唯一；释放后的恢复语义明确且有 Action 证据 |
| A5 | 运动中安全停止 | 非零运动 → 触发急停、超时或健康故障 → 在边界内归零；`fault_injection_trace.json` 完整 |
| A6 | 必测传感器/GUI | headless 与 GUI 分别记录；`/scan`、`/imu`、`/odom`、`/image_raw` 均有墙钟频率和来源 |
| A7 | 运行闭环 | 命令—仲裁—执行器—反馈—状态估计、健康门、TF 所有权和 QoS 可核查 |
| A8 | 性能 | headless RTF 及 GUI profile 的实际测量；阈值来自任务合同，不得用任意低值掩盖退化 |
| A9 | 回归 | 原有基础巡检/遥控能力不退化，新增能力有自动测试或如实标为 planned |
| A10 | 证据可复核 | JSON 引用的日志/探针随包交付，`evidence_manifest.json` 的哈希和扫描结果通过 |

不得把以下情况判为完整通过：仅节点 active；只启动 GUI；只观察相机插件；急停在静止后触发；只靠 YAML 配置频率；自定义话题伪造 Nav2 Action；缺失引用日志；或以信号退出码代替任务终态。

## 必交付工件

```text
<delivery_root>/
  project_intake.json
  generation_trace.json
  robot_contract.json
  runtime_graph.json
  runtime_observation_headless.json
  runtime_observation_gui.json
  action_trace.json
  fault_injection_trace.json
  evidence_manifest.json
  artifacts/
    commands-and-exit-codes.md
    build.log
    runtime-headless.json
    runtime-gui.json
    action-summary.md
    fault-injection-summary.md
    dynamic-obstacle-summary.md
    gui-camera-summary.md
    validator-results.txt
  tests/
```

运行或如实标为未运行：

```text
validate_project_intake.py project_intake.json --target-level L2
validate_generation_trace.py project_intake.json generation_trace.json --project-root <existing_project_root>
validate_robot_contract.py robot_contract.json
validate_runtime_graph.py runtime_graph.json
validate_runtime_observation.py runtime_observation_headless.json --require-ran --require-complete
validate_runtime_observation.py runtime_observation_gui.json --require-ran --require-complete
validate_action_trace.py action_trace.json --require-terminal
validate_fault_injection.py fault_injection_trace.json --require-ran --require-passed
validate_evidence_bundle.py evidence_manifest.json --root <delivery_root> --scan generation_trace.json --scan runtime_observation_headless.json --scan runtime_observation_gui.json --scan action_trace.json --scan fault_injection_trace.json
```

若 GUI 在无显示服务器的隔离环境中无法运行，仍生成 GUI profile 的测试与 JSON 骨架，但必须将相机/GUI 验收标为 `not_run`，最终结果只能为 `partial`，不能绕过 `--require-complete`。

## 最终反馈格式

```text
项目与来源：<项目名、来源提交/目录、允许修改范围>
输入与授权偏差：<十二项摘要；是否存在 user_explicit override>
环境：<OS、ROS、Gazebo、Nav2、CPU/GPU；是否为获授权隔离 VM>
实现摘要：<新增/修改模块、接口和命令所有权>
验收结果：<L2 complete / L2 partial / blocked；逐项 A1–A10 的 passed/partial/blocked>
实际运行：<命令、退出码、日志和探针相对路径>
校验器：<九条命令的结果；完整 profile 的 require-complete 结果>
未验证项与风险：<明确范围和最小下一步>
对 Skill 的反馈：<哪条指令缺失、含糊、冲突或导致额外工作；附原始证据路径>
```

只提交事实和证据；不要把该任务书中的通过标准、维护者建议或预期实现复制进 `generation_trace.json` 作为伪证据。
