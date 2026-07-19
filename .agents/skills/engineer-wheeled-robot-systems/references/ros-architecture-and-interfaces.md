# ROS 架构与接口契约

## 分层

保持依赖自底向上：

1. robot_description：URDF/Xacro、meshes、ros2_control 标签。
2. hardware：驱动器、硬件接口、MCU agent、总线适配。
3. control：controller_manager、底盘控制器、限幅和命令复用。
4. sensing：传感器驱动、标定、时间同步。
5. state_estimation：轮速/IMU/GNSS/视觉/雷达融合。
6. perception_mapping：障碍、地形、语义、地图。
7. navigation_decision：任务、行为树、规划和恢复。
8. bringup：生命周期、主机分布、参数和启动顺序。
9. monitoring_safety：健康、诊断、watchdog、记录和急停状态。
10. simulation_tests：仿真适配、场景、launch test 和 HIL。

高层包不得直接依赖供应商串口实现；通过稳定消息或 hardware_interface 隔离。

## ROS 2 优先

- 使用 ament_cmake 或 ament_python，避免一个包混合多种构建语义。
- 对硬件、定位、导航等可管理节点使用 lifecycle，并定义启动依赖。
- 同进程高带宽链路可使用 components 和 intra-process，但先测量复制与线程行为。
- 参数文件按机器人型号、环境和运行模式分层，不在 launch 文件中散落魔数。
- 使用 rosbag2、diagnostic_msgs、tracing 或系统指标形成证据。

## ROS 1 兼容

仅对遗留驱动或算法保留 ROS 1。明确：

- ROS 1 和 ROS 2 的权威数据源。
- ros1_bridge 的消息类型、方向、频率和时间语义。
- /tf、/cmd_vel、/odom 等不得出现双写。
- 分离 catkin 与 colcon 工作区和环境 sourcing。
- 制定替换触发条件，不让桥接成为永久隐含依赖。

## TF 契约

典型二维导航链：

~~~text
map -> odom -> base_link -> sensor frames
~~~

- map→odom 由定位/SLAM 发布。
- odom→base_link 由连续局部里程计或融合器发布。
- base_link→sensor 为标定后的静态 TF。
- 只允许一个发布者拥有每条动态边。
- 时间戳来自测量时刻，不是回调处理完成时刻。
- base_footprint 仅在确有二维投影需求时使用并明确所有者。

检查环、断链、重复发布者、未来时间戳、过旧变换和 frame_id 前导斜杠。

## ROS 接口契约

为每个接口记录：

- 完整名称、类型、发布者、订阅者和唯一所有者。
- frame_id、单位、坐标约定和时间源。
- 期望/最低/最高频率、允许抖动、最大年龄和最大端到端延迟。
- QoS reliability、durability、history、depth、deadline、lifespan 和 liveliness。
- 启动前置条件、失效语义、恢复方式和安全默认值。

传感器通常使用 SensorDataQoS；控制和状态接口按可靠性与时效性取舍，不要机械使用 reliable。QoS 不匹配时先用 ros2 topic info --verbose 取证。

## 命令通道

所有运动命令进入单一仲裁点：

~~~text
teleop / autonomy / docking / recovery
                 ↓
         command mux + safety filter
                 ↓
       base controller / hardware
~~~

定义优先级、租约、超时、速度/加速度/jerk 限制和急停覆盖。控制器收到陈旧命令时必须停止，不依赖上游继续发送零速度。

控制权变化必须经过显式停止屏障：先让旧所有者释放租约并输出确定的停止，再允许新所有者生效；必要时等待零速反馈或安全层确认。非活动生产者不得持续发布零命令与其他来源竞争，只在退出边沿发一次停止或直接释放租约。对“首次跨过阈值”“取消/超时”“进程退出”和新请求同周期到达分别增加回归测试。

若 watchdog/timeout 节点同时订阅并发布同一个命令 Topic，检查它是否形成自反馈、是否与导航/遥控构成多发布者竞争，以及零命令能否可靠覆盖陈旧非零命令。优先使用显式输入/输出 Topic 或单一 mux，而不是依赖发布时序。

## 包和配置质量

- package.xml 声明运行、构建、测试和导出依赖。
- CMakeLists/setup.py 不引用未声明依赖。
- launch 文件暴露 robot_name、namespace、use_sim_time、params_file 等必要参数。
- 多机器人使用 namespace 和 frame 前缀策略，避免硬编码全局名称。
- 配置更改可追踪、可回滚；机密不进入仓库。
- 测试覆盖消息契约、TF、生命周期、超时和故障恢复。
