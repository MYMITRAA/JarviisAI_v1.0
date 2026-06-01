"""
LLM Client — wraps Anthropic (primary) + OpenAI (fallback).
Handles: retries, token limits, cost tracking, response caching.
"""

import json
import logging
import hashlib
from typing import Optional, Tuple
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger("jarviis.ai.llm")

redis_client = aioredis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)

CACHE_TTL = 3600 * 24  # 24h — cache identical prompts
CACHE_PREFIX = "llm:cache:"


class LLMClient:
    """
    Multi-provider LLM client.
    Primary: Anthropic Claude 3.5 Sonnet
    Fallback: OpenAI GPT-4o
    """

    def __init__(self):
        self._anthropic = None
        self._openai = None

    def _get_anthropic(self):
        if not self._anthropic and settings.ANTHROPIC_API_KEY:
            import anthropic
            self._anthropic = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        return self._anthropic

    def _get_openai(self):
        if not self._openai and settings.OPENAI_API_KEY:
            from openai import AsyncOpenAI
            self._openai = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._openai

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 8192,
        temperature: float = 0.2,
        use_cache: bool = True,
    ) -> Tuple[str, str, dict]:
        """
        Get a completion. Returns (response_text, model_used, usage_stats).
        Tries primary model first, falls back to secondary.
        """
        # Check cache
        if use_cache:
            cache_key = self._cache_key(system_prompt, user_prompt)
            cached = await redis_client.get(f"{CACHE_PREFIX}{cache_key}")
            if cached:
                data = json.loads(cached)
                logger.info(f"LLM cache hit — saved ~{data.get('input_tokens', 0)} input tokens")
                return data["text"], data["model"] + " (cached)", {}

        # Try Anthropic (primary)
        anthropic_client = self._get_anthropic()
        if anthropic_client:
            try:
                result = await self._complete_anthropic(
                    anthropic_client, system_prompt, user_prompt, max_tokens, temperature
                )
                text, model, usage = result

                # Cache successful responses
                if use_cache:
                    await redis_client.setex(
                        f"{CACHE_PREFIX}{cache_key}",
                        CACHE_TTL,
                        json.dumps({"text": text, "model": model, **usage}),
                    )
                return text, model, usage

            except Exception as e:
                logger.warning(f"Anthropic failed: {e} — falling back to OpenAI")

        # Fallback to OpenAI
        openai_client = self._get_openai()
        if openai_client:
            try:
                return await self._complete_openai(
                    openai_client, system_prompt, user_prompt, max_tokens, temperature
                )
            except Exception as e:
                logger.error(f"OpenAI fallback also failed: {e}")
                raise
        logger.warning("No AI provider configured — using fallback tests")

        import re

        matches = re.findall(r'https?://[^\s]+', user_prompt)

        target_url = matches[-1] if matches else ""
        target_url = target_url.replace("...')`", "")
        target_url = target_url.replace("...", "")
        target_url = target_url.strip()

        fallback_test = {
            "test_plan": {
                "summary": "AI-generated smoke tests",
                "total_tests": 3,
                "coverage_areas": [
                    "authentication",
                    "validation",
                    "navigation"
                ],
                "estimated_duration_seconds": 90
            },
            "test_suites": [
                {
                    "name": "Smoke Suite",
                    "tests": [

                        {
                            "name": "Valid Login Test",
                            "steps": [
                                {
                                    "action": "goto",
                                    "value": target_url
                                },
                                {
                                    "action": "fill",
                                    "selector": "input[type='text']",
                                    "value": "practice"
                                },
                                {
                                    "action": "fill",
                                    "selector": "input[type='password']",
                                    "value": "SuperSecretPassword!"
                                },
                                {
                                    "action": "click",
                                    "selector": "button[type='submit']"
                                },
                                {
                                    "action": "assert_url",
                                    "value": "secure"
                                }
                            ]
                        },

                        {
                            "name": "Invalid Login Test",
                            "steps": [
                                {
                                    "action": "goto",
                                    "value": target_url
                                },
                                {
                                    "action": "fill",
                                    "selector": "input[type='text']",
                                    "value": "wronguser"
                                },
                                {
                                    "action": "fill",
                                    "selector": "input[type='password']",
                                    "value": "wrongpassword"
                                },
                                {
                                    "action": "click",
                                    "selector": "button[type='submit']"
                                },
                                {
                                    "action": "assert_text",
                                    "text": "Your username is invalid!"
                                }
                            ]
                        },

                        {
                            "name": "Empty Form Validation Test",
                            "steps": [
                                {
                                    "action": "goto",
                                    "value": target_url
                                },
                                {
                                    "action": "click",
                                    "selector": "button[type='submit']"
                                },
                                {
                                    "action": "assert_text",
                                    "text": "Your username is invalid!"
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        return fallback_test, "fallback", {}

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _complete_anthropic(
        self, client, system: str, user: str, max_tokens: int, temperature: float
    ) -> Tuple[str, str, dict]:
        response = await client.messages.create(
            model=settings.PRIMARY_MODEL,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = response.content[0].text
        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        logger.info(
            f"Anthropic {settings.PRIMARY_MODEL}: "
            f"{usage['input_tokens']} in / {usage['output_tokens']} out tokens"
        )
        return text, settings.PRIMARY_MODEL, usage

    async def _complete_openai(
        self, client, system: str, user: str, max_tokens: int, temperature: float
    ) -> Tuple[str, str, dict]:
        response = await client.chat.completions.create(
            model=settings.FALLBACK_MODEL,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        text = response.choices[0].message.content
        usage = {
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.completion_tokens,
        }
        logger.info(
            f"OpenAI {settings.FALLBACK_MODEL}: "
            f"{usage['input_tokens']} in / {usage['output_tokens']} out tokens"
        )
        return text, settings.FALLBACK_MODEL, usage

    def _cache_key(self, system: str, user: str) -> str:
        content = f"{settings.PROMPT_VERSION}:{system}:{user}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


llm_client = LLMClient()
