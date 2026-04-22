from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/oci_migration"
    REDIS_URL: str = "redis://localhost:6379"

    # LLM inference endpoint — OpenAI-compatible.
    # Default: Oracle internal Llama Stack (anonymous; no API key required).
    # Swap to OCI GenAI or any other OpenAI-compatible endpoint via .env.
    LLM_BASE_URL: str = "https://llama-stack.ai-apps-ord.oci-incubations.com/v1"
    LLM_API_KEY: str = ""  # leave blank for anonymous endpoints

    # Default models. Override per skill via MODEL_ROUTING (app.gateway.model_gateway)
    # or at runtime through the Settings page.
    #
    # - ``LLM_WRITER_MODEL`` drives the writer agents (drafts + revisions).
    # - ``LLM_REVIEWER_MODEL`` drives the reviewer agents (scoring + feedback).
    # - ``LLM_ORCHESTRATOR_MODEL`` drives the top-level orchestrator agent
    #   (inventory inspection + skill dispatch + final validation).
    #
    # The orchestrator benefits from a reasoning-capable model since it does
    # multi-step planning, so default it to the same model as writer.
    LLM_WRITER_MODEL: str = "oci/openai.gpt-5.4"
    LLM_REVIEWER_MODEL: str = "oci/openai.gpt-5.4-mini"
    LLM_ORCHESTRATOR_MODEL: str = "oci/openai.gpt-5.4"

    JWT_SECRET: str = "change-me-in-production"
    JWT_EXPIRE_MINUTES: int = 1440
    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
