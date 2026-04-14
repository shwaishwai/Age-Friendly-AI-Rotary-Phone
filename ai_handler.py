from openai import OpenAI
from base import BaseHandler
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from audio import record_audio, save_audio, transcribe, speak


class AIHandler(BaseHandler):
    """
    A conversational AI phone line.
    System prompt, model, and voice are all configured via lines.json.
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.system_prompt = config.get(
            "system_prompt", "You are a helpful assistant. Keep responses brief."
        )
        self.model = config.get("model", "gpt-3.5-turbo")
        self.client = OpenAI()  # reads OPENAI_API_KEY from env

    def run(self):
        print(f"\n  [call] Connected to '{self.name}'")
        speak(f"You are connected to {self.name}.", voice=self.voice)

        messages = []

        while True:
            try:
                audio = record_audio()
                save_audio(audio)

                print("  [stt] Transcribing...")
                user_text = transcribe()

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

                reply_text = response.choices[0].message.content
                print(f"  [{self.name}] {reply_text}")
                messages.append({"role": "assistant", "content": reply_text})

                speak(reply_text, voice=self.voice)

            except KeyboardInterrupt:
                print("  [call] Caller hung up.")
                break
            except Exception as e:
                print(f"  [error] {e}")
                speak("Sorry, there was a problem. Please try again.", voice=self.voice)
                break
