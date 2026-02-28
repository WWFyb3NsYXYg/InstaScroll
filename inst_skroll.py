import time
from playwright.sync_api import Error as PlaywrightError, sync_playwright

# -------- настройки --------
USE_MOBILE_LAYOUT = True         # True = мобильная версия Instagram
MOBILE_DEVICE = "iPhone 13"     # профиль устройства Playwright
DEBUG_VISUAL = True              # подсветка выбранного контейнера + подробные логи
FAST_SCROLL_MODE = True         # быстрый режим (похоже на автоскролл средней кнопкой)
FAST_SCROLL_BURST = 3           # сколько быстрых подшагов делать за один шаг цикла
PAUSE_BETWEEN_SCROLLS = 0.25 if FAST_SCROLL_MODE else 0.9   # пауза между прокрутками (сек)
MAX_STEPS = 500               # защита от бесконечного цикла
NO_PROGRESS_LIMIT = 10        # сколько шагов без движения/догрузки -> считаем, что дошли до начала
STEP_EXTENSION = 300          # на сколько увеличивать лимит, если есть прогресс
MAX_AUTO_EXTENSIONS = 8       # максимум авто-расширений лимита
# --------------------------


FIND_SCROLLABLE_JS = """
() => {
  // Ищем лучший скроллящийся контейнер внутри main (приоритет: правая панель диалога)
  const main = document.querySelector('main, div[role="main"]') || document.body;
  const all = [...main.querySelectorAll('*')];

  const isScrollable = (el) => {
    const style = getComputedStyle(el);
    const scrollable = el.scrollHeight - el.clientHeight;
    return ['auto', 'scroll'].includes(style.overflowY) && scrollable > 250;
  };

  const getScrollableAncestor = (el) => {
    let cur = el;
    while (cur && cur !== document.body) {
      if (isScrollable(cur)) return cur;
      cur = cur.parentElement;
    }
    return null;
  };

  const centerEl = document.elementFromPoint(window.innerWidth * 0.5, window.innerHeight * 0.55);
  let best = getScrollableAncestor(centerEl) || getScrollableAncestor(document.activeElement);
  let bestScore = best ? 2000 : -Infinity;

  for (const el of all) {
    if (!isScrollable(el)) continue;

    const scrollable = el.scrollHeight - el.clientHeight;

    const rect = el.getBoundingClientRect();
    const inView = rect.height > 120 && rect.width > 250;
    if (!inView) continue;

    const centerX = rect.left + rect.width / 2;
    const threadLinks = el.querySelectorAll('a[href*="/direct/t/"]').length;
    const msgLikeNodes = el.querySelectorAll('[role="row"], [role="listitem"], time').length;

    let score = scrollable + rect.height;

    // Для десктопа: правая часть окна обычно содержит сообщения, левая — список чатов
    if (window.innerWidth >= 900) {
      if (centerX > window.innerWidth * 0.48) score += 1500;
      else score -= 1500;
    }

    // В списке чатов много ссылок /direct/t/, штрафуем такие контейнеры
    score -= threadLinks * 80;

    // Небольшой бонус за узлы, похожие на сообщения
    score += Math.min(msgLikeNodes, 40) * 20;

    if (score > bestScore) {
      bestScore = score;
      best = el;
    }
  }

  if (!best) return null;
  document
    .querySelectorAll('[data-copilot-chat-scroll="1"]')
    .forEach((node) => node.removeAttribute('data-copilot-chat-scroll'));
  best.setAttribute('data-copilot-chat-scroll', '1');
  return { score: bestScore };
}
"""

GET_SCROLL_STATE_JS = """
() => {
  const el = document.querySelector('[data-copilot-chat-scroll="1"]');
  if (!el) return null;
  return {
    top: el.scrollTop,
    height: el.scrollHeight,
    client: el.clientHeight
  };
}
"""

SCROLL_UP_STEP_JS = """
({ burst }) => {
  const el = document.querySelector('[data-copilot-chat-scroll="1"]');
  if (!el) return null;
  const before = el.scrollTop;
  const delta = Math.max(260, el.clientHeight * 1.15);
  const loops = Math.max(1, Math.min(8, Number(burst || 1)));
  for (let i = 0; i < loops; i += 1) {
    el.scrollBy({ top: -delta, left: 0, behavior: 'instant' });
  }
  return {
    before,
    after: el.scrollTop,
    height: el.scrollHeight,
    client: el.clientHeight
  };
}
"""

SCROLL_TO_BOTTOM_JS = """
() => {
  const el = document.querySelector('[data-copilot-chat-scroll="1"]');
  if (!el) return null;
  el.scrollTop = el.scrollHeight;
  return { top: el.scrollTop, height: el.scrollHeight, client: el.clientHeight };
}
"""

GET_CONTAINER_DEBUG_JS = """
() => {
  const el = document.querySelector('[data-copilot-chat-scroll="1"]');
  if (!el) return null;
  const rect = el.getBoundingClientRect();
  return {
    tag: el.tagName,
    id: el.id || null,
    className: (el.className || '').toString().slice(0, 180),
    role: el.getAttribute('role'),
    top: Math.round(rect.top),
    left: Math.round(rect.left),
    width: Math.round(rect.width),
    height: Math.round(rect.height),
    scrollTop: Math.round(el.scrollTop),
    scrollHeight: Math.round(el.scrollHeight),
    clientHeight: Math.round(el.clientHeight)
  };
}
"""

HIGHLIGHT_CONTAINER_JS = """
() => {
  const el = document.querySelector('[data-copilot-chat-scroll="1"]');
  if (!el) return null;

  const prev = document.getElementById('copilot-scroll-debug-badge');
  if (prev) prev.remove();

  el.style.outline = '3px solid #00e0ff';
  el.style.outlineOffset = '-2px';

  const badge = document.createElement('div');
  badge.id = 'copilot-scroll-debug-badge';
  badge.textContent = 'SCROLL TARGET';
  badge.style.position = 'fixed';
  badge.style.top = '10px';
  badge.style.right = '10px';
  badge.style.zIndex = '2147483647';
  badge.style.padding = '6px 10px';
  badge.style.background = '#00e0ff';
  badge.style.color = '#001018';
  badge.style.fontSize = '12px';
  badge.style.fontWeight = '700';
  badge.style.borderRadius = '8px';
  badge.style.fontFamily = 'system-ui, -apple-system, Segoe UI, Roboto, sans-serif';
  document.body.appendChild(badge);
  return true;
}
"""


def wait_user_ready():
  input(
    "\\nОткрой нужный диалог Instagram, ткни в область сообщений (по центру экрана) и нажми Enter здесь...\\n"
  )


def ask_user_continue(reason):
  answer = input(f"{reason} Там есть ещё? [y/N]: ").strip().lower()
  return answer in {"y", "yes", "д", "да", "+"}


def safe_evaluate(page, script, retries=5):
  for attempt in range(1, retries + 1):
    try:
      return page.evaluate(script)
    except PlaywrightError as exc:
      message = str(exc)
      is_context_error = (
        "Execution context was destroyed" in message
        or "Cannot find context" in message
        or "Most likely the page has been closed" in message
      )

      if not is_context_error or attempt == retries:
        raise

      print("Страница обновилась/перенаправилась, жду стабилизацию и повторяю...")
      try:
        page.wait_for_load_state("domcontentloaded", timeout=10000)
      except PlaywrightError:
        pass
      time.sleep(0.7)

  return None


def print_target_debug(page):
  info = safe_evaluate(page, GET_CONTAINER_DEBUG_JS)
  if not info:
    print("DEBUG: контейнер не найден.")
    return
  print(
    "DEBUG target:",
    f"tag={info['tag']}",
    f"role={info['role']}",
    f"rect=({info['left']},{info['top']},{info['width']}x{info['height']})",
    f"scrollTop={info['scrollTop']}",
    f"scrollHeight={info['scrollHeight']}",
    f"clientHeight={info['clientHeight']}",
  )
  if info.get("id"):
    print(f"DEBUG target id={info['id']}")
  if info.get("className"):
    print(f"DEBUG target class={info['className']}")


def main():
  with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    if USE_MOBILE_LAYOUT:
      try:
        context = browser.new_context(**p.devices[MOBILE_DEVICE])
      except KeyError:
        context = browser.new_context(
          viewport={"width": 390, "height": 844},
          is_mobile=True,
          has_touch=True,
          device_scale_factor=3,
        )
    else:
      context = browser.new_context()
    page = context.new_page()

    page.goto("https://www.instagram.com/direct/inbox/", wait_until="domcontentloaded")
    if USE_MOBILE_LAYOUT:
      print("Браузер открыт в МОБИЛЬНОЙ версии. Войди в Instagram и открой нужный диалог.")
    else:
      print("Браузер открыт. Войди в Instagram, затем открой нужный диалог.")

    wait_user_ready()

    # Небольшой запас времени, чтобы DOM стабилизировался
    time.sleep(1.5)

    found = safe_evaluate(page, FIND_SCROLLABLE_JS)
    if not found:
      print("Не удалось найти скроллящийся контейнер чата. Убедись, что диалог открыт.")
      input("Нажми Enter, чтобы закрыть браузер...")
      return

    if DEBUG_VISUAL:
      safe_evaluate(page, HIGHLIGHT_CONTAINER_JS)
      print_target_debug(page)

    # Начинаем снизу диалога (где обычно последние сообщения), затем идем вверх к первому.
    safe_evaluate(page, SCROLL_TO_BOTTOM_JS)
    time.sleep(0.5)

    no_progress_count = 0
    step = 0
    max_steps_current = MAX_STEPS
    auto_extensions_used = 0

    while step < max_steps_current:
      step += 1
      before_state = safe_evaluate(page, GET_SCROLL_STATE_JS)
      if not before_state:
        found = safe_evaluate(page, FIND_SCROLLABLE_JS)
        if not found:
          print("Потерян контейнер прокрутки. Остановлено.")
          break
        before_state = safe_evaluate(page, GET_SCROLL_STATE_JS)
        if not before_state:
          print("Не удалось восстановить контейнер прокрутки. Остановлено.")
          break

      move = page.evaluate(SCROLL_UP_STEP_JS, {"burst": FAST_SCROLL_BURST if FAST_SCROLL_MODE else 1})
      time.sleep(PAUSE_BETWEEN_SCROLLS)
      after_state = safe_evaluate(page, GET_SCROLL_STATE_JS)

      if not move or not after_state:
        no_progress_count += 1
      else:
        moved = abs(after_state["top"] - before_state["top"]) >= 1
        grew = after_state["height"] > before_state["height"] + 2

        if moved or grew:
          no_progress_count = 0
        else:
          no_progress_count += 1

      if step % 10 == 0:
        top_before = int(before_state["top"])
        top_after = int(after_state["top"]) if after_state else "?"
        print(
          f"Шаг {step}: scrollTop={top_before} -> {top_after}, "
          f"noProgress={no_progress_count}/{NO_PROGRESS_LIMIT}"
        )

      if no_progress_count >= NO_PROGRESS_LIMIT:
        if ask_user_continue(f"Похоже, дошли до первого сообщения. Шагов: {step}."):
          no_progress_count = 0
          max_steps_current += STEP_EXTENSION
          print(f"Ок, продолжаю. Новый лимит шагов: {max_steps_current}")
        else:
          print(f"Остановлено пользователем на шаге {step}.")
          break

      if step >= max_steps_current:
        has_progress_now = no_progress_count < max(2, NO_PROGRESS_LIMIT // 2)
        if has_progress_now and auto_extensions_used < MAX_AUTO_EXTENSIONS:
          auto_extensions_used += 1
          max_steps_current += STEP_EXTENSION
          print(
            "Есть прогресс, увеличиваю лимит шагов до "
            f"{max_steps_current} (расширение {auto_extensions_used}/{MAX_AUTO_EXTENSIONS})"
          )
        else:
          if ask_user_continue("Достигнут лимит шагов без устойчивого прогресса."):
            max_steps_current += STEP_EXTENSION
            print(f"Ок, продолжаю. Новый лимит шагов: {max_steps_current}")
          else:
            print("Остановлено пользователем.")
            break

      if DEBUG_VISUAL and step % 25 == 0:
        safe_evaluate(page, HIGHLIGHT_CONTAINER_JS)
        print_target_debug(page)

    print("Готово. Браузер оставлен открытым для проверки.")
    input("Нажми Enter, чтобы закрыть браузер...")
    browser.close()


if __name__ == "__main__":
  main()