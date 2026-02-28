import os
import queue
import subprocess
import sys
import threading
import importlib
import importlib.util
import traceback
import tkinter as tk
from tkinter import messagebox, scrolledtext

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else BASE_DIR
BUNDLE_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
SCRIPT_PATH = os.path.join(APP_DIR, "inst_skroll.py")
BUNDLED_SCRIPT_PATH = os.path.join(BUNDLE_DIR, "inst_skroll.py")


class ScrollLauncherUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Instagram Scroll Launcher")
        self.root.geometry("520x340")
        self.root.minsize(480, 320)
        self.process = None
        self.log_queue = queue.Queue()
        self.show_tech_logs = tk.BooleanVar(value=False)
        self.progress_var = tk.StringVar(value="Прогресс: ожидание запуска")

        self._build_ui()
        self._schedule_log_pump()

    def _build_ui(self):
        top = tk.Frame(self.root, padx=12, pady=12)
        top.pack(fill="x")

        self.start_button = tk.Button(top, text="Старт", width=14, command=self.start_script)
        self.start_button.pack(side="left", padx=(0, 8))

        self.stop_button = tk.Button(top, text="Стоп", width=14, command=self.stop_script, state="disabled")
        self.stop_button.pack(side="left", padx=(0, 16))

        self.status_var = tk.StringVar(value="Статус: остановлено")
        status_label = tk.Label(top, textvariable=self.status_var, anchor="w")
        status_label.pack(side="left", fill="x", expand=True)

        progress_label = tk.Label(self.root, textvariable=self.progress_var, anchor="w", padx=12)
        progress_label.pack(fill="x")

        action = tk.Frame(self.root, padx=12)
        action.pack(fill="x", pady=(0, 8))

        tk.Button(action, text="Отправить Enter", width=18, command=self.send_enter).pack(side="left", padx=(0, 8))
        tk.Button(action, text="Ответить Да (y)", width=18, command=lambda: self.send_text("y\n")).pack(side="left", padx=(0, 8))
        tk.Button(action, text="Ответить Нет (n)", width=18, command=lambda: self.send_text("n\n")).pack(side="left", padx=(0, 8))
        tk.Button(action, text="Очистить лог", width=18, command=self.clear_log).pack(side="left")

        options = tk.Frame(self.root, padx=12)
        options.pack(fill="x", pady=(0, 8))

        tk.Checkbutton(
            options,
            text="Показывать техлог (DEBUG, scrollTop, шаги)",
            variable=self.show_tech_logs,
        ).pack(side="left")

        self.log = scrolledtext.ScrolledText(self.root, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def _append_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def start_script(self):
        if self.process and self.process.poll() is None:
            messagebox.showinfo("Уже запущено", "Скрипт уже работает.")
            return

        if not os.path.exists(SCRIPT_PATH) and not getattr(sys, "frozen", False):
            messagebox.showerror("Файл не найден", f"Не найден скрипт:\n{SCRIPT_PATH}")
            return

        try:
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"

            worker_cmd = self._resolve_worker_cmd()
            if not worker_cmd:
                messagebox.showerror("Ошибка запуска", "Не удалось определить команду запуска worker-процесса.")
                return

            self.process = subprocess.Popen(
                worker_cmd,
                cwd=APP_DIR,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                universal_newlines=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
        except Exception as exc:
            messagebox.showerror("Ошибка запуска", str(exc))
            return

        self.status_var.set("Статус: запущено")
        self.progress_var.set("Прогресс: скрипт запущен")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self._append_log("\n=== Запуск скрипта ===\n")
        self._append_log("Подсказка: когда скрипт ждёт действие — нажимай 'Отправить Enter' или Да/Нет.\n")

        threading.Thread(target=self._read_output_worker, daemon=True).start()
        threading.Thread(target=self._wait_process_worker, daemon=True).start()

    def stop_script(self):
        if not self.process or self.process.poll() is not None:
            return

        try:
            self.process.terminate()
        except Exception:
            pass

    def send_enter(self):
        self.send_text("\n")

    def send_text(self, text):
        if not self.process or self.process.poll() is not None:
            messagebox.showwarning("Не запущено", "Скрипт не запущен.")
            return

        try:
            assert self.process.stdin is not None
            self.process.stdin.write(text)
            self.process.stdin.flush()
        except Exception as exc:
            messagebox.showerror("Ошибка ввода", str(exc))

    def _read_output_worker(self):
        if not self.process or not self.process.stdout:
            return

        try:
            for line in self.process.stdout:
                self.log_queue.put(self._normalize_line(line))
        except Exception as exc:
            self.log_queue.put(f"\n[Ошибка чтения вывода] {exc}\n")

    def _wait_process_worker(self):
        if not self.process:
            return
        code = self.process.wait()
        self.log_queue.put(f"\n=== Процесс завершён, код {code} ===\n")
        self.log_queue.put("__PROCESS_DONE__")

    def _schedule_log_pump(self):
        try:
            while True:
                item = self.log_queue.get_nowait()
                if item == "__PROCESS_DONE__":
                    self._set_stopped_state()
                else:
                    self._update_progress(item)
                    if self._should_show_line(item):
                        self._append_log(item)
        except queue.Empty:
            pass

        self.root.after(120, self._schedule_log_pump)

    def _set_stopped_state(self):
        self.status_var.set("Статус: остановлено")
        self.progress_var.set("Прогресс: остановлено")
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.process = None

    def _resolve_worker_cmd(self):
        if getattr(sys, "frozen", False):
            return [sys.executable, "--worker"]

        if not os.path.exists(SCRIPT_PATH):
            return None

        return [sys.executable, "-X", "utf8", SCRIPT_PATH]

    def _normalize_line(self, line):
        return line.replace("\\n", "\n")

    def _should_show_line(self, line):
        if self.show_tech_logs.get():
            return True

        low = line.lower()
        tech_markers = [
            "debug target",
            "debug:",
            "scrolltop=",
            "rect=(",
            "class=",
            "шаг ",
            "noprogress=",
        ]
        return not any(marker in low for marker in tech_markers)

    def _update_progress(self, line):
        low = line.lower()
        if "шаг " in low and "noprogress=" in low:
            self.progress_var.set(f"Прогресс: {line.strip()}")
        elif "дошли до первого сообщения" in low:
            self.progress_var.set("Прогресс: похоже, найдено первое сообщение")
        elif "достигнут лимит шагов" in low:
            self.progress_var.set("Прогресс: достигнут лимит шагов")
        elif "потерян контейнер" in low or "не удалось восстановить" in low:
            self.progress_var.set("Прогресс: ошибка контейнера прокрутки")


if __name__ == "__main__":
    if "--worker" in sys.argv:
        try:
            inst_skroll = importlib.import_module("inst_skroll")
        except ModuleNotFoundError:
            fallback_path = SCRIPT_PATH if os.path.exists(SCRIPT_PATH) else BUNDLED_SCRIPT_PATH
            if os.path.exists(fallback_path):
                spec = importlib.util.spec_from_file_location("inst_skroll", fallback_path)
                if spec and spec.loader:
                    inst_skroll = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(inst_skroll)
                else:
                    raise
            else:
                raise
        try:
            print("[worker] Запуск inst_skroll...")
            inst_skroll.main()
        except Exception:
            print("[worker] Критическая ошибка:\n" + traceback.format_exc())
            raise
    else:
        root = tk.Tk()
        app = ScrollLauncherUI(root)
        root.mainloop()
