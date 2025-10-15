from kubernetes import client, config

# Load your kubeconfig
config.load_kube_config()

# Create CoreV1Api client
v1 = client.CoreV1Api()   # <-- must be here

# List all pods in all namespaces
for pod in v1.list_pod_for_all_namespaces().items:
    print(f"{pod.metadata.namespace}/{pod.metadata.name}")
