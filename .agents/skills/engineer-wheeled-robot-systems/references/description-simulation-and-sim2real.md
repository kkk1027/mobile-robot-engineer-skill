# 机器人描述、仿真与 Sim-to-Real

## 描述模型

使用 Xacro 将几何参数、底盘类型、传感器选件和仿真插件分离。至少检查：

- visual、collision 和 inertial 坐标一致。
- 质量为正，惯量矩阵物理可行且不过小。
- joint type、axis、limit、damping、friction 与实物一致。
- 轮接触几何和半径不由高多边形 mesh 决定。
- base_link、base_footprint、odom、map 和传感器 frames 符合接口契约。
- ros2_control joint/interface 与控制器配置一致。

使用 check_urdf、xacro 展开、RViz 和 TF 检查作为最小验证。

## 仿真器选择

| 条件 | 优先 |
|---|---|
| ROS 2 原生集成、常规移动机器人、传感器与 Nav2 | 现代 Gazebo 与 ros_gz |
| NVIDIA GPU、合成数据、高保真相机/雷达、Isaac ROS | Isaac Sim |
| 控制研究、强化学习、已有 MJCF/物理模型 | MuJoCo |

版本必须与 ROS 发行版、操作系统和桥接插件匹配。不要把 Gazebo Classic 配置未经验证地用于现代 Gazebo。

## 接口等价

仿真和实机保持相同的上层契约：

- 相同 Topic/Service/Action 名称和消息类型。
- 相同 TF 树、frame_id、单位和坐标方向。
- 相同控制器接口、限制和指令超时。
- 用 launch 参数或硬件插件替换底层，而不是复制整套导航配置。

允许物理和噪声参数不同，但要记录差异。

## 物理与传感器

至少建模：

- 轮地摩擦、侧滑、滚动阻力、接触刚度和执行器饱和。
- 电机响应、死区、延迟、制动和编码器量化。
- IMU bias/噪声、雷达量程和遮挡、相机内外参及帧率。
- 网络/处理延迟和丢包，特别是分布式系统。

不要通过不现实的高摩擦或无噪声传感器掩盖控制问题。

## 场景测试

建立可重复场景：

- 空场直线、旋转、横移或最小半径转向。
- 窄通道、动态障碍、斜坡、低摩擦和轮胎打滑。
- 传感器掉线、时间偏移、命令丢失、CPU/GPU 过载。
- 定位跳变、路径阻塞、恢复失败和急停。

固定随机种子，保存世界、参数、软件版本、输入和验收指标。

## 仿真运行图与运行事实闸门

L2 不以文件存在为判据。为仿真 profile 声明组件生产/消费接口并验证至少一条完整路径：测试/导航运动请求 → 唯一命令监督器 → 仿真执行器 → 轮式里程计 → 状态估计。机器人生成、传感器数据、健康门和仿真专用运动授权也必须有生产者与消费者。若真实硬件健康条件直接复用于仿真，必须提供等价仿真健康源；不得通过删除安全门让仿真“能动”。运行 `validate_runtime_graph.py` 后仍需实际启动和场景测试证据。

`runtime_graph.json` 的每个 profile 至少包含 `target_level`、`components`、`required_gate_topics` 和 `required_flows`。组件写明 `name`、`roles`、`consumes`、`produces`；L2 的标准角色是 `robot_spawn`、`motion_source`、`command_supervisor`、`actuator`、`feedback`、`state_estimation`、`health_gate` 和 `motion_authorizer`。例如必达流可写为 `{"name":"motion_feedback","from":"/motion/request","to":"/state/local"}`。

实际启动后再写 `runtime_observation.json` 并运行 `validate_runtime_observation.py --require-ran`。对每个 `active` 且 `in_critical_flow` 的组件，观测记录必须证明其输入输出连接到关键路径；启动但输出无人消费的平滑器、滤波器或安全器是失败，不得因为最终底盘仍能运动而忽略。`headless` 与 `gui` 是不同 profile：分别记录 RTF、墙钟频率、采样窗口和资源观测。配置的 `update_rate`、传感器频率或发布率不是验收测量值。

任务型仿真还要保存 `action_trace.json`。每个 terminal action 必须有 goal ID、来源、终态和结束时间；`aborted` 需要错误码/消息，`canceled` 需要取消来源。仅有 lifecycle 为 active 或日志中未见 traceback 不能证明任务完成。详细 schema 与 L2 回归最小集见 [runtime-evidence-and-regression.md](runtime-evidence-and-regression.md)。

## Sim-to-Real 闭环

1. 先标定实机轮径、轮距/轴距、传感器外参和执行器响应。
2. 将测量分布回填仿真，而不是只调到“看起来像”。
3. 在仿真通过同一接口契约和任务验收。
4. 进入 HIL，验证控制器与真实 MCU/驱动通信。
5. 实机从架空轮、低速空场、受控路径逐级放开。
6. 比较轨迹、延迟、轮速、电流和定位创新量，定位仿真实机差异。

仿真成功不等于实机安全；明确尚未验证的环境和故障模式。
