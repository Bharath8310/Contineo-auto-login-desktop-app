"""
Milestone 1 helper: dump form selectors from the Contineo login screens.

Read-only. It never types, clicks, or touches the captcha. YOU drive the browser;
this script only inspects the page structure at two moments you choose.

Usage:
    python tools/dump_selectors.py
Output is printed and also saved to tools/selectors_dump.txt.
Field *values* are never recorded (only option lists of dropdowns), so the
dump contains no USN / DOB / phone digits.
"""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://bnmit-students.contineo.in/parents/index.php"
OUT = Path(__file__).with_name("selectors_dump.txt")

# Runs inside the page: describes every form control in the document.
JS_DUMP = r"""
() => {
  const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const attrs = el => ({
    tag: el.tagName.toLowerCase(),
    id: el.id || null,
    name: el.getAttribute('name'),
    type: el.getAttribute('type'),
    class: el.className || null,
    placeholder: el.getAttribute('placeholder'),
    maxlength: el.getAttribute('maxlength'),
    text: (el.innerText || el.value || '').trim().slice(0, 40) || null,
    visible: visible(el),
  });
  const out = { title: document.title, url: location.href, forms: [], controls: [] };
  document.querySelectorAll('form').forEach(f => out.forms.push({
    id: f.id || null, name: f.getAttribute('name'),
    action: f.getAttribute('action'), method: f.getAttribute('method'),
  }));
  document.querySelectorAll('input, select, button, textarea, a.btn, [type=submit]').forEach(el => {
    const t = (el.getAttribute('type') || '').toLowerCase();
    if (el.tagName === 'INPUT' && t === 'hidden') {
      out.controls.push({ tag: 'input', type: 'hidden', id: el.id || null, name: el.getAttribute('name') });
      return;
    }
    const a = attrs(el);
    if (el.tagName === 'INPUT' && t !== 'submit' && t !== 'button') a.text = null; // never record typed values
    if (el.tagName === 'SELECT') {
      a.options = [...el.options].map(o => [o.value, o.text.trim()]);
    }
    out.controls.push(a);
  });
  const scripts = [...document.scripts].map(s => s.src).filter(s => /recaptcha|gstatic/.test(s));
  const iframes = [...document.querySelectorAll('iframe')].map(f => f.src).filter(Boolean);
  out.recaptcha = { scripts, iframes };
  return out;
}
"""


def dump(page, label: str) -> str:
    data = page.evaluate(JS_DUMP)
    lines = [f"\n===== {label} =====", f"url:   {data['url']}", f"title: {data['title']}"]
    lines.append(f"forms: {json.dumps(data['forms'])}")
    for c in data["controls"]:
        opts = c.pop("options", None)
        c = {k: v for k, v in c.items() if v not in (None, "", False) or k == "visible"}
        lines.append(json.dumps(c))
        if opts is not None:
            # Show every option; dropdowns like Year can be long but we need exact values.
            lines.append(f"    options ({len(opts)}): {json.dumps(opts)}")
    lines.append(f"recaptcha: {json.dumps(data['recaptcha'])}")
    return "\n".join(lines)


def main() -> None:
    report = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=False)
        page = browser.new_page()
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")

        report.append(dump(page, "SCREEN 1: LOGIN"))
        print(report[-1])

        input(
            "\n>>> Now log in MANUALLY in the Chrome window (USN, DOB, LOGIN).\n"
            ">>> When the 'Select Verification Type' screen is showing, press Enter here..."
        )
        report.append(dump(page, "SCREEN 2: VERIFICATION"))
        print(report[-1])

        input(
            "\n>>> Optional: finish verification manually. Once you're on the dashboard\n"
            ">>> press Enter (or just press Enter now to skip)..."
        )
        report.append(f"\n===== SCREEN 3: AFTER LOGIN =====\nurl:   {page.url}\ntitle: {page.title()}")
        print(report[-1])
        browser.close()

    OUT.write_text("\n".join(report), encoding="utf-8")
    print(f"\nSaved to {OUT}")


if __name__ == "__main__":
    main()
