"""Email the morning update from the latest collected position."""
import html
import json
import os
import smtplib
import sys
from datetime import date, datetime, timezone
from email.message import EmailMessage
from pathlib import Path

import facts

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "docs" / "data"))


def page_url():
    url = os.environ.get("PAGE_URL")
    if url:
        return url
    owner, _, repo = os.environ.get("GITHUB_REPOSITORY", "").partition("/")
    return f"https://{owner}.github.io/{repo}/" if repo else ""


def age_words(seconds):
    hours = seconds / 3600
    if hours < 1:
        return "less than an hour ago"
    if hours < 48:
        return f"{round(hours)} hour{'s' if round(hours) != 1 else ''} ago"
    return f"{round(hours / 24)} days ago"


def port_today(config, today):
    for stop in config["itinerary"]:
        if stop["date"] == today.isoformat():
            return stop
    return None


def build_email(config, latest, today, now, url):
    """Return (subject, text lines, html body)."""
    ship = config["ship_name"]
    days_left = (date.fromisoformat(config["end_date"]) - today).days
    countdown = "Home today!" if days_left == 0 else f"{days_left} day{'s' if days_left != 1 else ''} until home."
    position = latest.get("position")
    lines = []

    if position:
        age = (now - datetime.fromisoformat(position["time"])).total_seconds()
        stale = age > 6 * 3600
        subject = f"🚢 {ship} is {latest['location']}" if not stale else f"🚢 {ship}: last seen {latest['location']}"
        lines.append(f"{'Last seen' if stale else 'Right now'}: {latest['location']}, in {latest['sea']}.")
        lines.append(f"Coordinates: {position['lat']:.3f}, {position['lon']:.3f} (position from {age_words(age)}).")
        if position.get("speed_knots") is not None:
            speed = position["speed_knots"]
            if speed < 1:
                lines.append("The ship is stopped or barely moving.")
            else:
                heading = position.get("heading")
                direction = f" heading {facts.compass_word(heading)}" if heading is not None else ""
                lines.append(f"Speed: {speed:.0f} knots ({speed * 1.15078:.0f} mph){direction}.")
        if stale:
            lines.append("There's no newer signal, which is common far from shore.")
        lines.append(f"Distance from Southampton: {latest['home_km']:,} km.")
    else:
        subject = f"🚢 {ship}: no position yet"
        lines.append("The tracker hasn't picked up a position yet.")

    stop = port_today(config, today)
    if stop:
        lines.append(f"Today's schedule: {stop['port']} ({stop['note']}).")
    lines.append(countdown)
    if latest.get("error"):
        lines.append(f"Tracker problem: {latest['error']}")

    featured = latest.get("facts", {}).get("featured")
    paragraphs = "".join(f"<p style='margin:0 0 8px'>{html.escape(line)}</p>" for line in lines)
    fact_block = ""
    if featured:
        lines += ["", f"Fun fact: {featured['text']}"]
        link = f" <a href='{html.escape(featured['url'], quote=True)}'>Read more</a>" if featured.get("url") else ""
        fact_block = (f"<p style='margin:16px 0;padding:12px 14px;background:#fff6cf;border-radius:8px'>"
                      f"<b>Fun fact:</b> {html.escape(featured['text'])}{link}</p>")
    button = ""
    if url:
        lines += ["", f"See the map: {url}"]
        button = (f"<p><a href='{html.escape(url, quote=True)}' style='background:#0b2545;color:#fff;padding:10px 16px;"
                  f"border-radius:8px;text-decoration:none;display:inline-block'>See the map</a></p>")
    body = (f"<div style='font-family:system-ui,sans-serif;font-size:16px;line-height:1.45;color:#0b2545;max-width:520px'>"
            f"<h2 style='margin:0 0 12px'>Good morning from {html.escape(ship)}</h2>"
            f"{paragraphs}{fact_block}{button}</div>")
    return subject, "\n".join(lines), body


def main():
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    today = now.date()
    if not date.fromisoformat(config["start_date"]) <= today <= date.fromisoformat(config["end_date"]):
        print("Outside the cruise dates, so no email today.")
        return
    latest = json.loads((DATA_DIR / "latest.json").read_text(encoding="utf-8"))
    subject, text, body = build_email(config, latest, today, now, page_url())

    if "--dry-run" in sys.argv:
        print(subject, text, sep="\n\n")
        return

    sender = os.environ["GMAIL_ADDRESS"]
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = os.environ.get("MAIL_TO") or sender
    message.set_content(text)
    message.add_alternative(body, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(sender, os.environ["GMAIL_APP_PASSWORD"])
        smtp.send_message(message)
    print("Email sent.")


if __name__ == "__main__":
    main()
