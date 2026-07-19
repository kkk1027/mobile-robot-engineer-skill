# 四轮差速 Jetson + STM32 方案

## 结论

为四轮差速室内机器人建立 ROS 2 原生、仿真实机共接口的软件闭环。STM32 保持电机速度闭环、编码器采样和独立 watchdog；Jetson 运行传感器驱动、状态估计、SLAM、Nav2、任务编排和监控；Gazebo 用相同 Topic、TF 和限制替换 MCU/底盘物理层。

本方案处于 G0/G1：可用于仓库创建和仿真，不代表实机已验证。

## 已知输入

- 四轮差速，同侧电机同速。
- Jetson Orin Nano + STM32 + CAN 电机驱动器。
- 编码器、IMU、2D LiDAR。
- ROS 2、C++、Python、Gazebo、micro-ROS。
- 目标为建图、定位和自主导航。

## 假设与待确认

- 假设四轮为滑移转向等效差速，不具备独立转向或横移。
- 假设 MCU 可读取编码器并直接控制电机驱动器。
- 假设急停有独立硬件链路，可在 Jetson/DDS 失效时切断驱动使能。
- 待确认 JetPack/Ubuntu 与 ROS 2 发行版兼容矩阵后冻结版本。
- 待确认轮径、几何轮距、编码器分辨率、减速比、CAN 协议、最大速度、制动距离和传感器型号。

上述待确认参数不会阻塞仿真骨架，但在生成实机驱动参数或 G4 测试前必须补齐。

## 系统闭环

~~~mermaid
flowchart LR
  L["LiDAR /scan"] --> P["SLAM 或 AMCL"]
  I["IMU /imu/data_raw"] --> E["robot_localization EKF"]
  W["编码器 /wheel/odometry"] --> E
  P --> TF1["map→odom"]
  E --> TF2["odom→base_link"]
  TF1 --> N["Nav2"]
  TF2 --> N
  L --> N
  N --> M["命令 mux + safety supervisor"]
  T["遥控 /cmd_vel/teleop"] --> M
  M --> C["/cmd_vel_safe"]
  C --> U["STM32 micro-ROS"]
  U --> D["CAN 电机驱动"]
  D --> R["车轮与底盘"]
  R --> W
  S["急停/驱动故障"] --> U
  S --> M
~~~

Gazebo 分支以底盘插件、IMU 和 LiDAR 插件替换 STM32、驱动器和物理传感器，其余节点和配置保持一致。

## 主机职责

### STM32

- 以固定周期采样编码器和驱动器状态。
- 运行每轮或每侧速度闭环。
- 根据 v、w 和标定后的有效轮距计算左右轮目标。
- 发布带采样时间戳的轮式里程计、IMU/驱动状态和诊断。
- 在命令超过 150 ms、micro-ROS 断链、CAN bus-off、编码器异常或急停触发时主动置零并关闭使能。
- 不依赖 Jetson 发送零命令才能停车。

### Jetson

- 运行 micro_ros_agent、LiDAR 驱动、robot_state_publisher。
- 融合轮式里程计和 IMU，发布 odom→base_link。
- 运行 SLAM Toolbox 或 AMCL，发布 map→odom。
- 运行 Nav2、任务节点、命令仲裁、安全监督和 diagnostics。
- 记录 rosbag2、资源、温度、DDS 和端到端延迟。

## 建议仓库结构

~~~text
src/
  robot_description/
  robot_interfaces/
  robot_hardware/
  robot_base/
  robot_sensors/
  robot_localization/
  robot_navigation/
  robot_bringup/
  robot_monitoring/
  robot_gazebo/
  robot_tests/
firmware/
  stm32_base/
config/
  robot_contract.json
~~~

- robot_interfaces 只放确有必要的自定义消息；优先复用标准消息。
- robot_hardware 放 micro-ROS agent 和供应商/CAN 适配，不让 Nav2 依赖驱动细节。
- robot_base 放差速运动学、命令 mux、限制器和里程计适配。
- robot_bringup 负责生命周期、参数分层和启动依赖。

## 关键接口

完整机器可读契约见 diff-jetson-stm32-gazebo-contract.json。

| 接口 | 类型 | 所有者 | 目标频率 | 最大年龄 | 说明 |
|---|---|---|---:|---:|---|
| /cmd_vel/nav | TwistStamped | Nav2 controller | 20 Hz | 150 ms | 自主导航输入 |
| /cmd_vel/teleop | TwistStamped | teleop | 按输入 | 150 ms | 人工控制输入 |
| /cmd_vel_safe | TwistStamped | command mux | 20–50 Hz | 150 ms | 唯一底盘命令 |
| /wheel/odometry | Odometry | STM32/仿真插件 | 100 Hz | 50 ms | 原始轮式里程计 |
| /imu/data_raw | Imu | STM32/IMU 驱动 | 100 Hz | 50 ms | 原始惯性数据 |
| /scan | LaserScan | LiDAR 驱动 | 10 Hz | 200 ms | 二维障碍与定位 |
| /odom | Odometry | EKF | 50 Hz | 100 ms | 连续局部状态 |
| /diagnostics | DiagnosticArray | 各组件聚合 | 2 Hz | 1000 ms | 健康证据 |
| /safety/estop_state | Bool | safety IO | ≥10 Hz | 200 ms | 急停状态，不是急停执行链本身 |

## TF 所有权

~~~text
map --SLAM/AMCL--> odom --EKF--> base_link --static--> lidar_link
                                            └--static--> imu_link
~~~

禁止 MCU、EKF 和 Gazebo 插件同时发布 odom→base_link。仿真插件原始里程计只发布消息，最终 TF 仍由 EKF 拥有。

## 仿真设计

- 使用 Xacro 维护车体、四轮、LiDAR 和 IMU；为 visual、collision 和 inertial 分离几何。
- 四轮滑移模型在 Gazebo 中使用同侧前后轮映射；初始有效轮距取几何值，随后通过实机轨迹标定。
- 加入轮地摩擦、侧滑、编码器量化、IMU bias、LiDAR 噪声和命令/反馈延迟。
- 参数 sim 只替换硬件层并设置 use_sim_time；Nav2、EKF、TF 和接口契约不复制第二套。
- 固定场景覆盖直线、原地转向、八字、窄通道、低摩擦、传感器掉线和命令超时。

## 启动顺序

1. 启动 robot_state_publisher 和静态 TF。
2. 仿真时启动 Gazebo/桥接；实机时启动 micro_ros_agent、CAN/传感器驱动。
3. 等待编码器、IMU、LiDAR 和时间源达到最低频率。
4. 启动 EKF，确认 odom→base_link 连续且协方差合理。
5. 启动 SLAM 或 AMCL，确认 map→odom 的唯一所有者。
6. 激活命令 mux 和安全监督，默认不授予运动租约。
7. 启动 Nav2 lifecycle manager，确认所有 managed nodes active。
8. 用户授予任务或遥控租约后才允许输出 /cmd_vel_safe。

## 实施阶段

### P0：契约与骨架

- 冻结主机、ROS、RMW、Topic、TF、QoS、频率、时间和安全契约。
- 创建包结构、CI、格式化、静态分析和测试入口。

### P1：描述与底盘

- 完成 Xacro、惯量、碰撞和控制插件。
- 在仿真验证轮序、符号、直线、旋转、超时和里程计。
- 在 STM32 单元测试差速正逆解、饱和和 watchdog。

### P2：传感与估计

- 接入 LiDAR/IMU，完成坐标、内外参和时间同步。
- 以 rosbag 回放验证 EKF 和 TF。

### P3：SLAM 与导航

- 完成建图、地图保存、AMCL、全局规划、局部控制和恢复行为。
- 对滑移转向调大合理的航向/横向不确定性，不用错误协方差掩盖标定问题。

### P4：故障注入

- 注入 cmd_vel 丢失、MCU 断线、LiDAR/IMU 掉线、TF 陈旧、CPU/GPU 过载和 CAN 故障。
- 验证每类故障的状态、降级、停车和恢复。

### P5：HIL 与实机

- 依次执行 MCU 台架、架空轮、低速空场、受控路径和任务场景。
- 每次进入 G4 前重新确认急停、限速、场地、人员和停止机制。

## 验收指标

在用户提供任务指标前，以下仅作为必须测量的占位项，不作为最终阈值：

- 控制周期平均/P95/P99/最大抖动。
- cmd_vel 到驱动目标的端到端年龄。
- 直线尺度误差、原地旋转航向误差、八字轨迹闭环误差。
- 地图闭环误差、定位重获时间、导航成功率。
- 停止时间、停止距离、watchdog 触发时间。
- CPU/GPU/内存/温度和网络负载。

最终阈值由最大速度、场地、载荷和风险分析决定。

## 安全与回滚

- G0/G1 可直接执行；SSH 只读进入 G2。
- 参数、服务、固件和部署属于 G3，必须备份和准备回滚。
- 任何轮子动作属于 G4，每次单独授权。
- 固件升级失败时保留可恢复 bootloader 和上一稳定固件。
- 配置部署使用版本化文件和原子替换。
- 急停、编码器符号、CAN 状态、时间同步或 watchdog 任一未知时停止实机测试。
