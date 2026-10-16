"""
LLM-powered attack scenario generator.

Uses LangChain with Azure OpenAI (primary) or OpenAI (fallback) to translate
natural-language attack descriptions into structured Modbus attack scenarios
mapped to MITRE ATT&CK for ICS.
"""

from __future__ import annotations

import json
import logging

from ot_twin.config import (
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_DEPLOYMENT,
    AZURE_OPENAI_ENDPOINT,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
)
from ot_twin.llm_generator.mitre_mapping import (
    get_technique,
    map_description_to_techniques,
)
from ot_twin.llm_generator.prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from ot_twin.models import AttackScenario, AttackStep, MitreTechnique, RegisterType

logger = logging.getLogger(__name__)


def _make_openrouter_llm(model: str) -> "ChatOpenRouter":
    """Instantiate a ChatOpenRouter for a given model name."""
    from langchain_openrouter import ChatOpenRouter
    return ChatOpenRouter(
        model_name=model,
        openrouter_api_key=OPENROUTER_API_KEY,
        temperature=0.3,
    )


# Known free models on OpenRouter (tried in order if auto fails).
# Models with :free suffix are always free; openrouter/auto picks the best available.
_FREE_MODELS = [
    "openrouter/auto",                              # OpenRouter auto-selects best free model
    "meta-llama/llama-3.1-8b-instruct:free",       # Meta Llama 3.1 8B (free tier)
    "meta-llama/llama-3.2-3b-instruct:free",       # Meta Llama 3.2 3B (free tier)
    "mistralai/mistral-7b-instruct:free",           # Mistral 7B (free tier)
    "google/gemma-3-12b-it:free",                  # Google Gemma 3 12B (free tier)
    "google/gemma-3-4b-it:free",                   # Google Gemma 3 4B (free tier)
    "deepseek/deepseek-r1:free",                   # DeepSeek R1 (free tier)
    "deepseek/deepseek-chat-v3-0324:free",         # DeepSeek Chat v3 (free tier)
    "qwen/qwen3-8b:free",                          # Qwen 3 8B (free tier)
    "qwen/qwen3-4b:free",                          # Qwen 3 4B (free tier)
    "microsoft/phi-3-mini-128k-instruct:free",     # Microsoft Phi-3 Mini (free tier)
]


def _get_llm():
    """Get the best available LLM.

    Priority:
      1. OpenRouter — auto-rotates through free models until one works
      2. Azure OpenAI
      3. OpenAI direct
    """
    # --- OpenRouter with free-model auto-rotation ---
    if OPENROUTER_API_KEY:
        try:
            from langchain_openrouter import ChatOpenRouter  # noqa: F401 – confirm importable
        except ImportError:
            logger.warning("langchain-openrouter not installed; skipping OpenRouter")
        else:
            # Build candidate model list: env-configured model first, then free list
            candidates = [OPENROUTER_MODEL] if OPENROUTER_MODEL else []
            for m in _FREE_MODELS:
                if m not in candidates:
                    candidates.append(m)

            for model in candidates:
                try:
                    llm = _make_openrouter_llm(model)
                    # Quick smoke-test: just instantiating is enough — actual errors
                    # surface during invoke(), so we return on first successful build.
                    logger.info("OpenRouter LLM ready: %s", model)
                    return llm
                except Exception as e:
                    logger.debug("OpenRouter model %s skipped: %s", model, e)

    # --- Azure OpenAI ---
    if AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT:
        try:
            from langchain_openai import AzureChatOpenAI
            return AzureChatOpenAI(
                azure_deployment=AZURE_OPENAI_DEPLOYMENT,
                azure_endpoint=AZURE_OPENAI_ENDPOINT,
                api_key=AZURE_OPENAI_API_KEY,
                api_version=AZURE_OPENAI_API_VERSION,
                temperature=0.3,
            )
        except Exception as e:
            logger.warning("Azure OpenAI init failed: %s", e)

    # --- OpenAI direct ---
    if OPENAI_API_KEY:
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=OPENAI_MODEL,
                api_key=OPENAI_API_KEY,
                temperature=0.3,
            )
        except Exception as e:
            logger.warning("OpenAI init failed: %s", e)

    return None



def _parse_scenario_json(raw: str, description: str) -> AttackScenario:
    """Parse LLM JSON output into an AttackScenario."""
    # Strip markdown fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines)

    data = json.loads(text)

    steps = []
    for s in data.get("steps", []):
        rt_str = s.get("register_type", "holding_register")
        try:
            rt = RegisterType(rt_str)
        except ValueError:
            rt = RegisterType.HOLDING

        steps.append(AttackStep(
            order=s.get("order", 0),
            description=s.get("description", ""),
            function_code=s.get("function_code", 3),
            register_type=rt,
            start_address=s.get("start_address", 0),
            values=s.get("values", []),
            count=s.get("count", 1),
            delay_seconds=s.get("delay_seconds", 0.0),
        ))

    # Resolve MITRE techniques
    technique_ids = data.get("mitre_techniques", [])
    techniques = []
    for tid in technique_ids:
        t = get_technique(tid)
        if t:
            techniques.append(t)

    # Fallback: keyword-based mapping
    if not techniques:
        techniques = map_description_to_techniques(description)

    detection = data.get("detection_indicators", [])

    return AttackScenario(
        name=data.get("name", "llm_generated"),
        description=data.get("description", description),
        objective=data.get("objective", ""),
        steps=steps,
        mitre_techniques=techniques,
        estimated_impact=data.get("estimated_impact", ""),
        detection_indicators=detection,
    )


def generate_scenario(description: str) -> AttackScenario:
    """Generate an attack scenario from a natural-language description.

    Tries each OpenRouter free model in turn on failure, then falls back
    to rule-based generation if all LLM attempts fail.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=USER_PROMPT_TEMPLATE.format(description=description)),
    ]

    # Build the full candidate list for OpenRouter
    if OPENROUTER_API_KEY:
        try:
            from langchain_openrouter import ChatOpenRouter  # noqa: F401
            candidates = [OPENROUTER_MODEL] if OPENROUTER_MODEL else []
            for m in _FREE_MODELS:
                if m not in candidates:
                    candidates.append(m)

            for model in candidates:
                try:
                    llm = _make_openrouter_llm(model)
                    logger.info("Trying OpenRouter model: %s", model)
                    response = llm.invoke(messages)
                    raw_text = response.content
                    logger.info("LLM response received (%d chars) via %s", len(raw_text), model)
                    return _parse_scenario_json(raw_text, description)
                except Exception as e:
                    logger.warning("Model %s failed (%s), trying next...", model, e)
        except ImportError:
            pass

    # Azure OpenAI fallback
    if AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT:
        try:
            from langchain_openai import AzureChatOpenAI
            llm = AzureChatOpenAI(
                azure_deployment=AZURE_OPENAI_DEPLOYMENT,
                azure_endpoint=AZURE_OPENAI_ENDPOINT,
                api_key=AZURE_OPENAI_API_KEY,
                api_version=AZURE_OPENAI_API_VERSION,
                temperature=0.3,
            )
            response = llm.invoke(messages)
            return _parse_scenario_json(response.content, description)
        except Exception as e:
            logger.warning("Azure OpenAI failed: %s", e)

    # OpenAI direct fallback
    if OPENAI_API_KEY:
        try:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(model=OPENAI_MODEL, api_key=OPENAI_API_KEY, temperature=0.3)
            response = llm.invoke(messages)
            return _parse_scenario_json(response.content, description)
        except Exception as e:
            logger.warning("OpenAI failed: %s", e)

    # Rule-based fallback — all LLMs exhausted
    logger.warning("All LLM providers failed — using rule-based generation")
    return _generate_rule_based(description)



def _generate_rule_based(description: str) -> AttackScenario:
    """Generate a scenario using keyword-based rules when no LLM is available."""
    desc_lower = description.lower()
    techniques = map_description_to_techniques(description)
    steps: list[AttackStep] = []
    order = 1

    # Recon step
    steps.append(AttackStep(
        order=order,
        description="Scan holding registers for current setpoints",
        function_code=3,
        register_type=RegisterType.HOLDING,
        start_address=0,
        count=11,
    ))
    order += 1

    # Determine attack actions from keywords
    if any(kw in desc_lower for kw in ["overflow", "flood", "tank", "level"]):
        # Tank overflow attack
        steps.append(AttackStep(
            order=order,
            description="Close outlet valve to prevent drainage",
            function_code=5,
            register_type=RegisterType.COIL,
            start_address=1,
            values=[0],
        ))
        order += 1
        steps.append(AttackStep(
            order=order,
            description="Maximize inflow rate setpoint",
            function_code=6,
            register_type=RegisterType.HOLDING,
            start_address=1,
            values=[100],
        ))
        order += 1
        steps.append(AttackStep(
            order=order,
            description="Raise high-level alarm threshold to hide overflow",
            function_code=6,
            register_type=RegisterType.HOLDING,
            start_address=9,
            values=[100],
            delay_seconds=1.0,
        ))
        order += 1

    elif any(kw in desc_lower for kw in ["ph", "chemical", "poison", "contaminate"]):
        steps.append(AttackStep(
            order=order,
            description="Disable chemical mixer",
            function_code=5,
            register_type=RegisterType.COIL,
            start_address=3,
            values=[0],
        ))
        order += 1
        steps.append(AttackStep(
            order=order,
            description="Set dangerous pH level",
            function_code=6,
            register_type=RegisterType.HOLDING,
            start_address=3,
            values=[200],
        ))
        order += 1
        steps.append(AttackStep(
            order=order,
            description="Overdose chlorine",
            function_code=6,
            register_type=RegisterType.HOLDING,
            start_address=4,
            values=[500],
            delay_seconds=0.5,
        ))
        order += 1

    elif any(kw in desc_lower for kw in ["pressure", "pipe", "burst", "explode"]):
        steps.append(AttackStep(
            order=order,
            description="Close outlet valve to build pressure",
            function_code=5,
            register_type=RegisterType.COIL,
            start_address=1,
            values=[0],
        ))
        order += 1
        steps.append(AttackStep(
            order=order,
            description="Maximize pump speed",
            function_code=6,
            register_type=RegisterType.HOLDING,
            start_address=8,
            values=[3600],
        ))
        order += 1
        steps.append(AttackStep(
            order=order,
            description="Raise pressure alarm threshold to hide danger",
            function_code=6,
            register_type=RegisterType.HOLDING,
            start_address=5,
            values=[100],
            delay_seconds=1.0,
        ))
        order += 1

    elif any(kw in desc_lower for kw in ["stop", "shutdown", "disable", "dos"]):
        steps.append(AttackStep(
            order=order,
            description="Activate emergency stop",
            function_code=5,
            register_type=RegisterType.COIL,
            start_address=5,
            values=[1],
        ))
        order += 1
        steps.append(AttackStep(
            order=order,
            description="Disable pump",
            function_code=5,
            register_type=RegisterType.COIL,
            start_address=2,
            values=[0],
        ))
        order += 1
        steps.append(AttackStep(
            order=order,
            description="Close all valves",
            function_code=5,
            register_type=RegisterType.COIL,
            start_address=0,
            values=[0],
            delay_seconds=0.5,
        ))
        order += 1

    else:
        # Generic attack — write dangerous values
        steps.append(AttackStep(
            order=order,
            description="Write malicious setpoint to tank level",
            function_code=6,
            register_type=RegisterType.HOLDING,
            start_address=0,
            values=[100],
        ))
        order += 1
        steps.append(AttackStep(
            order=order,
            description="Toggle pump coil",
            function_code=5,
            register_type=RegisterType.COIL,
            start_address=2,
            values=[0],
            delay_seconds=0.5,
        ))
        order += 1

    objective = f"Execute attack based on: {description}"
    impact = "Disruption of water treatment process operations"

    return AttackScenario(
        name="rule_based_scenario",
        description=description,
        objective=objective,
        steps=steps,
        mitre_techniques=techniques,
        estimated_impact=impact,
        detection_indicators=[
            "Multiple write operations in short time window",
            "Setpoint values outside normal operating range",
            "Unusual Modbus function code sequences",
        ],
    )
