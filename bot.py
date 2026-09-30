"""
Voice agent using Pipecat + AssemblyAI Universal-3.6 Pro Realtime.

Stack:
  Transport — Daily.co WebRTC
  STT       — AssemblyAI Universal-3.6 Pro Realtime (universal-3-6-pro)
  LLM       — OpenAI GPT-4o with streaming
  TTS       — Cartesia Sonic

Requires pipecat-ai 1.9.0+ for universal-3-6-pro.
"""

import asyncio
import os
import sys

from dotenv import load_dotenv
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import EndFrame, LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.assemblyai.stt import AssemblyAISTTService
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.daily.transport import DailyParams, DailyTransport

from create_room import create_room

load_dotenv()

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

SYSTEM_PROMPT = """
You are a friendly, helpful voice assistant powered by AssemblyAI Universal-3.6 Pro Realtime.
Start the conversation with a short greeting.
Keep responses under 2–3 sentences. Speak naturally — no markdown, no lists, no bullet points.
""".strip()


async def main(room_url: str, token: str | None = None):
    # ── Transport ───────────────────────────────────────────────────────────
    transport = DailyTransport(
        room_url,
        token,
        "Voice Assistant",
        DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            transcription_enabled=False,  # We use AssemblyAI, not Daily transcription
        ),
    )

    # ── STT: AssemblyAI Universal-3.6 Pro Realtime ──────────────────────────
    stt = AssemblyAISTTService(
        api_key=os.environ["ASSEMBLYAI_API_KEY"],
        settings=AssemblyAISTTService.Settings(
            model="universal-3-6-pro",
            min_turn_silence=100,
        ),
        vad_force_turn_endpoint=True,  # Pipecat mode (default): VAD + Smart Turn control turns
    )

    # ── LLM ────────────────────────────────────────────────────────────────
    llm = OpenAILLMService(api_key=os.environ["OPENAI_API_KEY"], model="gpt-4o")

    # ── TTS ────────────────────────────────────────────────────────────────
    tts = CartesiaTTSService(
        api_key=os.environ["CARTESIA_API_KEY"],
        voice_id="79a125e8-cd45-4c13-8a67-188112f4dd22",
    )

    # ── Conversation context ─────────────────────────────────────────────────
    # The assistant aggregator at the end of the pipeline feeds each completed
    # agent reply back to the model as conversation context automatically.
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    context = LLMContext(messages)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    # ── Pipeline ───────────────────────────────────────────────────────────
    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,  # feeds each agent reply back as conversation context
        ]
    )

    task = PipelineTask(pipeline, params=PipelineParams())

    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(transport, participant):
        logger.info(f"Participant joined: {participant['id']}")
        # Greet the user on connection
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport, participant, reason):
        await task.queue_frame(EndFrame())

    runner = PipelineRunner()
    await runner.run(task)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Pipecat + AssemblyAI Universal-3.6 Pro Realtime voice agent")
    parser.add_argument(
        "--url",
        default=None,
        help="Daily.co room URL (optional; a new room is created if omitted)",
    )
    parser.add_argument("--token", default=None, help="Daily.co meeting token (optional)")
    args = parser.parse_args()

    room_url = args.url or create_room()
    print(f"Open this room in your browser and start talking: {room_url}")

    asyncio.run(main(room_url, args.token))
