#!/usr/bin/env python3
"""Validate a wheeled-robot project intake and report delivery-level gaps."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


LEVELS = ("L1", "L2", "L3", "L4")
UNSAFE_PROVENANCE = re.compile(r"(?:test_default|test_assumption|unresolved|conflict)", re.I)
SECRET_KEY = re.compile(r"(?:password|passwd|token|secret|api[_-]?key|private[_-]?key)", re.I)

SIGNALS: dict[str, tuple[str, ...]] = {
    "base_type": (
        "base.type", "base_type", "differential", "diff_drive", "skid_steer",
        "ackermann", "mecanum", "omni", "swerve", "articulated", "轮式", "差速",
        "阿克曼", "麦克纳姆", "全向轮", "舵轮",
    ),
    "project_direction": ("project_direction", "project_goal", "mission", "任务", "项目方向"),
    "technical_stack": ("technical_stack", "ros 1", "ros1", "ros 2", "ros2", "技术栈"),
    "ros": ("ros 1", "ros1", "ros 2", "ros2", "humble", "jazzy", "noetic"),
    "simulator": ("gazebo", "isaac sim", "isaac_sim", "mujoco", "simulation", "simulator", "仿真"),
    "compute": ("compute", "jetson", "industrial_pc", "industrial pc", "ipc", "upper_compute", "host", "工控机", "上位机"),
    "drive": ("drive", "motor", "driver", "mcpwm", "velocity pid", "speed pid", "电机", "驱动器"),
    "driver_topology": ("pwm+dir", "pwm_dir", "dual_h_bridge", "dual h bridge", "can-fd", "socketcan", "ethercat", "双输入", "h桥"),
    "driver_truth_table": ("truth_table", "truth table", "brake_polarity", "direction_polarity", "enable_polarity", "fault_polarity", "真值表", "刹车极性", "方向极性"),
    "geometry": ("wheel_radius", "wheel_diameter", "wheel_separation", "wheel_track", "track_width", "wheelbase", "轮径", "轮距", "轴距"),
    "encoder_scale": ("distance_per_count", "counts_per", "cpr", "ppr", "encoder_resolution", "gear_ratio", "reduction", "编码器", "减速比"),
    "sensors": ("sensors", "lidar", "laser", "imu", "camera", "gnss", "雷达", "相机"),
    "extrinsics": ("extrinsic", "xyz_m", "rpy_rad", "sensor_pose", "static_transform", "外参"),
    "power": ("battery", "power", "rated_voltage", "continuous_current", "peak_current", "电池", "供电", "欠压"),
    "physical_estop": ("physical_emergency_stop", "physical_estop", "safety_relay", "hardwired_estop", "物理急停", "安全继电器"),
    "communications": ("network", "communication", "uart", "serial", "can", "ethernet", "ethercat", "udp", "通信"),
    "acceptance": ("acceptance", "acceptance_tests", "success_metric", "test_profile", "验收", "通过标准"),
    "license": ("license", "spdx", "许可证"),
    "runtime_evidence": ("runtime_evidence", "build_evidence", "simulation_evidence", "real_robot_evidence", "运行证据", "实机验收记录"),
}

QUESTIONS = {
    "base_type": "底盘属于哪种轮式运动学？请说明驱动轮、转向轮、能否横移和原地旋转。",
    "project_direction": "项目要完成哪些任务？请给出优先级和至少一个可测验收指标。",
    "technical_stack": "目标操作系统、ROS 发行版、语言、构建系统和主要依赖是什么？",
    "ros": "目标使用 ROS 2、ROS 1 还是混合系统？请给出发行版。",
    "simulator": "选择 Gazebo、Isaac Sim、MuJoCo 还是其他仿真器？目标版本是什么？",
    "compute": "MCU、上位机/Jetson/工控机的型号、操作系统和资源配置是什么？",
    "drive": "电机、驱动器、闭环位置和控制接口是什么？",
    "driver_topology": "驱动器是 PWM+DIR、双输入 H 桥、CAN 或其他拓扑？enable/brake/fault 如何连接？",
    "driver_truth_table": "请提供驱动器方向、使能、制动和故障引脚的真值表与有效极性。仅有引脚号不足以确认。",
    "geometry": "请提供运动学所需几何量，例如轮径、轮距、轴距或舵轮模块位置。",
    "encoder_scale": "请提供编码器 CPR/PPR、解码方式、减速比或实测每计数距离，并消除来源冲突。",
    "sensors": "项目使用哪些传感器？请给出型号、接口、频率和时间戳来源。",
    "extrinsics": "请提供关键传感器相对 base_link 的 XYZ/RPY 外参及标定状态。",
    "power": "请提供供电/电池、电压电流上限、保险/限流和欠压停机阈值。",
    "physical_estop": "是否有独立物理急停或安全继电器？请说明其断能路径和复位方式。",
    "communications": "各计算节点和驱动/传感器之间使用什么总线、串口或网络拓扑？",
    "acceptance": "请给出构建、仿真、故障注入、低速实机和任务级验收标准。",
    "license": "新仓库采用什么许可证？未确认时应保持未授权状态而不是自动选择许可证。",
    "runtime_evidence": "L4 需要指定机器人上的构建、部署、低速运动、失联停机和任务验收证据。",
}


@dataclass(frozen=True)
class Record:
    path: str
    text: str
    provenance: str | None


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("top-level intake must be a JSON object")
    allowed = value.get("allowed_input", value)
    if not isinstance(allowed, dict):
        raise ValueError("allowed_input must be a JSON object")
    return allowed


def scalar_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value)
    return ""


def iter_records(value: Any, path: str = "", inherited_provenance: str | None = None) -> Iterable[Record]:
    if isinstance(value, dict):
        local_provenance = scalar_text(value.get("provenance")) or inherited_provenance
        if "value" in value:
            text = scalar_text(value.get("value"))
            if not text and isinstance(value.get("value"), (list, dict)):
                text = json.dumps(value.get("value"), ensure_ascii=False, sort_keys=True)
            yield Record(path, text, local_provenance)
            return
        for key, child in value.items():
            if key == "provenance" or SECRET_KEY.search(str(key)):
                continue
            child_path = f"{path}.{key}" if path else str(key)
            yield from iter_records(child, child_path, local_provenance)
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_records(child, f"{path}[{index}]", inherited_provenance)
        return
    yield Record(path, scalar_text(value), inherited_provenance)


def signal_hits(records: list[Record]) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    for name, needles in SIGNALS.items():
        matched_paths: list[str] = []
        for record in records:
            haystack = f"{record.path} {record.text}".lower()
            if any(needle.lower() in haystack for needle in needles):
                matched_paths.append(record.path)
        hits[name] = sorted(set(matched_paths))
    return hits


def evaluate(allowed: dict[str, Any]) -> dict[str, Any]:
    records = list(iter_records(allowed))
    hits = signal_hits(records)
    present = {name: bool(paths) for name, paths in hits.items()}
    provenance = Counter((record.provenance or "unspecified") for record in records)
    unsafe_paths = sorted({
        record.path
        for record in records
        if record.provenance and UNSAFE_PROVENANCE.search(record.provenance)
    })

    requirements = {
        "L1": ("base_type", "project_direction", "technical_stack"),
        "L2": ("base_type", "project_direction", "technical_stack", "ros", "simulator", "geometry", "sensors"),
        "L3": (
            "base_type", "project_direction", "technical_stack", "ros", "simulator",
            "compute", "drive", "driver_topology", "driver_truth_table", "geometry",
            "encoder_scale", "sensors", "extrinsics", "power", "physical_estop",
            "communications", "acceptance",
        ),
        "L4": ("runtime_evidence",),
    }
    eligibility: dict[str, Any] = {}
    previous_ok = True
    for level in LEVELS:
        missing = [name for name in requirements[level] if not present[name]]
        blockers: list[str] = []
        if level in {"L3", "L4"} and unsafe_paths:
            blockers.append("存在 test_default、unresolved 或 conflict 来源，不能解锁实机")
        if level == "L4":
            blockers.append("L4 必须人工核验运行证据和实机授权，验证器不能仅凭输入自动批准")
        ok = previous_ok and not missing and not blockers
        eligibility[level] = {
            "input_ready": ok,
            "missing": missing,
            "blockers": blockers,
        }
        previous_ok = ok

    maximum = "none"
    for level in LEVELS:
        if eligibility[level]["input_ready"]:
            maximum = level

    target_gaps: list[str] = []
    for level in ("L1", "L2", "L3"):
        target_gaps.extend(eligibility[level]["missing"])
    if not present["license"]:
        target_gaps.append("license")
    questions = [QUESTIONS[name] for name in dict.fromkeys(target_gaps)]

    return {
        "schema_version": 1,
        "ok": eligibility["L1"]["input_ready"],
        "maximum_automatic_input_level": maximum,
        "level_eligibility": eligibility,
        "signals": present,
        "signal_evidence_paths": hits,
        "provenance_summary": dict(sorted(provenance.items())),
        "unsafe_provenance_paths": unsafe_paths,
        "questions": questions,
        "notes": [
            "测试默认值只允许用于其标注的仿真或台架范围",
            "输出不回显输入值或凭据；证据仅列 JSON 路径",
            "许可证缺失不阻止架构分析，但阻止把自动选择的许可证当作用户决定",
        ],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("intake", type=Path, help="project intake JSON")
    parser.add_argument("--target-level", choices=LEVELS, help="fail if this level is not input-ready")
    parser.add_argument("--output", type=Path, help="write report JSON")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv or sys.argv[1:])
    try:
        allowed = load_json(args.intake.resolve())
        result = evaluate(allowed)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    text = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    if args.target_level and not result["level_eligibility"][args.target_level]["input_ready"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
