from mcp.server.fastmcp import FastMCP
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, ClassVar
from functools import lru_cache

# ---------------- MCP Initialization ---------------- #
mcp = FastMCP("Kubernetes MCP Server")

# ---------------- Kubernetes Initialization ---------------- #
try:
    config.load_kube_config()
except Exception as e:
    raise RuntimeError(f"Failed to load kubeconfig: {e}")

v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()
networking_v1 = client.NetworkingV1Api()

# ---------------- Helper ---------------- #
def safe_api_call(func):
    try:
        return func()
    except ApiException as e:
        return {"error": f"ApiException: {e.reason}"}
    except Exception as e:
        return {"error": f"Exception: {str(e)}"}


# ---------------- Kubernetes Validation Helpers ---------------- #

@lru_cache(maxsize=1, typed=False)
def get_cluster_namespaces(ttl_hash: int = None) -> set[str]:
    """
    Fetch all namespaces from the cluster with optional caching.
    The ttl_hash parameter can be used to invalidate cache periodically.
    """
    try:
        namespaces = v1.list_namespace()
        return {ns.metadata.name for ns in namespaces.items}
    except ApiException as e:
        raise ValueError(f"Failed to fetch namespaces from cluster: {e.reason}")


def validate_namespace_exists(namespace: str) -> str:
    """
    Validate that a namespace exists in the Kubernetes cluster.
    """
    cluster_namespaces = get_cluster_namespaces()
    if namespace not in cluster_namespaces:
        raise ValueError(
            f"Namespace '{namespace}' does not exist in the cluster. "
            f"Available namespaces: {', '.join(sorted(cluster_namespaces))}"
        )
    return namespace


# ---------------- Pydantic Models ---------------- #

class NamespaceInput(BaseModel):
    """Base model for operations requiring a namespace."""
    namespace: str = Field(
        default="default",
        min_length=1,
        max_length=253,
        description="Kubernetes namespace name"
    )
    
    @field_validator('namespace')
    @classmethod
    def validate_namespace(cls, v: str) -> str:
        """
        Validate namespace format and existence in cluster.
        Steps:
        1. Strip whitespace
        2. Check it's not empty
        3. Validate DNS label format
        4. Convert to lowercase
        5. Check if it exists in the cluster
        """
        # Step 1: Strip whitespace
        v = v.strip()
        
        # Step 2: Check not empty
        if not v:
            raise ValueError("Namespace cannot be empty or whitespace")
        
        # Step 3: Basic DNS label validation
        if not v.replace('-', '').replace('.', '').isalnum():
            raise ValueError(
                "Namespace must contain only alphanumeric characters, '-', or '.'"
            )
        
        # Step 4: Convert to lowercase
        v = v.lower()
        
        # Step 5: Validate existence in cluster
        v = validate_namespace_exists(v)
        
        return v


class PodNameInput(NamespaceInput):
    """Input model for pod-specific operations."""
    pod_name: str = Field(
        ...,
        min_length=1,
        max_length=253,
        description="Name of the pod"
    )
    
    @field_validator('pod_name')
    @classmethod
    def validate_pod_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Pod name cannot be empty")
        return v


class PodLogsInput(PodNameInput):
    """Input model for fetching pod logs."""
    tail_lines: int = Field(
        default=50,
        ge=1,
        le=10000,
        description="Number of log lines to retrieve"
    )
    container: Optional[str] = Field(
        default=None,
        description="Specific container name for multi-container pods"
    )


class DeploymentNameInput(NamespaceInput):
    """Input model for deployment-specific operations."""
    deployment_name: str = Field(
        ...,
        min_length=1,
        max_length=253,
        description="Name of the deployment"
    )
    
    @field_validator('deployment_name')
    @classmethod
    def validate_deployment_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Deployment name cannot be empty")
        return v


class ScaleDeploymentInput(DeploymentNameInput):
    """Input model for scaling deployments."""
    replicas: int = Field(
        ...,
        ge=0,
        le=1000,
        description="Desired number of replicas"
    )


class CreatePodInput(NamespaceInput):
    """Input model for creating pods."""
    name: str = Field(..., min_length=1, max_length=253)
    image: str = Field(..., min_length=1, description="Container image")
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    env_vars: Optional[dict[str, str]] = Field(default=None)
    labels: Optional[dict[str, str]] = Field(default=None)
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        return v.strip().lower()
    
    @field_validator('image')
    @classmethod
    def validate_image(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Image cannot be empty")
        return v


class CreateDeploymentInput(NamespaceInput):
    """Input model for creating deployments."""
    name: str = Field(..., min_length=1, max_length=253)
    image: str = Field(..., min_length=1)
    replicas: int = Field(default=1, ge=0, le=1000)
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    env_vars: Optional[dict[str, str]] = Field(default=None)
    labels: Optional[dict[str, str]] = Field(default=None)
    cpu_request: Optional[str] = Field(default=None, pattern=r'^\d+m?$')
    memory_request: Optional[str] = Field(default=None, pattern=r'^\d+(Mi|Gi|M|G)?$')
    cpu_limit: Optional[str] = Field(default=None, pattern=r'^\d+m?$')
    memory_limit: Optional[str] = Field(default=None, pattern=r'^\d+(Mi|Gi|M|G)?$')
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        return v.strip().lower()
    
    @field_validator('image')
    @classmethod
    def validate_image(cls, v: str) -> str:
        return v.strip()


class CreateServiceInput(NamespaceInput):
    """Input model for creating services."""
    name: str = Field(..., min_length=1, max_length=253)
    port: int = Field(..., ge=1, le=65535, description="Service port (external)")
    target_port: int = Field(..., ge=1, le=65535, description="Target pod port (internal)")
    selector: Optional[dict[str, str]] = Field(default=None)
    service_type: str = Field(default="ClusterIP", pattern=r'^(ClusterIP|NodePort|LoadBalancer)$')
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        return v.strip().lower()


class ServiceNameInput(NamespaceInput):
    """Input model for service operations."""
    service_name: str = Field(..., min_length=1, max_length=253)
    
    @field_validator('service_name')
    @classmethod
    def validate_service_name(cls, v: str) -> str:
        return v.strip()


# ---------------- Basic Resource Listing ---------------- #

@mcp.tool()
def get_nodes() -> list[str]:
    """Retrieves a comprehensive list of all **active node names** currently registered in the Kubernetes cluster."""
    return safe_api_call(lambda: [node.metadata.name for node in v1.list_node().items])


@mcp.tool()
def get_namespaces() -> list[str]:
    """Retrieves a list of all **existing namespace names** within the Kubernetes cluster."""
    return safe_api_call(lambda: [ns.metadata.name for ns in v1.list_namespace().items])


@mcp.tool()
def get_pods(input: NamespaceInput) -> list[str]:
    """List all pod names running in a specified Kubernetes namespace.

    Args:
        input: NamespaceInput model with validated namespace parameter
    """
    return safe_api_call(
        lambda: [pod.metadata.name for pod in v1.list_namespaced_pod(input.namespace).items]
    )


@mcp.tool()
def get_deployments(input: NamespaceInput) -> list[str]:
    """List all deployment names within a specified Kubernetes namespace.

    Args:
        input: NamespaceInput model with validated namespace parameter
    """
    return safe_api_call(
        lambda: [d.metadata.name for d in apps_v1.list_namespaced_deployment(input.namespace).items]
    )


@mcp.tool()
def get_services(input: NamespaceInput) -> list[str]:
    """List all service names in a specified Kubernetes namespace.

    Args:
        input: NamespaceInput model with validated namespace parameter
    """
    return safe_api_call(
        lambda: [s.metadata.name for s in v1.list_namespaced_service(input.namespace).items]
    )


# ---------------- Error Detection ---------------- #

@mcp.tool()
def get_pods_with_errors(input: NamespaceInput) -> list[dict]:
    """List pods with errors or non-running states.
    
    Args:
        input: NamespaceInput model with validated namespace parameter
    """
    def inner():
        pods = []
        for pod in v1.list_namespaced_pod(input.namespace).items:
            if pod.status.phase not in ["Running", "Succeeded"]:
                pods.append({
                    "name": pod.metadata.name,
                    "phase": pod.status.phase,
                    "reason": getattr(pod.status, "reason", None),
                    "message": getattr(pod.status, "message", None),
                })
            elif pod.status.container_statuses:
                for cs in pod.status.container_statuses:
                    state = cs.state
                    if state.waiting or (state.terminated and state.terminated.exit_code != 0):
                        pods.append({
                            "name": pod.metadata.name,
                            "phase": pod.status.phase,
                            "container": cs.name,
                            "state": "waiting" if state.waiting else "terminated",
                            "reason": getattr(state.waiting or state.terminated, "reason", None),
                            "exit_code": getattr(state.terminated, "exit_code", None) if state.terminated else None,
                        })
        return pods
    return safe_api_call(inner)


@mcp.tool()
def get_nodes_with_problems() -> list[dict]:
    """List nodes that are not in Ready state."""
    def inner():
        bad_nodes = []
        for node in v1.list_node().items:
            for cond in node.status.conditions:
                if cond.type == "Ready" and cond.status != "True":
                    bad_nodes.append({
                        "name": node.metadata.name,
                        "condition": cond.type,
                        "status": cond.status,
                        "reason": cond.reason,
                        "message": cond.message
                    })
        return bad_nodes
    return safe_api_call(inner)


@mcp.tool()
def get_warning_events(input: NamespaceInput) -> list[dict]:
    """List warning events in a namespace.
    
    Args:
        input: NamespaceInput model with validated namespace parameter
    """
    def inner():
        events_list = []
        for e in v1.list_namespaced_event(input.namespace).items:
            if e.type == "Warning":
                events_list.append({
                    "name": e.metadata.name,
                    "object": e.involved_object.name,
                    "reason": e.reason,
                    "message": e.message,
                    "last_timestamp": str(e.last_timestamp)
                })
        return events_list
    return safe_api_call(inner)


# ---------------- Pod Diagnostics & Details ---------------- #

@mcp.tool()
def get_pod_logs(input: PodLogsInput) -> str:
    """Get recent logs from a specific pod. Essential for debugging application issues.
    
    Args:
        input: PodLogsInput model with pod_name, namespace, tail_lines, and optional container
    """
    def inner():
        kwargs = {
            "name": input.pod_name,
            "namespace": input.namespace,
            "tail_lines": input.tail_lines
        }
        if input.container:
            kwargs["container"] = input.container
        return v1.read_namespaced_pod_log(**kwargs)
    return safe_api_call(inner)


@mcp.tool()
def get_pod_details(input: PodNameInput) -> dict:
    """Get comprehensive details about a specific pod including status, resources, node placement, and container states.
    
    Args:
        input: PodNameInput model with pod_name and namespace
    """
    def inner():
        pod = v1.read_namespaced_pod(input.pod_name, input.namespace)
        containers_info = []
        if pod.status.container_statuses:
            for cs in pod.status.container_statuses:
                containers_info.append({
                    "name": cs.name,
                    "image": cs.image,
                    "ready": cs.ready,
                    "restart_count": cs.restart_count,
                    "state": str(cs.state)
                })
        
        return {
            "name": pod.metadata.name,
            "namespace": pod.metadata.namespace,
            "status": pod.status.phase,
            "node": pod.spec.node_name,
            "pod_ip": pod.status.pod_ip,
            "host_ip": pod.status.host_ip,
            "start_time": str(pod.status.start_time) if pod.status.start_time else None,
            "containers": containers_info,
            "conditions": [
                {"type": c.type, "status": c.status, "reason": c.reason, "message": c.message}
                for c in (pod.status.conditions or [])
            ],
            "labels": pod.metadata.labels or {}
        }
    return safe_api_call(inner)


@mcp.tool()
def get_pod_events(input: PodNameInput) -> list[dict]:
    """Get all events related to a specific pod. Useful for understanding pod lifecycle and issues.
    
    Args:
        input: PodNameInput model with pod_name and namespace
    """
    def inner():
        events = v1.list_namespaced_event(input.namespace)
        pod_events = [
            {
                "type": e.type,
                "reason": e.reason,
                "message": e.message,
                "count": e.count,
                "first_timestamp": str(e.first_timestamp),
                "last_timestamp": str(e.last_timestamp)
            }
            for e in events.items
            if e.involved_object.name == input.pod_name and e.involved_object.kind == "Pod"
        ]
        return sorted(pod_events, key=lambda x: x["last_timestamp"], reverse=True)
    return safe_api_call(inner)


# ---------------- Deployment Management ---------------- #

@mcp.tool()
def get_deployment_status(input: DeploymentNameInput) -> dict:
    """Get detailed status of a deployment including replica counts and rollout conditions.
    
    Args:
        input: DeploymentNameInput model with deployment_name and namespace
    """
    def inner():
        dep = apps_v1.read_namespaced_deployment(input.deployment_name, input.namespace)
        return {
            "name": dep.metadata.name,
            "namespace": input.namespace,
            "replicas_desired": dep.spec.replicas,
            "replicas_ready": dep.status.ready_replicas or 0,
            "replicas_updated": dep.status.updated_replicas or 0,
            "replicas_available": dep.status.available_replicas or 0,
            "replicas_unavailable": dep.status.unavailable_replicas or 0,
            "strategy": dep.spec.strategy.type,
            "conditions": [
                {"type": c.type, "status": c.status, "reason": c.reason, "message": c.message}
                for c in (dep.status.conditions or [])
            ],
            "image": dep.spec.template.spec.containers[0].image if dep.spec.template.spec.containers else None
        }
    return safe_api_call(inner)


@mcp.tool()
def scale_deployment(input: ScaleDeploymentInput) -> dict:
    """Scale a deployment to the specified number of replicas.
    
    Args:
        input: ScaleDeploymentInput model with deployment_name, namespace, and replicas
    """
    def inner():
        body = {"spec": {"replicas": input.replicas}}
        apps_v1.patch_namespaced_deployment_scale(
            name=input.deployment_name,
            namespace=input.namespace,
            body=body
        )
        return {
            "status": "success",
            "deployment": input.deployment_name,
            "namespace": input.namespace,
            "new_replicas": input.replicas
        }
    return safe_api_call(inner)


@mcp.tool()
def restart_deployment(input: DeploymentNameInput) -> dict:
    """Restart a deployment by triggering a rolling restart of all pods.
    
    Args:
        input: DeploymentNameInput model with deployment_name and namespace
    """
    def inner():
        body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "kubectl.kubernetes.io/restartedAt": datetime.utcnow().isoformat()
                        }
                    }
                }
            }
        }
        apps_v1.patch_namespaced_deployment(input.deployment_name, input.namespace, body)
        return {
            "status": "restart triggered",
            "deployment": input.deployment_name,
            "namespace": input.namespace,
            "timestamp": datetime.utcnow().isoformat()
        }
    return safe_api_call(inner)


# ---------------- Pod Operations ---------------- #

@mcp.tool()
def delete_pod(input: PodNameInput) -> dict:
    """Delete a specific pod. The pod will be recreated by its controller.
    
    Args:
        input: PodNameInput model with pod_name and namespace
    """
    def inner():
        v1.delete_namespaced_pod(input.pod_name, input.namespace)
        return {
            "status": "deleted",
            "pod": input.pod_name,
            "namespace": input.namespace,
            "note": "Pod will be recreated by its controller if part of a Deployment/StatefulSet"
        }
    return safe_api_call(inner)


# ---------------- Additional Resources ---------------- #

@mcp.tool()
def get_configmaps(input: NamespaceInput) -> list[str]:
    """List all ConfigMap names in a namespace.
    
    Args:
        input: NamespaceInput model with validated namespace parameter
    """
    return safe_api_call(
        lambda: [cm.metadata.name for cm in v1.list_namespaced_config_map(input.namespace).items]
    )


@mcp.tool()
def get_secrets(input: NamespaceInput) -> list[str]:
    """List all Secret names in a namespace. Note: Only returns names, not the secret values.
    
    Args:
        input: NamespaceInput model with validated namespace parameter
    """
    return safe_api_call(
        lambda: [s.metadata.name for s in v1.list_namespaced_secret(input.namespace).items]
    )


@mcp.tool()
def get_ingresses(input: NamespaceInput) -> list[dict]:
    """List all Ingress resources with their hosts and routing rules.
    
    Args:
        input: NamespaceInput model with validated namespace parameter
    """
    def inner():
        ingresses = networking_v1.list_namespaced_ingress(input.namespace)
        return [
            {
                "name": ing.metadata.name,
                "hosts": [rule.host for rule in (ing.spec.rules or []) if rule.host],
                "class": ing.spec.ingress_class_name,
                "tls": len(ing.spec.tls or []) > 0
            }
            for ing in ingresses.items
        ]
    return safe_api_call(inner)


@mcp.tool()
def get_persistent_volumes() -> list[dict]:
    """List all PersistentVolumes in the cluster with their capacity and status."""
    def inner():
        pvs = v1.list_persistent_volume()
        return [
            {
                "name": pv.metadata.name,
                "capacity": pv.spec.capacity.get('storage') if pv.spec.capacity else None,
                "status": pv.status.phase,
                "claim": f"{pv.spec.claim_ref.namespace}/{pv.spec.claim_ref.name}" if pv.spec.claim_ref else None,
                "storage_class": pv.spec.storage_class_name
            }
            for pv in pvs.items
        ]
    return safe_api_call(inner)


@mcp.tool()
def get_persistent_volume_claims(input: NamespaceInput) -> list[dict]:
    """List all PersistentVolumeClaims in a namespace with their status and capacity.
    
    Args:
        input: NamespaceInput model with validated namespace parameter
    """
    def inner():
        pvcs = v1.list_namespaced_persistent_volume_claim(input.namespace)
        return [
            {
                "name": pvc.metadata.name,
                "status": pvc.status.phase,
                "volume": pvc.spec.volume_name,
                "capacity": pvc.status.capacity.get('storage') if pvc.status.capacity else None,
                "storage_class": pvc.spec.storage_class_name
            }
            for pvc in pvcs.items
        ]
    return safe_api_call(inner)


# ---------------- Cluster Overview ---------------- #

@mcp.tool()
def get_cluster_info() -> dict:
    """Get overall cluster information including Kubernetes version, node counts, and health summary."""
    def inner():
        version_api = client.VersionApi()
        version = version_api.get_code()
        nodes = v1.list_node()
        
        ready_nodes = sum(
            1 for n in nodes.items 
            if any(c.type == "Ready" and c.status == "True" for c in n.status.conditions)
        )
        
        all_namespaces = v1.list_namespace()
        
        return {
            "kubernetes_version": version.git_version,
            "platform": version.platform,
            "nodes": {
                "total": len(nodes.items),
                "ready": ready_nodes,
                "not_ready": len(nodes.items) - ready_nodes
            },
            "namespaces_count": len(all_namespaces.items)
        }
    return safe_api_call(inner)


# ---------------- Create Resources ---------------- #

@mcp.tool()
def create_pod(input: CreatePodInput) -> dict:
    """Create a new pod with a single container.
    
    Args:
        input: CreatePodInput model with name, image, namespace, port, env_vars, and labels
    """
    def inner():
        container = client.V1Container(
            name=input.name,
            image=input.image,
            ports=[client.V1ContainerPort(container_port=input.port)] if input.port else None,
            env=[client.V1EnvVar(name=k, value=v) for k, v in (input.env_vars or {}).items()]
        )
        
        pod_spec = client.V1PodSpec(
            containers=[container],
            restart_policy="Always"
        )
        
        metadata = client.V1ObjectMeta(
            name=input.name,
            labels=input.labels or {"app": input.name}
        )
        
        pod = client.V1Pod(
            api_version="v1",
            kind="Pod",
            metadata=metadata,
            spec=pod_spec
        )
        
        result = v1.create_namespaced_pod(namespace=input.namespace, body=pod)
        
        return {
            "status": "created",
            "name": result.metadata.name,
            "namespace": result.metadata.namespace,
            "image": input.image,
            "uid": result.metadata.uid
        }
    
    return safe_api_call(inner)


@mcp.tool()
def create_deployment(input: CreateDeploymentInput) -> dict:
    """Create a new deployment with specified configuration.
    
    Args:
        input: CreateDeploymentInput model with all deployment parameters
    """
    def inner():
        labels = input.labels or {"app": input.name}
        
        container = client.V1Container(
            name=input.name,
            image=input.image,
            ports=[client.V1ContainerPort(container_port=input.port)] if input.port else None,
            env=[client.V1EnvVar(name=k, value=v) for k, v in (input.env_vars or {}).items()]
        )
        
        # Add resource requirements if specified
        if any([input.cpu_request, input.memory_request, input.cpu_limit, input.memory_limit]):
            requests = {}
            limits = {}
            
            if input.cpu_request:
                requests["cpu"] = input.cpu_request
            if input.memory_request:
                requests["memory"] = input.memory_request
            if input.cpu_limit:
                limits["cpu"] = input.cpu_limit
            if input.memory_limit:
                limits["memory"] = input.memory_limit
            
            container.resources = client.V1ResourceRequirements(
                requests=requests if requests else None,
                limits=limits if limits else None
            )
        
        pod_template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(labels=labels),
            spec=client.V1PodSpec(containers=[container])
        )
        
        deployment_spec = client.V1DeploymentSpec(
            replicas=input.replicas,
            selector=client.V1LabelSelector(match_labels=labels),
            template=pod_template
        )
        
        deployment = client.V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=client.V1ObjectMeta(name=input.name, namespace=input.namespace),
            spec=deployment_spec
        )
        
        result = apps_v1.create_namespaced_deployment(
            namespace=input.namespace,
            body=deployment
        )
        
        return {
            "status": "created",
            "name": result.metadata.name,
            "namespace": result.metadata.namespace,
            "replicas": input.replicas,
            "image": input.image,
            "uid": result.metadata.uid,
            "labels": labels
        }
    
    return safe_api_call(inner)


@mcp.tool()
def create_service(input: CreateServiceInput) -> dict:
    """Create a service to expose pods.
    
    Args:
        input: CreateServiceInput model with service configuration
    """
    def inner():
        selector = input.selector or {"app": input.name}
        
        service_port = client.V1ServicePort(
            port=input.port,
            target_port=input.target_port,
            protocol="TCP"
        )
        
        service_spec = client.V1ServiceSpec(
            selector=selector,
            ports=[service_port],
            type=input.service_type
        )
        
        service = client.V1Service(
            api_version="v1",
            kind="Service",
            metadata=client.V1ObjectMeta(name=input.name),
            spec=service_spec
        )
        
        result = v1.create_namespaced_service(
            namespace=input.namespace,
            body=service
        )
        
        return {
            "status": "created",
            "name": result.metadata.name,
            "namespace": result.metadata.namespace,
            "type": input.service_type,
            "port": input.port,
            "target_port": input.target_port,
            "cluster_ip": result.spec.cluster_ip,
            "selector": selector
        }
    
    return safe_api_call(inner)


@mcp.tool()
def delete_deployment(input: DeploymentNameInput) -> dict:
    """Delete a deployment and its associated pods.
    
    Args:
        input: DeploymentNameInput model with deployment_name and namespace
    """
    def inner():
        apps_v1.delete_namespaced_deployment(
            name=input.deployment_name,
            namespace=input.namespace,
            body=client.V1DeleteOptions(propagation_policy="Foreground")
        )
        return {
            "status": "deleted",
            "deployment": input.deployment_name,
            "namespace": input.namespace,
            "note": "All associated pods will be terminated"
        }
    
    return safe_api_call(inner)


@mcp.tool()
def delete_service(input: ServiceNameInput) -> dict:
    """Delete a service.
    
    Args:
        input: ServiceNameInput model with service_name and namespace
    """
    def inner():
        v1.delete_namespaced_service(
            name=input.service_name,
            namespace=input.namespace
        )
        return {
            "status": "deleted",
            "service": input.service_name,
            "namespace": input.namespace
        }
    
    return safe_api_call(inner)


# ---------------- Run MCP Server ---------------- #
if __name__ == "__main__":
    mcp.run_http(host="0.0.0.0", port=8080)