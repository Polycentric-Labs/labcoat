# Model provider risk cards

Per-provider data-governance facts for labcoat's model-selection engine. The `government_adjacent_safe`
flag is **derived in code** (`model_selector.government_adjacent_safe`) from jurisdiction + regulatory
flags — NOT stored here, and NEVER from a model-asserted ownership %. Fields marked `verify-DPA` were
not primary-source-verified in the 2026-06 meta-research; check the provider's data-processing agreement
at selection time. Jurisdiction codes are ISO-3166 alpha-2. FISA-702 applies to ALL US-hosted providers.

| Provider | Country | Jurisdiction | State-owned | Data-retention | Trains-on-inputs | Regulatory-flags | Notes |
|---|---|---|---|---|---|---|---|
| OpenAI | United States | US | no | verify-DPA | API: opt-out default | none | none |
| Anthropic | United States | US | no | verify-DPA | API: no-train default | none | none |
| Google | United States | US | no | verify-DPA | verify-DPA | none | FISA-702 (all US providers) |
| Meta (Llama) | United States | US | no | self-hostable (open weights) | n/a if self-hosted | none | open weights |
| Amazon (Nova) | United States | US | no | verify-DPA | Bedrock: no-train default | none | none |
| xAI (Grok) | United States | US | no | verify-DPA | verify-DPA | none | labcoat policy: OPTIONAL-only |
| Mistral | France | FR | no (Bpifrance minority <10%) | verify-DPA | verify-DPA | none | EU jurisdiction |
| Cohere | Canada | CA | no | verify-DPA | enterprise no-train | none | none |
| DeepSeek | China | CN | contested; state-fund involvement reported (unverified); open weights self-hostable | verify-DPA | verify-DPA | PRC-data-law | hosted-use flagged |
| Alibaba (Qwen) | China | CN | publicly listed; PRC entity under national-security laws | verify-DPA | verify-DPA | PRC-data-law | hosted-use flagged |
| Moonshot (Kimi) | China | CN | private | verify-DPA | verify-DPA | PRC-data-law | hosted-use flagged |
| Zhipu (GLM) | China | CN | partial state-funded | verify-DPA | verify-DPA | BIS-Entity-List; export-controlled; PRC-data-law | US-restricted (Fed. Reg. 2025-00704) |

## Blunt-critic selection
The default blunt critic is chosen EMPIRICALLY at selection time (an A/B flawed-claim critique eval),
NOT hardcoded. Sycophancy/critique benchmarks are a *prior*, not the answer (they measure sycophancy-
resistance, not adversarial-critique recall, and often score prior-gen models): SycEval (arXiv 2502.08177),
CriticEval (arXiv 2402.13764), FindTheFlaws (arXiv 2503.22989), the lechmazur/sycophancy leaderboard.
