from flask import Flask, request, Response
from openai import OpenAI
import os
import logging
import re
from gmail_mailer import send_email
import tiktoken

app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
logging.basicConfig(level=logging.INFO)

session_memory = {}

# 🔹 İngilizce system prompt
SYSTEM_PROMPT_EN = """
You are a bilingual English and French-speaking customer support voice assistant for Neatliner, a household product brand sold in Canada and owned by a U.S.-based company, Brightstar Sales LLC.

The initial greeting will already be provided by the system. Do not repeat it. Continue the conversation in English.

Strictly follow these rules:
- GREET ONLY ONCE: Never say "Welcome..." again.
- DO NOT start over unless explicitly asked by the user.
- ALWAYS respond based on the full conversation history and the most recent user message.
- Use clear, polite, and professional language.

ENGLISH FLOW:
1. If the topic is unrelated to Neatliner → say: 
"This service is only available for issues related to the Neatliner brand. Unfortunately, I cannot assist with other topics. Thank you for calling Neatliner Customer Service." Then end.

2. If it's a complaint: ask where they bought the product and the order number. Confirm the number if provided.

3. Ask the user to explain their complaint in detail.
→ If during the explanation the user brings up something clearly unrelated to Neatliner, apply step 1 and politely end the call.

4. If it is a suggestion or request → acknowledge and ask: 
"I’ve noted your request. Is there anything else I can help you with?"

5. If user says "no", ask for email address and confirm it.

6. End the call with:
"Thank you for contacting Neatliner Customer Service. We’ll follow up with you as soon as possible. Goodbye!"
"""

# 🔹 Fransızca system prompt
SYSTEM_PROMPT_FR = """
Vous êtes un(e) assistant(e) bilingue du service client de Neatliner, une marque de produits ménagers vendue au Canada et appartenant à une entreprise américaine, Brightstar Sales LLC.

Le message de bienvenue a déjà été fourni par le système. Ne le répétez pas. Continuez la conversation en français.

Règles strictes :
- SALUEZ UNE SEULE FOIS : Ne répétez jamais « Bienvenue... ».
- NE REDÉMARREZ PAS la conversation sauf si l'utilisateur le demande.
- RÉPONDEZ TOUJOURS en fonction de l’historique complet de la conversation et du dernier message.
- Utilisez un langage clair, poli et professionnel.

FRENCH FLOW :
1. Si le sujet est sans rapport avec la marque Neatliner → dire :
"Ce service est réservé aux demandes concernant la marque Neatliner. Malheureusement, je ne peux pas vous aider pour d'autres sujets. Merci d'avoir contacté le service client Neatliner." Puis terminer.

2. Si c’est une réclamation : demander où le produit a été acheté et le numéro de commande. Confirmer ce numéro s’il est fourni.

3. Demander à l’utilisateur d’expliquer en détail le problème.
→ Si l'utilisateur parle d'un sujet sans rapport avec Neatliner, appliquez la règle 1 et terminez poliment.

4. S’il s’agit d’une suggestion ou d’une demande → accuser réception et demander :
"J’ai noté votre demande. Y a-t-il autre chose avec laquelle je peux vous aider ?"

5. Si l’utilisateur dit non, demander l’adresse e-mail et la confirmer.

6. Terminer avec :
"Merci d’avoir contacté le service client Neatliner. Nous vous recontacterons dans les plus brefs délais. Au revoir !"
"""

def trim_session_memory(memory, max_tokens=1500):
    encoding = tiktoken.encoding_for_model("gpt-4o")
    total_tokens = 0
    trimmed = []
    for msg in reversed(memory):
        tokens = len(encoding.encode(msg["content"]))
        if total_tokens + tokens > max_tokens:
            break
        trimmed.insert(0, msg)
        total_tokens += tokens
    return trimmed

@app.route("/", methods=["GET", "POST"])
def welcome():
    return Response("""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather action="/handle-selection" method="POST" input="dtmf" numDigits="1" timeout="5">
    <Say voice="Polly.Joanna" language="en-US">Welcome to Neatliner Customer Service.</Say>
    <Say voice="Polly.Celine" language="fr-CA">Bienvenue au service client Neatliner. Pour le service en français, appuyez sur 9.</Say>
  </Gather>
  <Redirect>/voice?lang=en</Redirect>
</Response>""", mimetype="text/xml")

@app.route("/handle-selection", methods=["POST"])
def handle_selection():
    digits = request.form.get("Digits")
    lang = "fr" if digits == "9" else "en"
    return Response(f"""<?xml version='1.0' encoding='UTF-8'?>
<Response>
  <Redirect>/voice?lang={lang}</Redirect>
</Response>""", mimetype="text/xml")

@app.route("/voice", methods=["GET", "POST"])
def voice_flow():
    lang = request.args.get("lang", "en")
    if lang == "fr":
        voice = "Polly.Celine"
        language = "fr-CA"
        welcome_line = "Je suis ici pour vous aider concernant les produits Neatliner. Comment puis-je vous aider aujourd'hui ?"
    else:
        voice = "Polly.Joanna"
        language = "en-US"
        welcome_line = "I’m here to assist you with anything related to Neatliner products. How can I assist you today?"

    return Response(f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="{voice}" language="{language}">{welcome_line}</Say>
  <Gather input="speech" timeout="5" action="/webhook?lang={lang}" method="POST" language="{language}"/>
</Response>""", mimetype="text/xml")

def extract_last_email(messages):
    for msg in reversed(messages):
        if msg["role"] == "user":
            match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', msg["content"])
            if match:
                return match.group(0)
    return "Not Provided"

def extract_last_order_number(messages):
    for msg in reversed(messages):
        if msg["role"] == "user":
            match = re.search(r'\b\d{3}[-\s]?\d{7}[-\s]?\d{7}\b', msg["content"])
            if match:
                return match.group(0).replace(" ", "")
    return "Not Provided"

def detect_call_type(messages):
    full_text = " ".join(msg["content"].lower() for msg in messages if msg["role"] == "user")
    if any(word in full_text for word in ["problem", "problème", "issue"]):
        return "Complaint"
    elif any(word in full_text for word in ["request", "demande", "exchange"]):
        return "Request"
    elif any(word in full_text for word in ["suggestion", "avis", "proposition"]):
        return "Suggestion"
    return "Not Identified"


def twiml_response(text, lang="en"):
    text_clean = text.strip()

    if lang == "fr":
        final_closures = [
            "Merci d’avoir contacté le service client Neatliner.",
            "Nous vous recontacterons dans les plus brefs délais. Au revoir !"
        ]
        skip_gather_phrases = [
            "Bienvenue au service client Neatliner",
            "Merci d’avoir contacté le service client Neatliner",
            "Malheureusement, je ne peux pas vous aider"
        ]
        voice = "Polly.Celine"
        language = "fr-CA"
    else:
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
        voice = "Polly.Joanna"
        language = "en-US"

    # Kapanış cümlesi veya sistem mesajı algılanırsa <Gather> ekleme, sadece oku
    if any(text_clean.startswith(phrase) for phrase in final_closures + skip_gather_phrases):
        logging.info("🛑 Final or passive phrase detected — returning without <Gather>")
        return Response(f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="{voice}" language="{language}">{text_clean}</Say>
</Response>""", mimetype="text/xml")

    # Normal akış — Gather ile cevap bekle
    return Response(f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="{voice}" language="{language}">{text_clean}</Say>
  <Gather input="speech" timeout="5" action="/webhook?lang={lang}" method="POST" language="{language}"/>
</Response>""", mimetype="text/xml")

@app.route("/webhook", methods=["POST"])
def webhook():
    call_sid = request.form.get("CallSid")
    speech_result = request.form.get("SpeechResult", "")
    lang = request.args.get("lang", "en")
    logging.info("===== Incoming Webhook =====")
    logging.info(f"CallSid: {call_sid}")
    logging.info(f"Caller said: {speech_result}")

    if not speech_result:
        return twiml_response("Sorry, I didn't catch that. Could you please repeat?", lang)

    # Doğru prompt'u başlat
    if call_sid not in session_memory:
        system_prompt = SYSTEM_PROMPT_FR if lang == "fr" else SYSTEM_PROMPT_EN
        session_memory[call_sid] = [
            {"role": "system", "content": system_prompt}
        ]
        logging.info("Initialized new session memory")

    session_memory[call_sid].append({"role": "user", "content": speech_result})

    trimmed = trim_session_memory([
        msg for msg in session_memory[call_sid] if msg.get("role") in ["user", "assistant", "system"]
    ])

    try:
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=trimmed
        )
        response_text = completion.choices[0].message.content
        logging.info(f"GPT response: {response_text}")

        session_memory[call_sid].append({"role": "assistant", "content": response_text})

        if "Thank you for contacting Neatliner Customer Service" in response_text or \
           "Merci d’avoir contacté le service client Neatliner" in response_text:
            transcript = ""
            for msg in session_memory[call_sid]:
                if msg["role"] in ["user", "assistant"]:
                    transcript += f"{msg['role'].upper()}: {msg['content'].strip()}\n"

            metadata = {
                "call_type": detect_call_type(session_memory[call_sid]),
                "from_number": request.form.get("From"),
                "location": f"{request.form.get('CallerCity', '')}, {request.form.get('CallerState', '')}".strip(", "),
                "email": extract_last_email(session_memory[call_sid]),
                "order_number": extract_last_order_number(session_memory[call_sid])
            }

            send_email(transcript, call_sid, metadata)


    except Exception as e:
        logging.error(f"OpenAI error: {e}")
        response_text = "I'm sorry, there was a problem connecting to the assistant."

    return twiml_response(response_text, lang)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
