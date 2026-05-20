import threading
import random
from openai import OpenAI
from base import BaseHandler
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from audio import (
    record_until_silence,
    transcribe_audio,
    speak,
    clean_text,
)


class AIHandler(BaseHandler):
    """
    Conversational AI phone line.

    Supports:
    - Natural answer phrases
    - Thinking filler phrases
    - Recovery phrases for unclear audio
    - Configurable TTS/STT
    """

    def __init__(self, config: dict):
        super().__init__(config)

        self.system_prompt = config.get(
            "system_prompt",
            "You are a helpful assistant. Keep responses brief."
        )

        self.model = config.get("model", "gpt-4o-mini")

        self.voice = config.get("voice", "alloy")
        self.tts_engine = config.get("tts_engine", "openai")
        self.tts_model = config.get("tts_model", "gpt-4o-mini-tts")

        self.stt_language = config.get("stt_language")
        self.stt_prompt = config.get("stt_prompt")

        self.answer_phrase = config.get(
            "answer_phrase",
            f"{self.name} speaking."
        )

        # Used while “thinking”
        self.filler_phrases = config.get(
            "filler_phrases",
            [
                "One moment now.",
                "Let me think about that.",
                "Right, let me see.",
                "Hmm, give me a second.",
                "I’m just thinking that through.",
            ]
        )

        # Used when nothing useful was heard
        self.no_hear_phrases = config.get(
            "no_hear_phrases",
            [
                "Sorry, what was that?",
                "I didn't quite catch that.",
                "Could you say that again for me?",
                "The line is a little unclear.",
                "Pardon?",
            ]
        )

        self.client = OpenAI()

    def _speak(self, text: str):
        speak(
            text,
            voice=self.voice,
            model=self.tts_model,
            tts_engine=self.tts_engine,
        )

    def run(self, hangup_event: threading.Event):
        print(f"\n  [call] Connected to '{self.name}'")

        # Natural answer phrase
        self._speak(self.answer_phrase)

        messages = []

        while not hangup_event.is_set():
            try:
                audio = record_until_silence(hangup_event)

                if audio is None or hangup_event.is_set():
                    break

                print("  [stt] Transcribing...")

                # Natural filler while processing
                if self.filler_phrases and not hangup_event.is_set():
                    self._speak(random.choice(self.filler_phrases))

                user_text = transcribe_audio(
                    audio,
                    language=self.stt_language,
                    prompt=self.stt_prompt,
                )

                user_text = clean_text(user_text)

                # Nothing useful heard
                if not user_text:
                    print("  [stt] Nothing heard")

                    if not hangup_event.is_set():
                        self._speak(
                            random.choice(self.no_hear_phrases)
                        )

                    continue

                print(f"  [user] {user_text}")

                messages.append({
                    "role": "user",
                    "content": user_text
                })

                response = self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=256,
                    messages=[
                        {
                            "role": "system",
                            "content": self.system_prompt
                        }
                    ] + messages,
                )

                reply_text = (
                    response.choices[0].message.content or ""
                )

                reply_text = clean_text(reply_text)

                print(f"  [{self.name}] {reply_text}")

                messages.append({
                    "role": "assistant",
                    "content": reply_text
                })

                if not hangup_event.is_set():
                    self._speak(reply_text)

            except Exception as e:
                print(f"  [error] {clean_text(str(e))}")

                if not hangup_event.is_set():
                    self._speak(
                        "Sorry, there was a problem. Please try again."
                    )

                break

        print(f"  [call] '{self.name}' call ended.")
