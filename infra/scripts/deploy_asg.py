"""Deploy immutable image digests through the existing ASG; run by GitHub only."""
import base64
import json
import os
import re
import subprocess
import time
from pathlib import Path


def aws(service, operation, **parameters):
    args = ["aws", service, operation, "--output", "json"]
    for key, value in parameters.items():
        args.extend(["--" + key.replace("_", "-"),
                     json.dumps(value) if isinstance(value, (dict, list)) else str(value)])
    return json.loads(subprocess.check_output(args, text=True) or "{}")


def build_user_data(images, bootstrap_directory=None, *, b07_package=None):
    # Read each AMI-provided config, preserving its database/secret/region settings.
    # Only public image references change. Credentials still come from the EC2 role.
    bootstrap = """import json, os, subprocess
from pathlib import Path
images = IMAGES
b07_package = B07_PACKAGE
for name, image in images.items():
    path = Path('/etc/fairrent') / (name + '.json')
    config = json.loads(path.read_text())
    config[name + '_image'] = image
    config['log_group'] = '/fairrent/dev/' + name
    if name == 'backend':
        if b07_package is None:
            config.pop('b07_package', None)
        else:
            config['b07_package'] = b07_package
    temporary = path.with_suffix('.json.release')
    temporary.write_text(json.dumps(config) + '\\n')
    temporary.chmod(0o640)
    os.replace(temporary, path)
subprocess.run(['systemctl', 'restart', 'fairrent-backend.service'], check=True)
subprocess.run(['systemctl', 'restart', 'fairrent-frontend.service'], check=True)
""".replace("IMAGES", repr(images)).replace("B07_PACKAGE", repr(b07_package))
    # JSON is valid YAML. This user data deliberately owns only release startup;
    # systemd units, Docker and AWS CLI are already installed in the golden AMI.
    cloud_config = {
        "bootcmd": [["systemctl", "stop", "fairrent-frontend.service", "fairrent-backend.service"]],
        "write_files": [{"path": "/opt/fairrent/release.py", "owner": "root:root",
                         "permissions": "0600", "content": bootstrap}],
        "runcmd": [["python3", "/opt/fairrent/release.py"]],
    }
    directory = bootstrap_directory or Path(__file__).resolve().parents[1] / "ansible" / "files"
    for name in ("backend", "frontend"):
        filename = f"fairrent-{name}-start.py"
        cloud_config["write_files"].append({
            "path": "/usr/local/sbin/" + filename, "owner": "root:root", "permissions": "0750",
            "content": (directory / filename).read_text(encoding="utf-8"),
        })
    payload = ("#cloud-config\n" + json.dumps(cloud_config)).encode()
    if len(payload) > 16384:
        raise ValueError("Release user data exceeds the EC2 16 KiB limit")
    return base64.b64encode(payload).decode()


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

    model_version = os.environ.get("B07_PACKAGE_VERSION", "")
    model_checksum = os.environ.get("B07_PACKAGE_SHA256", "")
    model = None
    if model_version or model_checksum:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", model_version) or not re.fullmatch(r"[a-f0-9]{64}", model_checksum):
            raise ValueError("Set both a valid B07 package version and checksum manifest SHA-256")
        model = {"version": model_version, "checksum_sha256": model_checksum}
    user_data = build_user_data(images, b07_package=model)
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
