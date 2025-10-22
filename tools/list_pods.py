# tools/list_pods.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from kubernetes.client.rest import ApiException

from utils.k8s_config import load_k8s_clients
from validators.namespace_validator import validate_namespace_exists

# Load Kubernetes CoreV1 client
core_v1, _, _ = load_k8s_clients()

# Metadata for LLM
name = "list_pods"
description = "Lists all pod names in the given Kubernetes namespace."
endpoint = "/tools/list_pods"

# Create a FastAPI router
router = APIRouter()

# Input model
class NamespaceInput(BaseModel):
    namespace: str = Field(
        ...,
        min_length=1,
        max_length=253,
        description="Kubernetes namespace to list pods from."
    )

# API Endpoint
@router.post("/", summary=description)
async def list_pods(input: NamespaceInput):
    """
    Returns the list of pod names in the specified namespace.
    """
    try:
        validate_namespace_exists(input.namespace)
        pods = core_v1.list_namespaced_pod(input.namespace)
        pod_names = [pod.metadata.name for pod in pods.items]
        return {"namespace": input.namespace, "pods": pod_names}
    except ApiException as e:
        raise HTTPException(status_code=e.status, detail=e.reason)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Register function to be picked up by server.py
def register(app):
    app.include_router(router, prefix=endpoint)
