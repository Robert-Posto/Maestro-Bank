"""DTO Pydantic pentru text-to-speech.

Extern (prin Gateway): POST /api/ai/speech — input `SpeechRequest`, output
audio MP3 brut (nu JSON — vezi app/routers/speech.py, Response cu
media_type="audio/mpeg").
"""

from pydantic import BaseModel, Field

from app.tts import MAX_TEXT_LENGTH


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)
