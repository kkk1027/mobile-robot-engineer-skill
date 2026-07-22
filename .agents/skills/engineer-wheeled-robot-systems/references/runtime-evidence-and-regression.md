# 运行事实、性能与回归证据

`runtime_graph.json` 是设计期合同；`runtime_observation.json` 是已启动 profile 的实测事实。不得由前者推断后者。`complete`、`partial` 和 `planned` 必须来自结构化覆盖记录，不能因为校验器的基础 schema 通过就自动变为完整验收。

## runtime_observation.json

最小结构：

~~~json
{
  "schema_version": 1,
  "profile": {
    "name": "headless",
    "kind": "simulation",
    "execution": "ran",
    "claim": "complete",
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
  "required_topics": [
    {"name": "/scan", "min_hz": 5.0},
    {"name": "/image_raw", "min_hz": 10.0}
  ],
  "critical_flows": [
    {"name": "motion", "components": ["controller", "safety_mux", "base"]}
  ],
  "dynamic_tf": [
    {"parent": "odom", "child": "base_link", "broadcasters": ["base"]}
  ],
  "actions": [
    {
      "name": "/navigate_to_pose",
      "clients": ["waypoint_loop"],
      "servers": ["nav2_controller"],
      "measurement_source": "artifacts/runtime/action_graph.json"
    }
  ]
}
~~~

`execution` 只能为 `ran` 或 `not_run`。当为 `ran` 时，profile 必须给出墙钟采样窗口和证据；仿真 profile 还需要 RTF。每个 active 组件必须明确为 `in_critical_flow`、`observability_only` 或 `disabled`；前者必须出现在 `critical_flows` 中。每个相邻组件之间必须存在一个实测 topic，且该 topic 的发布者/订阅者列表匹配。动态 TF 边只能有一个广播者。

`required_topics` 来自用户验收、传感器合同和当前 profile 的必测接口。每项必须在 `topics` 中有实测频率和测量来源。完整验收时该列表不能为空，且 `profile.claim=complete` 时不得存在缺失项；若缺失相机、GUI 或其他必测 profile，则写 `partial`，给出下一步，而不是删掉该项。对完整验收运行 `validate_runtime_observation.py --require-ran --require-complete`。`actions` 记录 ROS Action 的实测 client/server 关系；不要把 Action 强行伪装成普通 Topic 边。

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
      "evidence": ["artifacts/actions/goal-1.json"],
      "process_completion": {
        "mode": "controlled_shutdown",
        "reason": "有限循环在成功后仍保持 ROS spin",
        "evidence": ["artifacts/actions/goal-1-shutdown.log"]
      }
    }
  ]
}
~~~

状态只能为 `succeeded`、`canceled`、`aborted`、`active` 或 `not_run`。`canceled` 必须有 `cancel_requested_by`；`aborted` 必须有 `error_code` 和 `error_message`；terminal 状态必须有结束时间和证据。`active`/`not_run` 不可作为任务验收完成证据。若有限任务的进程在 terminal action 后仍 spin，可记录 `process_completion.mode=controlled_shutdown`，并给出关闭原因和证据；终态事件加受控清理是有效交互式验收，信号退出码不是成功证据。

## fault_injection_trace.json

对用户要求的急停、命令超时、健康门或传感器故障，记录独立的运动中注入证据：

~~~json
{
  "profile": {"name": "headless", "execution": "ran"},
  "cases": [{
    "id": "estop_under_motion",
    "kind": "emergency_stop",
    "status": "passed",
    "motion_observed_before_trigger": true,
    "safe_stop_observed": true,
    "stop_latency_ms": 96,
    "max_stop_latency_ms": 350,
    "evidence": ["artifacts/faults/estop.json"]
  }]
}
~~~

`passed` 只能在触发前已观察到非零运动、触发后观察到安全停止、停止时延未超过上限且有证据时使用。在任务已经静止后再发布急停，只能说明静止状态，不能作为运动中急停通过。运行 `validate_fault_injection.py --require-ran --require-passed`。

## evidence_manifest.json

交付包要包含每个交付文件的相对路径和 SHA-256，并用 `validate_evidence_bundle.py` 扫描 `generation_trace.json`、`runtime_observation.json`、`action_trace.json` 和 `fault_injection_trace.json` 中引用的 `artifacts/`/`evidence/` 路径。引用的日志、探针和 JSON 必须随包交付并在清单中；无法交付时不得把该证据当作可复核通过依据。源码是否随包交付由用户约定，但没有源码时必须把静态/生成追踪复核标为受限。

## L2 最低回归集

每个 L2 项目至少提供以下自动测试或可执行测试骨架：

1. launch/退出码和 lifecycle；
2. TF、关键传感器（含用户声明的相机/GUI profile）和状态估计可达；
3. 唯一最终命令、命令超时和运动中急停归零；
4. 一个任务 action 的 client/server 关系及成功、失败或取消终态；
5. 一个传感器掉线、障碍、QoS/TF 或性能门槛故障注入；
6. 可校验的证据清单、哈希和引用文件完整性。

优先用 `launch_testing` 和隔离的 ROS domain。若没有 ROS 环境，保留测试文件、命令和预期，但把验证标为 `planned`，不将其写入 `complete` 需求证据。
