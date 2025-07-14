from flask import Flask, request, Response
from openai import OpenAI
import os
import logging
import re
from gmail_mailer import send_email
import tiktoken
import xml.etree.ElementTree as ET

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

2. If it's a complaint:
First, ask:
"Where did you purchase the product?"
After the user answers, say:
"Thank you. Please enter your order number using your phone’s keypad, then press the pound key (#)."
Wait for the DTMF input.
Once the order number is received, confirm it with the user.

3. Ask the user to explain their complaint in detail.
→ If during the explanation the user brings up something clearly unrelated to Neatliner, apply step 1 and politely end the call.

4. If it is a suggestion or request → acknowledge and ask: 
"I’ve noted your request. Is there anything else I can help you with?"

5. If user says "no", ask for email address.
When asking for the email address, ask the user to clearly say each letter of the part before the @ sign one by one, with short pauses between letters. For example:
“A... S... O... Y... L... E... T... I... R...”
Then ask the user to say the rest like "@gmail.com", "@yahoo.com", etc.
Say:
"I'm ready when you are."
After user completes spelling, confirm email address by using EMAIL CONFIRMATION rules.

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

2. Si c’est une réclamation :
Commencez par demander :
"Où avez-vous acheté le produit ?"
Après la réponse de l'utilisateur, dites :
"Merci. Veuillez entrer votre numéro de commande au clavier téléphonique, puis appuyez sur la touche dièse (#)."
Attendez que l'utilisateur entre les chiffres.
Une fois reçu, confirmez le numéro de commande.

3. Demander à l’utilisateur d’expliquer en détail le problème.
→ Si l'utilisateur parle d'un sujet sans rapport avec Neatliner, appliquez la règle 1 et terminez poliment.

4. S’il s’agit d’une suggestion ou d’une demande → accuser réception et demander :
"J’ai noté votre demande. Y a-t-il autre chose avec laquelle je peux vous aider ?"

5. Si l’utilisateur dit « non », demandez l’adresse e-mail.
Lorsque vous demandez l’adresse e-mail, invitez l’utilisateur à dire chaque lettre de la partie avant l’arobase une par une, avec de courtes pauses entre les lettres. Par exemple :
« A... S... O... Y... L... E... T... I... R... »
Ensuite, demandez à l’utilisateur de prononcer le reste comme « @gmail.com », « @yahoo.fr », etc.
Dites :
« Je vous écoute. »
Une fois que l’utilisateur a terminé de l’épeler, confirmez l’adresse e-mail en utilisant les règles de CONFIRMATION D'EMAIL.

6. Terminer avec :
"Merci d’avoir contacté le service client Neatliner. Nous vous recontacterons dans les plus brefs délais. Au revoir !"

---

EMAIL CONFIRMATION:
- When confirming the user’s email address, spell out the part before the "@" sign slowly with short pauses between each letter (e.g., “A... B... C...”).
- Then say the domain part normally (e.g., “at gmail dot com”).
- For French: “arobase” for @ and “point” for . (e.g., “arobase gmail point com”).
- Ask the user to confirm if the email is correct.

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

def estimate_twiml_size(text):
    root = ET.Element("Response")
    say = ET.SubElement(root, "Say")
    say.text = text
    return len(ET.tostring(root, encoding="utf-8"))

@app.route("/order-number", methods=["POST"])
def handle_order_number():
    digits = request.form.get("Digits", "")
    logging.info(f"Received DTMF digits: {digits}")
    lang = request.args.get("lang", "en")
    call_sid = request.form.get("CallSid")

    logging.info(f"Received DTMF digits: {request.form.get('Digits')}")
    
    if not digits:
        message = "Sorry, I didn't receive your input. Please try again." if lang == "en" else "Désolé, je n'ai pas reçu votre saisie. Veuillez réessayer."
        return twiml_response(message, lang)

    formatted = f"{digits[:3]}-{digits[3:10]}-{digits[10:]}" if len(digits) == 17 else digits

    if call_sid in session_memory:
        session_memory[call_sid].append({
            "role": "user",
            "content": f"My order number is {formatted}"
        })

    confirm = f"Thank you. I’ve received your order number: {formatted}. Could you now explain your issue in detail?" \
              if lang == "en" else \
              f"Merci. J'ai bien reçu votre numéro de commande : {formatted}. Pourriez-vous maintenant expliquer votre problème en détail ?"

    return twiml_response(confirm, lang)

def extract_last_email(memory):
    import re

    email_pattern = r"\b[\w\.-]+@[\w\.-]+\.\w+\b"

    for msg in reversed(memory):
        if msg["role"] == "user":
            content = msg["content"].lower()

            # Dönüşümler
            content = content.replace(" at ", "@")
            content = content.replace("arobase", "@")
            content = content.replace(" dot ", ".").replace(" point ", ".")
            content = re.sub(r"\s+", "", content)     # boşlukları kaldır
            content = re.sub(r"\.(?=[^@]*@)", "", content)  # @ işaretinden önceki . karakterlerini kaldır
            content = content.strip(" .")             # baştaki/sondaki nokta ve boşlukları kaldır

            # E-mail yakala
            matches = re.findall(email_pattern, content)
            if matches:
                return matches[-1].lower()  # her ihtimale karşı küçük harfe çevir

    return "Not Provided"

def format_email_for_confirmation(email: str, lang: str = "en") -> str:
    import re

    match = re.match(r"([\w\.-]+)@([\w\.-]+\.\w+)", email)
    if not match:
        return email  # Format uygun değilse olduğu gibi döndür

    local_part, domain_part = match.groups()

    if lang == "fr":
        connector = "arobase"
        dot_replacement = "point"
    else:
        connector = "at"
        dot_replacement = "dot"

    # Her harf arasına 1 saniyelik durak ekle
    slow_letters = ""
    for char in local_part:
        slow_letters += f"{char.upper()}<break time=\"3s\"/> "

    domain_slow = domain_part.replace(".", f" {dot_replacement} ")

    # Sonuç: A <break/> S <break/> ... at gmail dot com
    return f"{slow_letters.strip()} {connector} {domain_slow}"

def extract_last_order_number(messages):
    for msg in reversed(messages):
        if msg["role"] == "user":
            spoken = msg["content"].lower()

            # Konuşma biçimlerini normalize et
            spoken = spoken.replace(" dash ", "-").replace(" tiré ", "-").replace(" hyphen ", "-")

            # Fazla boşlukları sil, çizgi formatına yaklaştır
            spoken = re.sub(r'\s+', '', spoken)

            # Order number formatını yakala: 702-1234567-9876543
            match = re.search(r'(\d{3})[-]?(\d{7})[-]?(\d{7})', spoken)
            if match:
                return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
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

def extract_platform(messages):
    full_text = " ".join(msg["content"].lower() for msg in messages if msg["role"] == "user")

    if "amazon" in full_text:
        return "Amazon"
    elif "walmart" in full_text:
        return "Walmart"
    elif "website" in full_text or "neatliner.com" in full_text:
        return "Neatliner Website"
    elif "store" in full_text or "in store" in full_text:
        return "Physical Store"
    elif "online" in full_text:
        return "Online (unspecified)"
    return "Not Provided"

@app.route("/repeat-order-number", methods=["GET", "POST"])
def repeat_order_number():
    lang = request.args.get("lang", "en")
    if lang == "fr":
        voice = "Polly.Celine"
        language = "fr-CA"
        repeat_msg = "Vous n'avez appuyé sur aucune touche. Veuillez entrer votre numéro de commande au clavier téléphonique, puis appuyez sur la touche dièse."
        goodbye_msg = "Je suis désolé, je n’ai toujours pas reçu d’entrée. Je vais maintenant mettre fin à l’appel."
    else:
        voice = "Polly.Joanna"
        language = "en-US"
        repeat_msg = "You didn’t press any keys. Please enter your order number using the keypad and press the pound key."
        goodbye_msg = "I'm sorry, I still didn’t receive any input. I will now end the call."

    return Response(f"""<?xml version="1.0" encoding="UTF-8"?>
    <Response>
      <Gather input="dtmf" timeout="10" finishOnKey="#" action="/order-number?lang={lang}" method="POST" language="{language}">
        <Say voice="{voice}" language="{language}">{repeat_msg}</Say>
      </Gather>
      <Say voice="{voice}" language="{language}">{goodbye_msg}</Say>
      <Hangup/>
    </Response>""", mimetype="text/xml")


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

    trigger_phrases = ["press the pound key", "press #", "type your order number", "enter your order number", 
                "appuyez sur la touche dièse", "touche dièse", "tapez votre numéro de commande"]

    if any(phrase in text.lower() for phrase in trigger_phrases):
        return Response(f"""<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Gather input="dtmf" timeout="15" finishOnKey="#" action="/order-number?lang={lang}" method="POST">
        <Say voice="{voice}" language="{language}">{text}</Say>
        </Gather>
        <Redirect>/repeat-order-number?lang={lang}</Redirect>
    </Response>""", mimetype="text/xml")

    
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
        trimmed = trim_session_memory(session_memory[call_sid], max_tokens=1500)
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=trimmed
        )
        response_text = completion.choices[0].message.content

        if len(response_text) > 3000:
            logging.warning("⚠️ GPT response too long, trimming for Twilio.")
            response_text = response_text[:3000] + "..."

        logging.info(f"TwiML size: {estimate_twiml_size(response_text)} bytes")
        logging.info(f"GPT response: {response_text}")

        if "email" in detect_call_type(session_memory[call_sid]):
            email_plain = extract_last_email(session_memory[call_sid])
            formatted_email = format_email_for_confirmation(email_plain, lang)
            response_text = {
                "en": f"To confirm, is your email address: {formatted_email}? If this is correct, please say yes.",
                "fr": f"Pour confirmer, votre adresse e-mail est-elle : {formatted_email} ? Si c’est correct, dites oui."
            }[lang]
        
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
                "order_number": extract_last_order_number(session_memory[call_sid]),
                "platform": extract_platform(session_memory[call_sid])
            }

            send_email(transcript, call_sid, metadata)


    except Exception as e:
        logging.error(f"OpenAI error: {e}")
        response_text = "I'm sorry, there was a problem connecting to the assistant."

    return twiml_response(response_text, lang)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
