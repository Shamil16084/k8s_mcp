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
