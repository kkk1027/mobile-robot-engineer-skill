# 诊断与验证

先读取 [wheeled-robot-problem-taxonomy.md](wheeled-robot-problem-taxonomy.md)，把现象归入命令/控制、运动学、TF/时间、定位、导航 action、障碍接管、QoS/网络、驱动、性能、仿真、配置或回归测试类别。一个现象可属于多个类别，但每次检查必须说明要证伪哪一个假设。

## 证据包

最小证据包括：

- 精确复现步骤、期望和实际。
- 软件版本、提交、ROS/OS/RMW、参数和 launch 参数。
- 节点/组件/生命周期状态。
- Topic 类型、发布订阅者、QoS、频率、延迟和样本时间戳。
- TF 树和变换年龄。
- diagnostics、控制器状态、硬件错误、CPU/GPU/内存/磁盘/网络。
- 最近变更和首次失败时间。

对实机证据去敏，不收集私钥、Token 和无关个人数据。

## 分层定位

| 现象 | 首先区分 |
|---|---|
| 完全不动 | 命令生成、仲裁、安全层、控制器、驱动、制动、供电 |
| 方向相反 | 坐标约定、轮序、电机极性、编码器符号、转角零位 |
| 直线跑偏 | 轮径/轮距、PID、载荷、摩擦、编码器、机械阻力 |
| 里程计漂移 | 运动模型、尺度、滑移、时间戳、融合重复信息 |
| TF 报错 | 所有者、断链、重复边、时间源、frame_id |
| Topic 有但节点收不到 | 类型、namespace、remap、QoS、domain、网络 |
| 导航不出路径 | 地图、footprint、起终点、约束、规划器状态 |
| 有路径不跟踪 | 控制器、速度限制、定位、costmap、命令仲裁 |
| 随机卡顿 | executor、锁、内存、IO、网络、温度、GPU、时钟 |
| 仿真正常实机失败 | 单位、延迟、噪声、摩擦、饱和、接口和启动时序 |

## 假设驱动

对每个候选根因写：

~~~text
假设：
若为真，应观察到：
若为假，应观察到：
最低风险检查：
证据：
结论：
~~~

一次只改变一个主要变量。修复症状前验证根因；临时调大 timeout、queue 或 covariance 不能自动视为根因修复。

## 静态验证

- 运行 inspect_ros_workspace.py。
- 检查 package.xml、构建文件和依赖闭包。
- 展开 Xacro，检查 URDF 和 ros2_control joint/interface。
- 检查 launch 参数、namespace、use_sim_time 和参数文件。
- 运行 validate_robot_contract.py。
- 审查命令通道单一写入者、超时和停止路径。

## 动态验证

- colcon build 使用独立 build/install/log 或容器。
- 运行单元、组件和 launch 测试。
- 记录 rosbag2 和 diagnostics。
- 测量频率、延迟、jitter、TF age 和资源。
- 在仿真中注入掉线、延迟、传感器异常和障碍。
- 实机按 G2→G3→G4 升级。

运行后写 `runtime_observation.json`，不要只保存终端截屏。对于关键路径记录实际发布者、订阅者、观测频率和墙钟采样窗口；对仿真记录 RTF；对动态 TF 记录唯一广播者；对导航/探索/跟随记录 action 的 goal、来源、终态、取消原因和错误码。运行 `validate_runtime_observation.py --require-ran` 与 `validate_action_trace.py --require-terminal`。

## 回归

每个修复至少增加一种可重复检查：

- 数学/解析单元测试。
- 消息或参数契约测试。
- launch/lifecycle 测试。
- rosbag 回放测试。
- 固定仿真场景。
- HIL 或低速实机验收。

记录修复前失败、修复后通过，避免只展示最终成功。

## 停止条件

遇到安全链状态未知、机器人身份不明、反馈符号异常、时间同步严重失效、测试场地未确认、急停不可用或回滚不可行时停止实机操作并请求用户处理。
