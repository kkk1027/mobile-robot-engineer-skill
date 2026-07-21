# 运行事实、性能与回归证据

`runtime_graph.json` 是设计期合同；`runtime_observation.json` 是已启动 profile 的实测事实。不得由前者推断后者。

## runtime_observation.json

最小结构：

~~~json
{
  "schema_version": 1,
  "profile": {
    "name": "headless",
    "kind": "simulation",
    "execution": "ran",
    "wall_clock_window_s": 15,
    "measurement_source": "artifacts/runtime/headless.txt",
    "real_time_factor": 0.92,
    "min_real_time_factor": 0.80
  },
  "components": [
    {"name": "controller", "state": "active", "disposition": "in_critical_flow"},
    {"name": "safety_mux", "state": "active", "disposition": "in_critical_flow"},
    {"name": "diagnostics", "state": "active", "disposition": "observability_only"}
  ],
  "topics": [
    {
      "name": "/cmd_vel_filtered",
      "publishers": ["controller"],
      "subscribers": ["safety_mux"],
      "required_min_hz": 10.0,
      "observed_hz": 12.0,
      "measurement_source": "artifacts/runtime/topic_hz.txt"
    }
  ],
  "critical_flows": [
    {"name": "motion", "components": ["controller", "safety_mux", "base"]}
  ],
  "dynamic_tf": [
    {"parent": "odom", "child": "base_link", "broadcasters": ["base"]}
  ]
}
~~~

`execution` 只能为 `ran` 或 `not_run`。当为 `ran` 时，profile 必须给出墙钟采样窗口和证据；仿真 profile 还需要 RTF。每个 active 组件必须明确为 `in_critical_flow`、`observability_only` 或 `disabled`；前者必须出现在 `critical_flows` 中。每个相邻组件之间必须存在一个实测 topic，且该 topic 的发布者/订阅者列表匹配。动态 TF 边只能有一个广播者。对有 `required_min_hz` 的 topic，必须记录实测频率和证据，且不低于门槛。

## action_trace.json

~~~json
{
  "schema_version": 1,
  "actions": [
    {
      "goal_id": "uuid-or-test-id",
      "action": "/navigate_to_pose",
      "source": "waypoint_loop",
      "status": "succeeded",
      "started_at": "2026-01-01T00:00:00Z",
      "finished_at": "2026-01-01T00:00:10Z",
      "evidence": ["artifacts/actions/goal-1.json"]
    }
  ]
}
~~~

状态只能为 `succeeded`、`canceled`、`aborted`、`active` 或 `not_run`。`canceled` 必须有 `cancel_requested_by`；`aborted` 必须有 `error_code` 和 `error_message`；terminal 状态必须有结束时间和证据。`active`/`not_run` 不可作为任务验收完成证据。

## L2 最低回归集

每个 L2 项目至少提供以下自动测试或可执行测试骨架：

1. launch/退出码和 lifecycle；
2. TF、关键传感器和状态估计可达；
3. 唯一最终命令、命令超时和急停归零；
4. 一个任务 action 的成功、失败或取消；
5. 一个传感器掉线、障碍、QoS/TF 或性能门槛故障注入。

优先用 `launch_testing` 和隔离的 ROS domain。若没有 ROS 环境，保留测试文件、命令和预期，但把验证标为 `planned`，不将其写入 `complete` 需求证据。
