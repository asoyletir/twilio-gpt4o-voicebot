from flask import Flask, request, Response
import openai
import os

app = Flask(__name__)

openai.api_key = os.getenv("OPENAI_API_KEY")

@app.route("/webhook", methods=["POST"])
def webhook():
    speech_result = request.form.get("SpeechResult", "")
    print("Caller said:", speech_result)

    if not speech_result:
        return twiml_response("Sorry, I didn't catch that.")

    try:
        completion = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful customer service assistant for Neatliner."},
                {"role": "user", "content": speech_result}
            ]
        )
        response_text = completion.choices[0].message["content"]
    except Exception as e:
        response_text = "I'm sorry, there was an error connecting to the assistant."

    return twiml_response(response_text)

def twiml_response(text):
    return Response(f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna" language="en-US">{text}</Say>
</Response>""", mimetype="text/xml")

if __name__ == "__main__":
    app.run(debug=True)
