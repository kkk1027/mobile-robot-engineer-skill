# SSH 实机操作与安全

## 身份与凭据

- 只使用用户预先配置的 OpenSSH alias，例如 ssh robot-lab。
- 让 OpenSSH 或 ssh-agent 处理密钥；不要读取、打印、复制或请求私钥内容。
- 不在命令参数、环境输出或日志中传递密码、Token。
- 首次连接由用户核对主机指纹。禁止 StrictHostKeyChecking=no，禁止未核验就删除 known_hosts 条目。
- 为机器人使用最小权限账号；sudo 和固件权限单独控制。

## 远程操作顺序

1. 确认 alias、机器人身份、现场状态、授权等级和维护窗口。
2. 运行只读身份检查：主机名别名、系统版本、时间、磁盘、负载、进程和网络。
3. 确认 ROS 环境、工作区、发行版、RMW、ROS_DOMAIN_ID 和命名空间。
4. 收集 ROS 图、节点生命周期、Topic 频率/QoS、TF、diagnostics 和日志。
5. 在本地形成假设和变更计划。
6. G3/G4 操作前再次说明精确命令、目标、影响、回滚和停止条件。
7. 执行后验证服务、ROS 图、安全状态和任务级指标。
8. 保存去敏后的命令、退出码、时间和证据。

## 只读 ROS 检查

根据远端 shell 固定构造命令，避免拼接未经验证的用户文本。常用检查：

~~~text
ros2 doctor --report
ros2 node list
ros2 topic list -t
ros2 service list -t
ros2 action list -t
ros2 lifecycle nodes
ros2 topic info --verbose <topic>
ros2 topic hz <topic>
ros2 topic delay <topic>
ros2 param dump <node>
ros2 run tf2_tools view_frames
ros2 bag info <bag>
~~~

对持续命令设置合理超时并限制输出量。不要在高带宽图像/点云 Topic 上无限 echo。

## G3 变更

部署、参数写入、服务重启和控制器切换前：

- 验证机器人已静止、任务已取消、运动授权已撤销。
- 备份当前配置并记录校验和。
- 使用明确工作目录和固定分支/提交，不在远端直接 git pull 未审查代码。
- 先 dry-run 或构建测试，再原子替换。
- 为 systemd/container/launch 定义回滚命令。
- 重启后验证 heartbeat、diagnostics、控制器状态和超时停机。

禁止批量覆盖未知路径，禁止清理整个工作区。

## G4 运动

每次运动前必须确认：

- 用户明确授权当前动作，而非仅授权 SSH。
- 现场人员知道测试并处于安全位置。
- 物理急停可达且已验证。
- 速度、角速度、加速度和测试时间有保守上限。
- 命令停止或 SSH/DDS 断开后，底层 watchdog 会自动置零。
- 机器人身份、朝向、架空/落地状态和场地边界正确。

先测试零命令和超时，再执行短脉冲；先单轮/架空，再低速直线，再转向。任何反馈符号、姿态、声音、电流或轨迹异常立即停止。

不要用无限循环持续发布 cmd_vel。运动命令必须有独立、短于操作超时的停止机制。

## 多主机与网络

- 记录每台主机的 alias、角色和时间同步状态。
- 检查 DDS discovery、组播、接口选择、防火墙、VPN 和 MTU。
- 不把 ROS_DOMAIN_ID 当作安全隔离；需要网络和权限控制。
- 通过跳板机时仍只使用 alias，不展开真实凭据。

## 安全模型来源

借鉴通用 SSH Skill 的 alias/config 使用方式，以及 sshepherd 的凭据隔离、结构化结果、确认闸门和审计思想。机器人场景额外加入 ROS 图证据、控制器状态、实机运动授权、急停和 watchdog；不直接继承任意服务器运维命令。
