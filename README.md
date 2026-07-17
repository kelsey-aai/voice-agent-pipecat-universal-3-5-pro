# Pipecat voice agent with AssemblyAI Universal-3.5 Pro Realtime

Build a real-time voice agent using **Pipecat** — the open-source Voice AI framework — and the **AssemblyAI Universal-3.5 Pro Realtime model** as the speech-to-text engine.

Pipecat's modular pipeline design means you can swap any component without touching the rest. AssemblyAI has a first-party Pipecat plugin (`pipecat-ai` 1.4.0+) with full Universal-3.5 Pro Realtime support — no manual WebSocket wiring required.

## Why AssemblyAI in Pipecat?

Universal-3.5 Pro Realtime is AssemblyAI's flagship real-time model, purpose-built for voice agents. On [Pipecat's own open STT benchmark](https://github.com/pipecat-ai/stt-benchmark) of real agent conversations, it leads the field:

| Metric | AssemblyAI Universal-3.5 Pro Realtime | Deepgram Flux | ElevenLabs Scribe v2 | Google Chirp 3 |
|--------|---------------------------------------|---------------|----------------------|----------------|
| Pooled WER (real agent conversations) | **6.99%** | 15.58% | 9.76% | 9.04% |

Beyond raw accuracy, it brings three things that matter for live conversation: punctuation-based turn detection (fewer awkward double-responses when users pause mid-thought), **Context Carryover** (the model hears each turn in the context of your agent's last question), and included keyterm prompting. Transcripts stream at roughly **150 ms P50**, and the model code-switches natively across **18 languages**.

> **Heads up on model IDs:** the older `u3-rt-pro` model auto-routes to `universal-3-5-pro` on **August 7, 2026** and stops accepting the old ID around **September 25, 2026**. This repo uses the current `universal-3-5-pro` string throughout.

## Architecture

```
Daily.co WebRTC room
       │ audio
       ▼
  Pipecat pipeline
  ┌─────────────────────────────────────────────┐
  │ transport.input()                           │
  │      │                                      │
  │ AssemblyAI Universal-3.5 Pro Realtime (STT) │
  │      │ transcript + turn signal             │
  │ TranscriptProcessor                         │
  │      │                                      │
  │ OpenAI GPT-4o (streaming)                  │
  │      │ text chunks                          │
  │ Cartesia Sonic (TTS)                        │
  │      │ audio                                │
  │ transport.output()                          │
  │      │                                      │
  │ assistant aggregator (conversation context) │
  └─────────────────────────────────────────────┘
```

Conversation context is **automatic**: the `LLMContextAggregatorPair` assistant aggregator at the end of the pipeline feeds each completed agent reply back to Universal-3.5 Pro Realtime as context for the next user turn.

## Prerequisites

- Python 3.11+
- [AssemblyAI API key](https://app.assemblyai.com)
- [Daily.co API key](https://dashboard.daily.co)
- [OpenAI API key](https://platform.openai.com/api-keys)
- [Cartesia API key](https://play.cartesia.ai)

## Quick start

```bash
git clone https://github.com/kelsey-aai/voice-agent-pipecat-universal-3-5-pro
cd voice-agent-pipecat-universal-3-5-pro

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # pins pipecat-ai>=1.4.0

cp .env.example .env
# Edit .env with your API keys

# Create a Daily.co room
python create_room.py

# Start the bot (paste the room URL from above)
python bot.py --url https://your-name.daily.co/your-room
```

Open the room URL in your browser and start talking.

## Universal-3.5 Pro Realtime features

### Keyterm prompting

Boost accuracy on domain-specific vocabulary — included at no extra cost, no restart required:

```python
stt = AssemblyAISTTService(
    api_key=os.environ["ASSEMBLYAI_API_KEY"],
    settings=AssemblyAISTTService.Settings(
        model="universal-3-5-pro",
        keyterms_prompt=["AssemblyAI", "Universal-3.5 Pro", "Pipecat", "YourBrandName"],
    ),
)
```

Essential for medical, legal, and financial applications where names and codes matter.

### Conversation context (Context Carryover)

Universal-3.5 Pro Realtime keeps a short memory of the dialog and transcribes each user turn in the context of what your agent just said. After your agent asks *"What's your email address?"*, it can produce `user@assemblyai.com` instead of `user at assemblyai dot com`.

**In Pipecat this is automatic** — as long as your pipeline includes the `assistant_aggregator` from `LLMContextAggregatorPair`, the plugin feeds each completed agent reply to the model as `agent_context`. To seed context for the very first user reply, set `agent_context` at construction time:

```python
settings=AssemblyAISTTService.Settings(
    model="universal-3-5-pro",
    agent_context="Hi! Thanks for calling Acme. What's the email on your account?",
)
```

### Voice Focus (noisy audio)

Server-side noise suppression that isolates the primary speaker before audio reaches the model — use it instead of client-side noise cancellation:

```python
settings=AssemblyAISTTService.Settings(
    model="universal-3-5-pro",
    voice_focus="far-field",   # "near-field" for close-talking mics
)
```

### Multilingual support

Universal-3.5 Pro Realtime code-switches natively across 18 languages — English, Spanish, French, German, Italian, Portuguese, and more — including mid-sentence switches. It's on by default; to bias toward a single language, pin `language_code`.

### Speaker labels (optional)

For multi-party conversations, enable per-turn speaker labels:

```python
settings=AssemblyAISTTService.Settings(
    model="universal-3-5-pro",
    speaker_labels=True,
)
```

## Tuning turn detection

In Pipecat mode (`vad_force_turn_endpoint=True`, the default), Pipecat's VAD + Smart Turn analyzer decide when the user is done, and `max_turn_silence` is auto-synced to `min_turn_silence`. Start with the `mode` preset and fine-tune from there:

```python
settings=AssemblyAISTTService.Settings(
    model="universal-3-5-pro",
    mode="balanced",       # "min_latency" · "balanced" · "max_accuracy"
    min_turn_silence=100,  # raise to 200–500 if entities split across turns
)
```

To let AssemblyAI's own punctuation-based turn detection control turn endings instead, set `vad_force_turn_endpoint=False` — then `max_turn_silence` is respected independently.

> Note: `end_of_turn_confidence_threshold` and `format_turns` do **not** apply to Universal-3.5 Pro Realtime. Turn detection is punctuation-based and transcripts are always formatted; those parameters belong to the older `universal-streaming` models.

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
  <div class="blog-cta_title">Add AssemblyAI to your Pipecat pipeline</div>
  <div class="blog-cta_rt w-richtext">
    <p>Sign up for a free AssemblyAI account and drop Universal-3.5 Pro Realtime into any Pipecat voice agent in minutes.</p>
  </div>
  <a href="https://www.assemblyai.com/dashboard/signup" class="button w-button">Start building</a>
</div>

<div class="blog-cta_component">
  <div class="blog-cta_title">Experiment with real-time turn detection</div>
  <div class="blog-cta_rt w-richtext">
    <p>Try streaming transcription in our Playground and observe how punctuation and silence handling shape turn boundaries in real time.</p>
  </div>
  <a href="https://www.assemblyai.com/playground" class="button w-button">Open playground</a>
</div>
