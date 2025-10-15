from mcp.server.fastmcp import FastMCP
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from datetime import datetime

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

# ---------------- Basic Resource Listing ---------------- #

@mcp.tool()
def get_nodes() -> list[str]:
    """Retrieves a comprehensive list of all **active node names** currently registered in the Kubernetes cluster. Use this tool when the 
    user asks about the **servers, machines, or worker components** of the cluster"""
    return safe_api_call(lambda: [node.metadata.name for node in v1.list_node().items])

@mcp.tool()
def get_namespaces() -> list[str]:
    """Retrieves a list of all **existing namespace names** within the Kubernetes cluster. Use this tool to get the available 
    scope or context when querying for resources like Pods or Deployments."""
    return safe_api_call(lambda: [ns.metadata.name for ns in v1.list_namespace().items])

@mcp.tool()
def get_pods(namespace: str = "default") -> list[str]:
    """List all pod names running in a specified Kubernetes namespace.

This tool connects to the active Kubernetes cluster and retrieves all pods within
the given namespace, returning their names as a list of strings. If no namespace
is provided, it defaults to the 'default' namespace."""
    return safe_api_call(lambda: [pod.metadata.name for pod in v1.list_namespaced_pod(namespace).items])

@mcp.tool()
def get_deployments(namespace: str = "default") -> list[str]:
    """List all deployment names within a specified Kubernetes namespace.

This tool connects to the active Kubernetes cluster and retrieves all deployments
present in the provided namespace, returning their names as a list of strings."""
    return safe_api_call(lambda: [d.metadata.name for d in apps_v1.list_namespaced_deployment(namespace).items])

@mcp.tool()
def get_services(namespace: str = "default") -> list[str]:
    """List all service names in a specified Kubernetes namespace.

This tool queries the active Kubernetes cluster and retrieves all services
running within the given namespace, returning their names as a list of strings."""
    return safe_api_call(lambda: [s.metadata.name for s in v1.list_namespaced_service(namespace).items])

# ---------------- Error Detection ---------------- #

@mcp.tool()
def get_pods_with_errors(namespace: str = "default") -> list[dict]:
    """List pods with errors or non-running states."""
    def inner():
        pods = []
        for pod in v1.list_namespaced_pod(namespace).items:
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
def get_warning_events(namespace: str = "default") -> list[dict]:
    """List warning events in a namespace."""
    def inner():
        events_list = []
        for e in v1.list_namespaced_event(namespace).items:
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
def get_pod_logs(pod_name: str, namespace: str = "default", tail_lines: int = 50, container: str = None) -> str:
    """Get recent logs from a specific pod. Essential for debugging application issues.
    
    Args:
        pod_name: Name of the pod
        namespace: Kubernetes namespace (default: 'default')
        tail_lines: Number of recent log lines to retrieve (default: 50)
        container: Specific container name (optional, for multi-container pods)
    """
    def inner():
        kwargs = {
            "name": pod_name,
            "namespace": namespace,
            "tail_lines": tail_lines
        }
        if container:
            kwargs["container"] = container
        return v1.read_namespaced_pod_log(**kwargs)
    return safe_api_call(inner)

@mcp.tool()
def get_pod_details(pod_name: str, namespace: str = "default") -> dict:
    """Get comprehensive details about a specific pod including status, resources, node placement, and container states."""
    def inner():
        pod = v1.read_namespaced_pod(pod_name, namespace)
        containers_info = []
        if pod.status.container_statuses:
            for cs in pod.status.container_statuses:
                container_spec = next((c for c in pod.spec.containers if c.name == cs.name), None)
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
def get_pod_events(pod_name: str, namespace: str = "default") -> list[dict]:
    """Get all events related to a specific pod. Useful for understanding pod lifecycle and issues."""
    def inner():
        events = v1.list_namespaced_event(namespace)
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
            if e.involved_object.name == pod_name and e.involved_object.kind == "Pod"
        ]
        return sorted(pod_events, key=lambda x: x["last_timestamp"], reverse=True)
    return safe_api_call(inner)

# ---------------- Deployment Management ---------------- #

@mcp.tool()
def get_deployment_status(deployment_name: str, namespace: str = "default") -> dict:
    """Get detailed status of a deployment including replica counts and rollout conditions."""
    def inner():
        dep = apps_v1.read_namespaced_deployment(deployment_name, namespace)
        return {
            "name": dep.metadata.name,
            "namespace": namespace,
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
def scale_deployment(deployment_name: str, replicas: int, namespace: str = "default") -> dict:
    """Scale a deployment to the specified number of replicas. Use this to increase or decrease pod count."""
    def inner():
        body = {"spec": {"replicas": replicas}}
        apps_v1.patch_namespaced_deployment_scale(
            name=deployment_name,
            namespace=namespace,
            body=body
        )
        return {
            "status": "success",
            "deployment": deployment_name,
            "namespace": namespace,
            "new_replicas": replicas
        }
    return safe_api_call(inner)

@mcp.tool()
def restart_deployment(deployment_name: str, namespace: str = "default") -> dict:
    """Restart a deployment by triggering a rolling restart of all pods. Useful for applying config changes or fixing stuck pods."""
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
        apps_v1.patch_namespaced_deployment(deployment_name, namespace, body)
        return {
            "status": "restart triggered",
            "deployment": deployment_name,
            "namespace": namespace,
            "timestamp": datetime.utcnow().isoformat()
        }
    return safe_api_call(inner)

# ---------------- Pod Operations ---------------- #

@mcp.tool()
def delete_pod(pod_name: str, namespace: str = "default") -> dict:
    """Delete a specific pod. The pod will be recreated by its controller (Deployment, StatefulSet, etc.). Useful for forcing restart of a problematic pod."""
    def inner():
        v1.delete_namespaced_pod(pod_name, namespace)
        return {
            "status": "deleted",
            "pod": pod_name,
            "namespace": namespace,
            "note": "Pod will be recreated by its controller if part of a Deployment/StatefulSet"
        }
    return safe_api_call(inner)

# ---------------- Additional Resources ---------------- #

@mcp.tool()
def get_configmaps(namespace: str = "default") -> list[str]:
    """List all ConfigMap names in a namespace. ConfigMaps store configuration data as key-value pairs."""
    return safe_api_call(lambda: [cm.metadata.name for cm in v1.list_namespaced_config_map(namespace).items])

@mcp.tool()
def get_secrets(namespace: str = "default") -> list[str]:
    """List all Secret names in a namespace. Note: Only returns names, not the secret values (for security)."""
    return safe_api_call(lambda: [s.metadata.name for s in v1.list_namespaced_secret(namespace).items])

@mcp.tool()
def get_ingresses(namespace: str = "default") -> list[dict]:
    """List all Ingress resources with their hosts and routing rules. Ingresses expose HTTP/HTTPS routes to services."""
    def inner():
        ingresses = networking_v1.list_namespaced_ingress(namespace)
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
def get_persistent_volume_claims(namespace: str = "default") -> list[dict]:
    """List all PersistentVolumeClaims in a namespace with their status and capacity."""
    def inner():
        pvcs = v1.list_namespaced_persistent_volume_claim(namespace)
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
def create_pod(
    name: str,
    image: str,
    namespace: str = "default",
    port: int = None,
    env_vars: dict = None,
    labels: dict = None
) -> dict:
    """Create a new pod with a single container.
    
    Args:
        name: Name of the pod
        image: Container image (e.g., 'nginx:latest', 'redis:alpine')
        namespace: Kubernetes namespace (default: 'default')
        port: Container port to expose (optional)
        env_vars: Environment variables as dict (optional, e.g., {"KEY": "value"})
        labels: Pod labels as dict (optional, e.g., {"app": "myapp"})
    
    Returns:
        Dict with creation status and pod details
    """
    def inner():
        # Build container spec
        container = client.V1Container(
            name=name,
            image=image,
            ports=[client.V1ContainerPort(container_port=port)] if port else None,
            env=[client.V1EnvVar(name=k, value=v) for k, v in (env_vars or {}).items()]
        )
        
        # Build pod spec
        pod_spec = client.V1PodSpec(
            containers=[container],
            restart_policy="Always"
        )
        
        # Build pod metadata
        metadata = client.V1ObjectMeta(
            name=name,
            labels=labels or {"app": name}
        )
        
        # Create pod object
        pod = client.V1Pod(
            api_version="v1",
            kind="Pod",
            metadata=metadata,
            spec=pod_spec
        )
        
        # Create the pod
        result = v1.create_namespaced_pod(namespace=namespace, body=pod)
        
        return {
            "status": "created",
            "name": result.metadata.name,
            "namespace": result.metadata.namespace,
            "image": image,
            "uid": result.metadata.uid
        }
    
    return safe_api_call(inner)



@mcp.tool()
def create_deployment(
    name: str,
    image: str,
    replicas: int = 1,
    namespace: str = "default",
    port: int = None,
    env_vars: dict = None,
    labels: dict = None,
    cpu_request: str = None,
    memory_request: str = None,
    cpu_limit: str = None,
    memory_limit: str = None
) -> dict:
    """Create a new deployment with specified configuration.
    
    # ... (Docstring omitted for brevity)
    """
    def inner():
        # 🚨 FIX: Declare 'labels' as nonlocal to refer to the argument in the outer scope
        nonlocal labels 
        
        # Default labels
        if labels is None:
            labels = {"app": name} # This line now modifies the outer 'labels' argument
        
        # Build container spec
        container = client.V1Container(
            name=name,
            image=image,
            ports=[client.V1ContainerPort(container_port=port)] if port else None,
            env=[client.V1EnvVar(name=k, value=v) for k, v in (env_vars or {}).items()]
        )
        
        # Add resource requirements if specified
        if any([cpu_request, memory_request, cpu_limit, memory_limit]):
            requests = {}
            limits = {}
            
            if cpu_request:
                requests["cpu"] = cpu_request
            if memory_request:
                requests["memory"] = memory_request
            if cpu_limit:
                limits["cpu"] = cpu_limit
            if memory_limit:
                limits["memory"] = memory_limit
            
            container.resources = client.V1ResourceRequirements(
                requests=requests if requests else None,
                limits=limits if limits else None
            )
        
        # Build pod template
        pod_template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(labels=labels),
            spec=client.V1PodSpec(containers=[container])
        )
        
        # Build deployment spec
        deployment_spec = client.V1DeploymentSpec(
            replicas=replicas,
            selector=client.V1LabelSelector(match_labels=labels),
            template=pod_template
        )
        
        # Build deployment object (using the minor suggestion from the previous review)
        deployment = client.V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=client.V1ObjectMeta(name=name, namespace=namespace), # Removed 'labels' from deployment metadata
            spec=deployment_spec
        )
        
        # Create the deployment
        result = apps_v1.create_namespaced_deployment(
            namespace=namespace,
            body=deployment
        )
        
        return {
            "status": "created",
            "name": result.metadata.name,
            "namespace": result.metadata.namespace,
            "replicas": replicas,
            "image": image,
            "uid": result.metadata.uid,
            "labels": labels
        }
    
    return safe_api_call(inner)


@mcp.tool()
def create_service(
    name: str,
    port: int,
    target_port: int,
    namespace: str = "default",
    selector: dict = None,
    service_type: str = "ClusterIP"
) -> dict:
    """Create a service to expose pods.
    
    Args:
        name: Name of the service
        port: Service port (external)
        target_port: Target pod port (internal)
        namespace: Kubernetes namespace (default: 'default')
        selector: Label selector to match pods (e.g., {"app": "web"})
        service_type: Service type - ClusterIP, NodePort, or LoadBalancer (default: 'ClusterIP')
    
    Returns:
        Dict with creation status and service details
    """
    def inner():
        if selector is None:
            selector = {"app": name}
        
        # Build service port
        service_port = client.V1ServicePort(
            port=port,
            target_port=target_port,
            protocol="TCP"
        )
        
        # Build service spec
        service_spec = client.V1ServiceSpec(
            selector=selector,
            ports=[service_port],
            type=service_type
        )
        
        # Build service object
        service = client.V1Service(
            api_version="v1",
            kind="Service",
            metadata=client.V1ObjectMeta(name=name),
            spec=service_spec
        )
        
        # Create the service
        result = v1.create_namespaced_service(
            namespace=namespace,
            body=service
        )
        
        return {
            "status": "created",
            "name": result.metadata.name,
            "namespace": result.metadata.namespace,
            "type": service_type,
            "port": port,
            "target_port": target_port,
            "cluster_ip": result.spec.cluster_ip,
            "selector": selector
        }
    
    return safe_api_call(inner)


@mcp.tool()
def delete_deployment(deployment_name: str, namespace: str = "default") -> dict:
    """Delete a deployment and its associated pods.
    
    Args:
        deployment_name: Name of the deployment to delete
        namespace: Kubernetes namespace (default: 'default')
    
    Returns:
        Dict with deletion status
    """
    def inner():
        apps_v1.delete_namespaced_deployment(
            name=deployment_name,
            namespace=namespace,
            body=client.V1DeleteOptions(propagation_policy="Foreground")
        )
        return {
            "status": "deleted",
            "deployment": deployment_name,
            "namespace": namespace,
            "note": "All associated pods will be terminated"
        }
    
    return safe_api_call(inner)


@mcp.tool()
def delete_service(service_name: str, namespace: str = "default") -> dict:
    """Delete a service.
    
    Args:
        service_name: Name of the service to delete
        namespace: Kubernetes namespace (default: 'default')
    
    Returns:
        Dict with deletion status
    """
    def inner():
        v1.delete_namespaced_service(
            name=service_name,
            namespace=namespace
        )
        return {
            "status": "deleted",
            "service": service_name,
            "namespace": namespace
        }
    
    return safe_api_call(inner)

# ---------------- Run MCP Server ---------------- #
if __name__ == "__main__":
    mcp.run_http(host="0.0.0.0", port=8080)