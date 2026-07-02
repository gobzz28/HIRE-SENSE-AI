# HireSense AI

Flask web app for building ATS-friendly resumes, portfolio content, interview practice, and hiring-readiness coaching with the OpenAI Python SDK.

## Setup

```bash
py -3 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Groq API

Create `local-gpt-chatbot\.env` with:

```env
GROQ_API_KEY=gsk_your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
```

The app uses Groq through its OpenAI-compatible API endpoint, so no separate
Python Groq package is required.

## Gemini API

Create `local-gpt-chatbot\.env` with:

```env
GEMINI_API_KEY=your_real_gemini_key
OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
OPENAI_MODEL=gemini-2.5-flash
```

`OPENAI_API_KEY` also works for the normal OpenAI API when `OPENAI_BASE_URL` is left blank.

## Run

```bash
python app.py
```

Open the local URL shown in the terminal, usually `http://127.0.0.1:3000`.
