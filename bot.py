"""
Voice agent using Pipecat + AssemblyAI Universal-3.5 Pro Realtime.

Stack:
  Transport — Daily.co WebRTC
  STT       — AssemblyAI Universal-3.5 Pro Realtime (universal-3-5-pro)
  LLM       — OpenAI GPT-4o with streaming
  TTS       — Cartesia Sonic
"""

import asyncio
import os
import sys

from dotenv import load_dotenv
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import EndFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.transcript_processor import TranscriptProcessor
from pipecat.services.assemblyai.stt import AssemblyAISTTService
from pipecat.services.cartesia import CartesiaTTSService
from pipecat.services.openai import OpenAILLMService
from pipecat.transports.services.daily import DailyParams, DailyTransport

load_dotenv()

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")

SYSTEM_PROMPT = """
You are a friendly, helpful voice assistant powered by AssemblyAI Universal-3.5 Pro Realtime.
Keep responses under 2–3 sentences. Speak naturally — no markdown, no lists, no bullet points.
""".strip()


async def main(room_url: str, token: str | None = None):
    # ── Transport ───────────────────────────────────────────────────────────
    transport = DailyTransport(
        room_url,
        token,
        "Voice Assistant",
        DailyParams(
            audio_out_enabled=True,
            transcription_enabled=False,  # We use AssemblyAI, not Daily transcription
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
            vad_audio_passthrough=True,
        ),
    )

    # ── STT: AssemblyAI Universal-3.5 Pro Realtime ──────────────────────────
    stt = AssemblyAISTTService(
        api_key=os.environ["ASSEMBLYAI_API_KEY"],
        settings=AssemblyAISTTService.Settings(
            model="universal-3-5-pro",
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

    # ── Transcript logging ─────────────────────────────────────────────────
    transcript = TranscriptProcessor()

    @transcript.event_handler("on_transcript_update")
    async def on_transcript_update(processor, frame):
        for msg in frame.messages:
            logger.info(f"[{msg.role}] {msg.content}")

    # ── Pipeline ───────────────────────────────────────────────────────────
    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            transcript.user(),
            user_aggregator,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
            transcript.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        PipelineParams(allow_interruptions=True),
    )

    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(transport, participant):
        await transport.capture_participant_transcription(participant["id"])
        # Greet the user on connection
        await task.queue_frames(
            [
                user_aggregator.get_context_frame(),
            ]
        )
        logger.info(f"Participant joined: {participant['id']}")

    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport, participant, reason):
        await task.queue_frame(EndFrame())

    runner = PipelineRunner()
    await runner.run(task)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Pipecat + AssemblyAI U3.5 Pro voice agent")
    parser.add_argument("--url", required=True, help="Daily.co room URL")
    parser.add_argument("--token", default=None, help="Daily.co meeting token (optional)")
    args = parser.parse_args()

    asyncio.run(main(args.url, args.token))
