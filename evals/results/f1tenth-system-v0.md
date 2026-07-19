# F1TENTH system 对照评测

## 范围

- 目标仓库：https://github.com/f1tenth/f1tenth_system
- 固定提交：ae64e05fbaf6eda592ef56c13ce89c896d489a55
- 评测日期：2026-07-19
- 方法：按“阿克曼、ROS 2、VESC、LiDAR、遥控/自主仲裁”场景检查关键配置和 bringup。
- 限制：该提交 README 明确处于迁移到 ROS 2 的开发阶段；本次只做静态关键路径抽查，不能代表当前生产建议。

## Skill 预期

1. 使用阿克曼速度/转角接口，不发布不可执行的横向速度或原地旋转。
2. 在高层命令与 VESC 之间设置转换和标定层。
3. 遥控和自主控制进入单一仲裁点，并具备 deadman/租约。
4. 由驱动反馈和转向状态生成 odom→base_link。
5. 对速度、转角、加速度和转向速率限幅。

## 源码证据

| 结论 | 源码证据 |
|---|---|
| 自主命令使用 AckermannDriveStamped | [README.md L11](https://github.com/f1tenth/f1tenth_system/blob/ae64e05fbaf6eda592ef56c13ce89c896d489a55/README.md#L11)，[package.xml L10](https://github.com/f1tenth/f1tenth_system/blob/ae64e05fbaf6eda592ef56c13ce89c896d489a55/f1tenth_stack/package.xml#L10) |
| 存在 ackermann_mux | [README.md L26](https://github.com/f1tenth/f1tenth_system/blob/ae64e05fbaf6eda592ef56c13ce89c896d489a55/README.md#L26)，[bringup_launch.py L117](https://github.com/f1tenth/f1tenth_system/blob/ae64e05fbaf6eda592ef56c13ce89c896d489a55/f1tenth_stack/launch/bringup_launch.py#L117) |
| mux 输出映射到 ackermann_drive | [bringup_launch.py L121](https://github.com/f1tenth/f1tenth_system/blob/ae64e05fbaf6eda592ef56c13ce89c896d489a55/f1tenth_stack/launch/bringup_launch.py#L121) |
| 存在 Ackermann→VESC 与 VESC→odom 节点 | [bringup_launch.py L87](https://github.com/f1tenth/f1tenth_system/blob/ae64e05fbaf6eda592ef56c13ce89c896d489a55/f1tenth_stack/launch/bringup_launch.py#L87)，[L95](https://github.com/f1tenth/f1tenth_system/blob/ae64e05fbaf6eda592ef56c13ce89c896d489a55/f1tenth_stack/launch/bringup_launch.py#L95) |
| 遥控与自主有独立 deadman 映射 | [joy_teleop.yaml L29](https://github.com/f1tenth/f1tenth_system/blob/ae64e05fbaf6eda592ef56c13ce89c896d489a55/f1tenth_stack/config/joy_teleop.yaml#L29)，[L44](https://github.com/f1tenth/f1tenth_system/blob/ae64e05fbaf6eda592ef56c13ce89c896d489a55/f1tenth_stack/config/joy_teleop.yaml#L44) |
| 速度与转向命令有增益/偏置标定 | [vesc.yaml L4-L9](https://github.com/f1tenth/f1tenth_system/blob/ae64e05fbaf6eda592ef56c13ce89c896d489a55/f1tenth_stack/config/vesc.yaml#L4) |
| 里程计使用 0.25 m 轴距 | [vesc.yaml L38](https://github.com/f1tenth/f1tenth_system/blob/ae64e05fbaf6eda592ef56c13ce89c896d489a55/f1tenth_stack/config/vesc.yaml#L38) |
| 加速度和转向速度有平滑参数 | [vesc.yaml L52-L55](https://github.com/f1tenth/f1tenth_system/blob/ae64e05fbaf6eda592ef56c13ce89c896d489a55/f1tenth_stack/config/vesc.yaml#L52) |

## 对照结论

- 阿克曼消息、命令 mux、VESC 适配、转向/速度标定和里程计链路与 Skill 方案一致。
- 配置允许使用舵机命令估计角速度，见 [vesc.yaml L36](https://github.com/f1tenth/f1tenth_system/blob/ae64e05fbaf6eda592ef56c13ce89c896d489a55/f1tenth_stack/config/vesc.yaml#L36)。这会把舵机延迟、饱和和机械间隙隐藏在模型内，必须通过外部轨迹验证并反映到协方差。
- deadman 和 mux 是必要的上层保护，但不能替代底层命令超时、物理急停和制动链。
- 本次文件中没有足够证据确认底层 watchdog、转向角实测反馈或高速制动安全；不能把“未检出”写成“不存在”。

## 本轮 Skill 改动

在阿克曼参考中增加：

1. 速度→电机转速、转向角→舵机位置的增益、偏置、饱和和死区标定。
2. 优先使用实测转向角；使用命令角近似时提高不确定性并进行外部轨迹验证。

## 尚未验证

- 未构建、运行或连接 F1TENTH 实车。
- 未测量 VESC 延迟、servo 实际角度、停止距离和 mux 切换时序。
- 未审查依赖仓库 vesc 与 ackermann_mux 的实现。
