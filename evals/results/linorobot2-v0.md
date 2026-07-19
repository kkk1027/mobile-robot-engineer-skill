# linorobot2 对照评测

## 范围

- 目标仓库：https://github.com/linorobot/linorobot2
- 固定提交：b96aa42fbfa4390a77e0aab90935fe55d66d04ba
- 评测日期：2026-07-19
- 方法：先按“2WD/4WD/麦克纳姆、ROS 2、MCU、Gazebo、SLAM、Nav2”场景生成通用方案，再读取关键源码核对。
- 限制：终端无法 clone GitHub，本次通过 GitHub 只读接口检查关键文件，不代表全仓库动态验证。
- 生成方案：[diff-jetson-stm32-gazebo-solution.md](diff-jetson-stm32-gazebo-solution.md)

## Skill 预期

1. 根据底盘在差速、滑移和麦克纳姆分支间路由。
2. MCU 承担轮速闭环，上位机承担状态估计、SLAM 和 Nav2。
3. 实机与仿真保持命令、里程计、IMU 和 TF 契约一致。
4. 使用 Gazebo 模拟底盘和传感器。
5. 运动命令具有超时停车机制。
6. ros2_control 为优先选择，但允许满足相同契约的固件或仿真插件。

## 源码证据

| 结论 | 源码证据 |
|---|---|
| 支持 2WD、4WD、麦克纳姆 | [README.md L16](https://github.com/linorobot/linorobot2/blob/b96aa42fbfa4390a77e0aab90935fe55d66d04ba/README.md#L16) |
| 实机使用 micro-ROS 固件 | [README.md L20](https://github.com/linorobot/linorobot2/blob/b96aa42fbfa4390a77e0aab90935fe55d66d04ba/README.md#L20)，[default_robot.launch.py L60](https://github.com/linorobot/linorobot2/blob/b96aa42fbfa4390a77e0aab90935fe55d66d04ba/linorobot2_bringup/launch/default_robot.launch.py#L60) |
| 串口和 UDP 传输可分支 | [default_robot.launch.py L64](https://github.com/linorobot/linorobot2/blob/b96aa42fbfa4390a77e0aab90935fe55d66d04ba/linorobot2_bringup/launch/default_robot.launch.py#L64)，[L68](https://github.com/linorobot/linorobot2/blob/b96aa42fbfa4390a77e0aab90935fe55d66d04ba/linorobot2_bringup/launch/default_robot.launch.py#L68) |
| 差速插件接收 cmd_vel 并以 50 Hz 发布里程计 | [diff_drive.urdf.xacro L7](https://github.com/linorobot/linorobot2/blob/b96aa42fbfa4390a77e0aab90935fe55d66d04ba/linorobot2_description/urdf/controllers/diff_drive.urdf.xacro#L7)，[L10](https://github.com/linorobot/linorobot2/blob/b96aa42fbfa4390a77e0aab90935fe55d66d04ba/linorobot2_description/urdf/controllers/diff_drive.urdf.xacro#L10)，[L16](https://github.com/linorobot/linorobot2/blob/b96aa42fbfa4390a77e0aab90935fe55d66d04ba/linorobot2_description/urdf/controllers/diff_drive.urdf.xacro#L16) |
| 四轮滑移把前后同侧轮加入差速插件 | [skid_steer.urdf.xacro L12](https://github.com/linorobot/linorobot2/blob/b96aa42fbfa4390a77e0aab90935fe55d66d04ba/linorobot2_description/urdf/controllers/skid_steer.urdf.xacro#L12)，[L14](https://github.com/linorobot/linorobot2/blob/b96aa42fbfa4390a77e0aab90935fe55d66d04ba/linorobot2_description/urdf/controllers/skid_steer.urdf.xacro#L14) |
| 麦克纳姆使用 Gazebo MecanumDrive | [omni_drive.urdf.xacro L5](https://github.com/linorobot/linorobot2/blob/b96aa42fbfa4390a77e0aab90935fe55d66d04ba/linorobot2_description/urdf/controllers/omni_drive.urdf.xacro#L5)，[L12](https://github.com/linorobot/linorobot2/blob/b96aa42fbfa4390a77e0aab90935fe55d66d04ba/linorobot2_description/urdf/controllers/omni_drive.urdf.xacro#L12) |
| 上位机使用 robot_localization EKF | [bringup.launch.py L120](https://github.com/linorobot/linorobot2/blob/b96aa42fbfa4390a77e0aab90935fe55d66d04ba/linorobot2_bringup/launch/bringup.launch.py#L120) |
| 导航包依赖 Nav2 和 SLAM Toolbox | [package.xml L13](https://github.com/linorobot/linorobot2/blob/b96aa42fbfa4390a77e0aab90935fe55d66d04ba/linorobot2_navigation/package.xml#L13)，[L15](https://github.com/linorobot/linorobot2/blob/b96aa42fbfa4390a77e0aab90935fe55d66d04ba/linorobot2_navigation/package.xml#L15) |
| 仿真桥接 cmd_vel 等上层接口 | [gazebo.launch.py L137](https://github.com/linorobot/linorobot2/blob/b96aa42fbfa4390a77e0aab90935fe55d66d04ba/linorobot2_gazebo/launch/gazebo.launch.py#L137)，[L141](https://github.com/linorobot/linorobot2/blob/b96aa42fbfa4390a77e0aab90935fe55d66d04ba/linorobot2_gazebo/launch/gazebo.launch.py#L141) |
| 仿真实机声明保持同一接口 | [README.md L21](https://github.com/linorobot/linorobot2/blob/b96aa42fbfa4390a77e0aab90935fe55d66d04ba/README.md#L21)，[base_controller.md L87](https://github.com/linorobot/linorobot2/blob/b96aa42fbfa4390a77e0aab90935fe55d66d04ba/docs/base_controller.md#L87) |
| 仿真中有 0.2 秒命令超时置零 | [command_timeout.py L42](https://github.com/linorobot/linorobot2/blob/b96aa42fbfa4390a77e0aab90935fe55d66d04ba/linorobot2_gazebo/linorobot2_gazebo/command_timeout.py#L42)，[L48](https://github.com/linorobot/linorobot2/blob/b96aa42fbfa4390a77e0aab90935fe55d66d04ba/linorobot2_gazebo/linorobot2_gazebo/command_timeout.py#L48) |

## 对照结论

- 底盘路由、MCU/上位机职责、状态估计、SLAM/Nav2、Gazebo 和仿真实机接口等价均与 Skill 方案一致。
- 项目用 micro-ROS 固件和 Gazebo 原生系统插件实现底盘闭环，而非强制 ros2_control。这是满足同一契约的可接受替代。
- command_timeout 节点同时发布和订阅 cmd_vel，见 [L26](https://github.com/linorobot/linorobot2/blob/b96aa42fbfa4390a77e0aab90935fe55d66d04ba/linorobot2_gazebo/linorobot2_gazebo/command_timeout.py#L26) 与 [L30](https://github.com/linorobot/linorobot2/blob/b96aa42fbfa4390a77e0aab90935fe55d66d04ba/linorobot2_gazebo/linorobot2_gazebo/command_timeout.py#L30)。这不自动判定为缺陷，但需要运行时验证自反馈、多发布者竞争和零命令覆盖行为。
- README 声称仿真实机共用 Nav2 配置；关键 launch 文件也把 sim 映射到 use_sim_time，并传入同一 params_file，见 [navigation.launch.py L86-L87](https://github.com/linorobot/linorobot2/blob/b96aa42fbfa4390a77e0aab90935fe55d66d04ba/linorobot2_navigation/launch/navigation.launch.py#L86)。

## 本轮 Skill 改动

1. 将 ros2_control 从“隐含唯一实现”改为“适合统一关节接口时优先”，允许经验证的 MCU 固件和仿真器插件。
2. 增加同一命令 Topic 上 pub/sub timeout 节点的自反馈和多写入者检查。
3. 保留“接口契约优先于实现框架”的判断标准。

## 尚未验证

- 未构建和启动 linorobot2。
- 未检查硬件仓库的 MCU watchdog、电机驱动和编码器实现。
- 未测量 QoS、TF、端到端延迟、停止距离或故障恢复。
- 静态源码证据不能证明实机安全。
