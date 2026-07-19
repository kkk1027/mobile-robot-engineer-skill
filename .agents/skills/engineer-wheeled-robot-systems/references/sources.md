# 来源与维护边界

## 使用方式

把以下来源用于核验概念、接口和评测样本。更新 Skill 时重新检查当前 ROS 发行版兼容性和来源许可证。只借鉴工作流和公开接口，不复制大段第三方文本或项目专有代码。

## Skill 设计来源

- OpenAI Codex Build skills：项目级 .agents/skills 路径、SKILL.md、渐进披露和 agents/openai.yaml。
  https://developers.openai.com/codex/skills
- robotics-agent-skills：ROS、感知、测试、bringup、安全等拆分方式。
  https://github.com/arpitg1304/robotics-agent-skills
- ros-skill：通过 rosbridge 操作 ROS 图和结构化输出的思路。
  https://github.com/lpigeon/ros-skill
- robotics-skills-suite：系统安全、ROS 架构、TF、Nav2 和 HIL 的评审视角。
  https://github.com/jherrodthomas/robotics-skills-suite

## SSH 来源

- OpenHands SSH Skill，MIT：OpenSSH、config、SCP 和常规故障排查。
  https://github.com/OpenHands/skills/tree/main/skills/ssh
- sshepherd，MIT：alias-only、凭据隔离、结构化结果、确认闸门和审计思想。
  https://github.com/Antheurus/sshepherd

不直接继承要求智能体读取密码/私钥的做法，也不把服务器运维操作默认映射为机器人运动权限。

## ROS 官方生态

- ROS 2 文档：https://docs.ros.org/
- ROS 1/ROS 2 bridge：https://github.com/ros2/ros1_bridge
- Nav2：https://docs.nav2.org/
- ros2_control：https://control.ros.org/
- robot_localization：https://github.com/cra-ros-pkg/robot_localization
- SLAM Toolbox：https://github.com/SteveMacenski/slam_toolbox
- Gazebo 与 ROS：https://gazebosim.org/docs/
- Isaac ROS：https://nvidia-isaac-ros.github.io/
- MuJoCo：https://mujoco.readthedocs.io/

## 轮式机器人评测候选

- TurtleBot3：差速、ROS 2、Nav2、Gazebo。
  https://github.com/ROBOTIS-GIT/turtlebot3
- linorobot2：2WD、4WD、麦克纳姆、micro-ROS、Gazebo、SLAM、Nav2。
  https://github.com/linorobot/linorobot2
- F1TENTH system：阿克曼底盘和车辆级系统。
  https://github.com/f1tenth/f1tenth_system
- Clearpath ROS 2：滑移转向工业移动平台。
  https://github.com/clearpathrobotics

对全向轮、舵轮、铰接和特殊轮式底盘继续选择有实机、仿真、测试和明确许可证的公开样本。

## 用户样本

- https://github.com/kkk1027/bishe.git
- https://github.com/kkk1027/stemm--huananhu.git

访问不到时不得猜测内容。要求用户提供可访问授权或本地只读克隆路径后再做源码对照。
