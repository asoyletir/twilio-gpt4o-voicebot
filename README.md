# Twilio GPT-4o Voicebot (Flask)

A simple Flask app that connects Twilio voice calls with OpenAI GPT-4o.

## Setup

1. Add your OpenAI API key to the environment:

```
export OPENAI_API_KEY=your_api_key_here
```

2. Install dependencies:

```
pip install -r requirements.txt
```

3. Run locally:

```
python app.py
```

4. Use ngrok or deploy to Render to expose `/webhook` URL to Twilio.

