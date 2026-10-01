#!/usr/bin/env python3
"""
aiKart Sandbox Runner for BoloAI
Runtime contract:
- Reads input JSON from AIKART_INPUT environment variable or /aikart/input.json
- Runs query through BoloAI Master Agent / orchestrator
- Writes output to /aikart/output.json with shape:
    {
      "format": "markdown",
      "response": "<answer>"
    }
- Exits 0 on success
"""

import json
import logging
import os
import sys

# Configure minimal logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("aikart-runner")


def load_input() -> dict:
    # 1. Check AIKART_INPUT environment variable
    raw_env = os.environ.get("AIKART_INPUT")
    if raw_env and raw_env.strip():
        try:
            return json.loads(raw_env)
        except Exception as exc:
            logger.warning(f"Failed to parse AIKART_INPUT env var: {exc}")

    # 2. Check /aikart/input.json and local fallbacks
    candidate_paths = [
        "/aikart/input.json",
        os.path.join(os.getcwd(), "aikart", "input.json"),
        os.path.join(os.path.dirname(__file__), "aikart", "input.json"),
    ]

    for p in candidate_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as exc:
                logger.warning(f"Failed reading input from {p}: {exc}")

    # Default fallback input if nothing supplied
    return {
        "query": "BoloAI se kya kya services milti hain?",
        "language": "Hinglish",
    }


def write_output(payload: dict):
    out_json = json.dumps(payload, indent=2, ensure_ascii=False)
    
    # Primary target required by aiKart specification
    targets = ["/aikart/output.json"]
    # Add local fallback target for testing outside root
    local_target = os.path.join(os.getcwd(), "aikart", "output.json")
    if local_target not in targets:
        targets.append(local_target)

    written = False
    for target in targets:
        try:
            parent = os.path.dirname(target)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(out_json)
            written = True
            logger.info(f"Successfully wrote output to {target}")
        except Exception as exc:
            logger.debug(f"Could not write to {target}: {exc}")

    if not written:
        # Final stdout fallback
        print(out_json)


def main():
    try:
        data = load_input()
        query = data.get("query", "").strip() or "Namaste"
        language = data.get("language", "Hinglish")

        # Map language to BoloAI internal locale
        lang_code = "hi-IN"
        if language and language.lower() in ("english", "en"):
            lang_code = "en-IN"

        # Import BoloAI components
        from app.store import create_session
        from app.agent.orchestrator import AgentOrchestrator

        # Create isolated session for this one-shot run
        session = create_session(caller="+919876543210", language=lang_code)

        # Process through BoloAI Master Agent
        result = AgentOrchestrator.respond(session.id, query)
        answer = result.get("answer") or "BoloAI: Jankari uplabdh nahi ho paayi."

        # Produce required aiKart response structure
        output_payload = {
            "format": "markdown",
            "response": answer,
        }

        write_output(output_payload)
        logger.info("aiKart one-shot execution completed successfully.")
        sys.exit(0)

    except Exception as exc:
        logger.exception("Error during aiKart execution")
        # Ensure contract compliance even on unexpected error
        fallback_payload = {
            "format": "markdown",
            "response": f"BoloAI safe fallback: Seva mein takneeki dikkat hai. Kripya baad mein prayas karein. ({str(exc)})",
        }
        write_output(fallback_payload)
        sys.exit(0)


if __name__ == "__main__":
    main()
