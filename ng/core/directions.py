"""What kind of video the one-button prompt makes, and whether anyone speaks.

H3-Context-IR, MiniMax's hosted preprocessing, turns loose input into a full prompt; it is not released. The Make H3 prompt
button is our version for people who do not want to write prompts: a direction ("music video", "fight", ...), whether
words are spoken, the Director's length and the Content cards are all it needs. The directions only steer planning and
writing; the H3 notation itself stays the compiler's and the checker's (part_prompt.py).
"""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Direction:
    label: str
    plan: str  # how the video is staged: story shape, pacing, camera
    write: str  # what the written description dwells on
    pace: tuple  # seconds per shot (shortest, longest)
    speech: str  # the speech setting the Studio picks with this direction
    music: str  # what non_diegetic_music should be when the user gave none


DIRECTIONS = {
    "auto": Direction(
        "Let the AI decide",
        "Choose the kind of scene that suits the pictures and the request best and stage it with a clear beginning, "
        "development and end.",
        "Balance appearance, action, light and sound.",
        (3.0, 6.0), "none", "a fitting score, or N/A for a quiet scene"),
    "music_video": Direction(
        "Music video",
        "A music video without words: strong images that follow the beat. Vary framing (close-up, medium, wide), let the "
        "subjects perform expressive movements, poses and gestures, light changes and atmospheric effects; cuts land on beats. "
        "Nobody tells a story with words.",
        "Describe rhythm in the movement and the light: motion that rises and falls with the music, accents on beats.",
        (2.0, 4.0), "none", "the driving score: instruments, tempo, rhythm and build"),
    "song": Direction(
        "Song (singing)",
        "A sung performance: the singer performs the lyrics to the camera or within the scene, with visible lip movement, "
        "breath and expression that follow the phrasing. Alternate performance close-ups with wider shots of the scene; cuts "
        "fall between sung lines, never inside one.",
        "Describe the singing performance: mouth and jaw shaping the words, breath, eyes, small head and hand accents on the "
        "phrasing.",
        (3.0, 6.0), "singing", "the accompaniment of the song: instruments and tempo"),
    "story": Direction(
        "Story",
        "A short story with a beginning, a turn and an end: establish the place and the character, show what they want or "
        "discover, end on a clear reaction or image. Each shot moves the story on.",
        "Describe the characters' intentions through visible action and facial expression.",
        (3.0, 6.0), "none", "a cinematic score that supports the story arc, or N/A"),
    "action": Direction(
        "Action / fight",
        "An action or fight scene: fast, physical, readable choreography. Attacks, dodges, impacts and reactions in clear "
        "cause and effect; dynamic camera (tracking, fast push-ins, slight shake on impacts); short shots, cuts on hits.",
        "Describe each move, its impact and the reaction concretely: weight, speed, sparks, debris, dust, cloth and hair "
        "in motion.",
        (1.5, 3.5), "none", "percussive, fast score with hits on the impacts"),
    "calm": Direction(
        "Calm scene",
        "A calm, atmospheric scene: few or slow movements, long shots, gentle camera (slow push-in, slow pan or static), "
        "small natural details (wind in hair, breathing, drifting light, particles).",
        "Describe light, texture, small motions and stillness; nothing sudden.",
        (5.0, 10.0), "none", "soft, slow ambient score, or N/A"),
    "dance": Direction(
        "Dance",
        "A dance performance: the subjects dance with clear, rhythmic full-body movement; show the whole body in wide and "
        "medium shots, accent moves in closer shots; the camera moves with the dance.",
        "Describe the dance moves step by step on the rhythm: arms, hips, turns, footwork, hair and cloth following.",
        (2.0, 4.0), "none", "an upbeat dance track: beat, tempo, bass"),
    "horror": Direction(
        "Horror / suspense",
        "Suspense or horror: slow build-up, darkness and partial visibility, something wrong in the frame, a sudden reveal "
        "or scare at the end. Low-key light, slow creeping camera, then a fast move on the reveal.",
        "Describe shadows, what is half seen, tense stillness, and the exact moment of the scare.",
        (3.0, 6.0), "none", "low drones and dissonant strings that swell before the reveal"),
    "comedy": Direction(
        "Comedy",
        "A light comic moment: a clear setup, a funny mishap or reaction, and a punchline beat. Expressive faces and timing; "
        "a reaction close-up after the gag.",
        "Describe comic timing: the pause before the gag, the exaggerated reaction.",
        (2.5, 5.0), "none", "light, playful score (pizzicato, woodwinds), or N/A"),
    "romance": Direction(
        "Romance",
        "A romantic, intimate moment between the characters: glances, closeness, touch, warm light; slow camera, close and "
        "medium shots.",
        "Describe glances, breathing, small touches, warm light on skin and hair.",
        (4.0, 8.0), "none", "warm, slow score (piano, strings)"),
    "spicy": Direction(
        "Spicy 18+",
        "An erotic scene between adults only: sensual, explicit if the request asks for it, with consent and desire clear in "
        "their expressions. Slow, intimate staging; close and medium shots; warm, soft light.",
        "Describe bodies, touch, clothing and its removal, movement and expressions of the adult characters directly and "
        "concretely, without euphemism and without moralizing.",
        (4.0, 8.0), "none", "slow, sensual score, or N/A"),
}

SPEECH = {
    "none": "No speech",
    "dialogue": "Dialogue",
    "voiceover": "Narrator (voice-over)",
    "singing": "Singing",
}

LANGUAGES = ("English", "German", "French", "Spanish", "Italian", "Japanese", "Chinese")

# Spicy 18+ is only ever about adults. A request or a card that speaks of a minor is refused before any AI sees it; the
# words below are the plain ones (English and German), not a filter of every euphemism - the AI is told the same rule.
MINOR_RE = re.compile(
    r"\b(child|children|kid|kids|minor|minors|underage|under-age|teen|teens|teenager|teenage|schoolgirl|schoolboy|"
    r"preteen|pre-teen|loli|lolita|shota|toddler|infant|baby|little girl|little boy|young girl|young boy|"
    r"kind|kinder|minderjährig\w*|jugendlich\w*|schulmädchen|schuljunge|teenie)\b"
    r"|\b(?:[1-9]|1[0-7])\s*(?:-|\s)?(?:years?[\s-]old|year-old|yo|jahre alt|jährig\w*)\b", re.I)


def direction(key):
    """The direction for a key; an unknown key (an older or edited workflow) is Let the AI decide."""
    return DIRECTIONS.get(key or "auto", DIRECTIONS["auto"])


def minors_named(*texts):
    """The words in the request or the cards that speak of a minor ("" when none)."""
    found = [match.group(0) for text in texts for match in MINOR_RE.finditer(text or "")]
    return ", ".join(dict.fromkeys(word.lower() for word in found))


def check_adults(key, *texts):
    """Spicy 18+ refuses a request that speaks of a minor, before the AI is asked."""
    if key != "spicy":
        return
    words = minors_named(*texts)
    if words:
        raise ValueError("Spicy 18+ is for adults only, and the request or a Content card speaks of a minor (%s). "
                         "Nothing was generated." % words)


def shot_count(seconds, key):
    """(fewest, most) shots for this length: the direction's pace, at least one shot."""
    shortest, longest = direction(key).pace
    return max(1, int(seconds // longest) or 1), max(1, int(round(seconds / shortest)))
