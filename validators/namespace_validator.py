# validators/namespace_validator.py

from functools import lru_cache
from kubernetes.client.rest import ApiException
from utils.k8s_config import load_k8s_clients

# Load CoreV1 client
core_v1, _, _ = load_k8s_clients()

@lru_cache(maxsize=1)
def get_cluster_namespaces() -> set:
    try:
        namespaces = core_v1.list_namespace()
        return {ns.metadata.name for ns in namespaces.items}
    except ApiException as e:
        raise RuntimeError(f"Failed to list namespaces: {e.reason}")
    except Exception as e:
        raise RuntimeError(f"Unexpected error while listing namespaces: {str(e)}")

def validate_namespace_exists(namespace: str) -> str:
    namespace = namespace.strip()
    if not namespace:
        raise ValueError("Namespace cannot be empty.")

    valid_namespaces = get_cluster_namespaces()
    if namespace not in valid_namespaces:
        raise ValueError(
            f"Namespace '{namespace}' does not exist. "
            f"Available: {', '.join(sorted(valid_namespaces))}"
        )
    return namespace
