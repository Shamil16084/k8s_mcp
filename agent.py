# agent.py
import requests
import re
import json
import logging
import argparse

LLM_URL = "http://10.150.249.12:8080/v1/chat/completions"
MCP_URL = "http://localhost:8080"

# --- Logging Setup ---
logger = logging.getLogger("agent")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%H:%M:%S")
handler.setFormatter(formatter)
logger.addHandler(handler)

# --- Helpers ---

def get_tools():
    try:
        r = requests.get(f"{MCP_URL}/tools")
        r.raise_for_status()
        tools = r.json().get("tools", [])
        logger.debug(f"Fetched tools: {tools}")
        return tools
    except Exception as e:
        logger.error(f"❌ Failed to fetch tools: {e}")
        return []

def ask_llm(prompt: str) -> str:
    logger.debug(f"Sending prompt to LLM:\n{prompt}")
    try:
        r = requests.post(LLM_URL, json={
            "model": "gpt-3.5-turbo",  # or whatever model is supported
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
            "stream": False
        }, timeout=60)

        r.raise_for_status()

        response = r.json()["choices"][0]["message"]["content"].strip()
        logger.debug(f"LLM response: {response}")
        return response
    except Exception as e:
        logger.error(f"❌ Failed to contact LLM: {e}")
        return ""


def call_tool(endpoint: str, payload: dict = None):
    """
    POST JSON payload (or empty body) to the tool endpoint.
    """
    url = f"{MCP_URL}{endpoint}"
    logger.debug(f"Calling tool at {url} with payload={payload}")
    try:
        if payload is None:
            r = requests.post(url, timeout=10)
        else:
            r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        result = r.json()
        logger.debug(f"Tool response: {result}")
        return result
    except Exception as e:
        logger.error(f"Tool call failed: {e}")
        return {"error": str(e)}

def parse_tool_call(response: str):
    """
    Returns (tool_name, args_list) if a tool call found, else (None, None).
    """
    if not response:
        return None, None

    # find tool name
    m = re.search(r"call_tool:([A-Za-z0-9_]+)", response)
    if not m:
        return None, None
    tool_name = m.group(1)
    logger.debug(f"Detected tool call: {tool_name}")

    # 1) JSON-list style
    list_match = re.search(r"with arguments:\s*(\[[^\]]*\])", response, re.IGNORECASE)
    if list_match:
        try:
            args = json.loads(list_match.group(1))
            logger.debug(f"Parsed tool args (list style): {args}")
            return tool_name, args
        except Exception as e:
            logger.debug(f"Failed to parse list args: {e}")

    # 2) Parentheses style
    paren_match = re.search(r"call_tool:[A-Za-z0-9_]+\s*\(([^)]*)\)", response)
    if paren_match:
        raw = paren_match.group(1).strip()
        if raw:
            parts = [p.strip() for p in raw.split(",") if p.strip() != ""]
            args = []
            for p in parts:
                try:
                    if "." in p:
                        args.append(float(p))
                    else:
                        args.append(int(p))
                except Exception:
                    args.append(p.strip("\"' "))
            logger.debug(f"Parsed tool args (paren style): {args}")
            return tool_name, args

    # 3) JSON object style
    json_obj_match = re.search(r"(\{.*\"args\".*\})", response, re.DOTALL)
    if json_obj_match:
        raw = json_obj_match.group(1)
        try:
            obj = json.loads(raw)
            args = obj.get("args")
            if isinstance(args, list):
                logger.debug(f"Parsed tool args (json object style): {args}")
                return tool_name, args
        except Exception:
            pass

    # 4) Fallback: numbers in text
    numbers = re.findall(r"-?\d+\.?\d*", response)
    if len(numbers) >= 2:
        parsed = []
        for n in numbers:
            parsed.append(float(n) if "." in n else int(n))
        logger.debug(f"Parsed tool args (fallback numbers): {parsed}")
        return tool_name, parsed

    return tool_name, []

# --- Main loop ---

def main(debug_mode=False):
    if debug_mode:
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug mode activated ✅")
    else:
        logger.setLevel(logging.INFO)

    logger.info("🧠 Universal MCP Agent Started")

    tools = get_tools()
    if not tools:
        logger.warning("⚠️ No tools found on MCP server.")
    else:
        logger.info(f"✅ Found {len(tools)} tool(s):")
        for t in tools:
            logger.info(f" - {t['name']}: {t['description']}")

    def build_prompt(user_input):
        tools_text = "\n".join([f"- {t['name']}: {t['description']}" for t in tools])
        prompt = f"""
You are an assistant with access to the following tools:
{tools_text}

Rules:
- If the user's question clearly requires using a tool, respond EXACTLY with one of:
  call_tool:<tool_name>
  call_tool:<tool_name> with arguments: [arg1, arg2, ...]
  or call_tool:<tool_name>(arg1, arg2)
- If the user's question is general conversation, greetings, or does NOT require a tool, answer normally.
Examples:
Q: What time is it?
A: call_tool:get_current_time

Q: Add 3 and 5.
A: call_tool:add_numbers with arguments: [3, 5]

In other cases,when the tool describtion does not match with the user input, answer normally!

User asked: {user_input}
"""
        logger.debug(f"Built prompt:\n{prompt}")
        return prompt

    while True:
        user_input = input("\nYou: ")
        if user_input.lower() in ["exit", "quit"]:
            logger.info("Exiting agent...")
            break

        prompt = build_prompt(user_input)
        # llm_response = ask_ollama(prompt)
        llm_response = ask_llm(prompt)

        logger.info(f"LLM Response: {llm_response}")

        if llm_response and "call_tool:" in llm_response:
            tool_name, args = parse_tool_call(llm_response)
            if not tool_name:
                logger.warning("⚠️ Could not parse tool name from LLM response.")
                print(f"Assistant: {llm_response}")
                continue

            match = next((t for t in tools if t["name"] == tool_name), None)
            if not match:
                logger.warning(f"⚠️ Tool '{tool_name}' not found.")
                continue

            payload = None
            if args:
                payload = {"args": args}
                if len(args) >= 2:
                    payload["a"] = args[0]
                    payload["b"] = args[1]

            result = call_tool(match["endpoint"], payload=payload)
            print(f"Tool result: {result}")
        else:
            print(f"Assistant: {llm_response}")

# --- Entry point ---
if __name__ == "__main__":

    test_prompt = "Say hello"
    print("🔧 Testing LLM connection...")
    print("Prompt:", test_prompt)
    print("Response:", ask_llm(test_prompt))
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()
    main(debug_mode=args.debug)
