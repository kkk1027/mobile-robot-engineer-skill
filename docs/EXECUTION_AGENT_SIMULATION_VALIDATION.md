# 仿真验证执行智能体：任务说明

本文件给执行 Skill 的智能体阅读。目标是以一个完整、用户提供的十二项输入为起点，独立创建或评估轮式机器人仿真项目，并产出可供维护者复核的运行证据。它不授予真实机器人、远程主机或外部账户权限。

## 0. 操作边界

- 只允许 G0/G1：本地文件、构建、测试、仿真和离线工件分析。
- 禁止 SSH、部署、固件、真实硬件、真实传感器、真实执行器和云端凭据。
- 每次任务在新的空输出目录中进行；不得读取其他用户项目、历史生成物或评分答案作为实现来源。
- 用户会提供十二项项目输入。已提供的信息不得重复索要；只有会改变运动学、接口、安全或验收结论的额外未知项才可追问。
- 环境没有 ROS、仿真器或依赖时，保留设计、测试骨架和失败证据，声明 `L1`/`planned`；禁止伪造已构建或已运行。

## 1. 启动前必读

1. [Skill 主流程](../.agents/skills/engineer-wheeled-robot-systems/SKILL.md)。
2. [系统输入与路由](../.agents/skills/engineer-wheeled-robot-systems/references/system-intake-and-routing.md)。
3. [仿真与 Sim-to-Real](../.agents/skills/engineer-wheeled-robot-systems/references/description-simulation-and-sim2real.md)。
4. [运行事实与回归证据](../.agents/skills/engineer-wheeled-robot-systems/references/runtime-evidence-and-regression.md)。

若任务是故障诊断，再读 [问题路由](../.agents/skills/engineer-wheeled-robot-systems/references/wheeled-robot-problem-taxonomy.md)。

## 2. 必须完成的工作

1. 将用户的十二项输入写为 `project_intake.json`，为默认值标记 `test_default_simulation_only`。
2. 运行 `validate_project_intake.py`，冻结输入哈希；生成 `generation_trace.json`、`robot_contract.json` 和 `runtime_graph.json`。
3. 先建立最小垂直切片：运动请求 → 唯一命令仲裁 → 仿真执行器 → 轮反馈 → 状态估计；不要先堆叠全部功能。
4. 为任何导航、探索、巡检、跟随或回充动作定义成功、失败、取消、超时和恢复出口；不允许只依赖节点仍为 active。
5. 实现或生成 L2 最低测试集：启动/退出、TF/传感器、命令超时/急停、一个 action 终态、一个故障注入或性能测试。
6. 如可运行仿真，分别执行 headless 和 GUI（如任务需要）profile；收集实际话题发布订阅者、频率、TF、diagnostics、RTF 和资源观测，写入 `runtime_observation.json`。
7. 如有任务 action，写入 `action_trace.json`，记录 goal ID、来源、开始/结束时间、终态、取消来源或错误码。

## 3. 必须运行或如实标为未运行的校验

```text
validate_project_intake.py project_intake.json --target-level L2
validate_generation_trace.py project_intake.json generation_trace.json --project-root <project>
validate_robot_contract.py robot_contract.json
validate_runtime_graph.py runtime_graph.json
validate_runtime_observation.py runtime_observation.json --require-ran
validate_action_trace.py action_trace.json --require-terminal
```

若仿真没有运行，最后两项不得伪造通过；保留可验证的 JSON 骨架并明确执行状态为 `not_run`/`planned`。

## 4. 运行期硬性规则

- 所有运动源只能把请求交给唯一命令仲裁器；最终执行器命令只能有一个发布者。
- 任何 active 且属于关键功能的组件必须写入 `critical_flows`。已启动但输出无人消费的平滑器、滤波器或安全器是失败，不是可忽略告警。
- 频率验收使用墙钟观测值和采样窗口，不使用 YAML 配置值代替。仿真同时记录 RTF；GUI 性能不等于 headless 性能。
- `canceled` action 必须记录取消来源；`aborted` action 必须记录错误码和消息；`active` 不能作为任务完成证据。
- 故障注入必须验证安全停止或明确降级行为，不得只观察进程仍在运行。

## 5. 交付给维护者的工件

```text
<project>/
  project_intake.json
  generation_trace.json
  robot_contract.json
  runtime_graph.json
  runtime_observation.json
  action_trace.json
  tests/
  artifacts/
    commands-and-exit-codes.md
    build.log
    runtime-summary.md
    action-summary.md
    failure-injection-summary.md
```

最后给出简短报告：实际执行的命令和退出码、构建/仿真/测试状态、L1 或 L2 声明、未验证项、发现的风险、最小下一步。工件中不得写入私钥、密码、Token、用户源码或无关个人数据。

## 6. 维护者需要的反馈格式

```text
输入项目：<名称与十二项摘要>
环境：<ROS、仿真器、OS、CPU/GPU>
结果：<L1/L2、passed/partial/blocked>
实际运行：<命令、退出码、日志/工件位置>
校验结果：<六个验证器的结果>
发现的问题：<按命令、TF、定位、Nav2、QoS、驱动、性能、测试分类>
对 Skill 的建议：<哪个指令缺失、错误或导致重复工作>
```

只报告可由证据支持的结论。若任务因环境或缺少输入受阻，说明阻塞点和最小补充信息，而不是扩展权限或猜测真实硬件参数。
