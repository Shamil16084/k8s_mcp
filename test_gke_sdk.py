from kubernetes import client, config

# Load kubeconfig
config.load_kube_config()

v1 = client.CoreV1Api()
print("=== Nodes ===")
for node in v1.list_node().items:
    print(node.metadata.name)
