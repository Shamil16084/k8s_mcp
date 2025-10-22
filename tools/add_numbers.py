# tools/add_numbers.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

name = "add_numbers"
description = "Adds two numbers together."
endpoint = "/tools/add_numbers"

def register(app: FastAPI):
    @app.post(endpoint)
    async def add_numbers(request: Request):
        """
        Accepts JSON body with either:
        - {"args": [3, 5]}
        - {"a": 3, "b": 5}
        - or no body (returns error)

        Returns {"result": <sum>}
        """
        try:
            data = await request.json()
        except Exception:
            data = {}

        # support multiple input styles
        args = data.get("args")
        a = data.get("a")
        b = data.get("b")

        if args and isinstance(args, (list, tuple)) and len(args) >= 2:
            try:
                x = float(args[0])
                y = float(args[1])
                return JSONResponse({"result": x + y})
            except Exception as e:
                return JSONResponse({"error": "Arguments must be numbers"}, status_code=400)

        if a is not None and b is not None:
            try:
                x = float(a)
                y = float(b)
                return JSONResponse({"result": x + y})
            except Exception:
                return JSONResponse({"error": "'a' and 'b' must be numbers"}, status_code=400)

        return JSONResponse({"error": "Provide either 'args':[a,b] or 'a' and 'b' in JSON body"}, status_code=400)
