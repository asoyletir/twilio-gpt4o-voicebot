from flask import Flask, request, Response
from openai import OpenAI
import os
import logging

app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
logging.basicConfig(level=logging.INFO)

# Konuşma geçmişini tutmak için CallSid'e göre oturum hafızası
session_memory = {}

SYSTEM_PROMPT = """
You are a professional English-speaking customer support voice assistant for Neatliner, a Canadian household product brand.

Strictly follow these rules:
- GREET ONLY ONCE: Say "Welcome to Neatliner Customer Service..." only in your first response.
- NEVER say "Welcome..." or any greeting again, even as part of a longer sentence.
- DO NOT start over unless explicitly asked by the user.
- ALWAYS respond based on the full conversation history and the most recent user message.

Flow:
1. Greet once: "Welcome to Neatliner Customer Service. How can I assist you today?"

2. If the topic is unrelated to Neatliner → say: 
"This service is only available for issues related to the Neatliner brand. Unfortunately, I cannot assist with other topics. Thank you for calling Neatliner Customer Service." Then end.

3. If it's a complaint: ask where they bought the product and the order number. Confirm the number if provided.

4. Ask the user to explain their complaint in detail.

5. If it is a suggestion or request → acknowledge and ask: 
"I’ve noted your request. Is there anything else I can help you with?"

6. If user says "no", ask for email address and confirm it.

7. End the call with:
"Thank you for contacting Neatliner Customer Service. We’ll follow up with you as soon as possible. Goodbye!"
"""

@app.route("/", methods=["GET", "POST"])
def welcome():
    return Response("""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather input="speech" timeout="5" action="/webhook" method="POST">
    <Say voice="Polly.Joanna" language="en-US">Welcome to Neatliner Customer Service. How can I assist you today?</Say>
  </Gather>
  <Say voice="Polly.Joanna" language="en-US">Sorry, I didn't hear anything.</Say>
</Response>""", mimetype="text/xml")

@app.route("/webhook", methods=["POST"])
def webhook():
    call_sid = request.form.get("CallSid")
    speech_result = request.form.get("SpeechResult", "")
    logging.info("===== Incoming Webhook =====")
    logging.info(f"CallSid: {call_sid}")
    logging.info(f"Caller said: {speech_result}")

    if not speech_result:
        return twiml_response("Sorry, I didn't catch that. Could you please repeat?")

    if call_sid not in session_memory:
        session_memory[call_sid] = [
                                      {"role": "system", "content": SYSTEM_PROMPT},
                                      {"role": "assistant", "content": "Welcome to Neatliner Customer Service. How can I assist you today?"}
                                    ]
        logging.info("Initialized new session memory")

    session_memory[call_sid].append({"role": "user", "content": speech_result})

    try:
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=session_memory[call_sid]
        )
        response_text = completion.choices[0].message.content
        logging.info(f"GPT response: {response_text}")

        session_memory[call_sid].append({"role": "assistant", "content": response_text})

        if "Welcome to Neatliner" in response_text:
            logging.warning("⚠️ GPT repeated the welcome message unexpectedly.")
            # Welcome tekrarını kırp (isteğe bağlı)
            parts = response_text.split("?")
            if len(parts) > 1:
                response_text = "?".join(parts[1:]).strip()
                logging.info(f"Trimmed GPT response: {response_text}")
    except Exception as e:
        logging.error(f"OpenAI error: {e}")
        response_text = "I'm sorry, there was a problem connecting to the assistant."

    return twiml_response(response_text)

def twiml_response(text):
    final_closures = [
        "Thank you for contacting Neatliner Customer Service.",
        "Thank you for calling Neatliner Customer Service.",
        "We’ll follow up with you as soon as possible. Goodbye!"
    ]

    skip_gather_phrases = [
        "Welcome to Neatliner Customer Service",
        "Thank you for contacting Neatliner Customer Service",
        "Unfortunately, I cannot assist with other topics"
    ]

    if any(phrase in text for phrase in final_closures):
        return Response(f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="Polly.Joanna" language="en-US">{text}</Say>
</Response>""", mimetype="text/xml")

    if any(phrase in text for phrase in skip_gather_phrases):
        return Response(f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="Polly.Joanna" language="en-US">{text}</Say>
</Response>""", mimetype="text/xml")

    return Response(f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="Polly.Joanna" language="en-US">{text}</Say>
  <Gather input="speech" timeout="5" action="/webhook" method="POST"/>
</Response>""", mimetype="text/xml")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
