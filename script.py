import os
import json
import argparse
import boto3
from kubernetes import client, config

# Initialize AWS clients
ssm_client = boto3.client("ssm")
autoscaling_client = boto3.client("autoscaling")

# AWS SSM Parameter Names
K8S_AWS_SSM_PARAMETER_NAME = "/kubernetes-aws-eks-auto-scaler/k8s-replica-counts"
ASG_AWS_SSM_PARAMETER_NAME = "/kubernetes-aws-eks-auto-scaler/asg-config"

def load_kubernetes_config():
    """Load Kubernetes configuration based on the environment."""
    print("Loading Kubernetes configuration...")
    try:
        if "KUBERNETES_SERVICE_HOST" in os.environ:
            print("Detected in-cluster environment.")
            config.load_incluster_config()
        else:
            print("Detected local environment. Using kubeconfig.")
            config.load_kube_config()
        print("Kubernetes configuration loaded successfully.")
    except Exception as e:
        print(f"Error loading Kubernetes configuration: {e}")
        raise

def filter_excluded_k8s_resources(kind, resources, exclude_list):
    """Remove Kubernetes resources that are in the exclude list."""
    if not exclude_list:
        print(f"No Kubernetes resources of kind '{kind}' to exclude.")
        return resources

    print(f"Excluding the following Kubernetes resources: {exclude_list}")
    exclude_set = {(res["namespace"], res["kind"].lower(), res["name"]) for res in exclude_list}

    filtered_resources = [
        res for res in resources
        if (res.metadata.namespace, kind.lower(), res.metadata.name) not in exclude_set
    ]

    print(f"Remaining Kubernetes resources after exclusion: {[f'{res.kind}/{res.metadata.namespace}/{res.metadata.name}' for res in filtered_resources]}")
    return filtered_resources

def filter_excluded_asgs(asg_list, exclude_list):
    """Remove AWS Auto Scaling Groups that are in the exclude list."""
    if not exclude_list:
        print("No AWS Auto Scaling Groups to exclude.")
        return asg_list

    print(f"Excluding the following AWS Auto Scaling Groups: {exclude_list}")
    filtered_asgs = [asg for asg in asg_list if asg not in exclude_list]

    print(f"Remaining AWS Auto Scaling Groups after exclusion: {filtered_asgs}")
    return filtered_asgs

def update_ssm_parameter(ssm_client, parameter_name, new_data):
    """Update AWS SSM parameter while preserving existing keys."""
    print(f"Updating AWS SSM parameter: {parameter_name}")
    try:
        existing_data = json.loads(ssm_client.get_parameter(Name=parameter_name)["Parameter"]["Value"])
        print("Fetched existing AWS SSM data.")
    except ssm_client.exceptions.ParameterNotFound:
        print("No existing AWS SSM data found. Initializing new parameter.")
        existing_data = {}

    existing_data.update(new_data)
    ssm_client.put_parameter(Name=parameter_name, Value=json.dumps(existing_data), Type="String", Overwrite=True)
    print(f"AWS SSM parameter {parameter_name} updated successfully.")

def scale_down(k8s_resources, aws_asg_resources, exclude_k8s_resources, exclude_aws_asg_resources):
    """Scale down Kubernetes resources and AWS Auto Scaling Groups."""
    print("Scaling down Kubernetes resources and AWS Auto Scaling Groups...")
    k8s_client = client.AppsV1Api()
    batch_client = client.BatchV1Api()

    # Fetch K8s resources
    if not k8s_resources:
        print("Fetching all Deployments, StatefulSets, and CronJobs...")
        all_deployments = k8s_client.list_deployment_for_all_namespaces().items
        all_statefulsets = k8s_client.list_stateful_set_for_all_namespaces().items
        all_cronjobs = batch_client.list_cron_job_for_all_namespaces().items
    else:
        print(f"Scaling down specific Kubernetes resources: {k8s_resources}")
        all_deployments = [k8s_client.read_namespaced_deployment(res["name"], res["namespace"]) for res in k8s_resources if res["kind"].lower() == "deployment"]
        all_statefulsets = [k8s_client.read_namespaced_stateful_set(res["name"], res["namespace"]) for res in k8s_resources if res["kind"].lower() == "statefulset"]
        all_cronjobs = [batch_client.read_namespaced_cron_job(res["name"], res["namespace"]) for res in k8s_resources if res["kind"].lower() == "cronjob"]

    # Exclude specified K8s resources
    all_deployments = filter_excluded_k8s_resources("Deployment", all_deployments, exclude_k8s_resources)
    all_statefulsets = filter_excluded_k8s_resources("StatefulSet", all_statefulsets, exclude_k8s_resources)
    all_cronjobs = filter_excluded_k8s_resources("CronJob", all_cronjobs, exclude_k8s_resources)

    # Scale down K8s resources
    k8s_scaling_data = {}
    for deployment in all_deployments:
        if deployment.spec.replicas > 0:
            print(f"Scaling down Deployment '{deployment.metadata.name}' in namespace '{deployment.metadata.namespace}'")
            k8s_scaling_data[f"deployment/{deployment.metadata.namespace}/{deployment.metadata.name}"] = deployment.spec.replicas
            deployment.spec.replicas = 0
            k8s_client.patch_namespaced_deployment(deployment.metadata.name, deployment.metadata.namespace, deployment)
        else:
            print(f"Deployment '{deployment.metadata.name}' in namespace '{deployment.metadata.namespace}' has already scaled down to zero.")

    for statefulset in all_statefulsets:
        if statefulset.spec.replicas > 0:
            print(f"Scaling down StatefulSet '{statefulset.metadata.name}' in namespace '{statefulset.metadata.namespace}'")
            k8s_scaling_data[f"statefulset/{statefulset.metadata.namespace}/{statefulset.metadata.name}"] = statefulset.spec.replicas
            statefulset.spec.replicas = 0
            k8s_client.patch_namespaced_stateful_set(statefulset.metadata.name, statefulset.metadata.namespace, statefulset)
        else:
            print(f"StatefulSet '{statefulset.metadata.name}' in namespace '{statefulset.metadata.namespace}' has already scaled down to zero.")

    for cronjob in all_cronjobs:
        print(f"Suspending CronJob '{cronjob.metadata.name}' in namespace '{cronjob.metadata.namespace}'")
        cronjob.spec.suspend = True
        batch_client.patch_namespaced_cron_job(cronjob.metadata.name, cronjob.metadata.namespace, cronjob)

    # Store K8s data
    if k8s_scaling_data:
        update_ssm_parameter(ssm_client, K8S_AWS_SSM_PARAMETER_NAME, k8s_scaling_data)

    # Fetch AWS ASGs
    if not aws_asg_resources:
        print("Fetching all AWS Auto Scaling Groups...")
        asg_response = autoscaling_client.describe_auto_scaling_groups()
        aws_asg_resources = [asg["AutoScalingGroupName"] for asg in asg_response["AutoScalingGroups"]]

    # Exclude specified AWS ASGs
    aws_asg_resources = filter_excluded_asgs(aws_asg_resources, exclude_aws_asg_resources)

    # Scale down AWS ASGs
    asg_scaling_data = {}
    for asg_name in aws_asg_resources:
        asg = autoscaling_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])["AutoScalingGroups"][0]
        if asg["MinSize"] > 0 or asg["DesiredCapacity"] != 0 or asg["MaxSize"] != 0:
            print(f"Scaling down AWS Auto Scaling Group '{asg_name}'")
            asg_scaling_data[asg_name] = {"MinSize": asg["MinSize"], "DesiredCapacity": asg["DesiredCapacity"], "MaxSize": asg["MaxSize"]}
            autoscaling_client.update_auto_scaling_group(AutoScalingGroupName=asg_name, MinSize=0, DesiredCapacity=0, MaxSize=0)
        else:
            print(f"AWS Auto Scaling Group '{asg_name}' has already scaled down to zero.")

    # Store AWS ASGs data
    if asg_scaling_data:
        update_ssm_parameter(ssm_client, ASG_AWS_SSM_PARAMETER_NAME, asg_scaling_data)

def scale_up():
    """Scale up Kubernetes resources and AWS Auto Scaling Groups."""
    print("Scaling up Kubernetes resources and AWS Auto Scaling Groups...")
    k8s_client = client.AppsV1Api()
    batch_client = client.BatchV1Api()

    # Restore AWS ASGs
    try:
        print("Fetching stored AWS Auto Scaling Group configurations...")
        asg_scaling_data = json.loads(ssm_client.get_parameter(Name=ASG_AWS_SSM_PARAMETER_NAME)["Parameter"]["Value"])
        for asg_name, config in asg_scaling_data.items():
            print(f"Restoring AWS Auto Scaling Group '{asg_name}'")
            autoscaling_client.update_auto_scaling_group(AutoScalingGroupName=asg_name, MinSize=config["MinSize"], DesiredCapacity=config["DesiredCapacity"], MaxSize=config["MaxSize"])
    except ssm_client.exceptions.ParameterNotFound:
        print("No stored AWS Auto Scaling Group configurations found.")

    # Restore K8s resources
    try:
        print("Fetching stored Kubernetes configurations...")
        k8s_scaling_data = json.loads(ssm_client.get_parameter(Name=K8S_AWS_SSM_PARAMETER_NAME)["Parameter"]["Value"])
        for key, replicas in k8s_scaling_data.items():
            kind, namespace, name = key.split("/")
            print(f"Restoring '{kind.capitalize()}' '{name}' in namespace {namespace}")
            if kind == "deployment":
                deployment = k8s_client.read_namespaced_deployment(name, namespace)
                deployment.spec.replicas = replicas
                k8s_client.patch_namespaced_deployment(name, namespace, deployment)
            elif kind == "statefulset":
                statefulset = k8s_client.read_namespaced_stateful_set(name, namespace)
                statefulset.spec.replicas = replicas
                k8s_client.patch_namespaced_stateful_set(name, namespace, statefulset)
    except ssm_client.exceptions.ParameterNotFound:
        print("No stored Kubernetes configurations found.")

    # Resume CronJobs
    print("Resuming suspended CronJobs...")
    cronjobs = batch_client.list_cron_job_for_all_namespaces().items
    for cronjob in cronjobs:
        print(f"Resuming CronJob '{cronjob.metadata.name}' in namespace '{cronjob.metadata.namespace}'")
        cronjob.spec.suspend = False
        batch_client.patch_namespaced_cron_job(cronjob.metadata.name, cronjob.metadata.namespace, cronjob)

def main():
    print("Starting script execution...")
    load_kubernetes_config()

    parser = argparse.ArgumentParser(description="Scale Kubernetes resources and AWS EKS node groups.")
    parser.add_argument("action", choices=["scale-down", "scale-up"], help="Action to perform. It can be either \"scale-down\" or \"scale-up\".")
    parser.add_argument("--k8s-resources", type=json.loads, help="List of Kubernetes resources to be considered, in JSON format. (e.g., [{\"namespace\": \"default\", \"kind\": \"deployment\", \"name\": \"example-deployment\"}])")
    parser.add_argument("--exclude-k8s-resources", type=json.loads, help="List of Kubernetes resources to be excluded, in JSON format. (e.g., [{\"namespace\": \"default\", \"kind\": \"deployment\", \"name\": \"example-deployment\"}])")
    parser.add_argument("--aws-asg-resources", nargs='*', help="List of AWS Auto Scaling Groups to be considered. (e.g., aws-asg-example-1, aws-asg-example-2)")
    parser.add_argument("--exclude-aws-asg-resources", nargs='*', help="List of AWS Auto Scaling Groups to be excluded. (e.g., aws-asg-example-1, aws-asg-example-2)")

    args = parser.parse_args()

    if args.action == "scale-down":
        scale_down(args.k8s_resources, args.aws_asg_resources, args.exclude_k8s_resources, args.exclude_aws_asg_resources)
    elif args.action == "scale-up":
        scale_up()
    print("Script execution finished!")

if __name__ == "__main__":
    main()
