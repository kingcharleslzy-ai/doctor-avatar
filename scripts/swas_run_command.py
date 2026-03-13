from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_swas_open20200601 import models as swas_models
from alibabacloud_swas_open20200601.client import Client as SwasClient


DEFAULT_REGION = "ap-southeast-3"
DEFAULT_INSTANCE_ID = "7c3a74523d1f49e192b158e0f919eed4"
DEFAULT_ENDPOINT = "swas.ap-southeast-3.aliyuncs.com"


def get_required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def build_client(region_id: str, endpoint: str | None) -> SwasClient:
    config = open_api_models.Config(
        access_key_id=get_required_env("ALIBABA_CLOUD_ACCESS_KEY_ID"),
        access_key_secret=get_required_env("ALIBABA_CLOUD_ACCESS_KEY_SECRET"),
        region_id=region_id,
    )
    config.endpoint = endpoint or f"swas.{region_id}.aliyuncs.com"
    return SwasClient(config)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a command on Alibaba SWAS and print the result.")
    parser.add_argument("--region", default=DEFAULT_REGION, help="SWAS region ID")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="SWAS endpoint")
    parser.add_argument("--instance-id", default=DEFAULT_INSTANCE_ID, help="SWAS instance ID")
    parser.add_argument("--name", default="codex-manual-command", help="Command name")
    parser.add_argument("--type", default="RunShellScript", help="Command type")
    parser.add_argument("--timeout", type=int, default=60, help="Command timeout in seconds")
    parser.add_argument("--working-dir", default="/root", help="Working directory")
    parser.add_argument("--working-user", default="root", help="Working user")
    parser.add_argument("--poll-seconds", type=float, default=1.5, help="Polling interval")
    parser.add_argument("--max-wait-seconds", type=float, default=60, help="Maximum polling time")
    parser.add_argument("command", help="Shell command to run on the SWAS instance")
    return parser.parse_args()


def normalize_body(value: Any) -> Any:
    return value.to_map() if hasattr(value, "to_map") else value


def main() -> int:
    args = parse_args()
    client = build_client(args.region, args.endpoint)

    run_req = swas_models.RunCommandRequest(
        instance_id=args.instance_id,
        region_id=args.region,
        name=args.name,
        type=args.type,
        command_content=args.command,
        timeout=args.timeout,
        working_dir=args.working_dir,
        working_user=args.working_user,
    )
    run_resp = client.run_command(run_req)
    run_body = normalize_body(run_resp.body)

    command_id = run_body.get("CommandId")
    invoke_id = run_body.get("InvokeId")
    if not invoke_id:
        print(json.dumps({"run": run_body}, ensure_ascii=False, indent=2))
        raise RuntimeError("RunCommand did not return InvokeId")

    deadline = time.time() + args.max_wait_seconds
    last_body: dict[str, Any] | None = None

    while time.time() < deadline:
        query = swas_models.DescribeCommandInvocationsRequest(
            instance_id=args.instance_id,
            region_id=args.region,
            command_id=command_id,
            invoke_id=invoke_id,
        )
        query_resp = client.describe_command_invocations(query)
        last_body = normalize_body(query_resp.body)
        invocations = last_body.get("CommandInvocations", [])
        if invocations:
            invoke_instances = invocations[0].get("InvokeInstances", [])
            if invoke_instances:
                status = invoke_instances[0].get("InvocationStatus")
                if status in {"Success", "Failed", "TimedOut", "Cancelled"}:
                    print(json.dumps(last_body, ensure_ascii=False, indent=2))
                    return 0 if status == "Success" else 1
        time.sleep(args.poll_seconds)

    print(json.dumps({"run": run_body, "last_query": last_body}, ensure_ascii=False, indent=2))
    print("Timed out waiting for command result.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
