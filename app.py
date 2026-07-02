from __future__ import annotations

import base64
import io
import json
import os
import re
import textwrap
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, session
from openai import (
    APIError,
    AuthenticationError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)


HISTORY_FILE = Path(
    os.getenv(
        "HISTORY_FILE",
        "/tmp/hiresense_chat_history.json"
        if os.getenv("VERCEL")
        else "hiresense_chat_history.json",
    )
)
DEFAULT_MODEL = "gpt-5.2"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
XAI_BASE_URL = "https://api.x.ai/v1"
API_KEY_PLACEHOLDERS = {
    "your_api_key_here",
    "replace_with_your_api_key",
    "replace_with_your_gemini_api_key",
    "your_gemini_key",
    "gsk_your_groq_api_key_here",
    "your_groq_api_key",
    "your_openrouter_key",
}

SYSTEM_INSTRUCTIONS = """
You are HireSense AI, a practical career copilot for job seekers. You create
ATS-friendly resumes, portfolio content, HR interview simulations, technical
interview simulations, and hiring-readiness estimates.

Ground all advice in the candidate information provided. Do not invent degrees,
employers, dates, certifications, metrics, or projects. When useful information
is missing, write a clear placeholder like [add measurable result]. Keep output
specific, skimmable, and action-oriented.
""".strip()

GENERATION_TITLES = {
    "resume": "ATS resume",
    "portfolio": "portfolio content",
    "score": "hiring probability score",
}

WORKSPACES: dict[str, dict[str, Any]] = {}
PDF_PAGE_WIDTH = 612
PDF_PAGE_HEIGHT = 792
PDF_MARGIN_X = 54
PDF_START_Y = 744
PDF_LINE_HEIGHT = 14
PDF_LINES_PER_PAGE = 50
PDF_WRAP_WIDTH = 88


@dataclass
class CandidateProfile:
    name: str = ""
    target_role: str = ""
    city: str = ""
    state: str = ""
    location: str = ""
    phone_country_code: str = "+91"
    phone: str = ""
    email: str = ""
    linkedin: str = ""
    profile_photo: str = ""
    resume_theme: str = "modern"
    degree_name: str = ""
    college_name: str = ""
    university_name: str = ""
    degree_year: str = ""
    degree_score: str = ""
    hsc_school: str = ""
    hsc_year: str = ""
    hsc_score: str = ""
    sslc_school: str = ""
    sslc_year: str = ""
    sslc_score: str = ""
    skills: str = ""
    candidate_notes: str = ""
    job_description: str = ""

    def has_context(self) -> bool:
        return bool(
            self.name
            or self.target_role
            or self.city
            or self.state
            or self.location
            or self.phone_country_code
            or self.phone
            or self.email
            or self.linkedin
            or self.profile_photo
            or self.resume_theme
            or self.degree_name
            or self.college_name
            or self.university_name
            or self.degree_year
            or self.degree_score
            or self.hsc_school
            or self.hsc_year
            or self.hsc_score
            or self.sslc_school
            or self.sslc_year
            or self.sslc_score
            or self.skills
            or self.candidate_notes
            or self.job_description
        )

    def to_context(self) -> str:
        return "\n".join(
            [
                f"Candidate name: {self.name or '[not provided]'}",
                f"Target role: {self.target_role or '[not provided]'}",
                f"City: {self.city or '[not provided]'}",
                f"State: {self.state or '[not provided]'}",
                f"City/State: {self.location or self.display_location() or '[not provided]'}",
                f"Phone country code: {self.phone_country_code or '[not provided]'}",
                f"Phone number: {self.display_phone() or '[not provided]'}",
                f"Email address: {self.email or '[not provided]'}",
                f"LinkedIn/profile link: {self.linkedin or '[not provided]'}",
                f"Profile picture: {'provided' if self.profile_photo else '[not provided]'}",
                f"Resume model/theme: {self.resume_theme or 'modern'}",
                "Education details:",
                f"Bachelor's degree: {self.degree_name or '[not provided]'}",
                f"College: {self.college_name or '[not provided]'}",
                f"University: {self.university_name or '[not provided]'}",
                f"Bachelor's year: {self.degree_year or '[not provided]'}",
                f"Bachelor's CGPA/Percentage: {self.degree_score or '[not provided]'}",
                f"Higher Secondary school: {self.hsc_school or '[not provided]'}",
                f"Higher Secondary year: {self.hsc_year or '[not provided]'}",
                f"Higher Secondary percentage: {self.hsc_score or '[not provided]'}",
                f"SSLC school: {self.sslc_school or '[not provided]'}",
                f"SSLC year: {self.sslc_year or '[not provided]'}",
                f"SSLC percentage: {self.sslc_score or '[not provided]'}",
                "Skills:",
                self.skills or "[not provided]",
                "Candidate profile/resume notes:",
                self.candidate_notes or "[not provided]",
                "Target job description:",
                self.job_description or "[not provided]",
            ]
        )

    def display_location(self) -> str:
        parts = [part for part in (self.city, self.state) if part]
        return ", ".join(parts)

    def display_phone(self) -> str:
        if not self.phone:
            return ""

        if self.phone.startswith("+"):
            return self.phone

        return f"{self.phone_country_code} {self.phone}".strip()


def create_app() -> Flask:
    load_dotenv(override=True)
    flask_app = Flask(__name__)
    flask_app.secret_key = os.getenv("FLASK_SECRET_KEY", "hiresense-local-dev")
    register_routes(flask_app)
    return flask_app


def load_history() -> list[dict[str, str]]:
    if not HISTORY_FILE.exists():
        return []

    try:
        history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    if not isinstance(history, list):
        return []

    clean_history: list[dict[str, str]] = []
    for item in history:
        if (
            isinstance(item, dict)
            and item.get("role") in {"user", "assistant"}
            and isinstance(item.get("content"), str)
        ):
            clean_history.append({"role": item["role"], "content": item["content"]})

    return clean_history


def save_history(history: list[dict[str, str]]) -> None:
    HISTORY_FILE.write_text(
        json.dumps(history, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def looks_like_placeholder(api_key: str) -> bool:
    normalized_key = api_key.strip().strip("\"'").lower()
    return (
        normalized_key in API_KEY_PLACEHOLDERS
        or "replace" in normalized_key
        or normalized_key.startswith("your_")
    )


def get_api_key() -> str | None:
    base_url = os.getenv("OPENAI_BASE_URL", "").strip().lower()
    if "generativelanguage.googleapis.com" in base_url:
        env_order = ("GEMINI_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY")
    elif "api.groq.com" in base_url:
        env_order = ("GROQ_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY")
    else:
        env_order = ("GROQ_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY")

    for env_name in env_order:
        api_key = os.getenv(env_name, "").strip()
        if not api_key or looks_like_placeholder(api_key):
            continue

        return api_key

    return None


def is_groq_api(api_key: str | None, base_url: str | None = None) -> bool:
    normalized_base_url = (base_url or os.getenv("OPENAI_BASE_URL", "")).strip().lower()
    return bool(
        (api_key and api_key.startswith("gsk_"))
        or "api.groq.com" in normalized_base_url
    )


def get_model(api_key: str | None) -> str:
    configured_model = (
        os.getenv("GROQ_MODEL", "").strip()
        if is_groq_api(api_key)
        else os.getenv("OPENAI_MODEL", "").strip()
    )
    if configured_model:
        if api_key and api_key.startswith("xai-") and configured_model.startswith("gemini-"):
            return "grok-4.20-non-reasoning"
        return configured_model

    base_url = os.getenv("OPENAI_BASE_URL", "").strip().lower()
    if is_groq_api(api_key, base_url):
        return DEFAULT_GROQ_MODEL

    if api_key and api_key.startswith("xai-"):
        return "grok-4.20-non-reasoning"

    if api_key and (
        api_key.startswith("AIza") or "generativelanguage.googleapis.com" in base_url
    ):
        return DEFAULT_GEMINI_MODEL

    return DEFAULT_MODEL


def get_base_url(api_key: str) -> str:
    base_url = os.getenv("OPENAI_BASE_URL", "").strip()
    if is_groq_api(api_key, base_url):
        return base_url or GROQ_BASE_URL
    if api_key.startswith("xai-"):
        return XAI_BASE_URL
    if not base_url and api_key.startswith("sk-or-v1-"):
        return OPENROUTER_BASE_URL
    if not base_url and api_key.startswith("AIza"):
        return GEMINI_BASE_URL
    return base_url


def create_client(api_key: str) -> OpenAI:
    base_url = get_base_url(api_key)

    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)

    return OpenAI(api_key=api_key)


def using_chat_completions(api_key: str, base_url: str | None) -> bool:
    return api_key.startswith("sk-or-v1-") or bool(base_url)


def ask_ai(
    messages: list[dict[str, str]],
    instructions: str = SYSTEM_INSTRUCTIONS,
) -> str:
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError(
            "No real API key is configured. Add GROQ_API_KEY, OPENAI_API_KEY, "
            "or GEMINI_API_KEY to your .env file."
        )

    client = create_client(api_key)
    model = get_model(api_key)
    base_url = get_base_url(api_key)

    for attempt in range(3):
        try:
            if using_chat_completions(api_key, base_url):
                chat_messages = [{"role": "system", "content": instructions}, *messages]
                response = client.chat.completions.create(
                    model=model,
                    messages=chat_messages,
                )
                return (response.choices[0].message.content or "").strip()

            response = client.responses.create(
                model=model,
                instructions=instructions,
                input=messages,
            )
            return response.output_text.strip()
        except APIError as error:
            if attempt < 2 and is_temporary_model_error(error):
                time.sleep(1.5 * (attempt + 1))
                continue
            raise

    raise RuntimeError("The AI model did not return a response.")


def is_temporary_model_error(error: APIError) -> bool:
    error_text = str(error).lower()
    status_code = getattr(error, "status_code", None)
    return (
        status_code in {429, 500, 502, 503, 504}
        or "high demand" in error_text
        or "temporarily" in error_text
        or "unavailable" in error_text
    )


def api_error_response(error: Exception) -> tuple[Any, int]:
    error_text = str(error).lower()

    if isinstance(error, AuthenticationError):
        return (
            jsonify(
                {
                    "error": (
                        "Authentication failed. Check that your API key belongs "
                        "to the selected provider and is active."
                    )
                }
            ),
            401,
        )

    if isinstance(error, PermissionDeniedError):
        if "credits" in error_text or "licenses" in error_text:
            return (
                jsonify(
                    {
                        "error": (
                            "Your xAI key is valid, but the xAI team has no credits "
                            "or licenses yet. Add credits in the xAI Console, then restart the app."
                        )
                    }
                ),
                403,
            )

        return (
            jsonify(
                {
                    "error": (
                        "The API provider denied access for this key. Check model access, "
                        "project/team permissions, credits, and billing."
                    )
                }
            ),
            403,
        )

    if isinstance(error, RateLimitError):
        if "quota exceeded" in error_text or "resource_exhausted" in error_text:
            model_env_name = "GROQ_MODEL" if is_groq_api(get_api_key()) else "OPENAI_MODEL"
            return (
                jsonify(
                    {
                        "error": (
                            "Your API key is valid, but its quota is exhausted "
                            "for the selected model. Wait for quota reset, check billing, "
                            f"or switch {model_env_name} in .env to another available model."
                        )
                    }
                ),
                429,
            )

        return (
            jsonify(
                {
                    "error": (
                        "The request was rejected for quota or rate limits. "
                        "Check billing credits, monthly budget, and rate limits."
                    )
                }
            ),
            429,
        )

    if isinstance(error, APIError):
        if is_temporary_model_error(error):
            return (
                jsonify(
                    {
                        "error": (
                            "The AI model is temporarily busy or unavailable. "
                            "Please wait a minute and try again. If it keeps happening, "
                            "switch OPENAI_MODEL or GROQ_MODEL in .env to another available "
                            "model and restart the app."
                        )
                    }
                ),
                503,
            )

        if "api key not valid" in error_text or "api_key_invalid" in error_text:
            return (
                jsonify(
                    {
                        "error": (
                            "Your API key is not valid for the selected provider. "
                            "Replace it in .env, then restart the web app."
                        )
                    }
                ),
                400,
            )

        return jsonify({"error": f"API request failed: {error}"}), 502

    if isinstance(error, RuntimeError):
        return jsonify({"error": str(error)}), 400

    return jsonify({"error": "Unexpected server error."}), 500


def get_workspace() -> dict[str, Any]:
    workspace_id = session.get("workspace_id")
    if not workspace_id:
        workspace_id = uuid.uuid4().hex
        session["workspace_id"] = workspace_id

    if workspace_id not in WORKSPACES:
        WORKSPACES[workspace_id] = {
            "profile": CandidateProfile(),
            "chat_history": load_history(),
            "interview": None,
        }

    return WORKSPACES[workspace_id]


def get_profile() -> CandidateProfile:
    return get_workspace()["profile"]


def profile_from_payload(payload: dict[str, Any]) -> CandidateProfile:
    city = str(payload.get("city", "")).strip()
    state = str(payload.get("state", "")).strip()
    location = str(payload.get("location", "")).strip()
    if not location:
        location = ", ".join(part for part in (city, state) if part)

    return CandidateProfile(
        name=str(payload.get("name", "")).strip(),
        target_role=str(payload.get("target_role", "")).strip(),
        city=city,
        state=state,
        location=location,
        phone_country_code=str(payload.get("phone_country_code", "+91")).strip(),
        phone=str(payload.get("phone", "")).strip(),
        email=str(payload.get("email", "")).strip(),
        linkedin=str(payload.get("linkedin", "")).strip(),
        profile_photo=str(payload.get("profile_photo", "")).strip(),
        resume_theme=str(payload.get("resume_theme", "modern")).strip() or "modern",
        degree_name=str(payload.get("degree_name", "")).strip(),
        college_name=str(payload.get("college_name", "")).strip(),
        university_name=str(payload.get("university_name", "")).strip(),
        degree_year=str(payload.get("degree_year", "")).strip(),
        degree_score=str(payload.get("degree_score", "")).strip(),
        hsc_school=str(payload.get("hsc_school", "")).strip(),
        hsc_year=str(payload.get("hsc_year", "")).strip(),
        hsc_score=str(payload.get("hsc_score", "")).strip(),
        sslc_school=str(payload.get("sslc_school", "")).strip(),
        sslc_year=str(payload.get("sslc_year", "")).strip(),
        sslc_score=str(payload.get("sslc_score", "")).strip(),
        skills=str(payload.get("skills", "")).strip(),
        candidate_notes=str(payload.get("candidate_notes", "")).strip(),
        job_description=str(payload.get("job_description", "")).strip(),
    )


def require_profile() -> CandidateProfile:
    profile = get_profile()
    if not profile.has_context():
        raise RuntimeError("Add candidate profile details before generating.")
    return profile


def generation_prompt(kind: str, profile: CandidateProfile) -> str:
    if kind == "resume":
        return f"""
Build a polished, professional, ATS-optimized resume for this candidate.

Output:
1. Resume header with candidate name, city/state, phone, email, and LinkedIn/profile link
2. Professional title line
3. Professional summary
4. Core skills grouped by category
5. Projects section with professional bullet points
6. Education section with Bachelor's Degree, Higher Secondary (12th), and SSLC (10th)
7. Experience section, if relevant

Rules:
- Use plain formatting that copies well into a document.
- Use clean section headings with no markdown symbols such as ###.
- Put contact details on one clean line below the name.
- Use the provided city/state, phone number, email address, and LinkedIn/profile link when available.
- Keep bullets concise, action-led, and measurable.
- Make the resume sound suitable for a fresher/early-career candidate if no formal experience is provided.
- For projects, describe problem, tools, implementation, and outcome.
- Use the structured education fields exactly where provided.
- Do not include an ATS keyword alignment table.
- Do not include a missing information checklist.
- Format education similar to:
  Education
  Bachelor's Degree Name
  College Name, University Name - Year
  CGPA/Percentage: value
  Higher Secondary (12th)
  School Name - Year
  Percentage: value
  SSLC (10th)
  School Name - Year
  Percentage: value
- Create a separate Skills section using the provided skills list.
- Do not invent facts; use placeholders for missing metrics.

Candidate context:
{profile.to_context()}
""".strip()

    if kind == "portfolio":
        return f"""
Create portfolio content for this candidate.

Output:
1. Homepage hero headline and subheading
2. About section
3. Featured skills section
4. Three project case-study templates using available projects
5. GitHub profile bio
6. LinkedIn About section
7. Contact CTA
8. Content gaps to fill before publishing

Rules:
- Make the tone confident, specific, and recruiter-friendly.
- Do not invent project names or results. Use placeholders where needed.

Candidate context:
{profile.to_context()}
""".strip()

    if kind == "score":
        return f"""
Estimate this candidate's hiring readiness for the target role.

Important: This is a coaching estimate, not a guarantee of hiring outcomes.

Output:
1. Hiring probability score from 0 to 100
2. Probability band: Low, Emerging, Competitive, Strong, or Interview-ready
3. Score breakdown:
   - Role alignment
   - ATS keyword match
   - Evidence strength
   - Portfolio strength
   - Interview readiness
4. Top 5 blockers
5. Highest-impact fixes in priority order
6. 7-day action plan
7. Recruiter-facing summary after improvements

Candidate context:
{profile.to_context()}
""".strip()

    raise RuntimeError("Unknown generation type.")


def interview_instructions(interview_type: str, role: str) -> str:
    return f"""
You are HireSense AI running a realistic {interview_type} interview for {role}.
Ask one question at a time. After each candidate answer, give concise feedback
and ask the next question. Be supportive but rigorous. Do not reveal an ideal
answer until the final evaluation.
""".strip()


def final_interview_prompt() -> str:
    return """
Now end the simulation with a final interview evaluation.

Output:
1. Overall interview score from 0 to 100
2. Hire/no-hire recommendation for practice purposes
3. Strengths observed
4. Weak answer patterns
5. Better sample answer structure
6. Three practice drills
""".strip()


def pdf_safe_text(value: str) -> str:
    return "".join(char if 32 <= ord(char) <= 126 else " " for char in value)


def pdf_escape(value: str) -> str:
    return (
        pdf_safe_text(value)
        .replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )


def clean_pdf_line(value: str) -> str:
    line = value.strip()
    line = re.sub(r"^#{1,6}\s*", "", line)
    line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
    line = re.sub(r"^\*\s+", "- ", line)
    line = re.sub(r"^[-]{3,}$", "", line)
    return line.strip()


def content_to_pdf_lines(content: str) -> list[str]:
    lines: list[str] = []
    for raw_line in content.replace("\r\n", "\n").split("\n"):
        clean_line = clean_pdf_line(raw_line)
        if not clean_line:
            lines.append("")
            continue

        wrapped_lines = textwrap.wrap(
            clean_line,
            width=PDF_WRAP_WIDTH,
            replace_whitespace=False,
            drop_whitespace=False,
        )
        lines.extend(wrapped_lines or [""])

    return lines or ["No content available."]


def profile_contact_line(profile: dict[str, Any]) -> str:
    city = str(profile.get("city", "")).strip()
    state = str(profile.get("state", "")).strip()
    location = str(profile.get("location", "")).strip()
    if not location:
        location = ", ".join(part for part in (city, state) if part)

    phone = str(profile.get("phone", "")).strip()
    phone_country_code = str(profile.get("phone_country_code", "")).strip()
    if phone and not phone.startswith("+"):
        phone = f"{phone_country_code} {phone}".strip()

    items = [
        location,
        phone,
        str(profile.get("email", "")).strip(),
        str(profile.get("linkedin", "")).strip(),
    ]
    return " | ".join(item for item in items if item)


def profile_photo_pdf_image(profile_photo: str) -> dict[str, Any] | None:
    if not profile_photo.startswith("data:image/") or "," not in profile_photo:
        return None

    try:
        from PIL import Image, ImageOps
    except ImportError:
        return None

    try:
        _, encoded_image = profile_photo.split(",", 1)
        image_bytes = base64.b64decode(encoded_image, validate=True)
        with Image.open(io.BytesIO(image_bytes)) as image:
            size = 320
            background = Image.new("RGB", (size, size), (232, 237, 226))
            fitted = ImageOps.fit(image.convert("RGB"), (size, size))
            mask = Image.new("L", (size, size), 0)
            from PIL import ImageDraw

            ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
            background.paste(fitted, mask=mask)
            buffer = io.BytesIO()
            background.save(buffer, format="JPEG", quality=90, optimize=True)
    except Exception:
        return None

    return {
        "width": 320,
        "height": 320,
        "bytes": buffer.getvalue(),
    }


def draw_pdf_text(
    stream_lines: list[str],
    x: float,
    y: float,
    text: str,
    size: int = 10,
    font: str = "F1",
    color: tuple[float, float, float] = (0.16, 0.36, 0.36),
) -> None:
    r, g, b = color
    stream_lines.extend(
        [
            "BT",
            f"/{font} {size} Tf",
            f"{r:.3f} {g:.3f} {b:.3f} rg",
            f"{x:.1f} {y:.1f} Td",
            f"({pdf_escape(text)}) Tj",
            "ET",
        ]
    )


def draw_pdf_wrapped_text(
    stream_lines: list[str],
    x: float,
    y: float,
    text: str,
    width: int,
    size: int = 9,
    leading: int = 12,
    font: str = "F1",
    color: tuple[float, float, float] = (0.20, 0.40, 0.40),
    max_lines: int = 20,
) -> float:
    lines: list[str] = []
    for paragraph in text.splitlines() or [text]:
        clean = clean_pdf_line(paragraph)
        if not clean:
            lines.append("")
            continue
        lines.extend(
            textwrap.wrap(clean, width=width, replace_whitespace=False)
            or [clean]
        )

    for line in lines[:max_lines]:
        draw_pdf_text(stream_lines, x, y, line, size=size, font=font, color=color)
        y -= leading
    return y


def draw_pdf_section_title(stream_lines: list[str], x: float, y: float, title: str) -> float:
    teal = (0.10, 0.50, 0.52)
    draw_pdf_text(stream_lines, x, y, title, size=24, font="F2", color=teal)
    stream_lines.extend(
        [
            "0.10 0.50 0.52 RG",
            "1.6 w",
            f"{x:.1f} {y - 8:.1f} m",
            f"{x + 190:.1f} {y - 8:.1f} l",
            "S",
            *pdf_circle_path(x + 195, y - 8, 4),
            "S",
        ]
    )
    return y - 32


def pdf_circle_path(cx: float, cy: float, radius: float) -> list[str]:
    k = radius * 0.5522847498
    return [
        f"{cx:.1f} {cy + radius:.1f} m",
        f"{cx + k:.1f} {cy + radius:.1f} {cx + radius:.1f} {cy + k:.1f} {cx + radius:.1f} {cy:.1f} c",
        f"{cx + radius:.1f} {cy - k:.1f} {cx + k:.1f} {cy - radius:.1f} {cx:.1f} {cy - radius:.1f} c",
        f"{cx - k:.1f} {cy - radius:.1f} {cx - radius:.1f} {cy - k:.1f} {cx - radius:.1f} {cy:.1f} c",
        f"{cx - radius:.1f} {cy + k:.1f} {cx - k:.1f} {cy + radius:.1f} {cx:.1f} {cy + radius:.1f} c",
    ]


def candidate_pdf_contact_items(profile: dict[str, Any]) -> list[str]:
    city = str(profile.get("city", "")).strip()
    state = str(profile.get("state", "")).strip()
    location = str(profile.get("location", "")).strip()
    if not location:
        location = ", ".join(part for part in (city, state) if part)

    phone = str(profile.get("phone", "")).strip()
    phone_country_code = str(profile.get("phone_country_code", "")).strip()
    if phone and not phone.startswith("+"):
        phone = f"{phone_country_code} {phone}".strip()

    return [
        item
        for item in [
            phone,
            str(profile.get("email", "")).strip(),
            location,
            str(profile.get("linkedin", "")).strip(),
        ]
        if item
    ]


def resume_pdf_sections(content: str, profile: dict[str, Any]) -> dict[str, list[str]]:
    section_aliases = {
        "professional summary": "Profile",
        "summary": "Profile",
        "profile": "Profile",
        "core skills": "Skills",
        "skills": "Skills",
        "technical skills": "Skills",
        "education": "Education",
        "experience": "Experience",
        "work experience": "Experience",
        "projects": "Experience",
        "project": "Experience",
    }
    sections: dict[str, list[str]] = {}
    current = "Profile"
    profile_values = {
        str(profile.get("name", "")).strip().lower(),
        str(profile.get("target_role", "")).strip().lower(),
        profile_contact_line(profile).lower(),
    }

    for raw_line in content.replace("\r\n", "\n").split("\n"):
        line = clean_pdf_line(raw_line)
        if not line:
            continue

        normalized = line.rstrip(":").lower()
        if normalized in profile_values or any(
            value and value in normalized for value in profile_values
        ):
            continue

        if normalized in section_aliases:
            current = section_aliases[normalized]
            sections.setdefault(current, [])
            continue

        sections.setdefault(current, []).append(line)

    return sections


def build_pdf(title: str, content: str, profile: dict[str, Any] | None = None) -> bytes:
    profile = profile or {}
    sections = resume_pdf_sections(content, profile)
    photo_image = profile_photo_pdf_image(str(profile.get("profile_photo", "")).strip())

    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    ]
    photo_ref = ""
    if photo_image:
        objects.append(
            (
                f"<< /Type /XObject /Subtype /Image /Width {photo_image['width']} "
                f"/Height {photo_image['height']} /ColorSpace /DeviceRGB "
                f"/BitsPerComponent 8 /Filter /DCTDecode /Length {len(photo_image['bytes'])} >>\n"
                "stream\n"
            ).encode("latin-1")
            + photo_image["bytes"]
            + b"\nendstream"
        )
        photo_ref = f"{len(objects)} 0 R"

    name = str(profile.get("name", "")).strip() or "Candidate Name"
    role = str(profile.get("target_role", "")).strip() or "Target Role"
    initials = "".join(part[:1] for part in name.split()[:2]).upper() or "HS"
    teal = (0.10, 0.50, 0.52)
    dark_teal = (0.08, 0.37, 0.38)
    body_color = (0.20, 0.40, 0.40)

    stream_lines: list[str] = [
        "0.04 0.05 0.07 rg",
        "0 0 612 792 re f",
        "0.90 0.93 0.88 rg",
        "26 58 560 650 re f",
        "0.78 0.88 0.86 rg",
        "26 58 m 220 58 l 26 126 l h f",
        "0.83 0.91 0.89 rg",
        "586 58 m 380 58 l 586 160 l h f",
    ]

    if photo_ref:
        stream_lines.extend(
            [
                "q",
                "150 0 0 150 48 575 cm",
                "/Im1 Do",
                "Q",
            ]
        )
    else:
        stream_lines.extend(["0.76 0.86 0.84 rg", *pdf_circle_path(123, 650, 75), "f"])
        draw_pdf_text(stream_lines, 103, 642, initials, size=26, font="F2", color=teal)

    stream_lines.extend(
        [
            "0.10 0.50 0.52 RG",
            "8 w",
            *pdf_circle_path(123, 650, 78),
            "S",
            "1.6 w",
            "198 648 m 586 648 l S",
            *pdf_circle_path(202, 648, 4),
            "S",
        ]
    )
    draw_pdf_text(stream_lines, 245, 665, name, size=28, font="F2", color=dark_teal)
    draw_pdf_text(stream_lines, 275, 626, role, size=20, font="F2", color=dark_teal)

    left_x = 80
    right_x = 316
    left_y = 540
    right_y = 540

    left_y = draw_pdf_section_title(stream_lines, left_x, left_y, "Contact")
    for item in candidate_pdf_contact_items(profile):
        stream_lines.extend(["0.10 0.50 0.52 rg", f"{left_x:.1f} {left_y + 3:.1f} 8 8 re f"])
        left_y = draw_pdf_wrapped_text(
            stream_lines,
            left_x + 22,
            left_y,
            item,
            width=28,
            size=9,
            leading=12,
            color=body_color,
            max_lines=2,
        ) - 4

    education_lines = sections.get("Education", [])
    if not education_lines:
        education_lines = [
            value
            for value in [
                str(profile.get("degree_year", "")).strip(),
                str(profile.get("degree_name", "")).strip(),
                str(profile.get("college_name", "")).strip(),
                str(profile.get("university_name", "")).strip(),
                str(profile.get("degree_score", "")).strip(),
            ]
            if value
        ]
    left_y -= 8
    left_y = draw_pdf_section_title(stream_lines, left_x, left_y, "Education")
    left_y = draw_pdf_wrapped_text(
        stream_lines,
        left_x,
        left_y,
        "\n".join(education_lines[:8]) or "Education details available on request.",
        width=30,
        size=9,
        leading=12,
        color=body_color,
        max_lines=11,
    )

    skills_text = "\n".join(sections.get("Skills", [])) or str(profile.get("skills", "")).strip()
    left_y -= 10
    left_y = draw_pdf_section_title(stream_lines, left_x, left_y, "Skills")
    skill_items = [item.strip(" -") for item in re.split(r"[\n,;]+", skills_text) if item.strip()]
    for item in skill_items[:7]:
        draw_pdf_text(stream_lines, left_x, left_y, item[:26], size=9, font="F2", color=body_color)
        stream_lines.extend(
            [
                "0.63 0.80 0.77 rg",
                f"{left_x + 100:.1f} {left_y - 2:.1f} 70 5 re f",
                "0.10 0.50 0.52 rg",
                f"{left_x + 100:.1f} {left_y - 2:.1f} 45 5 re f",
            ]
        )
        left_y -= 18

    right_y = draw_pdf_section_title(stream_lines, right_x, right_y, "Profile")
    right_y = draw_pdf_wrapped_text(
        stream_lines,
        right_x,
        right_y,
        " ".join(sections.get("Profile", [])) or content,
        width=42,
        size=10,
        leading=13,
        color=body_color,
        max_lines=10,
    )

    experience_lines = sections.get("Experience", [])
    if not experience_lines:
        experience_lines = [
            line
            for line in [
                "Project Experience",
                str(profile.get("candidate_notes", "")).strip(),
            ]
            if line
        ]
    right_y -= 18
    right_y = draw_pdf_section_title(stream_lines, right_x, right_y, "Experience")
    draw_pdf_wrapped_text(
        stream_lines,
        right_x,
        right_y,
        "\n".join(experience_lines[:18]) or "Add project or internship experience.",
        width=42,
        size=9,
        leading=12,
        color=body_color,
        max_lines=23,
    )

    stream = "\n".join(stream_lines).encode("latin-1", errors="replace")
    page_object_id = len(objects) + 1
    stream_object_id = page_object_id + 1
    resources = "/Font << /F1 3 0 R /F2 4 0 R >>"
    if photo_ref:
        resources += f" /XObject << /Im1 {photo_ref} >>"
    page = (
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PDF_PAGE_WIDTH} {PDF_PAGE_HEIGHT}] "
        f"/Resources << {resources} >> /Contents {stream_object_id} 0 R >>"
    ).encode("latin-1")
    stream_object = (
        b"<< /Length "
        + str(len(stream)).encode("ascii")
        + b" >>\nstream\n"
        + stream
        + b"\nendstream"
    )
    objects.extend([page, stream_object])
    objects[1] = f"<< /Type /Pages /Kids [{page_object_id} 0 R] /Count 1 >>".encode("latin-1")

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{object_id} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))

    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


def safe_filename(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip()).strip("-").lower()
    return clean or "hiresense-output"


def count_skill_items(skills: str) -> int:
    if not skills.strip():
        return 0

    items = re.split(r"[\n,;]+", skills)
    return len([item for item in items if item.strip()])


def local_hiring_score(profile: CandidateProfile) -> str:
    skill_count = count_skill_items(profile.skills)
    project_ready = bool(profile.candidate_notes.strip())
    education_ready = bool(profile.degree_name and profile.college_name)
    contact_ready = bool(profile.email and profile.phone and profile.display_location())
    portfolio_ready = bool(profile.linkedin)

    score = 20
    score += 15 if contact_ready else 6
    score += min(20, skill_count * 3)
    score += 18 if education_ready else 8
    score += 18 if project_ready else 4
    score += 10 if portfolio_ready else 3
    score = min(score, 100)

    if score >= 85:
        band = "Interview-ready"
    elif score >= 72:
        band = "Strong"
    elif score >= 58:
        band = "Competitive"
    elif score >= 42:
        band = "Emerging"
    else:
        band = "Low"

    blockers = []
    if not contact_ready:
        blockers.append("Complete city/state, phone number, and email address.")
    if skill_count < 6:
        blockers.append("Add at least 6-10 role-relevant skills.")
    if not project_ready:
        blockers.append("Add project details with tools, features, and outcomes.")
    if not education_ready:
        blockers.append("Complete degree, college, and education details.")
    if not portfolio_ready:
        blockers.append("Add LinkedIn, GitHub, or portfolio profile link.")

    if not blockers:
        blockers.append("Add measurable project outcomes to make the profile stronger.")

    return f"""
Hiring Probability Score: {score}/100
Probability Band: {band}

Note: The AI model was temporarily busy, so this is an offline coaching estimate based on the profile fields you entered.

Score Breakdown
- Role alignment: {'Strong' if profile.target_role else 'Needs target role'}
- ATS keyword match: {'Good foundation' if skill_count >= 6 else 'Needs more skills'}
- Evidence strength: {'Project evidence present' if project_ready else 'Needs project evidence'}
- Portfolio strength: {'Profile link present' if portfolio_ready else 'Needs LinkedIn/GitHub/portfolio link'}
- Interview readiness: {'Ready to practice' if score >= 60 else 'Build profile details first'}

Top Blockers
{chr(10).join(f"- {item}" for item in blockers[:5])}

Highest-Impact Fixes
- Add project bullets with problem, tools, implementation, and result.
- Match skills to the selected target role: {profile.target_role or '[target role]'}.
- Keep education details complete: degree, institution, year, and percentage/CGPA.
- Add a polished LinkedIn or portfolio link.

7-Day Action Plan
- Day 1: Finalize contact, education, and skills.
- Day 2: Write 2-3 project descriptions.
- Day 3: Add measurable outcomes or clear placeholders.
- Day 4: Generate and review the ATS resume.
- Day 5: Create portfolio content.
- Day 6: Practice HR interview answers.
- Day 7: Practice technical interview answers and revise weak areas.
""".strip()


def register_routes(flask_app: Flask) -> None:
    @flask_app.get("/")
    def index() -> str:
        api_key = get_api_key()
        return render_template(
            "index.html",
            model=get_model(api_key),
            api_configured=bool(api_key),
        )

    @flask_app.get("/api/state")
    def state() -> Any:
        api_key = get_api_key()
        workspace = get_workspace()
        return jsonify(
            {
                "api_configured": bool(api_key),
                "model": get_model(api_key),
                "profile": asdict(workspace["profile"]),
                "chat_history": workspace["chat_history"][-12:],
            }
        )

    @flask_app.post("/api/profile")
    def save_profile() -> Any:
        payload = request.get_json(silent=True) or {}
        profile = profile_from_payload(payload)
        get_workspace()["profile"] = profile
        return jsonify({"ok": True, "profile": asdict(profile)})

    @flask_app.post("/api/generate")
    def generate() -> Any:
        payload = request.get_json(silent=True) or {}
        kind = str(payload.get("type", "")).strip().lower()
        if kind not in GENERATION_TITLES:
            return jsonify({"error": "Choose resume, portfolio, or score."}), 400

        try:
            profile = require_profile()
            prompt = generation_prompt(kind, profile)
            try:
                result = ask_ai([{"role": "user", "content": prompt}])
            except APIError as error:
                if kind == "score" and is_temporary_model_error(error):
                    result = local_hiring_score(profile)
                    return jsonify(
                        {
                            "title": "hiring probability score",
                            "content": result,
                            "fallback": True,
                        }
                    )
                raise

            return jsonify({"title": GENERATION_TITLES[kind], "content": result})
        except Exception as error:
            return api_error_response(error)

    @flask_app.post("/api/chat")
    def chat() -> Any:
        payload = request.get_json(silent=True) or {}
        message = str(payload.get("message", "")).strip()
        if not message:
            return jsonify({"error": "Enter a message first."}), 400

        workspace = get_workspace()
        profile = workspace["profile"]
        profile_context = (
            f"\n\nCurrent candidate context:\n{profile.to_context()}"
            if profile.has_context()
            else ""
        )
        workspace["chat_history"].append(
            {"role": "user", "content": message + profile_context}
        )

        try:
            reply = ask_ai(workspace["chat_history"])
        except Exception as error:
            workspace["chat_history"].pop()
            return api_error_response(error)

        workspace["chat_history"].append({"role": "assistant", "content": reply})
        save_history(workspace["chat_history"])
        return jsonify({"reply": reply, "history": workspace["chat_history"][-12:]})

    @flask_app.post("/api/chat/clear")
    def clear_chat() -> Any:
        workspace = get_workspace()
        workspace["chat_history"] = []
        save_history([])
        return jsonify({"ok": True})

    @flask_app.post("/api/export/pdf")
    def export_pdf() -> Response:
        payload = request.get_json(silent=True) or {}
        title = str(payload.get("title", "HireSense Output")).strip()
        content = str(payload.get("content", "")).strip()
        profile = payload.get("profile")
        if not isinstance(profile, dict):
            profile = {}
        if not content:
            content = "No content available."

        pdf_bytes = build_pdf(title, content, profile)
        filename = f"{safe_filename(title)}.pdf"
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        )

    @flask_app.post("/api/interview/start")
    def start_interview() -> Any:
        payload = request.get_json(silent=True) or {}
        interview_type = str(payload.get("type", "HR")).strip() or "HR"
        if interview_type.lower() not in {"hr", "technical"}:
            return jsonify({"error": "Choose HR or technical interview."}), 400

        try:
            rounds = min(10, max(1, int(payload.get("rounds", 5))))
        except (TypeError, ValueError):
            rounds = 5

        try:
            profile = require_profile()
            role = profile.target_role or "the target role"
            instructions = interview_instructions(interview_type, role)
            messages = [
                {
                    "role": "user",
                    "content": f"""
Start the interview. Ask exactly one {interview_type} interview question.

Candidate context:
{profile.to_context()}
""".strip(),
                }
            ]
            question = ask_ai(messages, instructions)
        except Exception as error:
            return api_error_response(error)

        get_workspace()["interview"] = {
            "type": interview_type,
            "rounds": rounds,
            "current": 1,
            "instructions": instructions,
            "messages": [*messages, {"role": "assistant", "content": question}],
        }
        return jsonify(
            {
                "question": question,
                "question_number": 1,
                "rounds": rounds,
                "finished": False,
            }
        )

    @flask_app.post("/api/interview/answer")
    def answer_interview() -> Any:
        payload = request.get_json(silent=True) or {}
        answer = str(payload.get("answer", "")).strip()
        workspace = get_workspace()
        interview = workspace.get("interview")
        if not interview:
            return jsonify({"error": "Start an interview first."}), 400
        if not answer:
            return jsonify({"error": "Enter your answer before continuing."}), 400

        interview["messages"].append({"role": "user", "content": answer})
        finished = (
            answer.lower() == "stop" or interview["current"] >= interview["rounds"]
        )

        if finished:
            interview["messages"].append(
                {"role": "user", "content": final_interview_prompt()}
            )
            try:
                report = ask_ai(interview["messages"], interview["instructions"])
            except Exception as error:
                return api_error_response(error)

            workspace["interview"] = None
            return jsonify({"finished": True, "report": report})

        interview["messages"].append(
            {
                "role": "user",
                "content": (
                    "Give brief feedback on my last answer, then ask exactly one "
                    "next interview question."
                ),
            }
        )

        try:
            next_question = ask_ai(interview["messages"], interview["instructions"])
        except Exception as error:
            return api_error_response(error)

        interview["current"] += 1
        interview["messages"].append(
            {"role": "assistant", "content": next_question}
        )
        return jsonify(
            {
                "finished": False,
                "question": next_question,
                "question_number": interview["current"],
                "rounds": interview["rounds"],
            }
        )

    @flask_app.post("/api/interview/end")
    def end_interview() -> Any:
        workspace = get_workspace()
        interview = workspace.get("interview")
        if not interview:
            return jsonify({"error": "No interview is running."}), 400

        interview["messages"].append({"role": "user", "content": final_interview_prompt()})
        try:
            report = ask_ai(interview["messages"], interview["instructions"])
        except Exception as error:
            return api_error_response(error)

        workspace["interview"] = None
        return jsonify({"finished": True, "report": report})


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "3000"))
    debug = os.getenv("FLASK_DEBUG", "").strip().lower() in {"1", "true", "yes"}
    app.run(host="127.0.0.1", port=port, debug=debug)
