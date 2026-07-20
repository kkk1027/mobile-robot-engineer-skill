# 二次开发、功能集成与快速验证

## 适用边界

本流程用于用户已经拥有驱动、算法、功能包、ROS 工作区或部分整机源码，希望把它们组合成满足客户场景的产品。与“从零生成盲测”不同，集成模式可以在用户授权范围内深入读取源码；必须记录来源提交、允许目录、许可证和修改权限。

默认不要直接改供应商或用户基础模块。优先采用覆盖式工作区：

~~~text
vendor_or_existing (固定版本/默认只读)
            ↓
product_adapters (消息、坐标、时间、QoS、ROS 1/2、硬件适配)
            ↓
product_capabilities (导航、跟随、避障、巡检等客户能力)
            ↓
product_bringup + monitoring_safety + tests
~~~

只有原模块由用户拥有、修改范围明确且有回归计划时，才直接改原模块。

## 集成输入

在普通硬件/技术栈/任务输入之外，补充：

- 客户场景、优先级、可量化验收条件和不可接受行为。
- 每个来源工作区的路径/提交、许可证、允许读取目录和修改策略。
- 模块已知能力、当前可构建状态、已有测试、运行环境和依赖版本。
- 模块接口、参数、TF、QoS、时间语义、命名空间和资源需求；未知项必须标记。
- 集成目标：仿真、台架、HIL、实机；以及允许的 G0–G4 操作范围。

不要把“有源码”或“有 launch 文件”视为“可集成”。先构建或静态检查，区分可复用、需适配、需补写和阻塞四种状态。

## 资产清单

对每个来源运行：

~~~text
python scripts/inspect_ros_workspace.py <source-workspace> --output inventory.json --pretty
python scripts/create_module_manifest.py inventory.json --output module_manifest.json --pretty
python scripts/validate_module_manifest.py module_manifest.json
~~~

`create_module_manifest.py` 只生成候选项；它不会猜测接口方向、实际生命周期、运行质量或许可证。补全后的最小结构：

~~~json
{
  "schema_version": 1,
  "source_inventory_sha256": "...",
  "modules": [
    {
      "id": "base_driver",
      "origin": "existing_source",
      "source_package": "base_driver",
      "modification_policy": "adapter_only",
      "maturity": "M1",
      "classification": "needs_adapter",
      "roles": ["hardware", "control"],
      "interfaces": [
        {"id": "wheel_state", "name": "/wheel/state", "type": "sensor_msgs/msg/JointState", "direction": "produces"}
      ],
      "verification": [
        {"kind": "build", "evidence": ["ci/build.log"]},
        {"kind": "bench_or_fake", "evidence": ["tests/fake_transport_test.py"]}
      ]
    }
  ]
}
~~~

`origin` 只能是 `existing_source`、`new_driver`、`new_capability`、`adapter` 或 `product_bringup`；修改策略只能是 `read_only`、`adapter_only` 或 `owned`。分类只能是 `reusable`、`needs_adapter`、`needs_implementation` 或 `blocked`。`M0`–`M5` 表示集成熟度，不等同于实机交付等级。

## 集成熟度

| 等级 | 含义 | 最小证据 |
|---|---|---|
| M0 | 已发现资产 | 来源、路径、职责待确认 |
| M1 | 模块可独立验证 | 构建或静态验证、最小测试 |
| M2 | 接口已兼容或有适配器 | 模块清单和集成契约通过 |
| M3 | 仿真闭环可用 | launch/场景/故障注入证据 |
| M4 | 台架或 HIL 通过 | 设备、版本、日志和结果 |
| M5 | 客户场景实机验收 | 明确场地、授权、指标和记录 |

L1–L4 描述整机交付与安全证据；M0–M5 描述功能资产的集成熟度。M3 不自动表示 L3，M5 也不能绕过 G4 实机授权。

## 集成契约

`integration_contract.json` 通过接口 ID 建立模块连接：

~~~json
{
  "schema_version": 1,
  "modules": ["base_driver", "safety_mux", "navigation"],
  "connections": [
    {"from": "navigation.cmd_request", "to": "safety_mux.autonomy_request"},
    {"from": "safety_mux.safe_command", "to": "base_driver.command"}
  ],
  "internal_flows": [
    {"module": "safety_mux", "from": "autonomy_request", "to": "safe_command"}
  ],
  "tf_edges": [
    {"parent": "odom", "child": "base_link", "owner": "base_driver"}
  ],
  "command_authority": {"module": "safety_mux", "output": "safe_command", "actuator": "base_driver.command"}
}
~~~

每条连接必须从 `produces` 接口到 `consumes` 接口。`internal_flows` 显式声明一个模块如何把消费接口处理为生产接口，避免验证器猜测 mux、融合器或状态估计器的内部行为。类型不同只能在声明适配器模块后连接；适配器也必须出现在模块清单中。动态 TF 边只允许一个 owner。所有运动来源必须先进入唯一命令权威者；它的输出必须抵达执行器输入。

## 只有驱动时的单功能开发

将厂商 SDK、串口、CAN、USB 或 EtherCAT 驱动封装成 `new_driver`，先完成：

1. 参数合同：端口/总线、波特率或位速率、单位、量程、时间戳、错误码和安全默认值。
2. 最小 ROS 接口：消息/Service/Action、连接状态、diagnostics、生命周期或等价状态机。
3. 无动力验证：fake transport、协议回放、模拟硬件或断开执行器的台架测试。
4. 故障行为：连接失败、超时、异常数据、重连和命令拒绝。
5. 最小 launch 和可复现测试。没有 `bench_or_fake` 与 `safety_default` 验证时，不得把驱动声明为可集成。

真实电机、制动和执行器必须保持默认禁动，直到硬件合同、安全链和 G4 授权齐备。

## 客户需求追踪

`requirements_trace.json` 让每项客户需求链接到模块、接口、验证和证据：

~~~json
{
  "schema_version": 1,
  "requirements": [
    {
      "id": "REQ-001",
      "priority": "P1",
      "status": "partial",
      "module_refs": ["navigation", "safety_mux"],
      "interface_refs": ["navigation.cmd_request", "safety_mux.safe_command"],
      "verification": [
        {"id": "TEST-001", "level": "integration_sim", "status": "passed", "evidence": ["results/navigation_scene.json"]}
      ]
    }
  ]
}
~~~

`complete` 要求每一条引用存在且至少一个通过的验证具有证据。P0/P1 的 `complete` 还必须有 `integration_sim`、`bench`、`hil` 或 `field` 级验证；仅单元测试不足以证明产品功能完成。

## 集成顺序和快速验证

使用最小垂直切片，而不是一次启动所有包：

1. 建立一个客户需求和其安全停止路径。
2. 接入必要设备、状态估计、命令权威者和执行器反馈。
3. 检查模块清单、集成契约和运行图。
4. 运行模块单测、契约测试和仿真场景；注入掉线、错误时间戳、QoS 不匹配和命令超时。
5. 通过后再加下一项客户功能，并保留可回滚的工作配置。

若构建失败、接口不兼容、TF 双写、命令竞争、测试未覆盖或证据不足，把状态标为 `blocked`/`partial`，不要用临时 remap、无限 timeout 或多发布者竞态掩盖问题。

## 评测边界

从零生成评测继续使用盲测防火墙：生成阶段只能看冻结输入。集成评测可以看获准源码，但必须冻结来源提交和模块清单；评价“需求闭环、兼容性、运行证据和安全”，不评价代码重合度或复用文件数量。
