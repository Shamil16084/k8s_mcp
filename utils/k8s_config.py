# utils/k8s_config.py

from kubernetes import config, client
from kubernetes.config.config_exception import ConfigException

def load_k8s_clients():
    """
    Load Kubernetes configuration and return client objects for:
    - CoreV1Api
    - AppsV1Api
    - NetworkingV1Api
    """
    try:
        config.load_kube_config()
    except ConfigException:
        config.load_incluster_config()

    core_v1 = client.CoreV1Api()
    apps_v1 = client.AppsV1Api()
    net_v1 = client.NetworkingV1Api()

    return core_v1, apps_v1, net_v1
