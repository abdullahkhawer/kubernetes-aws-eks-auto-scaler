# Kubernetes AWS EKS Auto Scaler

##### kubernetes-aws-eks-auto-scaler

This tool automates the scaling of Kubernetes deployments, statefulsets, and cronjobs in Amazon EKS clusters, as well as AWS Auto Scaling Groups. It allows for scaling resources down (setting replicas to zero or suspending cronjobs) and scaling them back up by restoring previous configurations stored in AWS Parameter Store.

---

## Features

- **Scale Down**:
  - Sets `replicas` to zero for Deployments and StatefulSets.
  - Suspends CronJobs.
  - Scales down AWS Auto Scaling Groups by setting their `MinSize`, `DesiredCapacity` and `MaxSize` to zero.
  - Persists `replicas` for Deployments and StatefulSets and `MinSize`, `DesiredCapacity` and `MaxSize` for AWS Auto Scaling Groups in AWS SSM Parameter Store.
- **Scale Up**:
  - Restores Deployments and StatefulSets to their previous/original replica counts.
  - Resumes suspended CronJobs.
  - Restores AWS Auto Scaling Groups to their previous/original configurations.
- **Selective Scaling**:
  - Target specific Kubernetes resources using JSON-formatted parameters.
  - Target specific AWS Auto Scaling Groups.
  - Exclude specific Kubernetes resources or AWS Auto Scaling Groups from scaling operations.
- **Persistent State Management**:
  - Stores replica counts and ASG configurations in AWS Parameter Store for reliable state restoration.

## Upcoming Features

- **Docker Container**:
  - A Dockerfile will be added so that the tool can be executed inside a Docker container directly.
- **Helm Chart**:
  - A Helm chart will be added so that the tool can be executed via a CronJob on the Kubernetes cluster. This will only work if at least one of the EKS node groups have been excluded. Terraform code will be added for its deployment.
- **AWS Lambda function with AWS EventBridge Rule (AWS CloudWatch Event)**:
  - A Terraform code will be added to deploy this tool on an AWS Lambda function along with AWS EventBridge Rule (AWS CloudWatch Event) so that it can be executed automatically on the basis of a schedule defined using Cron. This will work even if all EKS node groups have been scaled down.

---

## Prerequisites

### 1. Dependencies

- Python 3.7+
- Required Python libraries:
  ```bash
  pip install boto3 kubernetes
  ```

### 2. AWS Setup
- Configure AWS credentials using the AWS CLI or AWS IAM role:
  ```bash
  aws configure
  ```
- Ensure the following AWS IAM permissions:
  - Access to AWS Systems Manager (SSM) Parameter Store.
  - Permissions to describe and update AWS Auto Scaling Groups.

### 3. Kubernetes Configuration
- **In-cluster Execution**:
  - Use a Kubernetes service account with RBAC permissions to manage Deployments, StatefulSets, and CronJobs.
- **Local Execution**:
  - Ensure `kubectl` is configured with cluster access.

### 4. AWS Parameter Store Key

The script uses the following keys to store configuration data:
- Replica counts for Kubernetes resources:
  ```
  /kubernetes-aws-eks-auto-scaler/k8s-replica-counts
  ```
- AWS Auto Scaling Group configurations:
  ```
  /kubernetes-aws-eks-auto-scaler/asg-config
  ```

*Note: These parameters will be created and managed automatically if they do not exist.*

---

## Usage

### Running the script locally

```bash
python script.py <action> [options]
```

### Arguments

| Argument                     | Description                                                                                         |
|------------------------------|-----------------------------------------------------------------------------------------------------|
| `<action>`                   | The action to perform: `scale-down` or `scale-up`.                                                 |
| `--k8s-resources`            | JSON-formatted array specifying the Kubernetes resources to scale. Example: `[{"namespace": "default", "kind": "deployment", "name": "example-deployment"}]` |
| `--exclude-k8s-resources`    | JSON-formatted array specifying Kubernetes resources to exclude from scaling.                      |
| `--aws-asg-resources`        | Space-separated list of AWS Auto Scaling Groups to target. Example: `aws-asg-example-1 aws-asg-example-2` |
| `--exclude-aws-asg-resources`| Space-separated list of AWS Auto Scaling Groups to exclude from scaling.                           |

### Examples

#### Scale Down All Resources

Scale down all Kubernetes Deployments, StatefulSets, CronJobs, and AWS Auto Scaling Groups in the cluster:

```bash
python script.py scale-down
```

#### Scale Up All Resources

Restore all previously scaled-down Kubernetes resources and AWS Auto Scaling Groups:

```bash
python script.py scale-up
```

#### Scale Down Specific Kubernetes Resources

Scale down only the specified Kubernetes resources (e.g., a specific Deployment):

```bash
python script.py scale-down --k8s-resources '[{"namespace": "default", "kind": "deployment", "name": "example-deployment"}]'
```

#### Exclude Specific Resources

Scale down all resources except those specified. For example, to exclude a particular Deployment and AWS ASG:

```bash
python script.py scale-down --exclude-k8s-resources '[{"namespace": "default", "kind": "deployment", "name": "example-deployment"}]' --exclude-aws-asg-resources aws-asg-example-1
```

#### Target Specific AWS Auto Scaling Groups

Scale down only the specified AWS Auto Scaling Groups:

```bash
python script.py scale-down --aws-asg-resources aws-asg-example-1, aws-asg-example-2
```

---

## Resource Specification Format

When specifying Kubernetes resources via the command-line, provide a JSON array of objects with the following keys:

```json
[
  {
    "namespace": "default",
    "kind": "deployment",
    "name": "my-deployment"
  },
  {
    "namespace": "default",
    "kind": "statefulset",
    "name": "my-statefulset"
  }
]
```

*Note: The kind field should be one of deployment, statefulset, or cronjob (case insensitive).*

## Logging and Error Handling

- **Logging**:
  - The script logs details for loading configurations, fetching/updating resources, and interactions with AWS Parameter Store.
- **Error Handling**:
  - Gracefully handles missing resources or invalid configurations.
  - Differentiates between in-cluster and local execution environments.

---

## Limitations

- The script does not manage custom resource definitions (CRDs) or other Kubernetes resource types.
- All AWS API calls are synchronous, which may affect performance with a large number of resources.
- Ensure that the AWS Parameter Store keys are correctly configured and accessible.

---

## Contributing

Contributions, suggestions, or bug reports are welcome. Feel free to open issues or submit pull requests.

---

Enjoy seamless Kubernetes scaling automation! 🎉
