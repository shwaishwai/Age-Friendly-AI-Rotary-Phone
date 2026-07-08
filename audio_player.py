import simpleaudio as sa
import threading


class AudioPlayer:
    def __init__(self):
        self.stop_flag = False
        self.thread = None
        self.current_play = None

    def _loop(self, filename):
        wave = sa.WaveObject.from_wave_file(filename)

        while not self.stop_flag:
            self.current_play = wave.play()
            self.current_play.wait_done()

    def play_loop(self, filename):
        self.stop()
        self.stop_flag = False
        self.thread = threading.Thread(target=self._loop, args=(filename,), daemon=True)
        self.thread.start()

    def play_once(self, filename):
        self.stop()
        wave = sa.WaveObject.from_wave_file(filename)
        self.current_play = wave.play()
        self.current_play.wait_done()
        self.current_play = None

    def stop(self):
        self.stop_flag = True

        if self.current_play:
            try:
                self.current_play.stop()
            except Exception:
                pass
            self.current_play = None

        if self.thread:
            self.thread.join(timeout=0.5)
            self.thread = None
