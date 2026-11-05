import os
import io
import re
import logging
import requests
from flask import Flask, request, Response
from pydub import AudioSegment
import speech_recognition as sr

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)s | %(message)s")
app = Flask(__name__)

# הטוקן של ימות נשמר ב-Render כמשתנה סביבה, לא בקוד
YEMOT_TOKEN = os.environ.get("YEMOT_TOKEN", "")
DOWNLOAD_URL = "https://www.call2all.co.il/ym/api/DownloadFile"


def download_recording(value: str) -> bytes:
    """מוריד את ההקלטה. ימות שולחים נתיב כמו /9/000.wav"""
    if value.startswith("http"):
        r = requests.get(value, timeout=20)
    else:
        path = value if value.startswith("ivr2:") else "ivr2:" + value
        r = requests.get(DOWNLOAD_URL,
                         params={"token": YEMOT_TOKEN, "path": path},
                         timeout=20)
    logging.info("Download status: %s, size: %s", r.status_code, len(r.content))
    if r.status_code != 200 or len(r.content) < 100:
        logging.error("Download response: %s", r.text[:300])
        raise RuntimeError("download failed")
    return r.content


def transcribe(wav_bytes: bytes) -> str:
    audio = AudioSegment.from_file(io.BytesIO(wav_bytes), format="wav")
    silence = AudioSegment.silent(duration=1000)  # שנייה שקט בתחילה ובסוף
    audio = silence + audio + silence
    buf = io.BytesIO()
    audio.export(buf, format="wav")
    buf.seek(0)

    recognizer = sr.Recognizer()
    with sr.AudioFile(buf) as source:
        data = recognizer.record(source)
    try:
        return recognizer.recognize_google(data, language="he-IL")
    except sr.UnknownValueError:
        return ""


def clean(text: str) -> str:
    # תווים שמפריעים לפורמט התשובה של ימות
    return re.sub(r"[,.&=\-]", " ", text).strip()


@app.route("/")
def home():
    return "ok"


@app.route("/upload_audio", methods=["GET", "POST"])
def upload_audio():
    params = request.values
    logging.info("Params from Yemot: %s", dict(params))
    value = params.get("file_url", "")
    phone = params.get("ApiPhone", "")
    if not value:
        return Response("id_list_message=t-לא התקבלה הקלטה",
                        mimetype="text/plain; charset=utf-8")
    try:
        text = transcribe(download_recording(value))
        logging.info("Phone=%s | Text=%s", phone, text)
        if not text:
            return Response("id_list_message=t-לא זוהה דיבור",
                            mimetype="text/plain; charset=utf-8")
        return Response("id_list_message=t-זוהה " + clean(text),
                        mimetype="text/plain; charset=utf-8")
    except Exception as e:
        logging.exception("Error: %s", e)
        return Response("id_list_message=t-אירעה שגיאה",
                        mimetype="text/plain; charset=utf-8")
