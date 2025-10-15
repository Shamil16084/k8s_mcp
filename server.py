# server.py
from fastapi import FastAPI
import importlib
import os
import uvicorn

app = FastAPI()
loaded_tools = []


def load_tools():
    """
    Dynamically loads all Python modules from the 'tools' folder.
    Each tool module must define a 'register(app)' function.
    """
    tools_folder = os.path.join(os.path.dirname(__file__), "tools")

    # Create the folder if it doesn't exist
    if not os.path.exists(tools_folder):
        os.makedirs(tools_folder)

    for filename in os.listdir(tools_folder):
        if filename.endswith(".py") and filename != "__init__.py":
            module_name = f"tools.{filename[:-3]}"

            try:
                module = importlib.import_module(module_name)

                # Register the tool's FastAPI endpoint
                if hasattr(module, "register"):
                    module.register(app)
                    loaded_tools.append({
                        "name": getattr(module, "name", filename[:-3]),
                        "description": getattr(module, "description", ""),
                        "endpoint": getattr(module, "endpoint", f"/tools/{filename[:-3]}")
                    })
                    print(f"✅ Loaded tool: {module_name}")
                else:
                    print(f"⚠️  Module '{module_name}' has no register(app) function")

            except Exception as e:
                print(f"❌ Failed to load tool '{module_name}': {e}")


@app.get("/tools")
def get_tools():
    """
    Returns the list of all loaded tools (name, description, endpoint)
    """
    return {"tools": loaded_tools}


if __name__ == "__main__":
    load_tools()
    uvicorn.run(app, host="0.0.0.0", port=8080)
