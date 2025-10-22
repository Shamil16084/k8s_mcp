# tools/list_pods.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# Load Kubernetes config inside the tool (can handle exceptions here)
try:
    config.load_kube_config()
except Exception:
    config.load_incluster_config()

v1 = client.CoreV1Api()

# Input model
class NamespaceInput(BaseModel):
    namespace: str = Field(..., min_length=1, max_length=253, description="Namespace name")

# Tool router
router = APIRouter()

@router.post("/")
async def list_pods(input: NamespaceInput):
    try:
        pods = v1.list_namespaced_pod(input.namespace)
        pod_names = [pod.metadata.name for pod in pods.items]
        return {"pods": pod_names}
    except ApiException as e:
        raise HTTPException(status_code=e.status, detail=e.reason)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Register function for main server to call
def register(app):
    app.include_router(router, prefix="/tools/list_pods")
