# Model Provider Plugins

AVA ships with a single inference provider profile:

- `openai-codex`

The upstream Hermes plugin registry supported many third-party LLM providers.
This fork keeps inference intentionally scoped to OpenAI/Codex, so bundled
non-OpenAI provider plugins and user-installed provider plugin discovery are
disabled.
