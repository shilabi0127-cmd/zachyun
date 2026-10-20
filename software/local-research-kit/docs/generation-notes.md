# GGUF smoke run

Qwen3-0.6B-Q8_0, llama-cpp-python 0.3.35, CPU, 4096-token context. The weight hash is recorded in `model.json` and matches the upstream file metadata. No fine-tuning was performed.

The initial JSON-object prompt returned an item that failed citation validation on one of the two answerable questions. That run is kept in `generation-run-unconstrained.json`.

The revised adapter uses short source aliases (`S1`, `S2`) and a JSON schema that restricts source IDs. It then maps aliases back to content-derived IDs and checks each quote against the retrieved text. An API integration check also exposed heading-only citations; the validator now rejects headings and quotes shorter than 16 characters, with a regression test. In the final rerun, both answerable questions returned items that passed these mechanical checks. The unrelated question had no retrieval matches and did not invoke the model. See `generation-run.json` for the full inputs and outputs.

This tiny run helped check integration behavior, not answer quality in general. It does not isolate the effects of aliases versus schema constraints, and passing quote checks does not establish semantic entailment. The initial and revised calls were separate processes, so first-call times include model loading in both runs.

The notes and queries used here are intentionally short. Longer contexts, multilingual documents and adversarial sources need more testing. The current CPU backend also serializes generation with a lock; it is not a concurrent inference server.
