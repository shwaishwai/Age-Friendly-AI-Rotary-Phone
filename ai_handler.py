import threading
from openai import OpenAI
from base import BaseHandler
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from audio import record_until_silence, transcribe_audio, speak, clean_text


class AIHandler(BaseHandler):
    """
    Conversational AI phone line.
    System prompt, model, TTS engine, TTS voice, and STT options are configured in lines.json.
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.system_prompt = config.get(
            "system_prompt", "You are a helpful assistant. Keep responses brief."
        )
        self.model = config.get("model", "gpt-4o-mini")
        self.voice = config.get("voice", "alloy")
        self.tts_engine = config.get("tts_engine", "openai")
        self.tts_model = config.get("tts_model", "gpt-4o-mini-tts")
        self.stt_language = config.get("stt_language")
        self.stt_prompt = config.get("stt_prompt")
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
        self._speak(f"You are connected to {self.name}.")

        messages = []

        while not hangup_event.is_set():
            try:
                audio = record_until_silence(hangup_event)

                if audio is None or hangup_event.is_set():
                    break

                print("  [stt] Transcribing...")
                user_text = transcribe_audio(
                    audio,
                    language=self.stt_language,
                    prompt=self.stt_prompt,
                )

                if not user_text:
                    print("  [stt] Nothing heard, listening again...")
                    continue

                print(f"  [user] {user_text}")
                messages.append({"role": "user", "content": user_text})

                response = self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=256,
                    messages=[{"role": "system", "content": self.system_prompt}] + messages,
                )

                reply_text = response.choices[0].message.content or ""
                reply_text = clean_text(reply_text)
                print(f"  [{self.name}] {reply_text}")
                messages.append({"role": "assistant", "content": reply_text})

                if not hangup_event.is_set():
                    self._speak(reply_text)

            except Exception as e:
                print(f"  [error] {clean_text(str(e))}")
                if not hangup_event.is_set():
                    self._speak("Sorry, there was a problem. Please try again.")
                break

        print(f"  [call] '{self.name}' call ended.")
