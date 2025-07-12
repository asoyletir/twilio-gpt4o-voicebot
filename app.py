from flask import Flask, request, Response
import openai
import os
import logging

app = Flask(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")
logging.basicConfig(level=logging.INFO)

SYSTEM_PROMPT = """
You are the AI voice assistant of Neatliner Customer Service. Follow this flow:

1. Greet the caller by saying:
"Welcome to Neatliner Customer Service. How can I assist you today?"

2. Listen to what the customer says and determine if:
  - It is a complaint → go to step 3.
  - It is a suggestion or request → skip to step 5.
  - It is unrelated to the Neatliner brand → respond with:
    "This service is only available for issues related to the Neatliner brand. Unfortunately, I cannot assist with other topics. Thank you for calling Neatliner Customer Service."
    Then end the conversation.

3. If it's a complaint:
  Ask: "Could you please tell me which marketplace you purchased the product from, and share your order number?"
  If an order number is given, confirm: "Is this your order number: [number]?"
  If the customer says it's incorrect and gives another one, confirm again.

4. Ask: "Please describe your complaint in detail."

5. Acknowledge what the customer said:
   "I’ve noted your request. Is there anything else I can help you with?"
   - If the user says "yes", return to step 2.
   - If the user says "no", proceed to step 6.

6. Ask: "In order to follow up on your request, may I have your email address?"
   - Confirm: "I’ve recorded your email as: [email]. Is that correct?"
   - If incorrect, ask again and confirm the new email.

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
    logging.info("===== Incoming Webhook =====")
    logging.info(f"Request form: {request.form.to_dict()}")

    speech_result = request.form.get("SpeechResult", "")
    logging.info(f"Caller said: {speech_result}")

    if not speech_result:
        return twiml_response("Sorry, I didn't catch that. Could you please repeat?")

    try:
        completion = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": speech_result}
            ]
        )
        response_text = completion.choices[0].message["content"]
        logging.info(f"GPT response: {response_text}")
    except Exception as e:
        logging.error(f"OpenAI error: {e}")
        response_text = "I'm sorry, there was a problem connecting to the assistant."

    return twiml_response(response_text)

def twiml_response(text):
    final_closures = [
        "Thank you for contacting Neatliner Customer Service.",
        "I cannot assist with other topics. Thank you for calling Neatliner Customer Service."
    ]

    if any(phrase in text for phrase in final_closures):
        return Response(f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna" language="en-US">{text}</Say>
</Response>""", mimetype="text/xml")

    return Response(f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna" language="en-US">{text}</Say>
    <Gather input="speech" timeout="5" action="/webhook" method="POST">
        <Say voice="Polly.Joanna" language="en-US">Is there anything else I can help you with?</Say>
    </Gather>
</Response>""", mimetype="text/xml")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
