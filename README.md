# Pipecat voice agent with AssemblyAI Universal-3.6 Pro Realtime

Build a real-time voice agent using **Pipecat** — the open-source Voice AI framework — and the **AssemblyAI Universal-3.6 Pro Realtime model** as the speech-to-text engine.

Pipecat's modular pipeline design means you can swap any component without touching the rest. AssemblyAI has a first-party Pipecat plugin with full Universal-3.6 Pro Realtime support (`pipecat-ai` 1.9.0+ for `universal-3-6-pro`) — no manual WebSocket wiring required.

## Why AssemblyAI in Pipecat?

Universal-3.6 Pro Realtime is AssemblyAI's flagship real-time model, purpose-built for voice agents and trained on real voice-agent and telephony conversations. On AssemblyAI's English voice-agent benchmark of 12,460 scripted voice-agent scenarios, it posts the lowest word error rate of the realtime models compared:

| Metric | AssemblyAI Universal-3.6 Pro Realtime | Deepgram Flux EN | ElevenLabs Scribe v2 | Deepgram Nova-3 |
|--------|---------------------------------------|------------------|----------------------|-----------------|
| Word error rate (voice-agent benchmark) | **5.19%** | 13.50% | 7.78% | 8.64% |

On [Pipecat's own open STT benchmark](https://github.com/pipecat-ai/stt-benchmark), it posts a **0.96% pooled semantic word error rate**, with the final transcript landing a median **307 ms** after the user stops speaking.

Beyond raw accuracy, it brings three things that matter for live conversation: turn detection that combines semantic context with voice activity (fewer awkward double-responses when users pause mid-thought), **Context Carryover** (the model hears each turn in the context of your agent's last question), and included keyterm prompting. The model code-switches natively across **32 languages** and costs **$0.45/hr**.

> **Heads up on model IDs:** this repo uses the current `universal-3-6-pro` string throughout. Upgrading from Universal-3.5 Pro Realtime is a one-line change to the model name, and `universal-3-5-pro` stays available if you need to pin the previous model. If you're still on the legacy `u3-rt-pro` ID, switch to `universal-3-6-pro`.

## Architecture

```
Daily.co WebRTC room
       │ audio
       ▼
  Pipecat pipeline
  ┌─────────────────────────────────────────────┐
  │ transport.input()                           │
  │      │                                      │
  │ AssemblyAI Universal-3.6 Pro Realtime (STT) │
  │      │ transcript + turn signal             │
  │ user aggregator (context + VAD)             │
  │      │                                      │
  │ OpenAI GPT-4o (streaming)                   │
  │      │ text chunks                          │
  │ Cartesia Sonic (TTS)                        │
  │      │ audio                                │
  │ transport.output()                          │
  │      │                                      │
  │ assistant aggregator (conversation context) │
  └─────────────────────────────────────────────┘
```

Conversation context is **automatic**: the `LLMContextAggregatorPair` assistant aggregator at the end of the pipeline feeds each completed agent reply back to Universal-3.6 Pro Realtime as context for the next user turn.

## Prerequisites

- Python 3.11+
- [AssemblyAI API key](https://www.assemblyai.com/dashboard/signup) (free account)
- [Daily.co API key](https://dashboard.daily.co)
- [OpenAI API key](https://platform.openai.com/api-keys)
- [Cartesia API key](https://play.cartesia.ai)

## Quick start

```bash
git clone https://github.com/kelsey-aai/voice-agent-pipecat-universal-3-5-pro
cd voice-agent-pipecat-universal-3-5-pro

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # requires pipecat-ai>=1.9.0 for universal-3-6-pro

cp .env.example .env
# Edit .env with your API keys

# Start the bot (creates a Daily.co room and prints its URL)
python bot.py

# ...or join an existing room
python bot.py --url https://your-name.daily.co/your-room
```

Open the printed room URL in your browser, allow microphone access, and speak after the greeting.

Universal-3.6 Pro Realtime needs `pipecat-ai` 1.9.0+; if your environment has an older version, upgrade before running.

## Universal-3.6 Pro Realtime features

### Keyterm prompting

Boost accuracy on domain-specific vocabulary — included at no extra cost, no restart required:

```python
stt = AssemblyAISTTService(
    api_key=os.environ["ASSEMBLYAI_API_KEY"],
    settings=AssemblyAISTTService.Settings(
        model="universal-3-6-pro",
        keyterms_prompt=["AssemblyAI", "Universal-3.6 Pro", "Pipecat", "YourBrandName"],
    ),
)
```

Essential for medical, legal, and financial applications where names and codes matter.

### Conversation context (Context Carryover)

Universal-3.6 Pro Realtime keeps a short memory of the dialog and transcribes each user turn in the context of what your agent just said. After your agent asks *"What's your email address?"*, it can produce `user@assemblyai.com` instead of `user at assemblyai dot com`. Feeding the agent's question to the model cut WER by 10.2% on a 20,000-file voice-agent benchmark.

**In Pipecat this is automatic** — as long as your pipeline includes the `assistant_aggregator` from `LLMContextAggregatorPair`, the plugin feeds each completed agent reply to the model as `agent_context`. To seed context for the very first user reply, set `agent_context` at construction time:

```python
settings=AssemblyAISTTService.Settings(
    model="universal-3-6-pro",
    agent_context="Hi! Thanks for calling Acme. What's the email on your account?",
)
```

### Voice Focus (noisy audio)

Server-side noise suppression that isolates the primary speaker before audio reaches the model — use it instead of client-side noise cancellation:

```python
settings=AssemblyAISTTService.Settings(
    model="universal-3-6-pro",
    voice_focus="far-field",   # "near-field" for close-talking mics
)
```

### Multilingual support

Universal-3.6 Pro Realtime code-switches natively across 32 languages — English, Spanish, French, German, Italian, Portuguese, Korean, Russian, and more — including mid-sentence switches. It's on by default; to bias toward a single language, pin `language_code`.

### Speaker labels (optional)

For multi-party conversations, enable per-turn speaker labels:

```python
settings=AssemblyAISTTService.Settings(
    model="universal-3-6-pro",
    speaker_labels=True,
)
```

## Tuning turn detection

In Pipecat mode (`vad_force_turn_endpoint=True`, the default), Pipecat's VAD + Smart Turn analyzer decide when the user is done, and `max_turn_silence` is auto-synced to `min_turn_silence`. Start with the `mode` preset and fine-tune from there:

```python
settings=AssemblyAISTTService.Settings(
    model="universal-3-6-pro",
    mode="balanced",       # "min_latency" · "balanced" · "max_accuracy"
    min_turn_silence=100,  # raise to 200–500 if entities split across turns
)
```

To let AssemblyAI's own turn detection control turn endings instead, set `vad_force_turn_endpoint=False` — then `max_turn_silence` is respected independently.

> Note: `end_of_turn_confidence_threshold` and `format_turns` do **not** apply to Universal-3.6 Pro Realtime. Turn detection is handled by the model and transcripts are always formatted; those parameters belong to the older `universal-streaming` models.

## Deploy to Pipecat Cloud

```bash
pip install pipecatcloud
pcc auth login
pcc init
pcc secrets set my-agent-secrets --file .env
pcc deploy
```

## Resources

- [AssemblyAI Pipecat integration guide](https://www.assemblyai.com/docs/voice-agents/u3pro-pipecat)
- [Pipecat docs](https://docs.pipecat.ai)
- [Pipecat GitHub](https://github.com/pipecat-ai/pipecat)

---

<div class="blog-cta_component">
  <div class="blog-cta_title">Start building your Pipecat agent free</div>
  <div class="blog-cta_rt w-richtext">
    <p>Get a free AssemblyAI account and connect Universal-3.6 Pro Realtime to Pipecat in minutes — $0.45/hr, keyterm prompting included, no credit card required.</p>
  </div>
  <a href="https://www.assemblyai.com/dashboard/signup" class="button w-button">Sign up free</a>
</div>

<div class="blog-cta_component">
  <div class="blog-cta_title">Test it on your own audio</div>
  <div class="blog-cta_rt w-richtext">
    <p>Stream real conversations through Universal-3.6 Pro Realtime in the Playground and watch turn detection and context carryover work before you wire up the pipeline.</p>
  </div>
  <a href="https://www.assemblyai.com/playground" class="button w-button">Try playground</a>
</div>
