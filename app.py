from flask import Flask, request, Response
import openai
import os

app = Flask(__name__)

# OpenAI API key ortam değişkeninden alınır
openai.api_key = os.getenv("OPENAI_API_KEY")

# Twilio ilk çağrıyı yaptığında çalışacak olan endpoint
@app.route("/", methods=["GET", "POST"])
def welcome():
    return Response("""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather input="speech" timeout="5" action="/webhook" method="POST">
    <Say voice="Polly.Joanna" language="en-US">Hi, how can I help you?</Say>
  </Gather>
  <Say voice="Polly.Joanna" language="en-US">Sorry, I didn't hear anything.</Say>
</Response>""", mimetype="text/xml")

# Kullanıcı konuştuğunda çağrılacak webhook
@app.route("/webhook", methods=["POST"])
def webhook():
    print("FULL FORM:", request.form)
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
    app.run(host="0.0.0.0", port=10000)
