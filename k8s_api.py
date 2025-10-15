from kubernetes import client, config
from kubernetes.client.rest import ApiException


# ---------------- Initialization ---------------- #
try:
    config.load_kube_config()
except Exception as e:
    print({"error": f"Failed to load kubeconfig: {str(e)}"})
    exit(1)

v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()


# ---------------- Helper Functions ---------------- #

def safe_api_call(func, *args, **kwargs):
    """Wrapper to handle exceptions and return dicts"""
    try:
        return {"success": True, "result": func(*args, **kwargs)}
    except ApiException as e:
        return {"success": False, "error": f"ApiException: {e}"}
    except Exception as e:
        return {"success": False, "error": f"Exception: {e}"}


# ---------------- Kubernetes API Functions ---------------- #

def get_nodes():
    """List node names in the cluster"""
    return safe_api_call(lambda: [node.metadata.name for node in v1.list_node().items])


def get_namespaces():
    """List all namespaces"""
    return safe_api_call(lambda: [ns.metadata.name for ns in v1.list_namespace().items])


def get_pods(namespace="default"):
    """List pods in a given namespace"""
    return safe_api_call(lambda: [pod.metadata.name for pod in v1.list_namespaced_pod(namespace).items])


def get_deployments(namespace="default"):
    """List deployments in a given namespace"""
    return safe_api_call(lambda: [d.metadata.name for d in apps_v1.list_namespaced_deployment(namespace).items])


def get_services(namespace="default"):
    """List services in a given namespace"""
    return safe_api_call(lambda: [s.metadata.name for s in v1.list_namespaced_service(namespace).items])


def create_configmap(name, namespace="default", data=None):
    """Create a simple ConfigMap"""
    if data is None:
        data = {}
    cm = client.V1ConfigMap(
        metadata=client.V1ObjectMeta(name=name),
        data=data
    )
    return safe_api_call(lambda: v1.create_namespaced_config_map(namespace=namespace, body=cm))


def delete_configmap(name, namespace="default"):
    """Delete a ConfigMap"""
    return safe_api_call(lambda: v1.delete_namespaced_config_map(name=name, namespace=namespace))

def get_statefulsets(namespace="default"):
    return safe_api_call(lambda: [s.metadata.name for s in apps_v1.list_namespaced_stateful_set(namespace).items])


def get_replicasets(namespace="default"):
    return safe_api_call(lambda: [r.metadata.name for r in apps_v1.list_namespaced_replica_set(namespace).items])


def get_jobs(namespace="default"):
    batch_v1 = client.BatchV1Api()
    return safe_api_call(lambda: [j.metadata.name for j in batch_v1.list_namespaced_job(namespace).items])


def get_cronjobs(namespace="default"):
    batch_v1beta = client.BatchV1beta1Api()
    return safe_api_call(lambda: [c.metadata.name for c in batch_v1beta.list_namespaced_cron_job(namespace).items])


def get_events(namespace="default"):
    return safe_api_call(lambda: [e.message for e in v1.list_namespaced_event(namespace).items])

def get_pods_with_errors(namespace="default"):
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
            else:
                # Check container-level failures
                if pod.status.container_statuses:
                    for cs in pod.status.container_statuses:
                        state = cs.state
                        if state.waiting or (state.terminated and state.terminated.exit_code != 0):
                            pods.append({
                                "name": pod.metadata.name,
                                "phase": pod.status.phase,
                                "container": cs.name,
                                "state": "waiting" if state.waiting else "terminated",
                                "reason": getattr(state.waiting or state.terminated, "reason", None),
                                "exit_code": getattr(state.terminated, "exit_code", None),
                            })
        return pods

    return safe_api_call(inner)

def get_nodes_with_problems():
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

def get_warning_events(namespace="default"):
    def inner():
        events_list = []
        for e in v1.list_namespaced_event(namespace).items:
            if e.type == "Warning":
                events_list.append({
                    "name": e.metadata.name,
                    "object": e.involved_object.name,
                    "reason": e.reason,
                    "message": e.message,
                    "last_timestamp": e.last_timestamp
                })
        return events_list
    return safe_api_call(inner)




# ---------------- Command-Line Argument Example ---------------- #
# If you want to test it directly via CLI:
if __name__ == "__main__":
    import sys

    namespace = sys.argv[1] if len(sys.argv) > 1 else "default"

    print("=== Nodes ===")
    print(get_nodes())

    print(f"\n=== Namespaces ===")
    print(get_namespaces())

    print(f"\n=== Pods in namespace '{namespace}' ===")
    print(get_pods(namespace))

    print(f"\n=== Deployments in namespace '{namespace}' ===")
    print(get_deployments(namespace))

    print(f"\n=== Services in namespace '{namespace}' ===")
    print(get_services(namespace))

print(f"\n=== Pods with Errors in namespace '{namespace}' ===")
print(get_pods_with_errors(namespace))

print(f"\n=== Nodes with Problems ===")
print(get_nodes_with_problems())

print(f"\n=== Warning Events in namespace '{namespace}' ===")
print(get_warning_events(namespace))
