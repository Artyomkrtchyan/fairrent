"""Deploy immutable image digests through the existing ASG; run by GitHub only."""
import base64
import json
import os
import re
import subprocess
import time


def aws(service, operation, **parameters):
    args = ["aws", service, operation, "--output", "json"]
    for key, value in parameters.items():
        args.extend(["--" + key.replace("_", "-"),
                     json.dumps(value) if isinstance(value, (dict, list)) else str(value)])
    return json.loads(subprocess.check_output(args, text=True) or "{}")


def main():
    group_name = os.environ["ASG_NAME"]
    images = {name: os.environ[name.upper() + "_IMAGE"] for name in ("backend", "frontend")}
    registry = os.environ["ECR_REGISTRY"]
    for name, image in images.items():
        if not re.fullmatch(re.escape(registry + "/fairrent-" + name) + r"@sha256:[0-9a-f]{64}", image):
            raise ValueError("Deployment requires ECR image digests")

    groups = aws("autoscaling", "describe-auto-scaling-groups",
                 auto_scaling_group_names=[group_name])["AutoScalingGroups"]
    if len(groups) != 1:
        raise RuntimeError("Expected one existing ASG")
    current = groups[0]["LaunchTemplate"]
    if not current["Version"].isdigit():
        raise RuntimeError("ASG must use a numbered launch template version for rollback")
    refreshes = aws("autoscaling", "describe-instance-refreshes",
                    auto_scaling_group_name=group_name)["InstanceRefreshes"]
    terminal = {"Successful", "Failed", "Cancelled", "RollbackSuccessful", "RollbackFailed"}
    if any(item["Status"] not in terminal for item in refreshes):
        raise RuntimeError("Another instance refresh is active; wait for it before deploying")

    # Read each AMI-provided config, preserving its database/secret/region settings.
    # Only public image references change. Credentials still come from the EC2 role.
    bootstrap = """import json, os, subprocess
from pathlib import Path
images = IMAGES
for name, image in images.items():
    path = Path('/etc/fairrent') / (name + '.json')
    config = json.loads(path.read_text())
    config[name + '_image'] = image
    temporary = path.with_suffix('.json.release')
    temporary.write_text(json.dumps(config) + '\\n')
    temporary.chmod(0o640)
    os.replace(temporary, path)
subprocess.run(['systemctl', 'restart', 'fairrent-backend.service'], check=True)
subprocess.run(['systemctl', 'restart', 'fairrent-frontend.service'], check=True)
""".replace("IMAGES", repr(images))
    # JSON is valid YAML. This user data deliberately owns only release startup;
    # systemd units, Docker and AWS CLI are already installed in the golden AMI.
    cloud_config = {
        "bootcmd": [["systemctl", "stop", "fairrent-frontend.service", "fairrent-backend.service"]],
        "write_files": [{"path": "/opt/fairrent/release.py", "owner": "root:root",
                         "permissions": "0600", "content": bootstrap}],
        "runcmd": [["python3", "/opt/fairrent/release.py"]],
    }
    user_data = base64.b64encode(("#cloud-config\n" + json.dumps(cloud_config)).encode()).decode()
    version = aws("ec2", "create-launch-template-version",
                  launch_template_id=current["LaunchTemplateId"],
                  source_version=current["Version"],
                  version_description=os.environ["RELEASE_TAG"],
                  launch_template_data={"UserData": user_data})["LaunchTemplateVersion"]["VersionNumber"]
    refresh_id = aws("autoscaling", "start-instance-refresh",
                     auto_scaling_group_name=group_name,
                     desired_configuration={"LaunchTemplate": {
                         "LaunchTemplateId": current["LaunchTemplateId"], "Version": str(version)}},
                     preferences={"MinHealthyPercentage": 100, "MaxHealthyPercentage": 200,
                                  "InstanceWarmup": 180, "SkipMatching": True,
                                  "AutoRollback": True})["InstanceRefreshId"]
    print(f"Refreshing {group_name}: template version {version}, refresh {refresh_id}", flush=True)
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
        summary.write(f"### FairRent release {os.environ['RELEASE_TAG']}\n"
                      f"Launch template version: {version}; previous: {current['Version']}\n\n"
                      f"Refresh: `{refresh_id}`\n\n"
                      + "\n".join(f"- {key}: `{value}`" for key, value in images.items()) + "\n")
    last_status = None
    deadline = time.monotonic() + 45 * 60
    while time.monotonic() < deadline:
        refresh = aws("autoscaling", "describe-instance-refreshes",
                      auto_scaling_group_name=group_name,
                      instance_refresh_ids=[refresh_id])["InstanceRefreshes"][0]
        status = refresh["Status"]
        if status != last_status:
            print(status, refresh.get("StatusReason", ""), flush=True)
            last_status = status
        if status == "Successful":
            return
        if status in terminal:
            raise RuntimeError(f"Deployment did not succeed: {status}")
        time.sleep(30)
    raise RuntimeError("Timed out waiting; the AWS refresh continues. Inspect it before another deployment.")


if __name__ == "__main__":
    main()
